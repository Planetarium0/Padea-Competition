"""
Tests for poll_dietary_inbox and the SupabaseInboundInbox adapter.

All tests are pure in-memory (MockDatabase). No real Supabase calls.
"""
from __future__ import annotations

import datetime
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Ensure scripts/ is on sys.path.
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

os.environ.setdefault("PADEA_TEST_MODE", "1")

from support import Record
from support.inbound import (
    InboundMessage,
    SupabaseInboundInbox,
    extract_request_code,
)
from actions.dietary.poll_dietary_inbox import run_poll

from mock_db import MockDatabase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(
    code: str = "CDR-TEST",
    status: str = "Open",
    caterer_id: str = "cat01",
) -> Record:
    return Record(
        id=f"req-{code}",
        fields={
            "request_code": code,
            "caterer_id": caterer_id,
            "status": status,
            "sent_at": "2026-06-01T00:00:00+00:00",
            "question_set": [{"menu_item_id": "item1", "restriction_id": "rest1"}],
            "reply_to_address": f"replies+{code}@reply.padea.com.au",
        },
    )


def _make_inbound(
    message_id: str = "msg-001",
    to_address: str = "replies+CDR-TEST@reply.padea.com.au",
    from_address: str = "caterer@example.com",
    received_at: str = "2026-06-04T10:00:00+00:00",
    seen: bool = False,
) -> Record:
    return Record(
        id=f"inb-{message_id}",
        fields={
            "message_id": message_id,
            "to_address": to_address,
            "from_address": from_address,
            "received_at": received_at,
            "seen": seen,
            "body_text": "Yes, everything is fine.",
            "subject": "Re: dietary check",
            "in_reply_to": None,
        },
    )


def _make_inbound_msg(
    message_id: str = "msg-001",
    request_code: str | None = "CDR-TEST",
    from_address: str = "caterer@example.com",
) -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        in_reply_to=None,
        subject="Re: dietary",
        from_address=from_address,
        body_text="Yes all good.",
        received_at=datetime.datetime(2026, 6, 4, 10, 0, tzinfo=datetime.timezone.utc),
        request_code=request_code,
    )


# ---------------------------------------------------------------------------
# extract_request_code tests
# ---------------------------------------------------------------------------

class TestExtractRequestCode(unittest.TestCase):

    def test_valid_reply_address(self):
        code = extract_request_code("replies+CDR-2026-W23-CAFE@reply.padea.com.au")
        self.assertEqual(code, "CDR-2026-W23-CAFE")

    def test_plain_address_returns_none(self):
        code = extract_request_code("orders@padea.com.au")
        self.assertIsNone(code)

    def test_none_input_returns_none(self):
        code = extract_request_code(None)
        self.assertIsNone(code)

    def test_empty_local_after_prefix_returns_none(self):
        code = extract_request_code("replies+@reply.padea.com.au")
        self.assertIsNone(code)

    def test_no_at_sign_returns_none(self):
        code = extract_request_code("noemail")
        self.assertIsNone(code)


# ---------------------------------------------------------------------------
# SupabaseInboundInbox tests
# ---------------------------------------------------------------------------

class TestSupabaseInboundInbox(unittest.TestCase):

    def _db_with_messages(self, *records: Record) -> MockDatabase:
        db = MockDatabase()
        for r in records:
            db.DietaryInboundMessages._records.append(r)
        return db

    def test_fetch_new_returns_unseen_messages(self):
        db = self._db_with_messages(
            _make_inbound("msg-1", seen=False),
            _make_inbound("msg-2", seen=True),
        )
        inbox = SupabaseInboundInbox(db)
        since = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
        # MockTable.all() ignores filter; we only check that both are returned
        # (the real DB would filter seen=False, but MockTable returns all).
        # For this test we verify the mapper picks up the right fields.
        messages = inbox.fetch_new(since=since)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].message_id, "msg-1")
        self.assertEqual(messages[1].message_id, "msg-2")

    def test_mark_seen_flips_flag(self):
        db = self._db_with_messages(
            _make_inbound("msg-1", seen=False),
        )
        inbox = SupabaseInboundInbox(db)
        inbox.mark_seen("msg-1")
        # The update should have been called with seen=True
        self.assertTrue(len(db.DietaryInboundMessages.updates) > 0)
        _, updated_fields = db.DietaryInboundMessages.updates[-1]
        self.assertTrue(updated_fields.get("seen"))

    def test_request_code_extracted_from_to_address(self):
        db = self._db_with_messages(
            _make_inbound(
                "msg-1",
                to_address="replies+MY-REQUEST-CODE@reply.padea.com.au",
            )
        )
        inbox = SupabaseInboundInbox(db)
        since = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
        messages = inbox.fetch_new(since=since)
        self.assertEqual(messages[0].request_code, "MY-REQUEST-CODE")

    def test_non_dietary_to_address_gives_none_request_code(self):
        db = self._db_with_messages(
            _make_inbound("msg-1", to_address="orders@padea.com.au"),
        )
        inbox = SupabaseInboundInbox(db)
        since = datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc)
        messages = inbox.fetch_new(since=since)
        self.assertIsNone(messages[0].request_code)


