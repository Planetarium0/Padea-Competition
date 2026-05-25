"""
execute_caterer_switch.py — Execute an approved caterer switch proposal.

Reads the named Caterer Switch Proposals record, verifies Status='Approved',
then:
  1. Sets Sessions.Incoming Caterer for every session at the affected school
     (the actual Caterer flip happens at the next register_orders.py run).
  2. Updates Caterers.Serves Schools (remove school from outgoing, add to incoming).
  3. Updates Caterers.Able to Serve Schools (add school to outgoing, remove from incoming).
  4. Clears Students.Meal Preference for every student enrolled at the school
     (their preferences referenced the old caterer's menu).
  5. Marks the proposal Status='Executed'.

The webapp uses Sessions.Incoming Caterer to show the new caterer's menu for
preference selection while still attributing ratings to the current caterer.
register_orders.py commits the full flip (Caterer ← Incoming Caterer) at run
time, after which Incoming Caterer is cleared.

Usage:
  python scripts/actions/execute_caterer_switch.py <proposal_id> [--dry-run]

<proposal_id> is the Airtable record ID of the Caterer Switch Proposals row
(e.g. recXXXXXXXXXXXXXX), not the human-readable Proposal ID field.
"""

import argparse
import sys

import support as s


def get_proposal(proposal_id):
    try:
        rec = s.get_table("Caterer Switch Proposals").get(proposal_id)
    except Exception as e:
        s.log.error(f"Failed to fetch proposal {proposal_id}: {e}")
        sys.exit(1)
    if not rec:
        s.log.error(f"Proposal {proposal_id} not found")
        sys.exit(1)
    return rec


def execute(proposal_id, dry_run=False):
    proposal = get_proposal(proposal_id)
    pf       = proposal["fields"]

    status = pf.get("Status")
    if status != "Approved":
        s.log.error(
            f"Proposal {proposal_id} has Status='{status}'. "
            "Only 'Approved' proposals can be executed."
        )
        sys.exit(1)

    school_id           = (pf.get("School")           or [None])[0]
    outgoing_caterer_id = (pf.get("Outgoing Caterer") or [None])[0]
    incoming_caterer_id = (pf.get("Incoming Caterer") or [None])[0]

    if not school_id or not outgoing_caterer_id or not incoming_caterer_id:
        s.log.error("Proposal is missing School, Outgoing Caterer, or Incoming Caterer.")
        sys.exit(1)

    # Resolve human-readable names for logging
    caterers_tbl = s.get_table("Caterers")
    try:
        out_rec = caterers_tbl.get(outgoing_caterer_id)
        in_rec  = caterers_tbl.get(incoming_caterer_id)
    except Exception as e:
        s.log.error(f"Failed to fetch caterer records: {e}")
        sys.exit(1)

    out_name = out_rec["fields"].get("Caterer Name", outgoing_caterer_id) if out_rec else outgoing_caterer_id
    in_name  = in_rec["fields"].get("Caterer Name", incoming_caterer_id)  if in_rec  else incoming_caterer_id

    school_name = school_id
    try:
        school_rec  = s.get_table("Schools").get(school_id)
        school_name = school_rec["fields"].get("School Name", school_id) if school_rec else school_id
    except Exception:
        pass

    s.log.info(
        f"Executing switch: {out_name} → {in_name} at {school_name}"
        + (" [DRY RUN]" if dry_run else "")
    )

    # ------------------------------------------------------------------
    # 1. Set Sessions.Incoming Caterer for all sessions at this school
    # ------------------------------------------------------------------
    all_sessions      = s.airtable_get("Sessions")
    affected_sessions = [
        r for r in all_sessions
        if school_id in (r["fields"].get("School") or [])
    ]
    s.log.info(f"  {len(affected_sessions)} session(s) will receive Incoming Caterer = {in_name}")

    if not dry_run:
        sessions_tbl = s.get_table("Sessions")
        for sess in affected_sessions:
            sessions_tbl.update(sess["id"], {"Incoming Caterer": [incoming_caterer_id]})

    # ------------------------------------------------------------------
    # 2. Update Caterers.Serves Schools
    # ------------------------------------------------------------------
    out_serves = out_rec["fields"].get("Serves Schools") or [] if out_rec else []
    in_serves  = in_rec["fields"].get("Serves Schools")  or [] if in_rec  else []

    new_out_serves = [sid for sid in out_serves if sid != school_id]
    new_in_serves  = list(set(in_serves + [school_id]))

    s.log.info(
        f"  Caterers.Serves Schools: removing {school_name} from {out_name}, "
        f"adding to {in_name}"
    )
    if not dry_run:
        caterers_tbl.update(outgoing_caterer_id, {"Serves Schools": new_out_serves})
        caterers_tbl.update(incoming_caterer_id, {"Serves Schools": new_in_serves})

    # ------------------------------------------------------------------
    # 3. Update Caterers.Able to Serve Schools
    # ------------------------------------------------------------------
    out_able = out_rec["fields"].get("Able to Serve Schools") or [] if out_rec else []
    in_able  = in_rec["fields"].get("Able to Serve Schools")  or [] if in_rec  else []

    new_out_able = list(set(out_able + [school_id]))
    new_in_able  = [sid for sid in in_able if sid != school_id]

    s.log.info(
        f"  Caterers.Able to Serve: adding {school_name} to {out_name}, "
        f"removing from {in_name}"
    )
    if not dry_run:
        caterers_tbl.update(outgoing_caterer_id, {"Able to Serve Schools": new_out_able})
        caterers_tbl.update(incoming_caterer_id,  {"Able to Serve Schools": new_in_able})

    # ------------------------------------------------------------------
    # 4. Clear Students.Meal Preference for affected students
    # ------------------------------------------------------------------
    affected_session_ids = {sess["id"] for sess in affected_sessions}
    all_students         = s.airtable_get("Students")
    affected_students    = [
        stu for stu in all_students
        if any(sid in affected_session_ids for sid in (stu["fields"].get("Sessions") or []))
    ]
    s.log.info(
        f"  Clearing Meal Preference for {len(affected_students)} student(s) "
        f"enrolled at {school_name}"
    )

    if not dry_run and affected_students:
        students_tbl = s.get_table("Students")
        updates = [{"id": stu["id"], "fields": {"Meal Preference": []}}
                   for stu in affected_students]
        for i in range(0, len(updates), 10):
            students_tbl.batch_update(updates[i:i + 10])

    # ------------------------------------------------------------------
    # 5. Mark proposal as Executed
    # ------------------------------------------------------------------
    s.log.info(f"  Marking proposal {proposal_id} as Executed")
    if not dry_run:
        s.get_table("Caterer Switch Proposals").update(proposal_id, {"Status": "Executed"})

    s.log.info(
        f"Switch executed successfully: {out_name} → {in_name} at {school_name}. "
        f"Caterer flip will take effect at the next register_orders.py run."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Execute an approved caterer switch")
    parser.add_argument("proposal_id",
                        help="Airtable record ID of the Caterer Switch Proposals row")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would happen without writing to Airtable")
    args = parser.parse_args()
    execute(args.proposal_id, dry_run=args.dry_run)
