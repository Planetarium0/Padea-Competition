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
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Literal

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
# Sender identity resolution
# ---------------------------------------------------------------------------

SenderRole = Literal[
    "developer", "coordinator", "parent", "student", "caterer", "on_site_manager", "unknown"
]


@dataclass
class SenderIdentity:
    """Resolved identity of an inbound email sender."""
    role: SenderRole
    email: str
    is_impersonating: bool = False
    original_email: str = ""
    # Role-specific DB records (at most one group will be populated)
    students: list[Record] = dataclass_field(default_factory=list)        # parent's children
    student_record: Record | None = None                                    # student's own row
    caterer_record: Record | None = None
    on_site_manager_record: Record | None = None


def resolve_sender_identity(
    db: Database,
    sender_email: str,
    *,
    original_email: str = "",
    is_impersonating: bool = False,
) -> SenderIdentity:
    """Look up sender_email against all DB tables and return the resolved identity.

    Resolution order (first match wins):
      coordinator env var → parent (parent_email) → student (email) →
      caterer (contact_email or chef_email) → on_site_manager → unknown
    """
    lower = sender_email.lower()
    base = dict(email=sender_email, original_email=original_email, is_impersonating=is_impersonating)

    coordinator_email = os.environ.get("COORDINATOR_EMAIL", "")
    if coordinator_email and lower == coordinator_email.lower():
        return SenderIdentity(role="coordinator", **base)

    dev_email = os.environ.get("DEV_NOTIFICATION_EMAIL", "")
    if dev_email and lower == dev_email.lower() and not is_impersonating:
        return SenderIdentity(role="developer", **base)

    all_students = db.Students.all()

    children = [s for s in all_students if (s.fields.get("parent_email") or "").lower() == lower]
    if children:
        return SenderIdentity(role="parent", students=children, **base)

    for student in all_students:
        if (student.fields.get("email") or "").lower() == lower:
            return SenderIdentity(role="student", student_record=student, **base)

    for caterer in db.Caterers.all():
        contact = (caterer.fields.get("contact_email") or "").lower()
        chef = (caterer.fields.get("chef_email") or "").lower()
        if lower in (contact, chef):
            return SenderIdentity(role="caterer", caterer_record=caterer, **base)

    for mgr in db.OnSiteManagers.all():
        if (mgr.fields.get("email") or "").lower() == lower:
            return SenderIdentity(role="on_site_manager", on_site_manager_record=mgr, **base)

    return SenderIdentity(role="unknown", **base)


def _identity_description(identity: SenderIdentity) -> str:
    """Return a one-line human-readable description of the sender identity."""
    role = identity.role
    if role == "parent":
        names = [s.fields.get("name", "?") for s in identity.students]
        return f"parent (children: {', '.join(names)})"
    if role == "student" and identity.student_record:
        name = identity.student_record.fields.get("name", "?")
        return f"student ({name})"
    if role == "caterer" and identity.caterer_record:
        name = identity.caterer_record.fields.get("name", "?")
        return f"caterer ({name})"
    if role == "on_site_manager" and identity.on_site_manager_record:
        name = identity.on_site_manager_record.fields.get("name", "?")
        return f"on-site manager ({name})"
    return role


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
  in the system. Use this when a parent needs a restriction that does not appear
  in the available list, and it is also reasonable to create that new dietary restriction
  (i.e., if a parent mentions "Allergic to Almonds", and "Nut Free" is already
  a dietary restriction, prefer using that to creating a new one).
  After creating it, assign it with update_dietary.
  Always inform the parent that their the updated dietary requirements will take time
  before they show up on the meals, since we have to wait for the caterers to get back
  to us with the information.

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
- Don't promise things you aren't able to do.
- Currently there is no mechanism for follow up emails, so don't say things
  like "We'll be in touch once that's sorted". However, saying things like:
  "feel free to reach out" are okay because if they email us first, then
  we can respond.
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

