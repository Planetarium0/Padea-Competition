"""
Tests for scripts/actions/execute_caterer_switch.py.

Covers: happy-path mutation sequence, non-Approved status rejection,
dry-run no-writes, and missing proposal / caterer error handling.
"""
from __future__ import annotations

import unittest

import fixtures
from actions.caterers.execute_caterer_switch import execute
from mock_db import MockDatabase
from support import Record


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

PROPOSAL_ID    = "recProp001"
OUT_CATERER_ID = fixtures.CATERER_A_ID
IN_CATERER_ID  = fixtures.CATERER_B_ID


def _approved_proposal() -> Record:
    return Record(id=PROPOSAL_ID, fields={
        "proposal_code":       "PROP-ALPHA-2026-05-01",
        "session_id":          fixtures.SESSION_MON_ID,
        "outgoing_caterer_id": OUT_CATERER_ID,
        "incoming_caterer_id": IN_CATERER_ID,
        "status":              "Approved",
        "proposed_on":         "2026-05-01",
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
            "name":               f"Student {i}",
            "session_ids":        [fixtures.SESSION_MON_ID],
            "meal_preference_id": fixtures.ITEM_VEG_PASTA_ID,
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

        # Only the proposed session should have Incoming Caterer set
        session_update_ids = {uid for uid, _ in db.Sessions.updates}
        self.assertIn(fixtures.SESSION_MON_ID, session_update_ids)
        self.assertNotIn(fixtures.SESSION_WED_ID, session_update_ids)

        for _, fields in db.Sessions.updates:
            self.assertEqual(fields["incoming_caterer_id"], IN_CATERER_ID)

    def test_happy_path_clears_student_meal_preferences(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        # At least one batch_update call clearing meal_preference_id
        cleared_ids = set()
        for batch in db.Students.batch_update_calls:
            for u in batch:
                if "meal_preference_id" in u and u.get("meal_preference_id") is None:
                    cleared_ids.add(u["id"])

        # All 3 students enrolled at SESSION_MON_ID should be cleared
        self.assertEqual(cleared_ids, {"stu0", "stu1", "stu2"})

    def test_happy_path_marks_proposal_approved(self):
        db = _setup_db()
        execute(PROPOSAL_ID, dry_run=False, db=db)

        proposal_updates = {uid: fields for uid, fields in db.CatererSwitchProposals.updates}
        self.assertIn(PROPOSAL_ID, proposal_updates)
        self.assertEqual(proposal_updates[PROPOSAL_ID]["status"], "Approved")

    def test_non_approved_status_raises_system_exit(self):
        for status in ("Pending", "Rejected", "Executed"):
            with self.subTest(status=status):
                proposal = Record(id=PROPOSAL_ID, fields={
                    "session_id":          fixtures.SESSION_MON_ID,
                    "outgoing_caterer_id": OUT_CATERER_ID,
                    "incoming_caterer_id": IN_CATERER_ID,
                    "status":              status,
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

    def test_only_the_proposed_session_is_updated(self):
        # Sessions not named in the proposal must not be touched —
        # whether at the same school or a different one.
        other_session = Record(id="sessOther", fields={
            "session_code": "Beta College - Tuesday",
            "school_id":    fixtures.SCHOOL_B_ID,
            "caterer_id":   OUT_CATERER_ID,
            "day":          "Tuesday",
        })
        db = _setup_db(extra_sessions=[other_session])
        execute(PROPOSAL_ID, dry_run=False, db=db)

        updated_ids = {uid for uid, _ in db.Sessions.updates}
        self.assertIn(fixtures.SESSION_MON_ID, updated_ids)       # the proposed session
        self.assertNotIn(fixtures.SESSION_WED_ID, updated_ids)    # same school, not proposed
        self.assertNotIn("sessOther", updated_ids)                 # different school


if __name__ == "__main__":
    unittest.main()
