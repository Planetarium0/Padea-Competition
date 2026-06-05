"""
handle_support_email.py — Process one inbound support email with AI tool use.

For a given support_inbound_messages row:
  1. Identify the parent by from_address → students with matching parent_email.
  2. If coordinator email: check for approval/denial reply first, then guard against loops.
  3. If unrecognised sender: notify coordinator and return.
  4. Find or create a support case (thread by In-Reply-To).
  5. Run an LLM action loop that can update dietary restrictions, update contact
     details, request coordinator approval for structural changes, and escalate.
  6. Update the support case with the conversation and new status.

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
    PendingChangeFields,
    Record,
    SupportCaseFields,
    ask_llm,
    log,
    notify_coordinator,
    schedule_email,
    self_healing_error_handler,
)
from support.email import Text, _send_via_sendgrid, _support_from, compose_email
from support.inbound import InboundMessage
from support.llm_tools import make_tool_executor

# Allow tests to reach executor factory via this module (backward-compat alias)
_make_tool_executor = make_tool_executor


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are the Padea parent support assistant. You help parents manage
their children's details in the Padea meal ordering system.

Padea is an after-school tutoring program that provides catered dinners. Parents
sometimes email in to update their child's details.

Your job is to:
1. Understand what the parent is asking.
2. Choose the correct action(s) from the list below.
3. Draft a polite, helpful reply.

Available actions:

- **update_dietary**: Set a student's dietary restrictions by name.
  You set the FULL list — if they want to add Vegetarian, include all existing
  restrictions plus Vegetarian.

- **create_dietary_restriction**: Create a new dietary restriction that is not yet
  in the system. Use this when a parent mentions a restriction that does not appear
  in the available list. After creating it, assign it with update_dietary.
  Always inform the parent that their meals will not have updated dietary requirements
  until the caterers have got back to us with more information.

- **update_contact**: Update parent contact details (parent_email, parent_mobile,
  or parent_name). Applied to all of the parent's students automatically.

- **request_change**: Request coordinator approval for a structural change to a
  student record (name, year_level, subjects, or student email).

- **escalate**: Forward a message to the coordinator when the parent wants to
  speak with someone directly or the request cannot be handled automatically.

Guidelines:
- Be friendly, concise, and professional.
- Only act on students in the provided list.
- If the request is ambiguous, explain clearly and ask them to contact the
  coordinator directly.
- Always include a reply — never leave the parent without a response.
- Use restriction names only (not IDs) when specifying dietary restrictions.
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
# LLM prompt builder
# ---------------------------------------------------------------------------

def _build_llm_prompt(
    students: list[Record],
    restrictions: list[Record],
    thread_text: str,
) -> str:
    student_lines = "\n".join(
        f"  id={s.id!r}  name={s.fields.get('name')!r}  "
        f"year_level={s.fields.get('year_level')}  "
        f"current_restrictions={[r.fields.get('name', r.id) for r in restrictions if r.id in (s.fields.get('dietary_requirement_ids') or [])]!r}"
        for s in students
    )
    restriction_lines = "\n".join(
        f"  name={r.fields.get('name', r.id)!r}"
        for r in restrictions
    )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"## Parent's children\n{student_lines}\n\n"
        f"## Available dietary restrictions (names only)\n{restriction_lines}\n\n"
        f"## Email thread\n{thread_text}\n\n"
        "## Action types\n"
        "- update_dietary: {type, student_id, restriction_names: [list of names]}\n"
        "- create_dietary_restriction: {type, name}  "
        "(use when restriction does not exist; then assign it with update_dietary)\n"
        "- update_contact: {type, field, new_value}  "
        "(field must be parent_email | parent_mobile | parent_name)\n"
        "- request_change: {type, student_id, field, new_value, reason}  "
        "(field must be name | year_level | subjects | email)\n"
        "- escalate: {type, message}\n\n"
        'Respond with ONLY a JSON object — no markdown fences, no other text:\n'
        '{"actions": [...], "reply": "..."}\n'
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
    """Process one inbound support message via ask_llm (single-turn JSON response).

    Injects students and restrictions into the prompt upfront, calls the LLM once,
    parses the JSON response, then dispatches each action to the tool executor.
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
    executor = make_tool_executor(db, sender_email, students, case, inbound_msg, dry_run=False)
    tool_call_log: list[dict[str, Any]] = []

    for action in result.get("actions") or []:
        action_type = action.get("type", "")

        if action_type == "update_dietary":
            tool_input = {
                "student_id": action.get("student_id", ""),
                "restriction_names": action.get("restriction_names") or [],
            }
        elif action_type == "update_contact":
            tool_input = {
                "field": action.get("field", ""),
                "new_value": action.get("new_value"),
            }
        elif action_type == "request_change":
            tool_input = {
                "student_id": action.get("student_id", ""),
                "field": action.get("field", ""),
                "new_value": action.get("new_value"),
                "reason": action.get("reason", ""),
            }
        elif action_type == "create_dietary_restriction":
            tool_input = {"name": action.get("name", "")}
        elif action_type == "escalate":
            tool_input = {"message": action.get("message", "")}
        elif action_type == "add_restriction":
            tool_input = {
                "student_id": action.get("student_id", ""),
                "restriction_id": action.get("restriction_id", ""),
            }
            action_type = "add_dietary_restriction"
        else:
            continue

        result_str = executor(action_type, tool_input)
        tool_call_log.append({"tool": action_type, "input": tool_input, "result": result_str})

    reply_sent = False
    reply_text = result.get("reply", "")
    if reply_text:
        result_str = executor("send_reply", {"body": reply_text})
        reply_sent = True
        tool_call_log.append({"tool": "send_reply", "input": {"body": reply_text}, "result": result_str})

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
# Coordinator approval/denial processing
# ---------------------------------------------------------------------------

