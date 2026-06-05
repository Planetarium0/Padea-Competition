"""
llm_tools.py — Tool schemas and executor factory for the support-email LLM loop.

Provides:
  TOOL_SCHEMAS  — list of tool definitions in Anthropic API format (input_schema).
  make_tool_executor  — factory that returns a callable (tool_name, tool_input) -> str.

The executor returned by make_tool_executor also has a ``reply_sent`` attribute
(a list[bool] with one element) that is set to True when the ``send_reply`` tool
is called.
"""

from __future__ import annotations

import os
from typing import Any

from .support import log


# ---------------------------------------------------------------------------
# Tool schemas (Anthropic API format — field name is `input_schema`)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "get_students",
        "description": (
            "Get the list of students belonging to this parent, including their IDs, "
            "names, year levels, and current dietary restriction names."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_dietary_restrictions",
        "description": "Get all available dietary restriction names that can be assigned to students.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_dietary_restrictions",
        "description": (
            "Set a student's dietary restrictions. Provide the FULL replacement list of "
            "restriction names (empty array clears all)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {"type": "string"},
                "restriction_names": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["student_id", "restriction_names"],
        },
    },
    {
        "name": "update_contact_detail",
        "description": (
            "Update a parent contact field. Applied to all of the parent's students "
            "automatically. Field must be one of: parent_email, parent_mobile, parent_name."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": ["parent_email", "parent_mobile", "parent_name"],
                },
                "new_value": {"type": "string"},
            },
            "required": ["field", "new_value"],
        },
    },
    {
        "name": "submit_change_request",
        "description": (
            "Submit a change to a student's structural field for coordinator approval. "
            "Field must be one of: name, year_level, subjects, email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {"type": "string"},
                "field": {
                    "type": "string",
                    "enum": ["name", "year_level", "subjects", "email"],
                },
                "new_value": {},
                "reason": {"type": "string"},
            },
            "required": ["student_id", "field", "new_value"],
        },
    },
    {
        "name": "escalate_to_coordinator",
        "description": (
            "Forward this case to the coordinator for human handling. Use when the request "
            "cannot be automated or the parent asks to speak with someone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "create_dietary_restriction",
        "description": (
            "Create a new dietary restriction that does not yet exist in the system. "
            "Use only when list_dietary_restrictions confirms the restriction is absent. "
            "After creating it, assign it to the student using update_dietary_restrictions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "send_reply",
        "description": (
            "Send a reply email to the parent. Always call this last to close the conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "body": {"type": "string"},
            },
            "required": ["body"],
        },
    },
]


# ---------------------------------------------------------------------------
# Executor factory
# ---------------------------------------------------------------------------

