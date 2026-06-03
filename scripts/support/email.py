"""Shared email sending helper used by all action scripts."""

from __future__ import annotations

import os

import resend

from .database import Database, Record
from .records import ScheduledEmailFields
from .support import log


def schedule_email(
    db:                          Database,
    to_email:                    str,
    cc_email:                    list[str] | None,
    subject:                     str,
    body:                        str,
    email_id:                    str,
    weekly_order_id:             str | None = None,
    caterer_switch_proposal_id:  str | None = None,
) -> "Record[ScheduledEmailFields] | None":
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

    from_addr = os.environ.get("RESEND_FROM", "Padea <orders@padea.com.au>")
    send_params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if cc_email:
        send_params["cc"] = cc_email
    try:
        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.Emails.send(send_params)
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Sent"})
        log.info(f"[SENT] Email sent to {to_email}")
    except Exception as exc:
        if se_record:
            db.ScheduledEmails.update(se_record.id, {"status": "Failed"})
        log.error(f"[FAILED] Failed to send email to {to_email}: {exc}")

    return se_record
