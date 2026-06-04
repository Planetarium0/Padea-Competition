"""
handle_support_email.py — Process one inbound support email with AI tool use.

For a given support_inbound_messages row:
  1. Identify the parent by from_address → students with matching parent_email.
  2. If unrecognised sender or coordinator email: notify coordinator and return.
  3. Find or create a support case (thread by In-Reply-To).
  4. Run an LLM tool-use loop that can list students, list dietary restrictions,
     add a restriction to a student, and send a reply.
  5. Update the support case with the conversation and new status.

Usage:
  python scripts/actions/inbox/handle_support_email.py --message-id <id> [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import os
import uuid
from typing import Any

from support import (
    Database,
    Record,
    SupportCaseFields,
    log,
    notify_coordinator,
    schedule_email,
    self_healing_error_handler,
)
from support.inbound import InboundMessage

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Padea dietary support assistant. You help parents update
their children's dietary requirements in the Padea meal ordering system.

Padea is an after-school tutoring program that provides catered dinners. Parents
sometimes email in to update their child's dietary needs.

Your job is to:
1. Understand what the parent is asking (usually: add or confirm a dietary restriction
   for one of their children).
2. Use the available tools to look up the parent's children and the available dietary
   restrictions in the system.
3. Make the requested change using add_dietary_restriction if appropriate.
4. Always send a polite reply to the parent summarising what was done (or explaining
   if something could not be done).

Guidelines:
- Be friendly, concise, and professional.
- Always call list_students first to know which children belong to this parent.
- Always call list_dietary_restrictions before trying to match the parent's description
  to a system restriction — never guess restriction IDs.
- Match the parent's plain-language description (e.g. "nut allergy", "vegetarian",
  "gluten free") to the closest system restriction.
- If the parent's request is ambiguous or no restriction matches, explain clearly in
  your reply and ask them to contact the coordinator directly.
- Always end by calling send_reply. Never leave the parent without a response.
- Do not modify restrictions for students whose parent_email does not match the sender.
"""

MAX_TOOL_ITERATIONS = 10

# ---------------------------------------------------------------------------
# Tool definitions (Anthropic format)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_students",
        "description": (
            "List the students linked to the parent's email. "
            "Returns name, year level, and current dietary requirement IDs."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_dietary_restrictions",
        "description": "List all available dietary restrictions in the system.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "add_dietary_restriction",
        "description": (
            "Add a dietary restriction to a student. "
            "Re-validates that the student belongs to the sender."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "string",
                    "description": "The student's UUID from list_students",
                },
                "restriction_id": {
                    "type": "string",
                    "description": "The restriction UUID from list_dietary_restrictions",
                },
            },
            "required": ["student_id", "restriction_id"],
        },
    },
    {
        "name": "send_reply",
        "description": (
            "Send a reply email to the parent. "
            "Always call this at the end — never leave the parent without a response."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "body_text": {
                    "type": "string",
                    "description": "The plain-text reply to send to the parent.",
                },
            },
            "required": ["body_text"],
        },
    },
]


# ---------------------------------------------------------------------------
# Thread utilities
# ---------------------------------------------------------------------------

