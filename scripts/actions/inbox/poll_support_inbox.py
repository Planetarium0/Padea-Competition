"""
poll_support_inbox.py — Drain the support inbound inbox and process messages.

For each unseen support_inbound_messages row:
  1. Build an InboundMessage from the row fields.
  2. Call handle_message from handle_support_email.
  3. Mark the row as seen.

Usage:
  python scripts/actions/inbox/poll_support_inbox.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import os
from typing import Any

from support import (
    Database,
    log,
    self_healing_error_handler,
)
from support.inbound import InboundMessage


# ---------------------------------------------------------------------------
# Core poll logic
# ---------------------------------------------------------------------------

def run_poll(
    db: Database,
    *,
    dry_run: bool = False,
) -> int:
    """Drain the support inbox and process unseen messages.

    Returns the number of messages processed.
    """
    support_email = os.environ.get("SUPPORT_EMAIL")
    if not support_email:
        log.warning("SUPPORT_EMAIL not set — skipping support poll")
        return 0

    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    rows = db.SupportInboundMessages.all(
        filter=lambda q: q.eq("seen", False).gte("received_at", since.isoformat())
    )
    # Filter unseen in Python for mock compatibility (MockTable ignores filters)
    messages_rows = [r for r in rows if not r.fields.get("seen")]

    log.info(f"Support poll: {len(messages_rows)} unseen message(s)")

    processed = 0
    for row in messages_rows:
        f = row.fields
        raw_ts = f.get("received_at")
        if isinstance(raw_ts, str):
            received_at = datetime.datetime.fromisoformat(
                raw_ts.replace("Z", "+00:00")
            )
        else:
            received_at = datetime.datetime.now(datetime.timezone.utc)

        inbound_msg = InboundMessage(
            message_id=f.get("message_id") or row.id,
            in_reply_to=f.get("in_reply_to"),
            subject=f.get("subject"),
            from_address=f.get("from_address", ""),
            body_text=f.get("body_text"),
            received_at=received_at,
            request_code=None,  # support emails don't carry a request code
        )

        log.info(
            f"Processing support message from {inbound_msg.from_address!r} "
            f"(id={row.id})"
        )

        if not dry_run:
            from actions.inbox.handle_support_email import handle_message  # noqa: PLC0415
            handle_message(db, inbound_msg)
            db.SupportInboundMessages.update(row.id, {"seen": True})

        processed += 1

    log.info(f"Support poll complete: {processed} message(s) processed.")
    return processed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Poll the support inbound inbox and process parent emails",
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
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("poll_support_inbox", state_provider=db_state_provider):
        db = Database.from_env()
        run_poll(db, dry_run=args.dry_run)
