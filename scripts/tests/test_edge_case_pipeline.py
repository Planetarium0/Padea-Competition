"""Tests for the edge case plan pipeline.

Covers:
- Plan I/O helpers (save, load, update, find_by_message_id)
- register_edge_case in dry-run mode
- _try_process_plan_approval: APPROVE, APPROVE with comments, REJECT, no-match, already-processed
- _classify_system_requirement: requirement vs personal request
- handle_message routing for plan approval replies and unknown-sender classification
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# Set test mode before any support imports so email sending is blocked.
os.environ["PADEA_TEST_MODE"] = "1"

from mock_db import MockDatabase
from support.inbound import InboundMessage


def _make_inbound(
    body: str,
    from_address: str = "test@example.com",
    subject: str | None = None,
    in_reply_to: str | None = None,
    message_id: str | None = None,
) -> InboundMessage:
    return InboundMessage(
        message_id=message_id or "<msg-001@example.com>",
        in_reply_to=in_reply_to,
        subject=subject,
        from_address=from_address,
        body_text=body,
        received_at=datetime.datetime(2026, 6, 6, 12, 0, 0, tzinfo=datetime.timezone.utc),
        request_code=None,
    )


# ---------------------------------------------------------------------------
# Plan I/O helpers
# ---------------------------------------------------------------------------

class TestPlanIO(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._plans_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _patch_plans_dir(self):
        import actions.system.register_edge_case as rce
        return mock.patch.object(rce, "_PLANS_DIR", self._plans_dir)

    def test_save_and_load_roundtrip(self) -> None:
        import actions.system.register_edge_case as rce
        plan = {
            "id": "plan_20260606_120000_test",
            "status": "pending",
            "title": "Test plan",
            "notification_message_id": "<plan-plan_20260606_120000_test@padea.com.au>",
        }
        with self._patch_plans_dir():
            rce.save_plan(plan)
            loaded = rce.load_plan(plan["id"])
        self.assertEqual(loaded["title"], "Test plan")

    def test_update_plan(self) -> None:
        import actions.system.register_edge_case as rce
        plan = {"id": "plan_20260606_120001_upd", "status": "pending", "title": "Upd"}
        with self._patch_plans_dir():
            rce.save_plan(plan)
            updated = rce.update_plan(plan["id"], {"status": "approved"})
        self.assertEqual(updated["status"], "approved")

    def test_find_plan_by_message_id_match(self) -> None:
        import actions.system.register_edge_case as rce
        msg_id = "<plan-plan_20260606_120002_find@padea.com.au>"
        plan = {
            "id": "plan_20260606_120002_find",
            "status": "pending",
            "notification_message_id": msg_id,
        }
        with self._patch_plans_dir():
            rce.save_plan(plan)
            found = rce.find_plan_by_message_id(msg_id)
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], plan["id"])  # type: ignore[index]

    def test_find_plan_by_message_id_no_match(self) -> None:
        import actions.system.register_edge_case as rce
        with self._patch_plans_dir():
            found = rce.find_plan_by_message_id("<no-such-id@padea.com.au>")
        self.assertIsNone(found)

    def test_slug(self) -> None:
        import actions.system.register_edge_case as rce
        self.assertEqual(rce._slug("Day-specific Menu (Tuesday)"), "day_specific_menu_tuesday")
        self.assertLessEqual(len(rce._slug("x" * 100)), 40)


# ---------------------------------------------------------------------------
# register_edge_case (dry-run, no real LLM / email)
# ---------------------------------------------------------------------------

class TestRegisterEdgeCase(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._plans_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _patch(self):
        import actions.system.register_edge_case as rce
        return [
            mock.patch.object(rce, "_PLANS_DIR", self._plans_dir),
            mock.patch.object(rce, "ask_llm", return_value=json.dumps({
                "title": "Test Edge Case",
                "plan_markdown": "## Summary\nTest plan body",
            })),
            mock.patch.object(rce, "_send_via_sendgrid"),
        ]

    def test_register_creates_plan_file(self) -> None:
        import actions.system.register_edge_case as rce
        patches = self._patch()
        for p in patches:
            p.start()
        try:
            plan = rce.register_edge_case("Caterer menu differs by day", source="manual", dry_run=True)
        finally:
            for p in patches:
                p.stop()

        self.assertEqual(plan["status"], "pending")
        self.assertEqual(plan["source"], "manual")
        self.assertTrue(plan["id"].startswith("plan_"))
        plan_file = self._plans_dir / f"{plan['id']}.json"
        self.assertTrue(plan_file.exists(), "Plan JSON not written to disk")

    def test_notification_message_id_format(self) -> None:
        import actions.system.register_edge_case as rce
        plan_id = "plan_20260606_120000_test"
        with mock.patch.dict(os.environ, {"APP_DOMAIN": "padea.com.au"}):
            msg_id = rce._notification_message_id(plan_id)
        self.assertEqual(msg_id, f"<plan-{plan_id}@padea.com.au>")

    def test_no_email_sent_in_dry_run(self) -> None:
        import actions.system.register_edge_case as rce
        patches = self._patch()
        mocks = [p.start() for p in patches]
        try:
            rce.register_edge_case("test", dry_run=True)
            send_mock = mocks[2]
            send_mock.assert_not_called()
        finally:
            for p in patches:
                p.stop()


# ---------------------------------------------------------------------------
# _try_process_plan_approval
# ---------------------------------------------------------------------------

class TestTryProcessPlanApproval(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._plans_dir = Path(self._tmp.name)

        import actions.system.register_edge_case as rce
        self._rce = rce
        self._plans_dir_patch = mock.patch.object(rce, "_PLANS_DIR", self._plans_dir)
        self._plans_dir_patch.start()

        # Seed a pending plan
        self._msg_id = "<plan-plan_20260606_120003_reply@padea.com.au>"
        self._plan_id = "plan_20260606_120003_reply"
        plan: dict[str, Any] = {
            "id": self._plan_id,
            "status": "pending",
            "title": "Reply Test",
            "description": "test",
            "notification_message_id": self._msg_id,
        }
        rce.save_plan(plan)

    def tearDown(self) -> None:
        self._plans_dir_patch.stop()
        self._tmp.cleanup()

    def _call(self, body: str, in_reply_to: str | None = None) -> bool:
        from actions.inbox.handle_support_email import _try_process_plan_approval
        msg = _make_inbound(body, in_reply_to=in_reply_to or self._msg_id)
        with mock.patch(
            "actions.inbox.handle_support_email._spawn_implementation"
        ) as spawn_mock:
            result = _try_process_plan_approval(msg, dry_run=False)
            self._spawn_mock = spawn_mock
        return result

    def test_approve_updates_status(self) -> None:
        result = self._call("APPROVE")
        self.assertTrue(result)
        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "approved")
        self.assertIsNone(plan["approval_comments"])
        self._spawn_mock.assert_called_once_with(self._plan_id)

    def test_approve_with_comments(self) -> None:
        result = self._call("APPROVE: please handle edge case for Tuesday too")
        self.assertTrue(result)
        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "approved")
        self.assertEqual(plan["approval_comments"], "please handle edge case for Tuesday too")

    def test_reject_updates_status(self) -> None:
        result = self._call("REJECT: not needed right now")
        self.assertTrue(result)
        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "rejected")
        self.assertEqual(plan["rejection_reason"], "not needed right now")

    def test_no_match_returns_false(self) -> None:
        result = self._call("APPROVE", in_reply_to="<unrelated@example.com>")
        self.assertFalse(result)

    def test_no_in_reply_to_returns_false(self) -> None:
        from actions.inbox.handle_support_email import _try_process_plan_approval
        msg = _make_inbound("APPROVE", in_reply_to=None)
        result = _try_process_plan_approval(msg, dry_run=False)
        self.assertFalse(result)

    def test_already_processed_returns_true_no_update(self) -> None:
        # Approve once
        self._call("APPROVE")
        # Attempt again — plan is now 'approved', should short-circuit
        from actions.inbox.handle_support_email import _try_process_plan_approval
        msg = _make_inbound("REJECT: change of mind", in_reply_to=self._msg_id)
        result = _try_process_plan_approval(msg, dry_run=False)
        self.assertTrue(result)
        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "approved")  # not changed to rejected

    def test_unrecognised_keyword_returns_false(self) -> None:
        from actions.inbox.handle_support_email import _try_process_plan_approval
        msg = _make_inbound("MAYBE later", in_reply_to=self._msg_id)
        result = _try_process_plan_approval(msg, dry_run=False)
        self.assertFalse(result)

    def test_dry_run_does_not_update(self) -> None:
        from actions.inbox.handle_support_email import _try_process_plan_approval
        msg = _make_inbound("APPROVE", in_reply_to=self._msg_id)
        with mock.patch(
            "actions.inbox.handle_support_email._spawn_implementation"
        ) as spawn_mock:
            _try_process_plan_approval(msg, dry_run=True)
        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "pending")
        spawn_mock.assert_not_called()


# ---------------------------------------------------------------------------
# _classify_system_requirement
# ---------------------------------------------------------------------------

class TestClassifySystemRequirement(unittest.TestCase):

    def _call(self, body: str, llm_response: str) -> tuple[bool, str]:
        from actions.inbox.handle_support_email import _classify_system_requirement
        msg = _make_inbound(body)
        with mock.patch("actions.inbox.handle_support_email.ask_llm", return_value=llm_response):
            return _classify_system_requirement(msg)

    def test_system_requirement_detected(self) -> None:
        llm_json = json.dumps({
            "is_system_requirement": True,
            "summary": "Caterer has different Tuesday and Wednesday menus",
        })
        is_req, summary = self._call("Our Tuesday menu is different to Wednesday.", llm_json)
        self.assertTrue(is_req)
        self.assertIn("Tuesday", summary)

    def test_personal_request_not_classified_as_requirement(self) -> None:
        llm_json = json.dumps({
            "is_system_requirement": False,
            "summary": "",
        })
        is_req, _ = self._call("Please update my son's dietary restrictions.", llm_json)
        self.assertFalse(is_req)

    def test_empty_body_short_circuits(self) -> None:
        from actions.inbox.handle_support_email import _classify_system_requirement
        msg = _make_inbound("")
        with mock.patch("actions.inbox.handle_support_email.ask_llm") as llm_mock:
            is_req, _ = _classify_system_requirement(msg)
        llm_mock.assert_not_called()
        self.assertFalse(is_req)

    def test_llm_failure_returns_false(self) -> None:
        is_req, summary = self._call("Something", None)  # type: ignore[arg-type]
        self.assertFalse(is_req)
        self.assertEqual(summary, "")


# ---------------------------------------------------------------------------
# handle_message routing for plan approval
# ---------------------------------------------------------------------------

class TestHandleMessagePlanApproval(unittest.TestCase):
    """Verify that handle_message routes coordinator replies to _try_process_plan_approval."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._plans_dir = Path(self._tmp.name)

        import actions.system.register_edge_case as rce
        self._rce = rce
        self._plans_dir_patch = mock.patch.object(rce, "_PLANS_DIR", self._plans_dir)
        self._plans_dir_patch.start()

        msg_id = "<plan-plan_20260606_120010_route@padea.com.au>"
        self._plan_id = "plan_20260606_120010_route"
        plan: dict[str, Any] = {
            "id": self._plan_id,
            "status": "pending",
            "title": "Route test",
            "description": "test routing",
            "notification_message_id": msg_id,
        }
        rce.save_plan(plan)
        self._msg_id = msg_id

    def tearDown(self) -> None:
        self._plans_dir_patch.stop()
        self._tmp.cleanup()

    def test_coordinator_approve_reply_routed(self) -> None:
        from actions.inbox.handle_support_email import handle_message

        db = MockDatabase()
        msg = _make_inbound(
            "APPROVE",
            from_address="coordinator@padea.com.au",
            in_reply_to=self._msg_id,
        )

        with mock.patch.dict(os.environ, {"COORDINATOR_EMAIL": "coordinator@padea.com.au"}), \
             mock.patch("actions.inbox.handle_support_email._try_process_approval", return_value=False), \
             mock.patch("actions.inbox.handle_support_email._spawn_implementation") as spawn_mock:
            handle_message(db, msg, dry_run=False)

        plan = self._rce.load_plan(self._plan_id)
        self.assertEqual(plan["status"], "approved")
        spawn_mock.assert_called_once_with(self._plan_id)


if __name__ == "__main__":
    unittest.main()