def _build_thread_text(
    prior_messages: list[dict[str, Any]],
    inbound_msg: InboundMessage,
) -> str:
    """Build a user-facing thread string for the LLM context."""
    parts: list[str] = []
    for msg in prior_messages:
        direction = msg.get("direction", "unknown")
        sent_at = msg.get("sent_at", "")[:10]
        body = msg.get("body") or ""
        label = "Parent" if direction == "inbound" else "Padea Support"
        parts.append(f"[{label} — {sent_at}]\n{body}")

    # Append the new inbound message
    today = datetime.date.today().isoformat()
    body = inbound_msg.body_text or "(no message body)"
    parts.append(f"[Parent — {today}]\n{body}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------

def find_or_create_case(
    db: Database,
    inbound_msg: InboundMessage,
    sender_email: str,
    *,
    dry_run: bool = False,
) -> tuple[Record[SupportCaseFields], bool]:
    """Return (case_record, is_new).

    Threads by In-Reply-To: if the new message has in_reply_to that matches
    any message_id in an existing Open case for this sender, reuse that case.
    Otherwise create a new one.

    In dry-run mode, returns a stub record without writing to the DB.
    """
    if inbound_msg.in_reply_to:
        open_cases = db.SupportCases.all()
        for case in open_cases:
            if case.fields.get("status") != "Open":
                continue
            if case.fields.get("parent_email") != sender_email:
                continue
            msgs: list[dict[str, Any]] = case.fields.get("messages") or []
            if any(m.get("message_id") == inbound_msg.in_reply_to for m in msgs):
                return case, False

    # Build new case
    case_code = f"SC-{datetime.date.today().year}-{uuid.uuid4().hex[:8].upper()}"
    new_fields: dict[str, Any] = {
        "case_code": case_code,
        "parent_email": sender_email,
        "status": "Open",
    }

    if dry_run:
        # Return a stub record without writing
        stub: Record[SupportCaseFields] = Record(
            id="dry-run-case",
            fields=new_fields,  # type: ignore[arg-type]
        )
        return stub, True

    created = db.SupportCases.create([new_fields])
    return created[0], True


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

def _make_tool_executor(
    db: Database,
    sender_email: str,
    students: list[Record],
    case: Record[SupportCaseFields],
    *,
    dry_run: bool = False,
) -> Any:
    """Return a closure that executes tool calls for the LLM loop."""
    reply_count = [0]  # mutable so closure can increment

    def execute(tool_name: str, tool_input: dict[str, Any]) -> str:
        if tool_name == "list_students":
            result = []
            for stu in students:
                result.append({
                    "id": stu.id,
                    "name": stu.fields.get("name", "Unknown"),
                    "year_level": stu.fields.get("year_level"),
                    "dietary_requirement_ids": stu.fields.get("dietary_requirement_ids") or [],
                })
            return str(result)

        elif tool_name == "list_dietary_restrictions":
            restrictions = db.DietaryRestrictions.all()
            result = [
                {"id": r.id, "name": r.fields.get("name", r.id)}
                for r in restrictions
            ]
            return str(result)

        elif tool_name == "add_dietary_restriction":
            student_id = tool_input.get("student_id", "")
            restriction_id = tool_input.get("restriction_id", "")

            # Re-fetch the student from DB (security: re-validate ownership)
            student = db.Students.get(student_id)
            if student is None:
                return f"Error: student {student_id!r} not found."
            if student.fields.get("parent_email") != sender_email:
                return (
                    f"Error: student {student_id!r} does not belong to {sender_email!r}. "
                    f"No change made."
                )

            # Validate restriction exists
            restriction = db.DietaryRestrictions.get(restriction_id)
            if restriction is None:
                return f"Error: restriction {restriction_id!r} not found."

            # Load current list, add if not present
            current_ids: list[str] = list(student.fields.get("dietary_requirement_ids") or [])
            if restriction_id in current_ids:
                restriction_name = restriction.fields.get("name", restriction_id)
                student_name = student.fields.get("name", student_id)
                return (
                    f"{student_name} already has '{restriction_name}' — no change needed."
                )

            current_ids.append(restriction_id)
            if not dry_run:
                db.Students.update(student_id, {"dietary_requirement_ids": current_ids})

            restriction_name = restriction.fields.get("name", restriction_id)
            student_name = student.fields.get("name", student_id)
            dry_suffix = " (dry-run: not written)" if dry_run else ""
            return f"Added '{restriction_name}' to {student_name}.{dry_suffix}"

        elif tool_name == "send_reply":
            body_text = tool_input.get("body_text", "")
            reply_count[0] += 1
            email_id = f"{case.fields.get('case_code', case.id)}-reply-{reply_count[0]}"

            if not dry_run:
                schedule_email(
                    db,
                    to_email=sender_email,
                    cc_email=None,
                    subject="Re: Padea dietary support",
                    body=body_text,
                    email_id=email_id,
                )
            else:
                log.info(f"[DRY RUN] Would send reply to {sender_email}: {body_text[:80]}...")

            return "Reply sent."

        else:
            return f"Error: unknown tool {tool_name!r}."

    return execute


# ---------------------------------------------------------------------------
# LLM tool loop
# ---------------------------------------------------------------------------

def run_tool_loop(
    db: Database,
    case: Record[SupportCaseFields],
    inbound_msg: InboundMessage,
    sender_email: str,
    students: list[Record],
    *,
    dry_run: bool = False,
) -> None:
    """Run the Anthropic tool-use loop for one inbound support message.

    Updates the case in the DB after the loop completes.
    """
    case_code = case.fields.get("case_code", case.id)

    api_key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.failure(
            f"No Anthropic API key — cannot run tool loop for support case {case_code}"
        )
        notify_coordinator(
            case.id,
            caterer_name=sender_email,
            num_open_questions=1,
        )
        return

    if Anthropic is None:
        log.failure(
            f"anthropic package not installed — cannot run tool loop for {case_code}"
        )
        notify_coordinator(
            case.id,
            caterer_name=sender_email,
            num_open_questions=1,
        )
        return

    client = Anthropic(api_key=api_key)

    # Build conversation from prior thread + new message
    prior_messages: list[dict[str, Any]] = case.fields.get("messages") or []
    thread_text = _build_thread_text(prior_messages, inbound_msg)
    messages: list[dict[str, Any]] = [{"role": "user", "content": thread_text}]

    tool_call_log: list[dict[str, Any]] = []
    reply_sent = False
    executor = _make_tool_executor(db, sender_email, students, case, dry_run=dry_run)

    for iteration in range(MAX_TOOL_ITERATIONS):
        if dry_run:
            log.info(f"[DRY RUN] Would call LLM (iteration {iteration + 1}) for {case_code}")
            break

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
        )

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if hasattr(block, "type") and block.type == "tool_use":
                    result_str = executor(block.name, block.input)
                    if block.name == "send_reply":
                        reply_sent = True
                    tool_call_log.append({
                        "tool": block.name,
                        "input": block.input,
                        "result": result_str,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    })
            messages.append({"role": "user", "content": tool_results})

    # Persist the case update
    updated_messages = list(prior_messages) + [{
        "direction": "inbound",
        "sent_at": inbound_msg.received_at.isoformat(),
        "message_id": inbound_msg.message_id,
        "body": inbound_msg.body_text or "",
        "tool_calls": tool_call_log,
    }]

    update_fields: dict[str, Any] = {"messages": updated_messages}
    if reply_sent:
        update_fields["status"] = "Resolved"
        update_fields["resolved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    # else: keep status="Open" — awaiting parent follow-up

    if not dry_run:
        db.SupportCases.update(case.id, update_fields)

    log.info(
        f"Support case {case_code}: "
        f"reply_sent={reply_sent}, status={update_fields.get('status', 'Open')}"
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def handle_message(
    db: Database,
    inbound_msg: InboundMessage,
    *,
    dry_run: bool = False,
) -> None:
    """Orchestrate handling of one inbound support message."""
    sender_email = inbound_msg.from_address
    coordinator_email = os.environ.get("COORDINATOR_EMAIL", "")

    # 1. Check if this is the coordinator emailing their own support inbox
    if coordinator_email and sender_email.lower() == coordinator_email.lower():
        log.warning(
            f"Support email from coordinator address {sender_email!r} — "
            f"routing to notify_coordinator to avoid loops"
        )
        notify_coordinator(
            f"coordinator-self-{inbound_msg.message_id or uuid.uuid4().hex[:8]}",
            caterer_name=sender_email,
            num_open_questions=0,
        )
        return

    # 2. Look up students by parent_email
    students = [
        s for s in db.Students.all()
        if s.fields.get("parent_email", "").lower() == sender_email.lower()
    ]

    if not students:
        log.warning(f"Unrecognised sender {sender_email!r} — notifying coordinator")
        notify_coordinator(
            f"unknown-parent-{inbound_msg.message_id or uuid.uuid4().hex[:8]}",
            caterer_name=sender_email,
            num_open_questions=0,
        )
        return

    log.info(
        f"Support email from {sender_email!r}: "
        f"{len(students)} student(s) found"
    )

    # 3. Find or create case
    case, is_new = find_or_create_case(db, inbound_msg, sender_email, dry_run=dry_run)
    case_code = case.fields.get("case_code", case.id)
    log.info(
        f"{'New' if is_new else 'Existing'} support case {case_code!r} "
        f"for {sender_email!r}"
    )

    # 4. Run the AI tool loop
    run_tool_loop(db, case, inbound_msg, sender_email, students, dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process one inbound support email with AI tool use",
    )
    parser.add_argument(
        "--message-id",
        required=True,
        help="The row id (UUID) of the support_inbound_messages record to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to the database",
    )
    args = parser.parse_args()

    def db_state_provider() -> dict[str, Any]:
        try:
            db = Database.from_env()
            return {
                "support_inbound_messages": db.SupportInboundMessages.all(),
                "support_cases": db.SupportCases.all(),
                "students": db.Students.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("handle_support_email", state_provider=db_state_provider):
        db = Database.from_env()
        row = db.SupportInboundMessages.get(args.message_id)
        if row is None:
            log.failure(f"No support_inbound_messages row with id={args.message_id!r}")
            raise SystemExit(1)

        f = row.fields
        raw_ts = f.get("received_at")
        if isinstance(raw_ts, str):
            received_at = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        else:
            received_at = datetime.datetime.now(datetime.timezone.utc)

        inbound = InboundMessage(
            message_id=f.get("message_id") or row.id,
            in_reply_to=f.get("in_reply_to"),
            subject=f.get("subject"),
            from_address=f.get("from_address", ""),
            body_text=f.get("body_text"),
            received_at=received_at,
            request_code=None,  # support emails don't have a request code
        )

        handle_message(db, inbound, dry_run=args.dry_run)

        if not args.dry_run:
            db.SupportInboundMessages.update(row.id, {"seen": True})
