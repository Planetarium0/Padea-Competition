"""
escalate_dietary.py — Escalate overdue dietary clarification requests.

Walks every dietary_clarification_requests row where status='Open' and
sent_at is more than 7 days ago. For each:
  1. Marks status='Escalated'.
  2. Calls notify_coordinator (artifact-first; deduped by request_id).

Dedupe: an already-Escalated request is not re-notified even if this action
runs again.

This action runs on demand and is also called at the end of
./run dietary clarify <school> so that the same command picks up any
prior-term sweeps that crossed the 7-day line.

Usage:
  python scripts/actions/dietary/escalate_dietary.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime

from support import (
    Database,
    Record,
    log,
    notify_coordinator,
    self_healing_error_handler,
)

ESCALATION_DAYS = 7


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _is_overdue(
    sent_at_str: str,
    reference: datetime.datetime,
) -> bool:
    """True if the request has been open for more than ESCALATION_DAYS days."""
    try:
        sent_at = datetime.datetime.fromisoformat(
            sent_at_str.replace("Z", "+00:00")
        )
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
        return (reference - sent_at) >= datetime.timedelta(days=ESCALATION_DAYS)
    except (ValueError, TypeError):
        log.warning(f"Could not parse sent_at={sent_at_str!r}; treating as not overdue")
        return False


def run_escalation(
    db: Database,
    *,
    reference_date: datetime.datetime | None = None,
    dry_run: bool = False,
) -> int:
    """Escalate all Open requests that have passed the 7-day window.

    Returns the number of requests escalated (or that would be escalated
    in dry-run mode).
    """
    reference = reference_date or datetime.datetime.now(datetime.timezone.utc)
    requests = db.DietaryClarificationRequests.all()

    open_requests = [
        req for req in requests
        if req.fields.get("status") in ("Open", "Clarifying")
    ]
    log.info(
        f"Escalation check: {len(open_requests)} open/clarifying request(s), "
        f"reference={reference.date()}"
    )

    # Build caterer name lookup
    caterers = {c.id: c.fields.get("name", c.id) for c in db.Caterers.all()}
    schools = {s.id: s.fields.get("name") for s in db.Schools.all()}

    escalated = 0
    for req in open_requests:
        sent_at_str = req.fields.get("sent_at") or ""
        if not _is_overdue(sent_at_str, reference):
            log.verbose(
                f"  Request {req.fields.get('request_code', req.id)!r}: "
                f"not yet overdue"
            )
            continue

        caterer_id = req.fields.get("caterer_id", "")
        school_id = req.fields.get("school_id")
        caterer_name = caterers.get(caterer_id, caterer_id)
        school_name = schools.get(school_id) if school_id else None
        num_open = len(req.fields.get("question_set") or [])
        request_code = req.fields.get("request_code", req.id)

        log.info(
            f"  Escalating {request_code!r}: {caterer_name} "
            f"({num_open} question(s), sent {sent_at_str[:10]})"
        )

        if dry_run:
            log.info(f"  [DRY RUN] Would mark Escalated and notify coordinator")
            escalated += 1
            continue

        db.DietaryClarificationRequests.update(req.id, {"status": "Escalated"})

        notify_coordinator(
            req.id,
            reason=caterer_name,
            school_name=school_name,
            num_open_questions=num_open,
            sent_at_str=sent_at_str,
        )

        escalated += 1

    log.info(f"Escalation complete: {escalated} request(s) escalated.")
    return escalated


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Escalate overdue dietary clarification requests",
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
                "caterers": db.Caterers.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("escalate_dietary", state_provider=db_state_provider):
        db = Database.from_env()
        run_escalation(db, dry_run=args.dry_run)