def make_tool_executor(
    db: Any,
    sender_email: str,
    students: list,         # list[Record] - parent's students already loaded
    case: Any,              # Record[SupportCaseFields]
    inbound_msg: Any | None = None,
    *,
    dry_run: bool = False,
) -> Any:
    """Return a callable (tool_name, tool_input) -> str that executes tool calls.

    The returned callable has a ``reply_sent`` attribute (list[bool], one element)
    that is set to True when ``send_reply`` is called.
    """
    # Import the email module (not specific names) so patches on support.email.X still work.
    from . import email as _email_mod

    reply_sent: list[bool] = [False]
    reply_count: list[int] = [0]

    # Pre-import build_thread_text lazily to avoid circular import
    def _build_thread_text_local(prior_messages: list, inbound: Any) -> str:
        """Local copy of thread text builder to avoid circular imports."""
        import datetime as _dt
        parts: list[str] = []
        for msg in prior_messages:
            direction = msg.get("direction", "unknown")
            sent_at = msg.get("sent_at", "")[:10]
            body = msg.get("body") or ""
            label = "Parent" if direction == "inbound" else "Padea Support"
            parts.append(f"[{label} — {sent_at}]\n{body}")

        today = _dt.date.today().isoformat()
        body = inbound.body_text or "(no message body)"
        parts.append(f"[Parent — {today}]\n{body}")

        return "\n\n---\n\n".join(parts)

    def execute(tool_name: str, tool_input: dict[str, Any]) -> str:

        # ------------------------------------------------------------------
        # get_students: return human-readable summary of parent's students
        # ------------------------------------------------------------------
        if tool_name == "get_students":
            all_restrictions = db.DietaryRestrictions.all()
            id_to_name: dict[str, str] = {
                r.id: r.fields.get("name", r.id) for r in all_restrictions
            }
            lines = [f"Students for {sender_email}:"]
            for s in students:
                restriction_ids: list[str] = s.fields.get("dietary_requirement_ids") or []
                restriction_names = [id_to_name.get(rid, rid) for rid in restriction_ids]
                names_str = ", ".join(restriction_names) if restriction_names else "(none)"
                lines.append(
                    f"  • {s.fields.get('name', s.id)} "
                    f"(id={s.id}, year={s.fields.get('year_level')}, "
                    f"restrictions={names_str})"
                )
            return "\n".join(lines)

        # ------------------------------------------------------------------
        # list_dietary_restrictions: return all restriction names
        # ------------------------------------------------------------------
        elif tool_name == "list_dietary_restrictions":
            all_restrictions = db.DietaryRestrictions.all()
            names = [r.fields.get("name", r.id) for r in all_restrictions]
            return "\n".join(names) if names else "(no dietary restrictions defined)"

        # ------------------------------------------------------------------
        # update_dietary_restrictions: set student's restrictions by name
        # ------------------------------------------------------------------
        elif tool_name == "update_dietary_restrictions":
            student_id = tool_input.get("student_id", "")
            restriction_names: list[str] = tool_input.get("restriction_names") or []

            # Validate student ownership
            student = db.Students.get(student_id)
            if student is None:
                return f"Error: student {student_id!r} not found."
            if student.fields.get("parent_email") != sender_email:
                return (
                    f"Error: student {student_id!r} does not belong to {sender_email!r}. "
                    f"No change made."
                )

            # Resolve names → IDs (case-insensitive)
            all_restrictions = db.DietaryRestrictions.all()
            name_to_id: dict[str, str] = {
                r.fields.get("name", "").lower(): r.id
                for r in all_restrictions
            }
            resolved_ids: list[str] = []
            unrecognised: list[str] = []
            for name in restriction_names:
                rid = name_to_id.get(name.lower())
                if rid:
                    resolved_ids.append(rid)
                else:
                    unrecognised.append(name)

            if unrecognised:
                return f"Error: unrecognised restriction name(s): {unrecognised!r}. No change made."

            student_name = student.fields.get("name", student_id)
            if not dry_run:
                db.Students.update(student_id, {"dietary_requirement_ids": resolved_ids})

            dry_suffix = " (dry-run: not written)" if dry_run else ""
            names_str = ", ".join(restriction_names) if restriction_names else "(none)"
            return f"Set dietary restrictions for {student_name} to: {names_str}.{dry_suffix}"

        # ------------------------------------------------------------------
        # update_contact_detail: update parent_email, parent_mobile, or parent_name
        # ------------------------------------------------------------------
        elif tool_name == "update_contact_detail":
            field = tool_input.get("field", "")
            new_value = tool_input.get("new_value")
            allowed_fields = {"parent_email", "parent_mobile", "parent_name"}
            if field not in allowed_fields:
                return (
                    f"Error: field {field!r} is not a directly-editable contact field. "
                    f"Allowed: {sorted(allowed_fields)!r}."
                )

            # Apply to ALL of sender's students
            updated_names: list[str] = []
            for stu in students:
                student_name = stu.fields.get("name", stu.id)
                if not dry_run:
                    db.Students.update(stu.id, {field: new_value})
                updated_names.append(student_name)

            dry_suffix = " (dry-run: not written)" if dry_run else ""
            return (
                f"Updated {field!r} to {new_value!r} for: "
                f"{', '.join(updated_names)}.{dry_suffix}"
            )

        # ------------------------------------------------------------------
        # submit_change_request: submit structural change for coordinator approval
        # ------------------------------------------------------------------
        elif tool_name == "submit_change_request":
            student_id = tool_input.get("student_id", "")
            field = tool_input.get("field", "")
            new_value = tool_input.get("new_value")
            reason = tool_input.get("reason", "")

            allowed_fields = {"name", "year_level", "subjects", "email"}
            if field not in allowed_fields:
                return (
                    f"Error: field {field!r} cannot be changed via submit_change_request. "
                    f"Allowed: {sorted(allowed_fields)!r}."
                )

            # Validate student ownership
            student = db.Students.get(student_id)
            if student is None:
                return f"Error: student {student_id!r} not found."
            if student.fields.get("parent_email") != sender_email:
                return (
                    f"Error: student {student_id!r} does not belong to {sender_email!r}. "
                    f"No change made."
                )

            student_name = student.fields.get("name", student_id)
            current_value = student.fields.get(field)

            if dry_run:
                return (
                    f"(dry-run) Would create pending change request: "
                    f"{student_name}'s {field!r} → {new_value!r}."
                )

            import uuid as _uuid
            # Create the pending_changes row
            pending_fields: dict[str, Any] = {
                "parent_email": sender_email,
                "student_id": student_id,
                "field_name": field,
                "current_value": current_value,
                "new_value": new_value,
                "reason": reason,
                "status": "Pending",
                "support_case_id": case.id if case.id != "dry-run-case" else None,
            }
            created = db.PendingChanges.create([pending_fields])
            pending = created[0]

            # Generate a stable Message-ID and persist it
            message_id = f"<pending-{pending.id}@padea.support>"
            db.PendingChanges.update(pending.id, {"notification_message_id": message_id})

            # Email coordinator
            coordinator_email = (
                os.environ.get("COORDINATOR_EMAIL")
                or os.environ.get("DEV_NOTIFICATION_EMAIL", "")
            )
            if coordinator_email:
                subject = f"[Padea] Change request: {student_name}'s {field}"
                body = (
                    f"A parent has requested a change to a student record.\n\n"
                    f"Parent: {sender_email}\n"
                    f"Student: {student_name} (id: {student_id})\n"
                    f"Field: {field}\n"
                    f"Current value: {current_value!r}\n"
                    f"Requested value: {new_value!r}\n"
                    + (f"Reason: {reason}\n" if reason else "")
                    + f"\nReply APPROVE or DENY (optionally followed by a message to the parent)."
                )
                try:
                    _email_mod._send_via_sendgrid(
                        to=[coordinator_email],
                        subject=subject,
                        body=body,
                        from_email=_email_mod._support_from(),
                        is_html=False,
                        message_id_header=message_id,
                    )
                except Exception as exc:
                    log.error(f"Failed to send coordinator notification for pending change: {exc}")

            return (
                f"Change request submitted for {student_name}'s {field!r}. "
                f"The coordinator will review and contact you with the outcome."
            )

        # ------------------------------------------------------------------
        # escalate_to_coordinator: forward message to coordinator
        # ------------------------------------------------------------------
        elif tool_name == "escalate_to_coordinator":
            message = tool_input.get("message", "")

            coordinator_email = (
                os.environ.get("COORDINATOR_EMAIL")
                or os.environ.get("DEV_NOTIFICATION_EMAIL", "")
            )

            if coordinator_email and not dry_run:
                prior_messages: list[dict[str, Any]] = case.fields.get("messages") or []
                thread_text = ""
                if inbound_msg is not None:
                    thread_text = _build_thread_text_local(prior_messages, inbound_msg)

                subject = f"[Padea] Escalation — {sender_email}"
                body = (
                    f"An email has been flagged for escalation.\n\n"
                    f"Parent: {sender_email}\n"
                    f"Message: {message}\n\n"
                    + (f"Email thread:\n\n{thread_text}" if thread_text else "")
                )
                try:
                    _email_mod._send_via_sendgrid(
                        to=[coordinator_email],
                        subject=subject,
                        body=body,
                        from_email=_email_mod._support_from(),
                        is_html=False,
                    )
                except Exception as exc:
                    log.error(f"Failed to send coordinator escalation email: {exc}")

            dry_suffix = " (dry-run: not sent)" if dry_run else ""
            return f"Escalated to coordinator.{dry_suffix}"

        # ------------------------------------------------------------------
        # send_reply: send a reply email to the parent
        # ------------------------------------------------------------------
        elif tool_name == "send_reply":
            body = tool_input.get("body", "")
            reply_count[0] += 1
            email_id = f"{case.fields.get('case_code', case.id)}-reply-{reply_count[0]}"

            html_body = _email_mod.compose_email([_email_mod.Text(body)])
            if not dry_run:
                orig_subject = (inbound_msg.subject or "Padea support") if inbound_msg else "Padea support"
                reply_subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"
                _email_mod.schedule_email(
                    db,
                    to_email=sender_email,
                    cc_email=None,
                    subject=reply_subject,
                    body=html_body,
                    email_id=email_id,
                    from_email=f"support@{os.environ.get('APP_DOMAIN', 'padea.com.au')}",
                    in_reply_to_header=inbound_msg.message_id if inbound_msg else None,
                )
            else:
                log.info(f"[DRY RUN] Would send reply to {sender_email}: {body[:80]}...")

            reply_sent[0] = True
            return "Reply sent."

        # ------------------------------------------------------------------
        # create_dietary_restriction: create a new restriction in the system
        # ------------------------------------------------------------------
        elif tool_name == "create_dietary_restriction":
            name = tool_input.get("name", "").strip()
            if not name:
                return "Error: name must not be empty."

            all_restrictions = db.DietaryRestrictions.all()
            existing = next(
                (r for r in all_restrictions if r.fields.get("name", "").lower() == name.lower()),
                None,
            )
            if existing:
                return (
                    f"Restriction {existing.fields.get('name', name)!r} already exists — "
                    f"use update_dietary_restrictions to assign it."
                )

            if not dry_run:
                db.DietaryRestrictions.create([{"name": name}])

            dry_suffix = " (dry-run: not written)" if dry_run else ""
            return (
                f"Created new dietary restriction {name!r}.{dry_suffix} "
                f"Note: existing meals will not reflect this restriction until caterers "
                f"have confirmed they can accommodate it."
            )

        # ------------------------------------------------------------------
        # Legacy tool handlers — kept for backward compatibility with tests 6-9
        # ------------------------------------------------------------------

        # update_dietary: old name for update_dietary_restrictions (different params)
        elif tool_name == "update_dietary":
            return execute("update_dietary_restrictions", tool_input)

        # update_contact: old name for update_contact_detail
        elif tool_name == "update_contact":
            return execute("update_contact_detail", tool_input)

        # request_change: old name for submit_change_request
        elif tool_name == "request_change":
            return execute("submit_change_request", tool_input)

        # escalate: old name for escalate_to_coordinator
        elif tool_name == "escalate":
            return execute("escalate_to_coordinator", tool_input)

        # add_dietary_restriction: legacy handler (kept for test compatibility, tests 6-9)
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

        else:
            return f"Error: unknown tool {tool_name!r}."

    execute.reply_sent = reply_sent  # type: ignore[attr-defined]
    return execute
