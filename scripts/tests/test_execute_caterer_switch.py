"""
Tests for scripts/actions/execute_caterer_switch.py.

Covers: happy-path mutation sequence, non-Approved status rejection,
dry-run no-writes, and missing proposal / caterer error handling.
"""
from __future__ import annotations

import unittest

import fixtures
from actions.execute_caterer_switch import execute
from mock_db import MockDatabase
from support import Record


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

PROPOSAL_ID   = "recProp001"
OUT_CATERER_ID = fixtures.CATERER_A_ID
IN_CATERER_ID  = fixtures.CATERER_B_ID
SCHOOL_ID      = fixtures.SCHOOL_A_ID


def _approved_proposal() -> Record:
    return Record(id=PROPOSAL_ID, fields={
        "Proposal ID":      "PROP-ALPHA-2026-05-01",
        "School":           [SCHOOL_ID],
        "Outgoing Caterer": [OUT_CATERER_ID],
        "Incoming Caterer": [IN_CATERER_ID],
        "Status":           "Approved",
        "Proposed On":      "2026-05-01",
    })


def _setup_db(proposal: Record | None = None, extra_sessions: list[Record] | None = None) -> MockDatabase:
    db = MockDatabase()
    db.CatererSwitchProposals._records = [proposal or _approved_proposal()]
    db.Caterers._records = [fixtures.caterer_a(), fixtures.caterer_b()]
    db.Schools._records  = [fixtures.school_alpha()]
    db.Sessions._records = [fixtures.session_monday(), fixtures.session_wednesday()] + (extra_sessions or [])
    # Two students enrolled at school A's sessions
    db.Students._records = [
        Record(id=f"stu{i}", fields={
            "Student Name":    f"Student {i}",
            "Sessions":        [fixtures.SESSION_MON_ID],
            "Meal Preference": [fixtures.ITEM_VEG_PASTA_ID],
        })
        for i in range(3)
    ]
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExecuteCatererSwitch(unittest.TestCase):

    def test_happy_path_sets_incoming_caterer_on_sessions(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        # Both sessions at SCHOOL_A should have Incoming Caterer set
        session_update_ids = {uid for uid, _ in db.Sessions.updates}
        self.assertIn(fixtures.SESSION_MON_ID, session_update_ids)
        self.assertIn(fixtures.SESSION_WED_ID, session_update_ids)

        for _, fields in db.Sessions.updates:
            self.assertEqual(fields["Incoming Caterer"], [IN_CATERER_ID])

    def test_happy_path_updates_serves_schools(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        # Each caterer gets two update calls (Serves Schools + Able to Serve),
        # so merge all updates per caterer before asserting.
        from collections import defaultdict
        merged: dict = defaultdict(dict)
        for uid, fields in db.Caterers.updates:
            merged[uid].update(fields)

        out_merged = merged.get(OUT_CATERER_ID, {})
        self.assertIn("Serves Schools", out_merged)
        self.assertNotIn(SCHOOL_ID, out_merged["Serves Schools"])

        in_merged = merged.get(IN_CATERER_ID, {})
        self.assertIn("Serves Schools", in_merged)
        self.assertIn(SCHOOL_ID, in_merged["Serves Schools"])

    def test_happy_path_updates_able_to_serve(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        from collections import defaultdict
        merged: dict = defaultdict(dict)
        for uid, fields in db.Caterers.updates:
            merged[uid].update(fields)

        out_merged = merged.get(OUT_CATERER_ID, {})
        self.assertIn("Able to Serve Schools", out_merged)
        self.assertIn(SCHOOL_ID, out_merged["Able to Serve Schools"])

        in_merged = merged.get(IN_CATERER_ID, {})
        self.assertIn("Able to Serve Schools", in_merged)
        self.assertNotIn(SCHOOL_ID, in_merged["Able to Serve Schools"])

    def test_happy_path_clears_student_meal_preferences(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        # At least one batch_update call clearing Meal Preference
        cleared_ids = set()
        for batch in db.Students.batch_update_calls:
            for u in batch:
                if u.get("fields", {}).get("Meal Preference") == []:
                    cleared_ids.add(u["id"])

        # All 3 students enrolled at SESSION_MON_ID should be cleared
        self.assertEqual(cleared_ids, {"stu0", "stu1", "stu2"})

    def test_happy_path_marks_proposal_executed(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        proposal_updates = {uid: fields for uid, fields in db.CatererSwitchProposals.updates}
        self.assertIn(PROPOSAL_ID, proposal_updates)
        self.assertEqual(proposal_updates[PROPOSAL_ID]["Status"], "Executed")

    def test_non_approved_status_raises_system_exit(self):
        for status in ("Pending", "Rejected", "Executed"):
            with self.subTest(status=status):
                proposal = Record(id=PROPOSAL_ID, fields={
                    "School":           [SCHOOL_ID],
                    "Outgoing Caterer": [OUT_CATERER_ID],
                    "Incoming Caterer": [IN_CATERER_ID],
                    "Status":           status,
                })
                db = _setup_db(proposal=proposal)
                with self.assertRaises(SystemExit) as cm:
                    execute(PROPOSAL_ID, dry_run=False, db=db)
                self.assertEqual(cm.exception.code, 1)

    def test_missing_proposal_raises_system_exit(self):
        db = _setup_db()
        db.CatererSwitchProposals._records = []  # nothing to find
        with self.assertRaises(SystemExit) as cm:
            execute(PROPOSAL_ID, dry_run=False, db=db)
        self.assertEqual(cm.exception.code, 1)

    def test_dry_run_makes_no_writes(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=True, db=db)

        self.assertEqual(db.Sessions.updates, [])
        self.assertEqual(db.Caterers.updates, [])
        self.assertEqual(db.Students.batch_update_calls, [])
        self.assertEqual(db.CatererSwitchProposals.updates, [])

    def test_only_sessions_at_affected_school_are_updated(self):
        # Add a session at a different school — must not be touched.
        other_session = Record(id="sessOther", fields={
            "Session ID": "Beta College - Tuesday",
            "School":     [fixtures.SCHOOL_B_ID],
            "Caterer":    [OUT_CATERER_ID],
            "Day":        "Tuesday",
        })
        db = _setup_db(extra_sessions=[other_session])
        execute(PROPOSAL_ID, dry_run=False, db=db)

        updated_ids = {uid for uid, _ in db.Sessions.updates}
        self.assertNotIn("sessOther", updated_ids)
        self.assertIn(fixtures.SESSION_MON_ID, updated_ids)
        self.assertIn(fixtures.SESSION_WED_ID, updated_ids)


if __name__ == "__main__":
    unittest.main()
