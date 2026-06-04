"""Shared email sending helpers used by all action scripts.

Two surfaces:

- :func:`schedule_email` — operational mail (caterer orders, QR codes,
  preference links, switch alerts). Writes an audit row to
  ``scheduled_emails`` and dispatches via SendGrid.
- :func:`escalate_to_dev` — last-resort human-in-the-loop notification
  used by the self-healing harness when an agent rules out a logical
  fix. Writes an artifact to ``cache/failures/escalation_<id>.md`` first
  so the escalation survives even if SendGrid is the thing failing, then
  best-effort sends a one-line notification.
"""

from __future__ import annotations

import datetime
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Optional

import httpx

from .records import ScheduledEmailFields
from .support import log

if TYPE_CHECKING:
    from .database import Database, Record


# ---------------------------------------------------------------------------
# Email component system
# ---------------------------------------------------------------------------

class Component(ABC):
    @abstractmethod
    def render(self) -> str: ...


@dataclass
class Text(Component):
    """A paragraph of text. Use ``\\n`` for line breaks. ``bold=True`` wraps in <strong>."""
    content: str
    bold: bool = False

    def render(self) -> str:
        body = self.content.replace("\n", "<br>")
        if self.bold:
            body = f"<strong>{body}</strong>"
        return f'<p style="margin:0 0 16px;">{body}</p>'


@dataclass
class Heading(Component):
    """A bold section heading. ``accent=True`` renders in primary red (#A51C30)."""
    text: str
    accent: bool = False

    def render(self) -> str:
        color = "#A51C30" if self.accent else "#1A1614"
        return f'<p style="margin:0 0 10px;font-weight:700;color:{color};">{self.text}</p>'


@dataclass
class Meta(Component):
    """A labelled key-value row, e.g. ``Meta("Deliver by", "6:20 PM")``."""
    label: str
    value: str

    def render(self) -> str:
        return (
            f'<p style="margin:0 0 4px;font-size:15px;">'
            f'<strong>{self.label}:</strong> {self.value}</p>'
        )


@dataclass
class Button(Component):
    """A CTA button in primary red."""
    label: str
    href: str

    def render(self) -> str:
        return (
            f'<p style="margin:12px 0 0;">'
            f'<a href="{self.href}" style="display:inline-block;background-color:#A51C30;'
            f'color:#FFFFFF;padding:10px 20px;border-radius:8px;text-decoration:none;'
            f'font-weight:600;font-size:15px;">{self.label}</a>'
            f'</p>'
        )


@dataclass
class List(Component):
    """A bulleted list. Items are rendered as raw HTML."""
    items: list[str]

    def render(self) -> str:
        items = "".join(
            f'<li style="margin:4px 0;font-size:15px;">{item}</li>'
            for item in self.items
        )
        return f'<ul style="margin:12px 0 4px;padding-left:20px;">{items}</ul>'


@dataclass
class Image(Component):
    """A centred image wrapped in a hyperlink."""
    src: str
    href: str
    alt: str
    size: int = 200

    def render(self) -> str:
        return (
            f'<p style="text-align:center;margin:0 0 12px;">'
            f'<a href="{self.href}">'
            f'<img src="{self.src}" alt="{self.alt}" width="{self.size}" height="{self.size}" '
            f'style="width:{self.size}px;height:{self.size}px;display:block;margin:0 auto;">'
            f'</a></p>'
        )


@dataclass
class Link(Component):
    """An inline text hyperlink. ``centered=True`` centres the paragraph."""
    text: str
    href: str
    centered: bool = False

    def render(self) -> str:
        align = "text-align:center;" if self.centered else ""
        return (
            f'<p style="margin:0 0 12px;font-size:14px;{align}">'
            f'<a href="{self.href}" style="color:#A51C30;">{self.text}</a>'
            f'</p>'
        )


@dataclass
class Card(Component):
    """A bordered card containing child components. ``shaded=True`` adds a light grey fill."""
    children: list[Component]
    shaded: bool = False

    def render(self) -> str:
        bg = "background-color:#FAF7F5;" if self.shaded else ""
        inner = "".join(child.render() for child in self.children)
        return (
            f'<div style="{bg}border:1px solid #ECE6E2;border-radius:8px;'
            f'padding:16px 20px;margin:0 0 16px;">'
            f'{inner}'
            f'</div>'
        )


