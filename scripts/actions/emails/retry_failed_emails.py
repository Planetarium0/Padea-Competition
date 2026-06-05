"""
retry_failed_emails.py — Re-send emails that previously failed to dispatch.

Queries scheduled_emails for rows with status='Failed', attempts to re-send
each one via SendGrid, and updates the row status to 'Sent' on success or
leaves it as 'Failed' (logging the error) if the retry also fails.

Idempotent: safe to run multiple times. Only rows currently in 'Failed'
status are retried.

Usage:
  python scripts/actions/emails/retry_failed_emails.py [--dry-run]
"""

from __future__ import annotations

import argparse

from support import Database, log, self_healing_error_handler
from support.email import _send_via_sendgrid


def retry_failed_emails(
    db: Database | None = None,
    dry_run: bool = False,
) -> None:
    db = db or Database.from_env()

    failed = db.ScheduledEmails.all(
        filter=lambda q: q.eq("status", "Failed"),
    )

    if not failed:
        log.info("No failed emails to retry.")
        return

    log.info(f"Found {len(failed)} failed email(s) to retry.")

    retried = 0
    succeeded = 0

    for record in failed:
        fields = record.fields
        email_id  = fields.get("email_code", record.id)
        to_addr   = fields.get("to_address")
        cc_raw    = fields.get("cc_address")
        subject   = fields.get("subject")
        body      = fields.get("body")

        if not to_addr or not subject or not body:
            log.warning(
                f"[SKIP] {email_id}: missing to_address, subject, or body — cannot retry."
            )
            retried += 1
            continue

        cc_list = [a.strip() for a in cc_raw.split(",")] if cc_raw else None

        log.info(f"Retrying: {email_id} → {to_addr}")
        if dry_run:
            log.info(f"[DRY RUN] Would resend: {email_id}")
            retried += 1
            continue

        try:
            _send_via_sendgrid(
                to=[to_addr],
                cc=cc_list,
                subject=subject,
                body=body,
                from_email=None or f"orders@{__import__('os').environ.get('APP_DOMAIN', 'padea.com.au')}",
                is_html=True,
            )
            db.ScheduledEmails.update(record.id, {"status": "Sent"})
            log.info(f"[SENT] {email_id}")
            succeeded += 1
        except Exception as exc:
            log.failure(f"[STILL FAILED] {email_id}: {exc}")

        retried += 1

    log.info(
        f"Retry complete: {succeeded}/{retried} email(s) succeeded."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retry scheduled emails with status=Failed",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would happen without sending",
    )
    args = parser.parse_args()

    def db_state_provider():
        try:
            db = Database.from_env()
            return {"scheduled_emails": db.ScheduledEmails.all()}
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("retry_failed_emails", state_provider=db_state_provider):
        retry_failed_emails(dry_run=args.dry_run)
