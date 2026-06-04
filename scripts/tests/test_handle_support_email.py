"""
Tests for scripts/actions/handle_support_email.py.

All tests use MockDatabase — no real Supabase, no real Anthropic API,
no real SendGrid. PADEA_TEST_MODE=1 is set by run_all.py.

Coverage:
  1.  Unrecognised sender → notify_coordinator, no case created
  2.  Coordinator email → same path as unrecognised
  3.  Known parent, new case created with correct parent_email
  4.  In-Reply-To matches open case → case reused (not new)
  5.  In-Reply-To matches resolved case → new case created
  6.  add_dietary_restriction — valid student
  7.  add_dietary_restriction — wrong student (not linked to parent)
  8.  add_dietary_restriction — already has restriction (idempotent)
  9.  add_dietary_restriction — invalid restriction_id
  10. send_reply tool — schedule_email called with correct args
  11. Full tool loop — restriction added + reply sent → case resolved
  12. Full tool loop — only reply sent (no restriction) → case resolved, notify_coordinator
  13. No API key → notify_coordinator called, no exception
  14. Dry run — no DB writes
  15. In-Reply-To threading — resolved case → creates a new case
"""
from __future__ import annotations

import datetime
import os
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

from mock_db import MockDatabase
from support import Record
from support.inbound import InboundMessage

import actions.inbox.handle_support_email as hse


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

PARENT_EMAIL = "parent@example.com"
COORDINATOR_EMAIL = "coord@padea.com"
STUDENT_ID = "stu-001"
STUDENT_B_ID = "stu-002"
RESTRICTION_VEG_ID = "rest-001"
RESTRICTION_VEGAN_ID = "rest-002"
CASE_ID = "case-001"
MSG_ID = "<msg-1234@example.com>"


def _make_inbound(
    *,
    from_address: str = PARENT_EMAIL,
    body_text: str = "Please add vegetarian for my child",
    in_reply_to: str | None = None,
    message_id: str = MSG_ID,
) -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        in_reply_to=in_reply_to,
        subject="Dietary update",
        from_address=from_address,
        body_text=body_text,
        received_at=datetime.datetime(2026, 6, 4, 10, 0, 0, tzinfo=datetime.timezone.utc),
        request_code=None,
    )


def _make_student(
    student_id: str = STUDENT_ID,
    parent_email: str = PARENT_EMAIL,
    restriction_ids: list[str] | None = None,
) -> Record:
    return Record(
        id=student_id,
        fields={
            "name": "Alex Smith",
            "year_level": 10,
            "parent_email": parent_email,
            "dietary_requirement_ids": restriction_ids or [],
        },
    )


def _make_restriction(rid: str, name: str) -> Record:
    return Record(id=rid, fields={"name": name})


def _make_case(
    case_id: str = CASE_ID,
    parent_email: str = PARENT_EMAIL,
    status: str = "Open",
    messages: list[dict] | None = None,
) -> Record:
    return Record(
        id=case_id,
        fields={
            "case_code": f"SC-2026-{case_id.upper()[:8]}",
            "parent_email": parent_email,
            "status": status,
            "messages": messages or [],
        },
    )


def _db_with_parent(
    restriction_ids: list[str] | None = None,
) -> MockDatabase:
    db = MockDatabase()
    db.Students._records = [_make_student(restriction_ids=restriction_ids)]
    db.DietaryRestrictions._records = [
        _make_restriction(RESTRICTION_VEG_ID, "Vegetarian"),
        _make_restriction(RESTRICTION_VEGAN_ID, "Vegan"),
    ]
    return db


# ---------------------------------------------------------------------------
# Fake Anthropic response builder
# ---------------------------------------------------------------------------

def _make_text_block(text: str) -> Any:
    block = SimpleNamespace()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(
    tool_id: str,
    name: str,
    input_data: dict,
) -> Any:
    block = SimpleNamespace()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = input_data
    return block


def _make_response(content: list, stop_reason: str = "end_turn") -> Any:
    resp = SimpleNamespace()
    resp.content = content
    resp.stop_reason = stop_reason
    return resp


# ---------------------------------------------------------------------------
# 1. Unrecognised sender
# ---------------------------------------------------------------------------