@dataclass
class Alert(Component):
    """A coloured callout. ``variant='red'`` (default) or ``'amber'``."""
    children: list[Component]
    variant: Literal["red", "amber"] = "red"

    def render(self) -> str:
        if self.variant == "amber":
            style = "background-color:#FFF7E8;border:1px solid #F2DDB1;color:#8A4F08;"
        else:
            style = "background-color:#FDECEF;border:1px solid #F6D2D9;"
        inner = "".join(child.render() for child in self.children)
        return (
            f'<div style="{style}border-radius:8px;padding:14px 18px;margin:0 0 20px;">'
            f'{inner}'
            f'</div>'
        )


@dataclass
class Divider(Component):
    """A horizontal rule separating major sections."""

    def render(self) -> str:
        return '<div style="border-top:2px solid #ECE6E2;margin:8px 0 16px;"></div>'


def html_email(content: str) -> str:
    """Wrap raw HTML content in the Padea email shell. Prefer :func:`compose_email`."""
    f = "-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif"
    return (
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '</head>'
        f'<body lang="en" style="margin:0;padding:20px;font-family:{f};font-size:16px;line-height:1.5;color:#1A1614;max-width:600px;">'
        f'{content}'
        '</body>'
        '</html>'
    )


def compose_email(components: list[Component]) -> str:
    """Render a list of email components into a complete HTML email string."""
    return html_email("".join(c.render() for c in components))


# ---------------------------------------------------------------------------
# SendGrid dispatch helpers
# ---------------------------------------------------------------------------

_SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
_FROM_EMAIL = "padea@kaqe-crgm-vqjj-lacj.cfd"


def _send_via_sendgrid(
    *,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    is_html: bool = True,
) -> None:
    """Dispatch an email via SendGrid. Raises RuntimeError if the API key is missing."""
    api_key = os.environ.get("SENDGRID_API_KEY")
    if not api_key:
        raise RuntimeError("SENDGRID_API_KEY is not configured")

    personalization: dict = {"to": [{"email": addr} for addr in to]}
    if cc:
        personalization["cc"] = [{"email": addr} for addr in cc]

    payload = {
        "personalizations": [personalization],
        "from": {"email": _FROM_EMAIL},
        "subject": subject,
        "content": [{"type": "text/html" if is_html else "text/plain", "value": body}],
    }

    if os.environ.get("PADEA_TEST_MODE") == "1":
        raise RuntimeError(
            "_send_via_sendgrid was called without being mocked. "
            "Patch support.email._send_via_sendgrid in your test setUp."
        )

    response = httpx.post(
        _SENDGRID_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
    )
    if response.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid error {response.status_code}: {response.text}")


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

    try:
        _send_via_sendgrid(to=[actual_to], cc=actual_cc, subject=subject, body=body)
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Sent"})
        log.info(f"[SENT] Email sent to {actual_to}")
    except Exception as exc:
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Failed"})
        log.failure(f"[FAILED] Failed to send email to {actual_to}: {exc}")

    return se_record


# ---------------------------------------------------------------------------
# Developer escalation — used by the self-healing harness when an agent
# decides a failure is environmental (bad credential, third-party schema
# drift, etc.) and not a logical bug it can patch.
# ---------------------------------------------------------------------------

# Resolved from the project root: scripts/support/email.py -> ../../cache/
_ESCALATION_DIR = Path(__file__).resolve().parents[2] / "cache" / "failures"
_NOTIFICATIONS_DIR = Path(__file__).resolve().parents[2] / "cache" / "notifications"


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

    subject = f"[Padea escalation] {workflow or 'workflow'} needs you — {failure_id}"
    short_body = (
        f"The self-healing agent cannot resolve this without human input.\n\n"
        f"Reason: {reason.strip().splitlines()[0]}\n\n"
        f"Full details on disk: {artifact_path}\n"
    )
    try:
        _send_via_sendgrid(to=[recipient], subject=subject, body=short_body, is_html=False)
        log.warning(f"[ESCALATION] Notification sent to {recipient}")
    except Exception as exc:
        log.error(
            f"[ESCALATION] Notification email failed ({exc}). Artifact "
            f"at {artifact_path} is the source of truth."
        )

    return artifact_path


