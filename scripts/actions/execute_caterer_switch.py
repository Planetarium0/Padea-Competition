"""
execute_caterer_switch.py — Execute an approved caterer switch proposal.

Reads the named Caterer Switch Proposals record, verifies Status='Approved',
then:
  1. Sets Sessions.Incoming Caterer for the affected session
     (the actual Caterer flip happens at the next register_orders.py run).
  2. Updates Caterers.Able to Serve Schools (add school to outgoing, remove from incoming).
  3. Clears Students.Meal Preference for every student enrolled in that session
     (their preferences referenced the old caterer's menu).
  4. Marks the proposal Status='Executed'.

Note: there is no separate "Serves Schools" field. The current caterer for a
session is always derived from Sessions.Caterer, which is the single source of truth.

Usage:
  python scripts/actions/execute_caterer_switch.py <proposal_id> [--dry-run]
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
    school_id:    str
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
    if status != "Approved":
        log.error(
            f"Proposal {proposal_id} has Status='{status}'. "
            "Only 'Approved' proposals can be executed."
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
        school_id=school_id,
        outgoing=out_rec,
        incoming=in_rec,
    )


def execute(proposal_id: str, dry_run: bool = False, db: Database | None = None) -> None:
    db = db or Database.from_env()
    ctx = _resolve_context(db, proposal_id)

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
    # 2. Update Caterers.Able to Serve Schools (still school-scoped)
    # ------------------------------------------------------------------
    out_able = ctx.outgoing.fields.get("Able to Serve Schools") or []
    in_able  = ctx.incoming.fields.get("Able to Serve Schools") or []
    new_out_able = list(set(out_able + [ctx.school_id]))
    new_in_able  = [sid for sid in in_able if sid != ctx.school_id]

    log.info(
        f"  Caterers.Able to Serve: adding school to "
        f"{ctx.outgoing_name}, removing from {ctx.incoming_name}"
    )
    if not dry_run:
        db.Caterers.update(ctx.outgoing.id, {"Able to Serve Schools": new_out_able})
        db.Caterers.update(ctx.incoming.id, {"Able to Serve Schools": new_in_able})

    # ------------------------------------------------------------------
    # 3. Clear Students.Meal Preference for students in this session
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
    # 4. Mark proposal as Executed
    # ------------------------------------------------------------------
    log.info(f"  Marking proposal {proposal_id} as Executed")
    if not dry_run:
        db.CatererSwitchProposals.update(proposal_id, {"Status": "Executed"})

    log.info(
        f"Switch executed successfully: {ctx.outgoing_name} → {ctx.incoming_name} "
        f"for session {ctx.session_name}. Caterer flip will take effect at the next "
        f"register_orders.py run."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute an approved caterer switch")
    parser.add_argument(
        "proposal_id",
        help="Airtable record ID of the Caterer Switch Proposals row",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would happen without writing to Airtable",
    )
    args = parser.parse_args()
    execute(args.proposal_id, dry_run=args.dry_run)
