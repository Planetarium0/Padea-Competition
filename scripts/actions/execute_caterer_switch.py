"""
execute_caterer_switch.py — Execute a caterer switch proposal.

Reads the named Caterer Switch Proposals record, verifies the status, then:
  1. Sets Sessions.Incoming Caterer for the affected session
     (the actual Caterer flip happens at the next register_orders.py run).
  2. Clears Students.Meal Preference for every student enrolled in that session
     (their preferences referenced the old caterer's menu).
  3. Marks the proposal Status='Executed'.

By default only Status='Approved' proposals are accepted.  Pass --approve
(CLI) or approve=True (Python) to also accept Status='Pending', which is
what the webapp does when the coordinator clicks the Approve button.

Note: Caterers.Able to Serve Schools is intentionally NOT modified. That field
tracks capability (can a caterer serve a school?), not current assignment. The
current assignment is always derived from Sessions.Caterer.

Usage:
  python scripts/actions/execute_caterer_switch.py <proposal_id> [--approve] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from support import (
    CatererFields,
    CatererSwitchProposalFields,
    Database,
    Record,
    SessionFields,
    log,
)


@dataclass(frozen=True)
class SwitchContext:
    """Resolved view of an approved Caterer Switch Proposal."""

    proposal:     Record[CatererSwitchProposalFields]
    session_id:   str
    session_name: str
    outgoing:     Record[CatererFields]
    incoming:     Record[CatererFields]

    @property
    def outgoing_name(self) -> str:
        return self.outgoing.fields.get("Caterer Name", self.outgoing.id)

    @property
    def incoming_name(self) -> str:
        return self.incoming.fields.get("Caterer Name", self.incoming.id)


def _resolve_context(
    db:          Database,
    proposal_id: str,
    approve:     bool = False,
) -> SwitchContext:
    try:
        proposal = db.CatererSwitchProposals.get(proposal_id)
    except Exception as e:
        log.error(f"Failed to fetch proposal {proposal_id}: {e}")
        sys.exit(1)
    if not proposal:
        log.error(f"Proposal {proposal_id} not found")
        sys.exit(1)

    pf = proposal.fields
    status = pf.get("Status")
    allowed = ("Pending", "Approved") if approve else ("Approved",)
    if status not in allowed:
        log.error(
            f"Proposal {proposal_id} has Status='{status}'. "
            + ("Only 'Approved' or 'Pending' proposals can be executed with --approve."
               if approve else
               "Only 'Approved' proposals can be executed. Use --approve to also accept 'Pending'.")
        )
        sys.exit(1)

    session_id          = (pf.get("Session")          or [None])[0]
    outgoing_caterer_id = (pf.get("Outgoing Caterer") or [None])[0]
    incoming_caterer_id = (pf.get("Incoming Caterer") or [None])[0]

    if not session_id or not outgoing_caterer_id or not incoming_caterer_id:
        log.error("Proposal is missing Session, Outgoing Caterer, or Incoming Caterer.")
        sys.exit(1)

    try:
        out_rec = db.Caterers.get(outgoing_caterer_id)
        in_rec  = db.Caterers.get(incoming_caterer_id)
    except Exception as e:
        log.error(f"Failed to fetch caterer records: {e}")
        sys.exit(1)

    if not out_rec or not in_rec:
        log.error("Outgoing or incoming caterer record could not be loaded.")
        sys.exit(1)

    # Fetch the session to derive school_id and build a human-readable session name.
    school_id    = session_id
    session_name = session_id
    try:
        session_rec: Record[SessionFields] | None = db.Sessions.get(session_id)
        if session_rec:
            sf        = session_rec.fields
            school_id = (sf.get("School") or [session_id])[0]
            day       = sf.get("Day") or ""
            school_name_str = school_id
            try:
                school_rec = db.Schools.get(school_id)
                if school_rec:
                    school_name_str = school_rec.fields.get("School Name", school_id)
            except Exception:
                pass
            session_name = f"{school_name_str} — {day}" if day else school_name_str
    except Exception:
        pass

    return SwitchContext(
        proposal=proposal,
        session_id=session_id,
        session_name=session_name,
        outgoing=out_rec,
        incoming=in_rec,
    )


def execute(proposal_id: str, dry_run: bool = False, approve: bool = False, db: Database | None = None) -> None:
    db = db or Database.from_env()
    ctx = _resolve_context(db, proposal_id, approve=approve)

    log.info(
        f"Executing switch: {ctx.outgoing_name} → {ctx.incoming_name} "
        f"for session {ctx.session_name}"
        + (" [DRY RUN]" if dry_run else "")
    )

    # ------------------------------------------------------------------
    # 1. Set Sessions.Incoming Caterer for the affected session
    # ------------------------------------------------------------------
    log.info(
        f"  Session {ctx.session_name} will receive "
        f"Incoming Caterer = {ctx.incoming_name}"
    )

    if not dry_run:
        db.Sessions.update(ctx.session_id, {"Incoming Caterer": [ctx.incoming.id]})

    # ------------------------------------------------------------------
    # 2. Clear Students.Meal Preference for students in this session
    # ------------------------------------------------------------------
    all_students = db.Students.all()
    affected_students = [
        stu for stu in all_students
        if ctx.session_id in (stu.fields.get("Sessions") or [])
    ]
    log.info(
        f"  Clearing Meal Preference for {len(affected_students)} student(s) "
        f"enrolled in {ctx.session_name}"
    )

    if not dry_run and affected_students:
        updates = [{"id": stu.id, "fields": {"Meal Preference": []}}
                   for stu in affected_students]
        db.Students.batch_update(updates)

    # ------------------------------------------------------------------
    # 3. Mark proposal Approved — the order run marks it Executed
    # ------------------------------------------------------------------
    log.info(f"  Marking proposal {proposal_id} as Approved")
    if not dry_run:
        db.CatererSwitchProposals.update(proposal_id, {"Status": "Approved"})

    log.info(
        f"Switch queued: {ctx.outgoing_name} → {ctx.incoming_name} "
        f"for session {ctx.session_name}. Caterer flip will take effect at the next "
        f"register_orders.py run, which will also mark this proposal Executed."
    )


def reject(proposal_id: str, notes: str = "", db: Database | None = None) -> None:
    """Mark a Caterer Switch Proposal as Rejected with optional coordinator notes."""
    db = db or Database.from_env()
    fields: dict[str, object] = {"Status": "Rejected"}
    if notes:
        fields["Notes"] = notes
    db.CatererSwitchProposals.update(proposal_id, fields)
    log.info(f"Proposal {proposal_id} marked Rejected.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from support import self_healing_error_handler, Database

    parser = argparse.ArgumentParser(description="Execute an approved caterer switch")
    parser.add_argument(
        "proposal_id",
        help="Airtable record ID of the Caterer Switch Proposals row",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would happen without writing to Airtable",
    )
    parser.add_argument(
        "--approve", action="store_true",
        help="Also accept Pending proposals (approve and execute in one step)",
    )
    args = parser.parse_args()

    # Dynamic database state provider to serialize DB context if an edge case fails
    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "caterer_switch_proposals": db.CatererSwitchProposals.all(),
                "sessions": db.Sessions.all(),
                "students": db.Students.all(),
                "caterers": db.Caterers.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("execute_caterer_switch", state_provider=db_state_provider):
        execute(args.proposal_id, dry_run=args.dry_run, approve=args.approve)
