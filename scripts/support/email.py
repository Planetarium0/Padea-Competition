"""Shared email sending helpers used by all action scripts.

Two surfaces:

- :func:`schedule_email` — operational mail (caterer orders, QR codes,
  preference links, switch alerts). Writes an audit row to
  ``scheduled_emails`` and dispatches via Resend.
- :func:`escalate_to_dev` — last-resort human-in-the-loop notification
  used by the self-healing harness when an agent rules out a logical
  fix. Writes an artifact to ``cache/failures/escalation_<id>.md`` first
  so the escalation survives even if Resend is the thing failing, then
  best-effort sends a one-line notification.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import resend

from .records import ScheduledEmailFields
from .support import log

if TYPE_CHECKING:
    from .database import Database, Record


def schedule_email(
    db:                          Database,
    to_email:                    str,
    cc_email:                    list[str] | None,
    subject:                     str,
    body:                        str,
    email_id:                    str,
    weekly_order_id:             str | None = None,
    caterer_switch_proposal_id:  str | None = None,
) -> Record[ScheduledEmailFields] | None:
    """Create an audit record in scheduled_emails and immediately send via Resend.

    Exactly one of ``weekly_order_id`` or ``caterer_switch_proposal_id`` should
    be provided so the email is traceable back to its source record.
    """
    fields: dict[str, object] = {
        "email_code":  email_id,
        "to_address":  to_email,
        "subject":     subject,
        "body":        body,
        "status":      "Queued",
        "send_date":   None,
    }
    if cc_email:
        fields["cc_address"] = ", ".join(cc_email)
    if weekly_order_id:
        fields["weekly_order_id"] = weekly_order_id
    if caterer_switch_proposal_id:
        fields["caterer_switch_proposal_id"] = caterer_switch_proposal_id
    created = db.ScheduledEmails.create([fields])
    se_record = created[0] if created else None
    log.info(f"[QUEUED] Email record created: {email_id}")

    # Development override: redirect all outbound mail to the dev inbox.
    # The audit record retains the original to_address so the log stays truthful.
    if os.environ.get("APP_ENV") == "development":
        dev_recipient = os.environ.get("DEV_NOTIFICATION_EMAIL")
        if not dev_recipient:
            log.error(
                f"[DEV] APP_ENV=development but DEV_NOTIFICATION_EMAIL is not set — "
                f"skipping send to {to_email}"
            )
            return se_record
        log.warning(f"[DEV] Redirecting {to_email} → {dev_recipient} (APP_ENV=development)")
        actual_to = dev_recipient
        actual_cc: list[str] | None = None
    else:
        actual_to = to_email
        actual_cc = cc_email

    from_addr = os.environ.get("RESEND_FROM", "Padea <orders@padea.com.au>")
    send_params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [actual_to],
        "subject": subject,
        "text": body,
    }
    if actual_cc:
        send_params["cc"] = actual_cc
    try:
        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.Emails.send(send_params)
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Sent"})
        log.info(f"[SENT] Email sent to {actual_to}")
    except Exception as exc:
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Failed"})
        log.error(f"[FAILED] Failed to send email to {actual_to}: {exc}")

    return se_record


# ---------------------------------------------------------------------------
# Developer escalation — used by the self-healing harness when an agent
# decides a failure is environmental (bad credential, third-party schema
# drift, etc.) and not a logical bug it can patch.
# ---------------------------------------------------------------------------

# Resolved from the project root: scripts/support/email.py -> ../../cache/failures
_ESCALATION_DIR = Path(__file__).resolve().parents[2] / "cache" / "failures"


def _escalation_artifact_path(failure_id: str) -> Path:
    return _ESCALATION_DIR / f"escalation_{failure_id}.md"


def _build_escalation_body(
    failure_id:        str,
    reason:            str,
    workflow:          Optional[str],
    suggested_action:  Optional[str],
    traceback_text:    Optional[str],
) -> str:
    parts: list[str] = [
        f"# Escalation: {failure_id}",
        "",
        f"- **Workflow**: `{workflow or 'unknown'}`",
        f"- **Raised at**: {datetime.datetime.now().isoformat()}",
        "",
        "## Why this needs a human",
        "",
        reason.strip(),
        "",
    ]
    if suggested_action:
        parts.extend([
            "## Suggested human action",
            "",
            suggested_action.strip(),
            "",
        ])
    if traceback_text:
        parts.extend([
            "## Stack trace at point of failure",
            "",
            "```",
            traceback_text.rstrip(),
            "```",
            "",
        ])
    parts.append(
        "_Generated by `support.email.escalate_to_dev`. The agent reached "
        "this point after ruling out logical fixes per `plans/current/principles.md §2`._"
    )
    return "\n".join(parts)


def escalate_to_dev(
    failure_id:        str,
    reason:            str,
    *,
    workflow:          Optional[str]   = None,
    suggested_action:  Optional[str]   = None,
    traceback_text:    Optional[str]   = None,
    notify_email:      Optional[str]   = None,
) -> Path:
    """Record a developer escalation and best-effort notify by email.

    Writes ``cache/failures/escalation_<failure_id>.md`` first so the
    escalation survives email failures, then dispatches a one-line
    notification via Resend pointing at the artifact.

    Deduplicates by ``failure_id``: if the artifact already exists, the
    call is a no-op — returns the existing path without re-sending. This
    protects against retry loops in the self-healing harness spamming the
    dev mailbox for the same root cause.

    Args:
        failure_id: stable identifier tying the escalation to a captured
            failure under ``cache/failures/failure_<id>.json``.
        reason: free-text explanation of why the agent cannot patch this
            (e.g. "Resend returned 401 Unauthorized; tested with two
            different payloads, same response — likely invalid API key").
        workflow: the workflow name from ``self_healing_error_handler``
            (e.g. ``"register_orders"``).
        suggested_action: optional concrete instruction for the developer
            (e.g. "rotate RESEND_API_KEY in .env and rerun ./run orders").
        traceback_text: optional captured traceback for context.
        notify_email: override the env-resolved recipient. Defaults to
            ``DEV_NOTIFICATION_EMAIL`` from the environment.

    Returns:
        Path to the (possibly pre-existing) escalation artifact.
    """
    artifact_path = _escalation_artifact_path(failure_id)
    if artifact_path.exists():
        log.info(f"[ESCALATION DEDUPE] {artifact_path.name} already exists; not re-notifying")
        return artifact_path

    _ESCALATION_DIR.mkdir(parents=True, exist_ok=True)
    body = _build_escalation_body(
        failure_id=failure_id,
        reason=reason,
        workflow=workflow,
        suggested_action=suggested_action,
        traceback_text=traceback_text,
    )
    artifact_path.write_text(body, encoding="utf-8")
    log.warning(f"[ESCALATION] Written to {artifact_path}")

    recipient = notify_email or os.environ.get("DEV_NOTIFICATION_EMAIL")
    if not recipient:
        log.error(
            "[ESCALATION] DEV_NOTIFICATION_EMAIL not set — artifact written "
            "but no email was sent. Configure the env var to enable notifications."
        )
        return artifact_path

    from_addr = os.environ.get("RESEND_FROM", "Padea <orders@padea.com.au>")
    subject = f"[Padea escalation] {workflow or 'workflow'} needs you — {failure_id}"
    short_body = (
        f"The self-healing agent cannot resolve this without human input.\n\n"
        f"Reason: {reason.strip().splitlines()[0]}\n\n"
        f"Full details on disk: {artifact_path}\n"
    )
    send_params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [recipient],
        "subject": subject,
        "text": short_body,
    }
    try:
        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.Emails.send(send_params)
        log.warning(f"[ESCALATION] Notification sent to {recipient}")
    except KeyError:
        log.error(
            "[ESCALATION] RESEND_API_KEY not set — artifact written but no "
            "email sent. Check the artifact directly."
        )
    except Exception as exc:
        log.error(
            f"[ESCALATION] Notification email failed ({exc}). Artifact "
            f"at {artifact_path} is the source of truth."
        )

    return artifact_path
