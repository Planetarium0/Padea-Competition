"""Tests for scripts/support/email.py — schedule_email dev redirect and escalate_to_dev."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support.email as email_module
import support.error_handler as eh_module
from support.email import escalate_to_dev, schedule_email
from support.error_handler import LoggedFailureBatch, self_healing_error_handler
from mock_db import MockDatabase


class TestScheduleEmailDevRedirect(unittest.TestCase):
    """APP_ENV=development redirects sends to DEV_NOTIFICATION_EMAIL."""

    def setUp(self) -> None:
        self._send_patch = mock.patch("support.email.resend.Emails.send")
        self.mock_send = self._send_patch.start()

    def tearDown(self) -> None:
        self._send_patch.stop()

    def _call(self, to_email: str = "caterer@example.com", cc_email: list[str] | None = None) -> None:
        schedule_email(
            MockDatabase(),
            to_email=to_email,
            cc_email=cc_email,
            subject="Test subject",
            body="Test body",
            email_id="EMAIL-TEST-001",
        )

    def test_dev_mode_redirects_to_to_dev_recipient(self) -> None:
        with mock.patch.dict(os.environ, {
            "APP_ENV": "development",
            "DEV_NOTIFICATION_EMAIL": "dev@example.com",
            "RESEND_API_KEY": "key",
        }):
            self._call(to_email="caterer@real.com")
        sent = self.mock_send.call_args[0][0]
        self.assertEqual(sent["to"], ["dev@example.com"])

    def test_dev_mode_drops_cc(self) -> None:
        with mock.patch.dict(os.environ, {
            "APP_ENV": "development",
            "DEV_NOTIFICATION_EMAIL": "dev@example.com",
            "RESEND_API_KEY": "key",
        }):
            self._call(cc_email=["chef@real.com", "manager@real.com"])
        sent = self.mock_send.call_args[0][0]
        self.assertNotIn("cc", sent)

    def test_dev_mode_audit_record_keeps_original_to_address(self) -> None:
        db = MockDatabase()
        with mock.patch.dict(os.environ, {
            "APP_ENV": "development",
            "DEV_NOTIFICATION_EMAIL": "dev@example.com",
            "RESEND_API_KEY": "key",
        }):
            schedule_email(db, to_email="caterer@real.com", cc_email=None,
                           subject="S", body="B", email_id="E-001")
        self.assertEqual(db.ScheduledEmails.created_fields[0]["to_address"], "caterer@real.com")

    def test_dev_mode_no_dev_recipient_skips_send(self) -> None:
        env = {"APP_ENV": "development", "RESEND_API_KEY": "key"}
        env.pop("DEV_NOTIFICATION_EMAIL", None)
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("DEV_NOTIFICATION_EMAIL", None)
            self._call()
        self.mock_send.assert_not_called()

    def test_production_mode_sends_to_real_recipient(self) -> None:
        with mock.patch.dict(os.environ, {"RESEND_API_KEY": "key"}, clear=False):
            os.environ.pop("APP_ENV", None)
            self._call(to_email="caterer@real.com")
        sent = self.mock_send.call_args[0][0]
        self.assertEqual(sent["to"], ["caterer@real.com"])


class TestEscalateToDev(unittest.TestCase):

    def setUp(self) -> None:
        # Sandbox the escalation directory so tests don't pollute cache/failures.
        self._tmp = Path(tempfile.mkdtemp(prefix="padea_escalation_test_"))
        self._patch_dir = mock.patch.object(email_module, "_ESCALATION_DIR", self._tmp)
        self._patch_dir.start()

        # Default env: a recipient is set and Resend is patched to succeed
        # unless an individual test overrides.
        self._env_patch = mock.patch.dict(
            os.environ,
            {
                "DEV_NOTIFICATION_EMAIL": "dev@example.com",
                "RESEND_API_KEY":         "test-key",
            },
        )
        self._env_patch.start()

        self._send_patch = mock.patch("support.email.resend.Emails.send")
        self.mock_send = self._send_patch.start()

    def tearDown(self) -> None:
        self._send_patch.stop()
        self._env_patch.stop()
        self._patch_dir.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_writes_artifact_and_notifies(self) -> None:
        path = escalate_to_dev(
            failure_id="20260101_120000_register_orders",
            reason="Resend 401 — likely invalid API key after rotation",
            workflow="register_orders",
            suggested_action="Rotate RESEND_API_KEY and rerun ./run orders",
            traceback_text="Traceback (most recent call last):\n  ...",
        )
        self.assertTrue(path.exists())
        body = path.read_text(encoding="utf-8")
        self.assertIn("Resend 401", body)
        self.assertIn("Rotate RESEND_API_KEY", body)
        self.assertIn("register_orders", body)
        self.assertIn("Traceback", body)
        self.mock_send.assert_called_once()
        sent = self.mock_send.call_args[0][0]
        self.assertEqual(sent["to"], ["dev@example.com"])
        self.assertIn("register_orders", sent["subject"])

    def test_dedupes_by_failure_id(self) -> None:
        first = escalate_to_dev(
            failure_id="20260101_120000_register_orders",
            reason="First call",
        )
        second = escalate_to_dev(
            failure_id="20260101_120000_register_orders",
            reason="Second call — same id, different reason",
        )
        self.assertEqual(first, second)
        # First call's body wins; second is a no-op (no overwrite, no resend).
        self.assertIn("First call", first.read_text(encoding="utf-8"))
        self.assertNotIn("Second call", first.read_text(encoding="utf-8"))
        self.mock_send.assert_called_once()

    def test_artifact_written_even_when_resend_fails(self) -> None:
        self.mock_send.side_effect = RuntimeError("Resend exploded")
        path = escalate_to_dev(
            failure_id="20260101_120001_send_orders",
            reason="Network outage to api.resend.com",
        )
        # Artifact survives even though the notification failed.
        self.assertTrue(path.exists())
        self.assertIn("Network outage", path.read_text(encoding="utf-8"))

    def test_artifact_written_when_recipient_unset(self) -> None:
        with mock.patch.dict(os.environ, {"DEV_NOTIFICATION_EMAIL": ""}, clear=False):
            # Force the env var to be absent by removing it cleanly.
            os.environ.pop("DEV_NOTIFICATION_EMAIL", None)
            path = escalate_to_dev(
                failure_id="20260101_120002_evaluate_caterers",
                reason="No recipient configured",
            )
        self.assertTrue(path.exists())
        self.mock_send.assert_not_called()

    def test_explicit_recipient_override(self) -> None:
        escalate_to_dev(
            failure_id="20260101_120003_execute_caterer_switch",
            reason="Custom recipient routing",
            notify_email="oncall@example.com",
        )
        self.mock_send.assert_called_once()
        sent = self.mock_send.call_args[0][0]
        self.assertEqual(sent["to"], ["oncall@example.com"])


class TestScheduleEmailCapturesResendFailures(unittest.TestCase):
    """Resend failures inside a wrapped workflow must register with the
    active self_healing_error_handler so the agent gets a capture artifact.

    Regression for: ``./run forms send parents --limit 1`` logging
    ``[FAILED]`` without producing a failure_*.json / patch_prompt_*.md pair.
    """

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="padea_email_handler_test_"))
        self._patch_dir = mock.patch.object(eh_module, "_FAILURES_DIR", self._tmp)
        self._patch_dir.start()
        self._send_patch = mock.patch("support.email.resend.Emails.send")
        self.mock_send = self._send_patch.start()
        self._env_patch = mock.patch.dict(
            os.environ, {"RESEND_API_KEY": "test-key"}, clear=False
        )
        self._env_patch.start()
        # Ensure APP_ENV isn't 'development' for this test.
        os.environ.pop("APP_ENV", None)

    def tearDown(self) -> None:
        self._env_patch.stop()
        self._send_patch.stop()
        self._patch_dir.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_resend_failure_inside_handler_is_captured(self) -> None:
        self.mock_send.side_effect = RuntimeError("Resend 401 Unauthorized")
        db = MockDatabase()
        with self_healing_error_handler("send_meals_links"):
            schedule_email(
                db,
                to_email="recipient@example.com",
                cc_email=None,
                subject="Test",
                body="Body",
                email_id="EMAIL-TEST-001",
            )
        jsons = sorted(self._tmp.glob("failure_*.json"))
        self.assertEqual(len(jsons), 1, "schedule_email should register a failure on Resend exception")
        payload = json.loads(jsons[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["error"]["type"], LoggedFailureBatch.__name__)
        self.assertEqual(len(payload["logged_failures"]), 1)
        self.assertIn("recipient@example.com", payload["logged_failures"][0])
        self.assertIn("Resend 401", payload["logged_failures"][0])
        # The row was still marked Failed in the audit log.
        update_call = db.ScheduledEmails.updates[-1]
        self.assertEqual(update_call[1], {"status": "Failed"})

    def test_resend_failure_outside_handler_just_logs(self) -> None:
        # Same Resend failure, but no wrapping handler — must not write any artifact.
        self.mock_send.side_effect = RuntimeError("Resend down")
        db = MockDatabase()
        schedule_email(
            db,
            to_email="recipient@example.com",
            cc_email=None,
            subject="Test",
            body="Body",
            email_id="EMAIL-TEST-002",
        )
        jsons = sorted(self._tmp.glob("failure_*.json"))
        self.assertEqual(jsons, [])


if __name__ == "__main__":
    unittest.main()