def _build_sender_context(identity: SenderIdentity, restrictions: list[Record]) -> str:
    """Build a '## Sender' section for the LLM prompt describing who is emailing."""
    lines: list[str] = ["## Sender"]
    lines.append(f"Role: {identity.role}")
    lines.append(f"Email: {identity.email}")
    if identity.is_impersonating:
        lines.append(f"(Developer {identity.original_email!r} is impersonating this address)")

    if identity.role == "parent":
        for s in identity.students:
            f = s.fields
            restrictions_for_s = [
                r.fields.get("name", r.id)
                for r in restrictions
                if r.id in (f.get("dietary_requirement_ids") or [])
            ]
            lines.append(
                f"  child  id={s.id!r}  name={f.get('name')!r}  "
                f"year_level={f.get('year_level')}  "
                f"current_restrictions={restrictions_for_s!r}"
            )

    elif identity.role == "student" and identity.student_record:
        f = identity.student_record.fields
        restrictions_for_s = [
            r.fields.get("name", r.id)
            for r in restrictions
            if r.id in (f.get("dietary_requirement_ids") or [])
        ]
        lines.append(
            f"  id={identity.student_record.id!r}  name={f.get('name')!r}  "
            f"year_level={f.get('year_level')}  subjects={f.get('subjects')!r}  "
            f"current_restrictions={restrictions_for_s!r}  "
            f"parent_name={f.get('parent_name')!r}  parent_email={f.get('parent_email')!r}"
        )

    elif identity.role == "caterer" and identity.caterer_record:
        f = identity.caterer_record.fields
        lines.append(
            f"  id={identity.caterer_record.id!r}  name={f.get('name')!r}  "
            f"region={f.get('region')!r}  "
            f"contact_name={f.get('contact_name')!r}  contact_email={f.get('contact_email')!r}  "
            f"chef_name={f.get('chef_name')!r}  chef_email={f.get('chef_email')!r}"
        )

    elif identity.role == "on_site_manager" and identity.on_site_manager_record:
        f = identity.on_site_manager_record.fields
        lines.append(
            f"  id={identity.on_site_manager_record.id!r}  name={f.get('name')!r}  "
            f"mobile={f.get('mobile')!r}  email={f.get('email')!r}"
        )

    return "\n".join(lines)


def _build_llm_prompt(
    students: list[Record],
    restrictions: list[Record],
    thread_text: str,
    identity: SenderIdentity | None = None,
) -> str:
    if identity is not None:
        sender_section = _build_sender_context(identity, restrictions)
        # For backward-compat: if identity is parent, students come from identity.students
        effective_students = identity.students if identity.role == "parent" else students
    else:
        sender_section = (
            "## Parent's children\n"
            + "\n".join(
                f"  id={s.id!r}  name={s.fields.get('name')!r}  "
                f"year_level={s.fields.get('year_level')}  "
                f"current_restrictions={[r.fields.get('name', r.id) for r in restrictions if r.id in (s.fields.get('dietary_requirement_ids') or [])]!r}"
                for s in students
            )
        )
        effective_students = students

    restriction_lines = "\n".join(
        f"  name={r.fields.get('name', r.id)!r}"
        for r in restrictions
    )
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"{sender_section}\n\n"
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
        'The "actions" list may be empty. The "reply" must always be present.\n'
        'Use \\n within the "reply" string to add line breaks — they are rendered as <br> in the email.'
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
    identity: SenderIdentity | None = None,
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
    prompt = _build_llm_prompt(students, restrictions, thread_text, identity=identity)

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
# Plan approval / rejection processing
# ---------------------------------------------------------------------------

