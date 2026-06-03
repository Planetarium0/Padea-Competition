"""Tests for scripts/support/error_handler.py — self_healing_error_handler.

Covers the two capture paths:

1. **Exception path** — an exception escapes the wrapped block.
2. **Logged-failure path** — no exception escapes, but ``log.failure(...)``
   calls accumulated during the block.

Plus the ``log.failure`` plumbing itself: ContextVar-based handler discovery,
no-op outside a wrapped block, and proper accumulation of multiple calls.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support.error_handler as eh_module
from support import log
from support.error_handler import LoggedFailureBatch, self_healing_error_handler
from support.support import _active_handler


class _HandlerTestBase(unittest.TestCase):
    """Sandboxes the failures dir so tests don't pollute cache/failures/."""

    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="padea_handler_test_"))
        self._patch_dir = mock.patch.object(eh_module, "_FAILURES_DIR", self._tmp)
        self._patch_dir.start()

    def tearDown(self) -> None:
        self._patch_dir.stop()
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _failure_artifacts(self) -> tuple[list[Path], list[Path]]:
        jsons = sorted(self._tmp.glob("failure_*.json"))
        prompts = sorted(self._tmp.glob("patch_prompt_*.md"))
        return jsons, prompts


class TestLogFailureRouting(_HandlerTestBase):

    def test_log_failure_outside_handler_is_noop(self) -> None:
        # No active handler → log.failure must not write any artifact, must not blow up.
        self.assertIsNone(_active_handler.get())
        log.failure("Nobody is listening")
        jsons, prompts = self._failure_artifacts()
        self.assertEqual(jsons, [])
        self.assertEqual(prompts, [])

    def test_handler_registers_and_deregisters(self) -> None:
        # __enter__ should set the ContextVar; __exit__ should clear it.
        self.assertIsNone(_active_handler.get())
        with self_healing_error_handler("scoped_workflow") as h:
            self.assertIs(_active_handler.get(), h)
        self.assertIsNone(_active_handler.get())

    def test_log_failure_inside_handler_registers_message(self) -> None:
        with self_healing_error_handler("scoped_workflow") as h:
            log.failure("Boom: %s", "value")
            self.assertEqual(h._logged_failures, ["Boom: value"])

    def test_log_failure_outside_handler_does_not_register_to_prior_handler(self) -> None:
        # Once the with-block exits, subsequent log.failure() calls must NOT
        # accumulate on the de-registered handler.
        with self_healing_error_handler("scoped_workflow") as h:
            pass
        log.failure("After the block")
        self.assertEqual(h._logged_failures, [])


class TestLoggedFailureCapture(_HandlerTestBase):

    def test_clean_exit_with_one_failure_writes_artifact(self) -> None:
        with self_healing_error_handler("register_orders"):
            log.failure("Caterer A: no compatible meal for student 42")
        jsons, prompts = self._failure_artifacts()
        self.assertEqual(len(jsons), 1)
        self.assertEqual(len(prompts), 1)

        payload = json.loads(jsons[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["error"]["type"], LoggedFailureBatch.__name__)
        self.assertIn("register_orders", payload["error"]["message"])
        self.assertEqual(
            payload["logged_failures"],
            ["Caterer A: no compatible meal for student 42"],
        )
        # The "traceback" slot carries the bulleted list, not a Python TB.
        self.assertIn("no exception was raised", payload["error"]["traceback"])
        self.assertIn(
            "Caterer A: no compatible meal for student 42",
            payload["error"]["traceback"],
        )

    def test_multiple_failures_accumulate(self) -> None:
        with self_healing_error_handler("send_orders"):
            log.failure("Email 1 of 6 failed")
            log.failure("Email 4 of 6 failed")
            log.failure("Email 5 of 6 failed")
        jsons, _ = self._failure_artifacts()
        payload = json.loads(jsons[0].read_text(encoding="utf-8"))
        self.assertEqual(len(payload["logged_failures"]), 3)
        self.assertIn("3 failure(s) registered", payload["error"]["message"])

    def test_clean_exit_with_no_failures_writes_nothing(self) -> None:
        with self_healing_error_handler("register_orders"):
            log.info("All good")
        jsons, prompts = self._failure_artifacts()
        self.assertEqual(jsons, [])
        self.assertEqual(prompts, [])

    def test_prompt_uses_logged_failure_framing(self) -> None:
        with self_healing_error_handler("evaluate_caterers"):
            log.failure("Rating window empty for caterer X")
        _, prompts = self._failure_artifacts()
        prompt = prompts[0].read_text(encoding="utf-8")
        self.assertIn("## Registered Failures", prompt)
        self.assertNotIn("## Stack Trace", prompt)
        self.assertIn("Rating window empty for caterer X", prompt)
        self.assertIn("`LoggedFailureBatch`", prompt)


class TestExceptionPathStillWins(_HandlerTestBase):

    def test_exception_path_writes_traceback_artifact(self) -> None:
        with self.assertRaises(ValueError):
            with self_healing_error_handler("register_orders"):
                log.failure("Soft warning before the boom")
                raise ValueError("hard failure")
        jsons, prompts = self._failure_artifacts()
        self.assertEqual(len(jsons), 1)
        payload = json.loads(jsons[0].read_text(encoding="utf-8"))
        # Exception path wins: error.type is ValueError, not LoggedFailureBatch.
        self.assertEqual(payload["error"]["type"], "ValueError")
        self.assertEqual(payload["error"]["message"], "hard failure")
        # But the soft failure list is preserved in the payload for diagnosis.
        self.assertEqual(payload["logged_failures"], ["Soft warning before the boom"])
        # Prompt still uses the exception framing, not the logged-failure framing.
        prompt = prompts[0].read_text(encoding="utf-8")
        self.assertIn("## Stack Trace", prompt)
        self.assertNotIn("## Registered Failures", prompt)

    def test_systemexit_is_not_captured(self) -> None:
        # SystemExit and KeyboardInterrupt must pass through untouched —
        # they're the canonical "human misuse" exit path.
        with self.assertRaises(SystemExit):
            with self_healing_error_handler("evaluate_caterers"):
                raise SystemExit(2)
        jsons, _ = self._failure_artifacts()
        self.assertEqual(jsons, [])


class TestStateProviderSnapshotting(_HandlerTestBase):

    def test_state_provider_callable_resolved_at_exit(self) -> None:
        captured = {"snapshot_taken": False}

        def provider() -> dict:
            captured["snapshot_taken"] = True
            return {"students": ["a", "b"]}

        with self_healing_error_handler("register_orders", state_provider=provider):
            log.failure("Anything")
        self.assertTrue(captured["snapshot_taken"])
        jsons, _ = self._failure_artifacts()
        payload = json.loads(jsons[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["state_snapshot"], {"students": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
