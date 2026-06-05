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
import email.utils
import json
import os
import re
import uuid
from typing import Any

from support import (
    Database,
    Record,
    SupportCaseFields,
    ask_llm,
    log,
    notify_coordinator,
    schedule_email,
    self_healing_error_handler,
)
from support.inbound import InboundMessage


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
2. Match the parent's plain-language description (e.g. "nut allergy", "vegetarian",
   "gluten free") to the closest restriction in the list provided.
3. Decide what changes to make and draft a polite reply.

Guidelines:
- Be friendly, concise, and professional.
- Only add restrictions for students in the provided list.
- If the request is ambiguous or no restriction matches, explain clearly in your reply
  and ask them to contact the coordinator directly.
- Always include a reply — never leave the parent without a response.
- Do not modify restrictions for students not in the provided list.
"""


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
                    from_email=f"support@{os.environ.get('APP_DOMAIN', 'padea.com.au')}",
                )
            else:
                log.info(f"[DRY RUN] Would send reply to {sender_email}: {body_text[:80]}...")

            return "Reply sent."

        else:
            return f"Error: unknown tool {tool_name!r}."

    return execute


# ---------------------------------------------------------------------------
# LLM prompt builder and response parser
# ---------------------------------------------------------------------------

def _build_llm_prompt(
    students: list[Record],
    restrictions: list[Record],
    thread_text: str,
) -> str:
    student_lines = "\n".join(
        f"  id={s.id!r}  name={s.fields.get('name')!r}  "
        f"year_level={s.fields.get('year_level')}  "
        f"current_restriction_ids={s.fields.get('dietary_requirement_ids') or []}"
        for s in students
    )
    restriction_lines = "\n".join(
        f"  id={r.id!r}  name={r.fields.get('name', r.id)!r}"
        for r in restrictions
    )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"## Parent's children\n{student_lines}\n\n"
        f"## Available dietary restrictions\n{restriction_lines}\n\n"
        f"## Email thread\n{thread_text}\n\n"
        'Respond with ONLY a JSON object — no markdown fences, no other text:\n'
        '{"actions": [{"type": "add_restriction", "student_id": "...", "restriction_id": "..."}], '
        '"reply": "..."}\n'
        'The "actions" list may be empty. The "reply" must always be present.'
    )


def _parse_llm_response(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    log.warning(f"Could not parse LLM response as JSON: {text[:200]!r}")
    return {}


# ---------------------------------------------------------------------------
# LLM loop
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
    """Process one inbound support message via ask_llm (SDK or CLI fallback).

    Fetches all context up front, calls ask_llm with a single structured prompt,
    parses the JSON response, executes the requested actions, and updates the case.
    """
    case_code = case.fields.get("case_code", case.id)

    if dry_run:
        log.info(f"[DRY RUN] Would call LLM for {case_code}")
        return

    restrictions = db.DietaryRestrictions.all()
    prior_messages: list[dict[str, Any]] = case.fields.get("messages") or []
    thread_text = _build_thread_text(prior_messages, inbound_msg)

    prompt = _build_llm_prompt(students, restrictions, thread_text)
    response_text = ask_llm(prompt)

    if response_text is None:
        log.failure(f"LLM returned no response for support case {case_code}")
        notify_coordinator(case.id, reason=sender_email, num_open_questions=1)
        return

    result = _parse_llm_response(response_text)
    executor = _make_tool_executor(db, sender_email, students, case, dry_run=False)

    tool_call_log: list[dict[str, Any]] = []
    for action in result.get("actions") or []:
        if action.get("type") == "add_restriction":
            tool_input = {
                "student_id": action.get("student_id", ""),
                "restriction_id": action.get("restriction_id", ""),
            }
            result_str = executor("add_dietary_restriction", tool_input)
            tool_call_log.append({"tool": "add_dietary_restriction", "input": tool_input, "result": result_str})

    reply_sent = False
    reply_text = result.get("reply", "")
    if reply_text:
        result_str = executor("send_reply", {"body_text": reply_text})
        reply_sent = True
        tool_call_log.append({"tool": "send_reply", "input": {"body_text": reply_text}, "result": result_str})

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

    db.SupportCases.update(case.id, update_fields)

    log.info(
        f"Support case {case_code}: "
        f"reply_sent={reply_sent}, status={update_fields.get('status', 'Open')}"
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _dev_impersonate(sender_email: str, subject: str | None) -> str | None:
    """Return an impersonated sender if the dev address embeds one in the subject."""
    dev_email = os.environ.get("DEV_NOTIFICATION_EMAIL", "")
    if not dev_email or sender_email.lower() != dev_email.lower():
        return None
    if not subject:
        return None
    match = re.search(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", subject)
    return match.group(0) if match else None


def handle_message(
    db: Database,
    inbound_msg: InboundMessage,
    *,
    dry_run: bool = False,
) -> None:
    """Orchestrate handling of one inbound support message."""
    _, sender_email = email.utils.parseaddr(inbound_msg.from_address)
    if not sender_email:
        sender_email = inbound_msg.from_address

    impersonated = _dev_impersonate(sender_email, inbound_msg.subject)
    if impersonated:
        log.warning(
            f"[DEV] Impersonating {impersonated!r} "
            f"(subject override from {sender_email!r})"
        )
        sender_email = impersonated

    coordinator_email = os.environ.get("COORDINATOR_EMAIL", "")

    # 1. Check if this is the coordinator emailing their own support inbox
    if coordinator_email and sender_email.lower() == coordinator_email.lower():
        log.warning(
            f"Support email from coordinator address {sender_email!r} — "
            f"routing to notify_coordinator to avoid loops"
        )
        notify_coordinator(
            f"coordinator-self-{inbound_msg.message_id or uuid.uuid4().hex[:8]}",
            reason=sender_email,
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
            reason=sender_email,
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