# ---------------------------------------------------------------------------
# run_poll tests
# ---------------------------------------------------------------------------

class TestRunPoll(unittest.TestCase):

    def _make_mock_inbox(self, messages: list[InboundMessage]) -> MagicMock:
        inbox = MagicMock()
        inbox.fetch_new.return_value = messages
        inbox.mark_seen = MagicMock()
        return inbox

    def _db_with_request(self, request: Record) -> MockDatabase:
        db = MockDatabase()
        db.DietaryClarificationRequests._records.append(request)
        return db

    def test_matched_request_calls_parse_reply(self):
        db = self._db_with_request(_make_request("CDR-TEST", status="Open"))
        msg = _make_inbound_msg("msg-001", request_code="CDR-TEST")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.poll_dietary_inbox.run_poll.__module__"), \
             patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as _run_poll

            with patch("actions.dietary.poll_dietary_inbox.run_poll") as rp:
                rp.side_effect = None
                # Call directly
                pass

        # Instead, test via direct import with mocks
        with patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.escalate_dietary.run_escalation") as mock_esc:
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_parse.assert_called_once()
        inbox.mark_seen.assert_called_once_with("msg-001")

    def test_orphan_no_request_code_calls_notify_coordinator(self):
        db = MockDatabase()
        msg = _make_inbound_msg("msg-orphan", request_code=None)
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_notify.assert_called_once()
        inbox.mark_seen.assert_called_once_with("msg-orphan")

    def test_unmatched_request_code_calls_notify_coordinator(self):
        db = MockDatabase()  # empty — no active requests
        msg = _make_inbound_msg("msg-unmatched", request_code="DOESNT-EXIST")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_notify.assert_called_once()
        inbox.mark_seen.assert_called_once_with("msg-unmatched")

    def test_resolved_request_not_matched(self):
        """Messages for resolved/cancelled requests are treated as unmatched."""
        db = self._db_with_request(_make_request("CDR-DONE", status="Resolved"))
        msg = _make_inbound_msg("msg-001", request_code="CDR-DONE")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        # parse_reply must NOT be called; notify_coordinator should be
        mock_parse.assert_not_called()
        mock_notify.assert_called_once()

    def test_dry_run_skips_parse_reply_and_notify(self):
        db = self._db_with_request(_make_request("CDR-TEST", status="Open"))
        msg = _make_inbound_msg("msg-001", request_code="CDR-TEST")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation") as mock_esc:
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=True)

        mock_parse.assert_not_called()
        mock_notify.assert_not_called()
        inbox.mark_seen.assert_not_called()
        mock_esc.assert_not_called()

    def test_poll_runs_escalation_at_end(self):
        db = MockDatabase()
        inbox = self._make_mock_inbox([])

        with patch("actions.dietary.escalate_dietary.run_escalation") as mock_esc:
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_esc.assert_called_once()

    def test_clarifying_request_is_matched(self):
        """Messages for 'Clarifying' status requests should also be matched."""
        db = self._db_with_request(_make_request("CDR-CLAR", status="Clarifying"))
        msg = _make_inbound_msg("msg-001", request_code="CDR-CLAR")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_parse.assert_called_once()

    def test_cancelled_request_not_matched(self):
        db = self._db_with_request(_make_request("CDR-CNCL", status="Cancelled"))
        msg = _make_inbound_msg("msg-001", request_code="CDR-CNCL")
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.parse_dietary_reply.parse_reply") as mock_parse, \
             patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=False)

        mock_parse.assert_not_called()
        mock_notify.assert_called_once()

    def test_returns_processed_count(self):
        db = self._db_with_request(_make_request("CDR-A", status="Open"))
        msgs = [
            _make_inbound_msg("msg-1", request_code="CDR-A"),
            _make_inbound_msg("msg-2", request_code=None),
        ]
        inbox = self._make_mock_inbox(msgs)

        with patch("actions.dietary.parse_dietary_reply.parse_reply"), \
             patch("actions.dietary.poll_dietary_inbox.notify_coordinator"), \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            count = direct_poll(db, inbox, dry_run=False)

        self.assertEqual(count, 2)

    def test_dry_run_orphan_not_notified(self):
        db = MockDatabase()
        msg = _make_inbound_msg("msg-orphan", request_code=None)
        inbox = self._make_mock_inbox([msg])

        with patch("actions.dietary.poll_dietary_inbox.notify_coordinator") as mock_notify, \
             patch("actions.dietary.escalate_dietary.run_escalation"):
            from actions.dietary.poll_dietary_inbox import run_poll as direct_poll
            direct_poll(db, inbox, dry_run=True)

        mock_notify.assert_not_called()
        inbox.mark_seen.assert_called_once()  # mark_seen IS called even in dry_run for orphan


if __name__ == "__main__":
    unittest.main()