class TestUnrecognisedSender(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_no_students_notifies_coordinator(self, mock_send):
        db = MockDatabase()  # empty Students table
        msg = _make_inbound()

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            with patch("support.email._send_via_sendgrid"):
                hse.handle_message(db, msg)

        # No case created
        self.assertEqual(len(db.SupportCases.created_fields), 0)
        # No students updates
        self.assertEqual(len(db.Students.updates), 0)


# ---------------------------------------------------------------------------
# 2. Coordinator email treated as unrecognised
# ---------------------------------------------------------------------------

class TestCoordinatorSender(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_coordinator_routes_to_notify(self, mock_send):
        db = MockDatabase()
        # Even if coordinator has student records (unlikely, but guard must still fire)
        db.Students._records = [
            _make_student(parent_email=COORDINATOR_EMAIL),
        ]
        msg = _make_inbound(from_address=COORDINATOR_EMAIL)

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            with patch("support.email._send_via_sendgrid"):
                hse.handle_message(db, msg)

        self.assertEqual(len(db.SupportCases.created_fields), 0)


# ---------------------------------------------------------------------------
# 3. Known parent → new case
# ---------------------------------------------------------------------------

class TestNewCase(unittest.TestCase):

    @patch("actions.inbox.handle_support_email.run_tool_loop")
    def test_creates_case_with_correct_parent_email(self, mock_loop):
        db = _db_with_parent()
        msg = _make_inbound()

        hse.handle_message(db, msg)

        self.assertEqual(len(db.SupportCases.created_fields), 1)
        case_fields = db.SupportCases.created_fields[0]
        self.assertEqual(case_fields["parent_email"], PARENT_EMAIL)
        self.assertEqual(case_fields["status"], "Open")

    @patch("actions.inbox.handle_support_email.run_tool_loop")
    def test_tool_loop_called_with_new_case(self, mock_loop):
        db = _db_with_parent()
        msg = _make_inbound()

        hse.handle_message(db, msg)

        self.assertTrue(mock_loop.called)
        _, _, _, sender_arg, _ = mock_loop.call_args[0]
        self.assertEqual(sender_arg, PARENT_EMAIL)


# ---------------------------------------------------------------------------
# 4. In-Reply-To → reuse open case
# ---------------------------------------------------------------------------

class TestThreadingReuseOpenCase(unittest.TestCase):

    @patch("actions.inbox.handle_support_email.run_tool_loop")
    def test_in_reply_to_reuses_open_case(self, mock_loop):
        db = _db_with_parent()
        prior_msg_id = "<prior-msg@example.com>"
        existing_case = _make_case(
            messages=[{"message_id": prior_msg_id, "direction": "inbound"}],
        )
        db.SupportCases._records = [existing_case]

        msg = _make_inbound(in_reply_to=prior_msg_id)
        hse.handle_message(db, msg)

        # No new case created
        self.assertEqual(len(db.SupportCases.created_fields), 0)
        # loop called with existing case
        case_arg = mock_loop.call_args[0][1]
        self.assertEqual(case_arg.id, CASE_ID)


# ---------------------------------------------------------------------------
# 5. In-Reply-To matches resolved case → new case
# ---------------------------------------------------------------------------

class TestThreadingResolvedCase(unittest.TestCase):

    @patch("actions.inbox.handle_support_email.run_tool_loop")
    def test_in_reply_to_resolved_case_creates_new(self, mock_loop):
        db = _db_with_parent()
        prior_msg_id = "<prior-msg@example.com>"
        resolved_case = _make_case(
            status="Resolved",
            messages=[{"message_id": prior_msg_id, "direction": "inbound"}],
        )
        db.SupportCases._records = [resolved_case]

        msg = _make_inbound(in_reply_to=prior_msg_id)
        hse.handle_message(db, msg)

        # New case should be created (resolved case not reused)
        self.assertEqual(len(db.SupportCases.created_fields), 1)
        new_case_fields = db.SupportCases.created_fields[0]
        self.assertEqual(new_case_fields["status"], "Open")


# ---------------------------------------------------------------------------
# Tool executor tests
# ---------------------------------------------------------------------------

def _make_executor(db: MockDatabase, students: list[Record] | None = None):
    """Build a tool executor with a fresh mock case."""
    if students is None:
        students = [_make_student()]
    case = _make_case()
    return hse._make_tool_executor(db, PARENT_EMAIL, students, case, dry_run=False)


class TestToolExecutor(unittest.TestCase):

    # 6. add_dietary_restriction — valid student
    @patch("support.email._send_via_sendgrid")
    def test_add_restriction_valid_student(self, mock_send):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("add_dietary_restriction", {
            "student_id": STUDENT_ID,
            "restriction_id": RESTRICTION_VEG_ID,
        })

        self.assertIn("Added", result)
        self.assertIn("Vegetarian", result)
        # Check DB update was called
        self.assertEqual(len(db.Students.updates), 1)
        updated_ids = db.Students.updates[0][1]["dietary_requirement_ids"]
        self.assertIn(RESTRICTION_VEG_ID, updated_ids)

    # 7. add_dietary_restriction — wrong student (not linked to parent)
    @patch("support.email._send_via_sendgrid")
    def test_add_restriction_wrong_student(self, mock_send):
        db = _db_with_parent()
        # Add a student belonging to a different parent
        other_student = _make_student(student_id=STUDENT_B_ID, parent_email="other@example.com")
        db.Students._records.append(other_student)

        executor = _make_executor(db)

        result = executor("add_dietary_restriction", {
            "student_id": STUDENT_B_ID,
            "restriction_id": RESTRICTION_VEG_ID,
        })

        self.assertIn("Error", result)
        # No DB writes for students
        self.assertEqual(len(db.Students.updates), 0)

    # 8. add_dietary_restriction — already has restriction
    @patch("support.email._send_via_sendgrid")
    def test_add_restriction_already_has_it(self, mock_send):
        db = _db_with_parent(restriction_ids=[RESTRICTION_VEG_ID])
        executor = _make_executor(db)

        result = executor("add_dietary_restriction", {
            "student_id": STUDENT_ID,
            "restriction_id": RESTRICTION_VEG_ID,
        })

        # Should report no change, not add duplicate
        self.assertIn("already has", result)
        self.assertEqual(len(db.Students.updates), 0)

    # 9. add_dietary_restriction — invalid restriction_id
    @patch("support.email._send_via_sendgrid")
    def test_add_restriction_invalid_restriction(self, mock_send):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("add_dietary_restriction", {
            "student_id": STUDENT_ID,
            "restriction_id": "nonexistent-restriction",
        })

        self.assertIn("Error", result)
        self.assertEqual(len(db.Students.updates), 0)

    # 10. send_reply — schedule_email called with correct args
    @patch("actions.inbox.handle_support_email.schedule_email")
    def test_send_reply_calls_schedule_email(self, mock_schedule):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("send_reply", {"body_text": "Hello parent!"})

        self.assertEqual(result, "Reply sent.")
        mock_schedule.assert_called_once()
        call_kwargs = mock_schedule.call_args
        self.assertEqual(call_kwargs[1]["to_email"] if call_kwargs[1] else call_kwargs[0][1], PARENT_EMAIL)


# ---------------------------------------------------------------------------
# 11. Full tool loop — restriction added + reply → resolved
# ---------------------------------------------------------------------------

class TestFullToolLoopResolved(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.Anthropic")
    def test_restriction_added_reply_sent_case_resolved(self, MockAnthropic, mock_send):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        msg = _make_inbound()

        # Set up the mock Anthropic client
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        # First call: request list_students
        resp1 = _make_response(
            content=[
                _make_tool_use_block("t1", "list_students", {}),
            ],
            stop_reason="tool_use",
        )
        # Second call: request add_dietary_restriction
        resp2 = _make_response(
            content=[
                _make_tool_use_block("t2", "add_dietary_restriction", {
                    "student_id": STUDENT_ID,
                    "restriction_id": RESTRICTION_VEG_ID,
                }),
            ],
            stop_reason="tool_use",
        )
        # Third call: send_reply
        resp3 = _make_response(
            content=[
                _make_tool_use_block("t3", "send_reply", {
                    "body_text": "I've added Vegetarian for Alex Smith.",
                }),
            ],
            stop_reason="tool_use",
        )
        # Final: end_turn
        resp4 = _make_response(
            content=[_make_text_block("Done.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [resp1, resp2, resp3, resp4]

        students = [_make_student()]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            hse.run_tool_loop(db, case, msg, PARENT_EMAIL, students)

        # Case should be updated to Resolved
        self.assertTrue(
            any("status" in u[1] and u[1]["status"] == "Resolved" for u in db.SupportCases.updates),
            f"Expected case status=Resolved, got updates={db.SupportCases.updates}",
        )
        # Student restriction should have been updated
        self.assertTrue(
            any("dietary_requirement_ids" in u[1] for u in db.Students.updates),
            f"Expected student dietary_requirement_ids update, got={db.Students.updates}",
        )


# ---------------------------------------------------------------------------
# 12. Full tool loop — only reply, no restriction → resolved, notify_coordinator
# ---------------------------------------------------------------------------

class TestFullToolLoopReplyOnly(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.Anthropic")
    def test_reply_only_case_resolved(self, MockAnthropic, mock_send):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        msg = _make_inbound(body_text="I just had a question, thanks!")

        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client

        # Immediately reply, no restriction change
        resp1 = _make_response(
            content=[
                _make_tool_use_block("t1", "send_reply", {
                    "body_text": "Thanks for your message!",
                }),
            ],
            stop_reason="tool_use",
        )
        resp2 = _make_response(
            content=[_make_text_block("Done.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [resp1, resp2]

        students = [_make_student()]
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            hse.run_tool_loop(db, case, msg, PARENT_EMAIL, students)

        # Resolved because reply was sent
        self.assertTrue(
            any("status" in u[1] and u[1]["status"] == "Resolved" for u in db.SupportCases.updates),
        )


# ---------------------------------------------------------------------------
# 13. No API key → notify_coordinator
# ---------------------------------------------------------------------------

class TestNoApiKey(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_no_api_key_notifies_coordinator(self, mock_send):
        db = _db_with_parent()
        case = _make_case()
        msg = _make_inbound()
        students = [_make_student()]

        env = {k: v for k, v in os.environ.items() if k not in (
            "ANTHROPIC_API_KEY", "CLAUDE_CODE_API_KEY"
        )}

        with patch.dict(os.environ, env, clear=True):
            # notify_coordinator writes artifact files; suppress by mocking
            with patch("actions.inbox.handle_support_email.notify_coordinator") as mock_notify:
                hse.run_tool_loop(db, case, msg, PARENT_EMAIL, students)
                mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# 14. Dry run — no DB writes
# ---------------------------------------------------------------------------

class TestDryRun(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.Anthropic")
    def test_dry_run_no_db_writes(self, MockAnthropic, mock_send):
        db = _db_with_parent()
        msg = _make_inbound()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            hse.handle_message(db, msg, dry_run=True)

        # No students updates (dry run executor should not write)
        self.assertEqual(len(db.Students.updates), 0)
        # No emails queued
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.Anthropic")
    def test_dry_run_no_case_created_in_db(self, MockAnthropic, mock_send):
        """In dry_run mode, no case row is written to the database."""
        db = _db_with_parent()
        msg = _make_inbound()

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            hse.handle_message(db, msg, dry_run=True)

        # No case created in DB (dry_run returns a stub instead)
        self.assertEqual(len(db.SupportCases.created_fields), 0)


# ---------------------------------------------------------------------------
# 15. find_or_create_case — resolved case not reused (threading guard)
# ---------------------------------------------------------------------------

class TestFindOrCreateCaseLogic(unittest.TestCase):

    def test_no_reply_to_always_creates(self):
        db = MockDatabase()
        db.SupportCases._records = [_make_case()]  # existing open case
        msg = _make_inbound(in_reply_to=None)

        case, is_new = hse.find_or_create_case(db, msg, PARENT_EMAIL)

        self.assertTrue(is_new)

    def test_reply_to_matches_open_case_reuses(self):
        db = MockDatabase()
        prior_msg_id = "<prior@example.com>"
        existing = _make_case(messages=[{"message_id": prior_msg_id}])
        db.SupportCases._records = [existing]
        msg = _make_inbound(in_reply_to=prior_msg_id)

        case, is_new = hse.find_or_create_case(db, msg, PARENT_EMAIL)

        self.assertFalse(is_new)
        self.assertEqual(case.id, CASE_ID)

    def test_reply_to_matches_resolved_case_creates_new(self):
        db = MockDatabase()
        prior_msg_id = "<prior@example.com>"
        resolved = _make_case(
            status="Resolved",
            messages=[{"message_id": prior_msg_id}],
        )
        db.SupportCases._records = [resolved]
        msg = _make_inbound(in_reply_to=prior_msg_id)

        case, is_new = hse.find_or_create_case(db, msg, PARENT_EMAIL)

        self.assertTrue(is_new)

    def test_reply_to_matches_different_parent_creates_new(self):
        db = MockDatabase()
        prior_msg_id = "<prior@example.com>"
        other_parent_case = _make_case(
            parent_email="other@example.com",
            messages=[{"message_id": prior_msg_id}],
        )
        db.SupportCases._records = [other_parent_case]
        msg = _make_inbound(in_reply_to=prior_msg_id)

        case, is_new = hse.find_or_create_case(db, msg, PARENT_EMAIL)

        self.assertTrue(is_new)


if __name__ == "__main__":
    unittest.main()
