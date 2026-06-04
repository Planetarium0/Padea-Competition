"""
poll_dietary_inbox.py — drain the dietary inbound inbox and parse replies.

For each unseen inbound message:
  1. Extract the request code from the to_address local part.
  2. Match to an active (Open or Clarifying) dietary_clarification_requests row.
  3. If matched: call parse_dietary_reply.parse_reply.
  4. If unmatched or no code: notify coordinator (best-effort) and mark seen.

After draining the inbox, runs the escalation check so overdue requests
are also caught in the same command.

Usage:
  python scripts/actions/poll_dietary_inbox.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime

from support import (
    Database,
    log,
    notify_coordinator,
    self_healing_error_handler,
)
from support.inbound import InboundMailbox, InboundMessage, SupabaseInboundInbox


# ---------------------------------------------------------------------------
# Core poll logic
# ---------------------------------------------------------------------------

def run_poll(
    db: Database,
    inbox: InboundMailbox,
    *,
    dry_run: bool = False,
) -> int:
    """Drain the inbound inbox and parse any matched replies.

    Returns the number of messages processed (matched or not).
    """
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    messages = inbox.fetch_new(since=since)
    log.info(f"Poll: {len(messages)} unseen message(s)")

    requests = db.DietaryClarificationRequests.all()
    active_by_code: dict[str, object] = {
        r.fields["request_code"]: r
        for r in requests
        if r.fields.get("status") in ("Open", "Clarifying")
        and r.fields.get("request_code")
    }

    processed = 0
    for msg in messages:
        if msg.request_code is None:
            log.warning(
                f"Orphan inbound: no request code in to_address, from={msg.from_address}"
            )
            if not dry_run:
                _notify_orphan(msg)
            inbox.mark_seen(msg.message_id)
            processed += 1
            continue

        request = active_by_code.get(msg.request_code)
        if request is None:
            log.warning(
                f"No active request for code {msg.request_code!r}, "
                f"from={msg.from_address}"
            )
            if not dry_run:
                _notify_orphan(msg)
                inbox.mark_seen(msg.message_id)
            processed += 1
            continue

        log.info(
            f"Processing reply for request {msg.request_code!r} "
            f"from {msg.from_address}"
        )
        if not dry_run:
            from actions.parse_dietary_reply import parse_reply
            parse_reply(db, request, msg)
            inbox.mark_seen(msg.message_id)
        processed += 1

    # Run escalation so overdue requests are caught in the same command.
    if not dry_run:
        from actions.escalate_dietary import run_escalation
        run_escalation(db)

    log.info(f"Poll complete: {processed} message(s) processed.")
    return processed


def _notify_orphan(msg: InboundMessage) -> None:
    """Best-effort coordinator notification for an orphan / unmatched reply."""
    pseudo_id = "orphan-" + (msg.message_id or "unknown")[:16]
    # notify_coordinator dedupes by request_id so repeated orphans won't flood.
    try:
        notify_coordinator(
            pseudo_id,
            caterer_name=msg.from_address or "unknown",
            num_open_questions=0,
        )
    except Exception as exc:
        log.warning(f"Could not notify coordinator about orphan reply: {exc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Poll the dietary inbound inbox and parse caterer replies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to the database",
    )
    args = parser.parse_args()

    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "dietary_clarification_requests": db.DietaryClarificationRequests.all(),
                "dietary_inbound_messages": db.DietaryInboundMessages.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("poll_dietary_inbox", state_provider=db_state_provider):
        db = Database.from_env()
        inbox = SupabaseInboundInbox(db)
        run_poll(db, inbox, dry_run=args.dry_run)
