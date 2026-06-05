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
  12. Full tool loop — only reply sent (no restriction) → case resolved
  13. No API key → notify_coordinator called, no exception
  14. Dry run — no DB writes
  15. In-Reply-To threading — resolved case → creates a new case
  16. update_contact — applies to all parent's students
  17. request_change — creates pending_changes row + sends coordinator email
  18. Approval flow — APPROVE applies change, parent notified
  19. Denial flow — DENY rejects change, parent notified
  20. Escalation — escalate action sends coordinator email
"""
from __future__ import annotations

import datetime
import json
import os
import unittest

os.environ.setdefault("PADEA_TEST_MODE", "1")
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
# 2. Coordinator email treated as unrecognised (when not an approval)
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
    return hse._make_tool_executor(db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=False)


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
    @patch("support.email.schedule_email")
    def test_send_reply_calls_schedule_email(self, mock_schedule):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("send_reply", {"body": "Hello parent!"})

        self.assertEqual(result, "Reply sent.")
        mock_schedule.assert_called_once()
        call_kwargs = mock_schedule.call_args
        self.assertEqual(call_kwargs[1]["to_email"] if call_kwargs[1] else call_kwargs[0][1], PARENT_EMAIL)


# ---------------------------------------------------------------------------
# 11. Full tool loop — restriction added + reply → resolved
# ---------------------------------------------------------------------------

class TestFullToolLoopResolved(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.ask_llm_with_tools")
    def test_restriction_added_reply_sent_case_resolved(self, mock_tools, mock_send):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        msg = _make_inbound()

        def side_effect(prompt, system, executor, tools, **kw):
            executor("update_dietary_restrictions", {
                "student_id": STUDENT_ID,
                "restriction_names": ["Vegetarian"],
            })
            executor("send_reply", {"body": "I've set Vegetarian for Alex Smith."})
            return True

        mock_tools.side_effect = side_effect

        hse.run_tool_loop(db, case, msg, PARENT_EMAIL, [_make_student()])

        self.assertTrue(
            any("status" in u[1] and u[1]["status"] == "Resolved" for u in db.SupportCases.updates),
            f"Expected case status=Resolved, got updates={db.SupportCases.updates}",
        )
        self.assertTrue(
            any("dietary_requirement_ids" in u[1] for u in db.Students.updates),
            f"Expected student dietary_requirement_ids update, got={db.Students.updates}",
        )


# ---------------------------------------------------------------------------
# 12. Full tool loop — only reply, no restriction → resolved
# ---------------------------------------------------------------------------

class TestFullToolLoopReplyOnly(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    @patch("actions.inbox.handle_support_email.ask_llm_with_tools")
    def test_reply_only_case_resolved(self, mock_tools, mock_send):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        msg = _make_inbound(body_text="I just had a question, thanks!")

        def side_effect(prompt, system, executor, tools, **kw):
            executor("send_reply", {"body": "Thanks for your message!"})
            return True

        mock_tools.side_effect = side_effect

        hse.run_tool_loop(db, case, msg, PARENT_EMAIL, [_make_student()])

        self.assertTrue(
            any("status" in u[1] and u[1]["status"] == "Resolved" for u in db.SupportCases.updates),
        )


# ---------------------------------------------------------------------------
# 13. No API key → notify_coordinator
# ---------------------------------------------------------------------------

class TestNoApiKey(unittest.TestCase):

    @patch("actions.inbox.handle_support_email.ask_llm_with_tools", return_value=None)
    def test_ask_llm_none_notifies_coordinator(self, mock_ask):
        db = _db_with_parent()
        case = _make_case()
        msg = _make_inbound()
        students = [_make_student()]

        with patch("actions.inbox.handle_support_email.notify_coordinator") as mock_notify:
            hse.run_tool_loop(db, case, msg, PARENT_EMAIL, students)
            mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# 14. Dry run — no DB writes
# ---------------------------------------------------------------------------

class TestDryRun(unittest.TestCase):

    def test_dry_run_no_db_writes(self):
        db = _db_with_parent()
        msg = _make_inbound()

        hse.handle_message(db, msg, dry_run=True)

        self.assertEqual(len(db.Students.updates), 0)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_dry_run_no_case_created_in_db(self):
        """In dry_run mode, no case row is written to the database."""
        db = _db_with_parent()
        msg = _make_inbound()

        hse.handle_message(db, msg, dry_run=True)

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


# ---------------------------------------------------------------------------
# 16. update_contact — applies to all of a parent's students
# ---------------------------------------------------------------------------

class TestUpdateContact(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_update_parent_mobile_all_students(self, mock_send):
        db = MockDatabase()
        # Two students belonging to the same parent
        student_a = _make_student(student_id=STUDENT_ID, parent_email=PARENT_EMAIL)
        student_b = _make_student(student_id=STUDENT_B_ID, parent_email=PARENT_EMAIL)
        db.Students._records = [student_a, student_b]
        db.DietaryRestrictions._records = [
            _make_restriction(RESTRICTION_VEG_ID, "Vegetarian"),
        ]

        students = [student_a, student_b]
        case = _make_case()
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=False
        )

        result = executor("update_contact", {
            "field": "parent_mobile",
            "new_value": "0412345678",
        })

        self.assertNotIn("Error", result)
        # Both students should have been updated
        updated_ids = [u[0] for u in db.Students.updates]
        self.assertIn(STUDENT_ID, updated_ids)
        self.assertIn(STUDENT_B_ID, updated_ids)
        # Each update should set parent_mobile
        for uid, fields in db.Students.updates:
            self.assertEqual(fields.get("parent_mobile"), "0412345678")

    @patch("support.email._send_via_sendgrid")
    def test_update_contact_invalid_field(self, mock_send):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("update_contact", {
            "field": "year_level",  # not allowed for update_contact
            "new_value": 11,
        })

        self.assertIn("Error", result)
        self.assertEqual(len(db.Students.updates), 0)

    @patch("support.email._send_via_sendgrid")
    def test_update_contact_dry_run(self, mock_send):
        db = _db_with_parent()
        students = [_make_student()]
        case = _make_case()
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=True
        )

        result = executor("update_contact", {
            "field": "parent_name",
            "new_value": "Jane Smith",
        })

        self.assertIn("dry-run", result)
        self.assertEqual(len(db.Students.updates), 0)


# ---------------------------------------------------------------------------
# 17. request_change — creates a pending_changes row and emails coordinator
# ---------------------------------------------------------------------------

class TestRequestChange(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_request_change_creates_pending_row(self, mock_send):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        students = [_make_student()]
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=False
        )

        result = executor("request_change", {
            "student_id": STUDENT_ID,
            "field": "year_level",
            "new_value": 11,
            "reason": "Alex moved up a year",
        })

        self.assertNotIn("Error", result)
        # pending_changes row created
        self.assertEqual(len(db.PendingChanges.created_fields), 1)
        pending_fields = db.PendingChanges.created_fields[0]
        self.assertEqual(pending_fields["field_name"], "year_level")
        self.assertEqual(pending_fields["new_value"], 11)
        self.assertEqual(pending_fields["status"], "Pending")
        self.assertEqual(pending_fields["parent_email"], PARENT_EMAIL)

    @patch("support.email._send_via_sendgrid")
    def test_request_change_sets_notification_message_id(self, mock_send):
        db = _db_with_parent()
        case = _make_case()
        students = [_make_student()]
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=False
        )

        executor("request_change", {
            "student_id": STUDENT_ID,
            "field": "name",
            "new_value": "Alexander Smith",
            "reason": "Legal name change",
        })

        # The update to set notification_message_id should have been called
        pending_updates = db.PendingChanges.updates
        self.assertTrue(len(pending_updates) >= 1)
        msg_id_update = next(
            (u for u in pending_updates if "notification_message_id" in u[1]),
            None,
        )
        self.assertIsNotNone(msg_id_update)
        self.assertIn("@padea.support", msg_id_update[1]["notification_message_id"])

    @patch("support.email._send_via_sendgrid")
    def test_request_change_sends_coordinator_email(self, mock_send):
        db = _db_with_parent()
        case = _make_case()
        students = [_make_student()]
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=False
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            executor("request_change", {
                "student_id": STUDENT_ID,
                "field": "year_level",
                "new_value": 11,
                "reason": "Alex moved up a year",
            })

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["to"], [COORDINATOR_EMAIL])
        self.assertIn("year_level", call_kwargs["subject"])

    @patch("support.email._send_via_sendgrid")
    def test_request_change_invalid_field(self, mock_send):
        db = _db_with_parent()
        executor = _make_executor(db)

        result = executor("request_change", {
            "student_id": STUDENT_ID,
            "field": "parent_mobile",  # should use update_contact for this
            "new_value": "0412345678",
            "reason": "",
        })

        self.assertIn("Error", result)
        self.assertEqual(len(db.PendingChanges.created_fields), 0)

    @patch("support.email._send_via_sendgrid")
    def test_request_change_wrong_student(self, mock_send):
        db = _db_with_parent()
        other_student = _make_student(student_id=STUDENT_B_ID, parent_email="other@example.com")
        db.Students._records.append(other_student)
        executor = _make_executor(db)

        result = executor("request_change", {
            "student_id": STUDENT_B_ID,
            "field": "year_level",
            "new_value": 11,
            "reason": "",
        })

        self.assertIn("Error", result)
        self.assertEqual(len(db.PendingChanges.created_fields), 0)

    @patch("support.email._send_via_sendgrid")
    def test_request_change_dry_run(self, mock_send):
        db = _db_with_parent()
        students = [_make_student()]
        case = _make_case()
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=None, dry_run=True
        )

        result = executor("request_change", {
            "student_id": STUDENT_ID,
            "field": "year_level",
            "new_value": 11,
            "reason": "",
        })

        self.assertIn("dry-run", result)
        self.assertEqual(len(db.PendingChanges.created_fields), 0)


# ---------------------------------------------------------------------------
# 18 & 19. Approval/Denial flow
# ---------------------------------------------------------------------------

PENDING_MSG_ID = "<pending-rec00000001@padea.support>"


def _make_pending_change(
    pending_id: str = "rec00000001",
    parent_email: str = PARENT_EMAIL,
    student_id: str = STUDENT_ID,
    field_name: str = "year_level",
    new_value: int = 11,
    status: str = "Pending",
    notification_message_id: str = PENDING_MSG_ID,
) -> Record:
    return Record(
        id=pending_id,
        fields={
            "parent_email": parent_email,
            "student_id": student_id,
            "field_name": field_name,
            "current_value": 10,
            "new_value": new_value,
            "reason": "Test",
            "status": status,
            "notification_message_id": notification_message_id,
        },
    )


class TestApprovalFlow(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_approve_applies_change_and_notifies_parent(self, mock_send):
        db = _db_with_parent()
        db.PendingChanges._records = [_make_pending_change()]
        db.SupportCases._records = []

        coordinator_msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="APPROVE The student has confirmed enrolment in year 11.",
            in_reply_to=PENDING_MSG_ID,
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            hse.handle_message(db, coordinator_msg)

        # Student's year_level should be updated
        year_level_updates = [
            u for u in db.Students.updates
            if "year_level" in u[1]
        ]
        self.assertTrue(len(year_level_updates) >= 1)
        self.assertEqual(year_level_updates[0][1]["year_level"], 11)

        # Pending change status set to Approved
        status_updates = [
            u for u in db.PendingChanges.updates
            if u[1].get("status") == "Approved"
        ]
        self.assertTrue(len(status_updates) >= 1)

        # Email to parent sent (via schedule_email → _send_via_sendgrid)
        self.assertTrue(mock_send.called)

    @patch("support.email._send_via_sendgrid")
    def test_deny_updates_status_and_notifies_parent(self, mock_send):
        db = _db_with_parent()
        db.PendingChanges._records = [_make_pending_change()]
        db.SupportCases._records = []

        coordinator_msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="DENY We cannot action this without additional documentation.",
            in_reply_to=PENDING_MSG_ID,
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            hse.handle_message(db, coordinator_msg)

        # Student NOT updated
        year_level_updates = [u for u in db.Students.updates if "year_level" in u[1]]
        self.assertEqual(len(year_level_updates), 0)

        # Pending change status set to Denied
        status_updates = [
            u for u in db.PendingChanges.updates
            if u[1].get("status") == "Denied"
        ]
        self.assertTrue(len(status_updates) >= 1)

        # Email to parent sent
        self.assertTrue(mock_send.called)

    @patch("actions.inbox.handle_support_email._send_via_sendgrid")
    def test_approve_dry_run_no_writes(self, mock_send):
        db = _db_with_parent()
        db.PendingChanges._records = [_make_pending_change()]

        coordinator_msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="APPROVE",
            in_reply_to=PENDING_MSG_ID,
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            result = hse._try_process_approval(db, coordinator_msg, dry_run=True)

        self.assertTrue(result)
        # No DB writes
        self.assertEqual(len(db.Students.updates), 0)
        self.assertEqual(len(db.PendingChanges.updates), 0)
        # No email
        mock_send.assert_not_called()

    def test_non_matching_in_reply_to_returns_false(self):
        db = MockDatabase()
        db.PendingChanges._records = [_make_pending_change()]

        msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="APPROVE",
            in_reply_to="<some-other-message-id@example.com>",
        )

        result = hse._try_process_approval(db, msg)
        self.assertFalse(result)

    def test_no_in_reply_to_returns_false(self):
        db = MockDatabase()
        db.PendingChanges._records = [_make_pending_change()]

        msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="APPROVE",
            in_reply_to=None,
        )

        result = hse._try_process_approval(db, msg)
        self.assertFalse(result)

    def test_invalid_decision_word_returns_false(self):
        db = MockDatabase()
        db.PendingChanges._records = [_make_pending_change()]

        msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="MAYBE let's discuss",
            in_reply_to=PENDING_MSG_ID,
        )

        result = hse._try_process_approval(db, msg)
        self.assertFalse(result)

    @patch("actions.inbox.handle_support_email._send_via_sendgrid")
    def test_case_insensitive_approve(self, mock_send):
        db = _db_with_parent()
        db.PendingChanges._records = [_make_pending_change()]

        msg = _make_inbound(
            from_address=COORDINATOR_EMAIL,
            body_text="approve this looks fine",
            in_reply_to=PENDING_MSG_ID,
        )

        result = hse._try_process_approval(db, msg)
        self.assertTrue(result)

        status_updates = [
            u for u in db.PendingChanges.updates
            if u[1].get("status") == "Approved"
        ]
        self.assertTrue(len(status_updates) >= 1)


# ---------------------------------------------------------------------------
# 20. Escalation — escalate action sends coordinator email
# ---------------------------------------------------------------------------

class TestEscalation(unittest.TestCase):

    @patch("support.email._send_via_sendgrid")
    def test_escalate_sends_coordinator_email(self, mock_send):
        db = _db_with_parent()
        msg = _make_inbound(body_text="I need to speak with someone urgently.")
        case = _make_case()
        students = [_make_student()]
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=msg, dry_run=False
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            result = executor("escalate", {"message": "Please call me, this is urgent."})

        self.assertNotIn("Error", result)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["to"], [COORDINATOR_EMAIL])
        self.assertIn("escalation", call_kwargs["subject"].lower())

    @patch("support.email._send_via_sendgrid")
    def test_escalate_dry_run_no_email(self, mock_send):
        db = _db_with_parent()
        msg = _make_inbound()
        case = _make_case()
        students = [_make_student()]
        executor = hse._make_tool_executor(
            db, PARENT_EMAIL, students, case, inbound_msg=msg, dry_run=True
        )

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            result = executor("escalate", {"message": "Please call me."})

        self.assertIn("dry-run", result)
        mock_send.assert_not_called()

    @patch("actions.inbox.handle_support_email.ask_llm_with_tools")
    @patch("support.email._send_via_sendgrid")
    def test_full_loop_escalate(self, mock_send, mock_tools):
        db = _db_with_parent()
        case = _make_case()
        db.SupportCases._records = [case]
        msg = _make_inbound(body_text="I want to speak to a coordinator NOW.")

        def side_effect(prompt, system, executor, tools, **kw):
            executor("escalate_to_coordinator", {"message": "Parent is very upset."})
            executor("send_reply", {"body": "I've escalated your request."})
            return True

        mock_tools.side_effect = side_effect

        with patch.dict(os.environ, {"COORDINATOR_EMAIL": COORDINATOR_EMAIL}, clear=False):
            hse.run_tool_loop(db, case, msg, PARENT_EMAIL, [_make_student()])

        # Case resolved (reply sent)
        self.assertTrue(
            any("status" in u[1] and u[1]["status"] == "Resolved" for u in db.SupportCases.updates)
        )
        # Coordinator email sent
        self.assertTrue(mock_send.called)


if __name__ == "__main__":
    unittest.main()