# ---------------------------------------------------------------------------
# Coordinator notification — used by escalate_dietary when a caterer has not
# responded to a dietary clarification request within 7 days.
# ---------------------------------------------------------------------------

def _coordinator_artifact_path(request_id: str) -> Path:
    return _NOTIFICATIONS_DIR / f"clarify_{request_id}.md"


def notify_coordinator(
    request_id: str,
    *,
    caterer_name: str,
    school_name: Optional[str] = None,
    num_open_questions: int = 0,
    sent_at_str: Optional[str] = None,
    notify_email: Optional[str] = None,
) -> Path:
    """Notify the program coordinator that a dietary clarification request went unanswered.

    Writes ``cache/notifications/clarify_<request_id>.md`` first so the
    notification survives email failures, then best-effort emails
    ``COORDINATOR_EMAIL`` (falling back to ``DEV_NOTIFICATION_EMAIL``).

    Deduplicates by ``request_id``: if the artifact already exists, returns
    the existing path without re-notifying.

    Args:
        request_id: the ``id`` UUID of the dietary_clarification_requests row.
        caterer_name: human-readable caterer name for the notification body.
        school_name: optional school name for context.
        num_open_questions: count of unanswered (item, restriction) pairs.
        sent_at_str: ISO timestamp when the clarification email was first sent.
        notify_email: override the env-resolved recipient.

    Returns:
        Path to the (possibly pre-existing) notification artifact.
    """
    artifact_path = _coordinator_artifact_path(request_id)
    if artifact_path.exists():
        log.info(
            f"[COORDINATOR NOTIFY DEDUPE] {artifact_path.name} already exists; "
            f"not re-notifying"
        )
        return artifact_path

    _NOTIFICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    school_line = f" / {school_name}" if school_name else ""
    body_lines = [
        f"# Dietary clarification unanswered — {caterer_name}{school_line}",
        "",
        f"- **Request ID**: `{request_id}`",
        f"- **Caterer**: {caterer_name}{school_line}",
        f"- **Open questions**: {num_open_questions}",
        f"- **Email sent at**: {sent_at_str or 'unknown'}",
        f"- **Escalated at**: {datetime.datetime.now().isoformat()}",
        "",
        "The caterer did not respond to the dietary clarification email within 7 days.",
        "Please follow up directly and transcribe their answers.",
        "",
        "_Generated by `support.email.notify_coordinator`._",
    ]
    artifact_path.write_text("\n".join(body_lines), encoding="utf-8")
    log.warning(f"[COORDINATOR NOTIFY] Written to {artifact_path}")

    recipient = (
        notify_email
        or os.environ.get("COORDINATOR_EMAIL")
        or os.environ.get("DEV_NOTIFICATION_EMAIL")
    )
    if not recipient:
        log.error(
            "[COORDINATOR NOTIFY] Neither COORDINATOR_EMAIL nor DEV_NOTIFICATION_EMAIL "
            "is set — artifact written but no email was sent."
        )
        return artifact_path

    subject = f"[Padea] Dietary clarification unanswered — {caterer_name}{school_line}"
    short_body = (
        f"The caterer {caterer_name}{school_line} did not respond to the dietary "
        f"clarification email within 7 days.\n\n"
        f"There are {num_open_questions} open question(s). Please follow up directly.\n\n"
        f"Full details: {artifact_path}\n"
    )
    try:
        _send_via_sendgrid(to=[recipient], subject=subject, body=short_body, is_html=False)
        log.warning(f"[COORDINATOR NOTIFY] Notification sent to {recipient}")
    except Exception as exc:
        log.error(
            f"[COORDINATOR NOTIFY] Notification email failed ({exc}). Artifact "
            f"at {artifact_path} is the source of truth."
        )

    return artifact_path
