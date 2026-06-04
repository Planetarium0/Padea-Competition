"""
Tests for scripts/actions/escalate_dietary.py.

Covers: _is_overdue (7-day boundary), run_escalation (status transitions,
dedupe on already-Escalated, skips Resolved/Cancelled, correct notify call).
"""
from __future__ import annotations

import datetime
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fixtures
from actions.dietary.escalate_dietary import ESCALATION_DAYS, _is_overdue, run_escalation
from mock_db import MockDatabase
from support import Record


# ---------------------------------------------------------------------------
# _is_overdue
# ---------------------------------------------------------------------------

_REF = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)


class TestIsOverdue(unittest.TestCase):

    def test_exactly_at_boundary_is_overdue(self):
        sent = (_REF - datetime.timedelta(days=ESCALATION_DAYS)).isoformat()
        self.assertTrue(_is_overdue(sent, _REF))

    def test_one_second_past_boundary(self):
        sent = (_REF - datetime.timedelta(days=ESCALATION_DAYS, seconds=1)).isoformat()
        self.assertTrue(_is_overdue(sent, _REF))

    def test_just_under_boundary_not_overdue(self):
        sent = (_REF - datetime.timedelta(days=ESCALATION_DAYS - 1)).isoformat()
        self.assertFalse(_is_overdue(sent, _REF))

    def test_same_day_not_overdue(self):
        sent = _REF.isoformat()
        self.assertFalse(_is_overdue(sent, _REF))

    def test_z_suffix_handled(self):
        sent = (_REF - datetime.timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(_is_overdue(sent, _REF))

    def test_unparseable_string_not_overdue(self):
        self.assertFalse(_is_overdue("not-a-date", _REF))

    def test_naive_datetime_string_treated_as_utc(self):
        naive = (_REF - datetime.timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%S")
        self.assertTrue(_is_overdue(naive, _REF))


# ---------------------------------------------------------------------------
# run_escalation
# ---------------------------------------------------------------------------

def _open_request(
    req_id: str,
    sent_at: datetime.datetime,
    caterer_id: str = fixtures.CATERER_A_ID,
    school_id: str | None = fixtures.SCHOOL_A_ID,
    question_set: list | None = None,
) -> Record:
    return Record(id=req_id, fields={
        "request_code": f"CDR-{req_id}",
        "caterer_id": caterer_id,
        "school_id": school_id,
        "sent_at": sent_at.isoformat(),
        "status": "Open",
        "question_set": question_set or [{"menu_item_id": "i1", "restriction_id": "r1"}],
    })


def _make_db(requests: list[Record]) -> MockDatabase:
    db = MockDatabase()
    db.DietaryClarificationRequests._records = list(requests)
    db.Caterers._records = [fixtures.caterer_a()]
    db.Schools._records = [fixtures.school_alpha()]
    return db


class TestRunEscalation(unittest.TestCase):

    def setUp(self):
        # Patch notify_coordinator so we don't touch the filesystem or send email
        self._patcher = patch(
            "actions.dietary.escalate_dietary.notify_coordinator",
            return_value=Path("/tmp/fake_artifact.md"),
        )
        self.mock_notify = self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_escalates_overdue_open_request(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=8)
        req = _open_request("req-001", sent)
        db = _make_db([req])

        count = run_escalation(db, reference_date=ref)

        self.assertEqual(count, 1)
        # Status should be updated to Escalated
        self.assertEqual(len(db.DietaryClarificationRequests.updates), 1)
        _, update_fields = db.DietaryClarificationRequests.updates[0]
        self.assertEqual(update_fields["status"], "Escalated")
        # notify_coordinator called once
        self.mock_notify.assert_called_once()
        call_kwargs = self.mock_notify.call_args
        self.assertEqual(call_kwargs.args[0], "req-001")

    def test_does_not_escalate_recent_open_request(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=3)
        req = _open_request("req-002", sent)
        db = _make_db([req])

        count = run_escalation(db, reference_date=ref)

        self.assertEqual(count, 0)
        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)
        self.mock_notify.assert_not_called()

    def test_does_not_re_escalate_already_escalated(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=10)
        # Already Escalated — should not appear in Open query
        req = Record(id="req-003", fields={
            "request_code": "CDR-req-003",
            "caterer_id": fixtures.CATERER_A_ID,
            "school_id": fixtures.SCHOOL_A_ID,
            "sent_at": sent.isoformat(),
            "status": "Escalated",
            "question_set": [],
        })
        db = _make_db([req])

        count = run_escalation(db, reference_date=ref)

        self.assertEqual(count, 0)
        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)
        self.mock_notify.assert_not_called()

    def test_does_not_escalate_resolved_request(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=10)
        req = Record(id="req-004", fields={
            "request_code": "CDR-req-004",
            "caterer_id": fixtures.CATERER_A_ID,
            "school_id": fixtures.SCHOOL_A_ID,
            "sent_at": sent.isoformat(),
            "status": "Resolved",
            "question_set": [],
        })
        db = _make_db([req])

        count = run_escalation(db, reference_date=ref)

        self.assertEqual(count, 0)
        self.mock_notify.assert_not_called()

    def test_mixed_requests_only_overdue_open_escalated(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        overdue = _open_request("req-overdue", ref - datetime.timedelta(days=9))
        recent = _open_request("req-recent", ref - datetime.timedelta(days=2))
        already_esc = Record(id="req-esc", fields={
            "request_code": "CDR-req-esc",
            "caterer_id": fixtures.CATERER_A_ID,
            "school_id": fixtures.SCHOOL_A_ID,
            "sent_at": (ref - datetime.timedelta(days=12)).isoformat(),
            "status": "Escalated",
            "question_set": [],
        })
        db = _make_db([overdue, recent, already_esc])

        count = run_escalation(db, reference_date=ref)

        self.assertEqual(count, 1)
        updated_ids = [upd[0] for upd in db.DietaryClarificationRequests.updates]
        self.assertIn("req-overdue", updated_ids)
        self.assertNotIn("req-recent", updated_ids)
        self.assertNotIn("req-esc", updated_ids)

    def test_dry_run_does_not_write(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=8)
        req = _open_request("req-dry", sent)
        db = _make_db([req])

        count = run_escalation(db, reference_date=ref, dry_run=True)

        self.assertEqual(count, 1)
        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)
        self.mock_notify.assert_not_called()

    def test_notify_called_with_correct_args(self):
        ref = datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.timezone.utc)
        sent = ref - datetime.timedelta(days=8)
        req = _open_request(
            "req-check", sent,
            question_set=[{"menu_item_id": "i1", "restriction_id": "r1"},
                          {"menu_item_id": "i2", "restriction_id": "r1"}],
        )
        db = _make_db([req])

        run_escalation(db, reference_date=ref)

        self.mock_notify.assert_called_once_with(
            "req-check",
            caterer_name=fixtures.caterer_a().fields["name"],
            school_name=fixtures.school_alpha().fields["name"],
            num_open_questions=2,
            sent_at_str=sent.isoformat(),
        )

    def test_empty_requests_returns_zero(self):
        db = _make_db([])
        count = run_escalation(db)
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