def _try_process_approval(
    db: Database,
    inbound_msg: InboundMessage,
    *,
    dry_run: bool = False,
) -> bool:
    """Attempt to process a coordinator approval/denial reply.

    Returns True if the message was handled as an approval/denial, False otherwise.
    """
    if inbound_msg.in_reply_to is None:
        return False

    # Find a Pending change whose notification_message_id matches in_reply_to
    all_pending = db.PendingChanges.all()
    pending: Record[PendingChangeFields] | None = None
    for p in all_pending:
        if (
            p.fields.get("status") == "Pending"
            and p.fields.get("notification_message_id") == inbound_msg.in_reply_to
        ):
            pending = p  # type: ignore[assignment]
            break

    if pending is None:
        return False

    # Parse the first word of the body
    body = (inbound_msg.body_text or "").strip()
    if not body:
        return False

    first_line = body.splitlines()[0]
    parts = first_line.split(None, 1)
    decision = parts[0].upper()

    if decision not in ("APPROVE", "DENY"):
        return False

    coordinator_message = parts[1].strip() if len(parts) > 1 else ""

    parent_email: str = pending.fields.get("parent_email", "")
    student_id: str = pending.fields.get("student_id", "")
    field_name: str = pending.fields.get("field_name", "")
    new_value = pending.fields.get("new_value")

    if decision == "APPROVE":
        if not dry_run:
            # Apply the change to the student
            if student_id and field_name:
                db.Students.update(student_id, {field_name: new_value})

            # Update pending_change status
            db.PendingChanges.update(
                pending.id,
                {
                    "status": "Approved",
                    "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "coordinator_message": coordinator_message,
                },
            )

        # Email the parent
        reply_body = (
            f"Good news! Your requested change to {field_name!r} has been approved.\n\n"
            + (f"Message from the coordinator: {coordinator_message}\n\n" if coordinator_message else "")
            + "If you have any further questions, please reply to this email."
        )
        if not dry_run:
            _send_approved_denial_email(
                db, parent_email, field_name, "approved", reply_body
            )

        log.info(
            f"Pending change {pending.id} APPROVED by coordinator. "
            f"Applied {field_name!r}={new_value!r} to student {student_id!r}."
        )

    else:  # DENY
        if not dry_run:
            db.PendingChanges.update(
                pending.id,
                {
                    "status": "Denied",
                    "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "coordinator_message": coordinator_message,
                },
            )

        reply_body = (
            f"Your requested change to {field_name!r} has been reviewed and not approved "
            f"at this time.\n\n"
            + (f"Message from the coordinator: {coordinator_message}\n\n" if coordinator_message else "")
            + "If you have any further questions, please reply to this email."
        )
        if not dry_run:
            _send_approved_denial_email(
                db, parent_email, field_name, "denied", reply_body
            )

        log.info(
            f"Pending change {pending.id} DENIED by coordinator. "
            f"Parent {parent_email!r} notified."
        )

    return True


def _send_approved_denial_email(
    db: Database,
    parent_email: str,
    field_name: str,
    outcome: str,
    body: str,
) -> None:
    """Send an outcome email to the parent via schedule_email."""
    email_id = f"pending-change-{outcome}-{uuid.uuid4().hex[:8]}"
    schedule_email(
        db,
        to_email=parent_email,
        cc_email=None,
        subject=f"Re: Your Padea change request ({field_name})",
        body=compose_email([Text(body)]),
        email_id=email_id,
        from_email=f"support@{os.environ.get('APP_DOMAIN', 'padea.com.au')}",
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

    # 1. Check if this is the coordinator — may be an approval/denial reply
    if coordinator_email and sender_email.lower() == coordinator_email.lower():
        if _try_process_approval(db, inbound_msg, dry_run=dry_run):
            return
        # Not an approval — guard against loops
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
                "pending_changes": db.PendingChanges.all(),
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
