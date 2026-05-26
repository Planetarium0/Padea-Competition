"""Tests for scripts/actions/api.py — switch-proposal API handlers."""
from __future__ import annotations

import unittest

import fixtures
from actions.api import api_approve_proposal, api_get_proposal, api_reject_proposal
from mock_db import MockDatabase
from support import Record

PROPOSAL_ID = "recProp001"
OUT_ID      = fixtures.CATERER_A_ID
IN_ID       = fixtures.CATERER_B_ID


def _pending_proposal() -> Record:
    return Record(id=PROPOSAL_ID, fields={
        "Status":           "Pending",
        "Session":          [fixtures.SESSION_MON_ID],
        "Outgoing Caterer": [OUT_ID],
        "Incoming Caterer": [IN_ID],
        "Avg Rating":       3.4,
        "Sessions Sampled": 5,
        "Unique Raters":    8,
        "Effective Week":   "2026-05-26",
        "Notes":            "",
    })


def _approved_proposal() -> Record:
    return Record(id=PROPOSAL_ID, fields={
        "Status":           "Approved",
        "Session":          [fixtures.SESSION_MON_ID],
        "Outgoing Caterer": [OUT_ID],
        "Incoming Caterer": [IN_ID],
    })


def _base_db(proposal: Record | None = None) -> MockDatabase:
    db = MockDatabase()
    db.CatererSwitchProposals._records = [proposal or _pending_proposal()]
    db.Caterers._records = [fixtures.caterer_a(), fixtures.caterer_b()]
    db.Schools._records  = [fixtures.school_alpha()]
    db.Sessions._records = [fixtures.session_monday()]
    db.Students._records = fixtures.make_students(3)
    return db


# ---------------------------------------------------------------------------
# GET /api/proposal/<id>
# ---------------------------------------------------------------------------

class TestApiGetProposal(unittest.TestCase):

    def test_returns_display_data(self):
        status, body = api_get_proposal(PROPOSAL_ID, _base_db())
        self.assertEqual(status, 200)
        self.assertEqual(body["status"],       "Pending")
        self.assertEqual(body["outgoingName"], "Café Deluxe")
        self.assertEqual(body["incomingName"], "Fresh Eats")
        self.assertIn("Alpha Academy", body["sessionName"])
        self.assertIn("Monday",        body["sessionName"])
        self.assertEqual(body["avgRating"],       3.4)
        self.assertEqual(body["sessionsSampled"], 5)
        self.assertEqual(body["uniqueRaters"],    8)
        self.assertEqual(body["effectiveWeek"],   "2026-05-26")

    def test_missing_proposal_returns_404(self):
        db = MockDatabase()
        db.CatererSwitchProposals._records = []
        status, body = api_get_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_notes_included_when_present(self):
        db = _base_db(Record(id=PROPOSAL_ID, fields={
            "Status":           "Pending",
            "Session":          [fixtures.SESSION_MON_ID],
            "Outgoing Caterer": [OUT_ID],
            "Incoming Caterer": [IN_ID],
            "Notes":            "Caterer has been underperforming",
        }))
        status, body = api_get_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 200)
        self.assertEqual(body["notes"], "Caterer has been underperforming")

    def test_missing_session_returns_dash(self):
        db = _base_db(Record(id=PROPOSAL_ID, fields={
            "Status":           "Pending",
            "Outgoing Caterer": [OUT_ID],
            "Incoming Caterer": [IN_ID],
        }))
        status, body = api_get_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 200)
        self.assertEqual(body["sessionName"], "—")


# ---------------------------------------------------------------------------
# POST /api/proposal/<id>/approve
# ---------------------------------------------------------------------------

class TestApiApproveProposal(unittest.TestCase):

    def test_approve_executes_switch(self):
        db = _base_db(_approved_proposal())
        status, body = api_approve_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_approve_marks_proposal_executed(self):
        db = _base_db(_approved_proposal())
        api_approve_proposal(PROPOSAL_ID, db)
        updates = {uid: f for uid, f in db.CatererSwitchProposals.updates}
        self.assertEqual(updates[PROPOSAL_ID]["Status"], "Executed")

    def test_approve_updates_session(self):
        db = _base_db(_approved_proposal())
        api_approve_proposal(PROPOSAL_ID, db)
        updated_ids = {uid for uid, _ in db.Sessions.updates}
        self.assertIn(fixtures.SESSION_MON_ID, updated_ids)

    def test_pending_proposal_returns_422(self):
        db = _base_db(_pending_proposal())
        status, body = api_approve_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 422)
        self.assertIn("error", body)

    def test_missing_proposal_returns_422(self):
        db = MockDatabase()
        db.CatererSwitchProposals._records = []
        status, body = api_approve_proposal(PROPOSAL_ID, db)
        self.assertEqual(status, 422)
        self.assertIn("error", body)


# ---------------------------------------------------------------------------
# POST /api/proposal/<id>/reject
# ---------------------------------------------------------------------------

class TestApiRejectProposal(unittest.TestCase):

    def test_reject_marks_rejected(self):
        db = _base_db()
        status, body = api_reject_proposal(PROPOSAL_ID, notes="", db=db)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        updates = {uid: f for uid, f in db.CatererSwitchProposals.updates}
        self.assertEqual(updates[PROPOSAL_ID]["Status"], "Rejected")

    def test_reject_saves_notes(self):
        db = _base_db()
        api_reject_proposal(PROPOSAL_ID, notes="Too expensive", db=db)
        updates = {uid: f for uid, f in db.CatererSwitchProposals.updates}
        self.assertEqual(updates[PROPOSAL_ID]["Notes"], "Too expensive")

    def test_reject_omits_notes_field_when_empty(self):
        db = _base_db()
        api_reject_proposal(PROPOSAL_ID, notes="", db=db)
        updates = {uid: f for uid, f in db.CatererSwitchProposals.updates}
        self.assertNotIn("Notes", updates[PROPOSAL_ID])


if __name__ == "__main__":
    unittest.main()