def _spawn_implementation(plan_id: str) -> None:
    """Spawn implement_plan.py as a fully detached background process."""
    project_root = Path(__file__).resolve().parents[3]
    script = project_root / "scripts" / "actions" / "system" / "implement_plan.py"
    python = project_root / ".venv" / "bin" / "python"
    if not python.exists():
        found = shutil.which("python3")
        python = Path(found) if found else Path("python3")

    env = os.environ.copy()
    scripts_dir = str(project_root / "scripts")
    root_dir = str(project_root)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = ":".join(
        [scripts_dir, root_dir] + ([existing] if existing else [])
    )

    subprocess.Popen(
        [str(python), str(script), "--plan-id", plan_id],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    log.info(f"[PLAN] Implementation spawned for plan {plan_id!r}")


def _try_process_plan_approval(
    inbound_msg: InboundMessage,
    *,
    dry_run: bool = False,
) -> bool:
    """Attempt to process a coordinator approval or rejection of an implementation plan.

    Returns True if the message was consumed as a plan verdict, False otherwise.
    """
    if inbound_msg.in_reply_to is None:
        return False

    from actions.system.register_edge_case import find_plan_by_message_id, update_plan

    plan = find_plan_by_message_id(inbound_msg.in_reply_to)
    if plan is None:
        return False

    if plan.get("status") != "pending":
        log.warning(
            f"[PLAN] Reply matches plan {plan['id']!r} "
            f"but status is already {plan.get('status')!r} — ignoring"
        )
        return True

    body = (inbound_msg.body_text or "").strip()
    if not body:
        return False

    first_line = body.splitlines()[0].strip()
    match = re.match(r"^(APPROVE|REJECT)(?:[:\s]+(.*))?$", first_line, re.IGNORECASE)
    if not match:
        return False

    keyword = match.group(1).upper()
    comments = (match.group(2) or "").strip()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if keyword == "APPROVE":
        if not dry_run:
            update_plan(
                plan["id"],
                {
                    "status": "approved",
                    "approved_at": now,
                    "approval_comments": comments or None,
                },
            )
            _spawn_implementation(plan["id"])
        log.info(
            f"[PLAN] Coordinator approved plan {plan['id']!r}. Comments: {comments!r}"
        )
    else:
        if not dry_run:
            update_plan(
                plan["id"],
                {
                    "status": "rejected",
                    "approved_at": now,
                    "rejection_reason": comments or "No reason given",
                },
            )
        log.info(
            f"[PLAN] Coordinator rejected plan {plan['id']!r}. Reason: {comments!r}"
        )

    return True


# ---------------------------------------------------------------------------
# System requirement classification for unrecognised senders
# ---------------------------------------------------------------------------

def _classify_system_requirement(
    inbound_msg: InboundMessage,
) -> tuple[bool, str]:
    """Use the LLM to check whether an email from an unknown sender describes a
    system-level requirement (needing a code change) rather than a personal
    support request.

    Returns (is_requirement, one_sentence_summary).
    """
    body = (inbound_msg.body_text or "").strip()
    subject = inbound_msg.subject or ""

    if not body:
        return False, ""

    prompt = (
        "You are an assistant for Padea, an after-school tutoring program that organises "
        "catered dinners at partner high schools.\n\n"
        "An email has arrived from an unrecognised sender. Determine whether it describes "
        "a SYSTEM REQUIREMENT — a change to how the software or operations should work — "
        "or a PERSONAL SUPPORT REQUEST for a specific person.\n\n"
        "Examples of system requirements:\n"
        "- A caterer says their Tuesday menu differs from their Wednesday menu\n"
        "- A caterer changes their minimum order quantity\n"
        "- A school changes its delivery address\n"
        "- A policy change affects how orders are generated\n\n"
        "Examples of personal support requests:\n"
        "- A parent asks to update their child's dietary restrictions\n"
        "- Someone has a billing question\n"
        "- A specific order was incorrect\n\n"
        f"Subject: {subject}\n"
        f"Body:\n{body[:1200]}\n\n"
        "Respond with ONLY a JSON object (no markdown fences):\n"
        '{"is_system_requirement": true or false, '
        '"summary": "One sentence describing the requirement, if applicable, otherwise empty string"}'
    )

    response = ask_llm(prompt)
    if response is None:
        return False, ""

    cleaned = re.sub(r"```(?:json)?\n?", "", response).strip()
    try:
        data = json.loads(cleaned)
        return bool(data.get("is_system_requirement")), data.get("summary", "")
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                return bool(data.get("is_system_requirement")), data.get("summary", "")
            except json.JSONDecodeError:
                pass
    return False, ""


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

    original_sender = sender_email
    impersonated = _dev_impersonate(sender_email, inbound_msg.subject)
    if impersonated:
        log.warning(
            f"[DEV] Impersonating {impersonated!r} "
            f"(subject override from {sender_email!r})"
        )
        sender_email = impersonated

    coordinator_email = os.environ.get("COORDINATOR_EMAIL", "")

    # 1a. Plan approval/rejection — check before role-based routing so replies from
    #     the developer address (which doubles as coordinator in dev mode) are handled.
    if _try_process_plan_approval(inbound_msg, dry_run=dry_run):
        return

    # 1b. Check if this is the coordinator — may be an approval/denial reply
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

    # 2. Resolve sender identity (always; logged prominently for new threads)
    is_new_thread = inbound_msg.in_reply_to is None
    identity = resolve_sender_identity(
        db,
        sender_email,
        original_email=original_sender if impersonated else "",
        is_impersonating=bool(impersonated),
    )
    if is_new_thread:
        log.info(
            f"[NEW THREAD] {sender_email!r} identified as {_identity_description(identity)}"
        )

    # 3. Derive students list from identity (parent role) or fall back to empty
    students = identity.students if identity.role == "parent" else []

    if not students:
        # Check if this is a system requirement from an external contact (e.g. caterer).
        is_req, summary = _classify_system_requirement(inbound_msg)
        if is_req and summary and not dry_run:
            from actions.system.register_edge_case import register_edge_case
            register_edge_case(summary, source="email")
            log.info(
                f"[PLAN] Auto-registered system requirement from {sender_email!r} "
                f"({identity.role}): {summary!r}"
            )
            return

        log.warning(
            f"No students linked to {sender_email!r} "
            f"(role={identity.role}) — notifying coordinator"
        )
        notify_coordinator(
            f"unknown-sender-{inbound_msg.message_id or uuid.uuid4().hex[:8]}",
            reason=f"{sender_email} (role={identity.role}, desc={_identity_description(identity)})",
            num_open_questions=0,
        )
        return

    log.info(
        f"Support email from {sender_email!r} ({_identity_description(identity)}): "
        f"{len(students)} student(s) found"
    )

    # 4. Find or create case
    case, is_new = find_or_create_case(db, inbound_msg, sender_email, dry_run=dry_run)
    case_code = case.fields.get("case_code", case.id)
    log.info(
        f"{'New' if is_new else 'Existing'} support case {case_code!r} "
        f"for {sender_email!r}"
    )

    # 5. Run the AI tool loop with full sender context
    run_tool_loop(db, case, inbound_msg, sender_email, students, identity=identity, dry_run=dry_run)


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
