"""
Test runner for all Padea action-script unit tests.

Usage (from the project root):
    PYTHONPATH=$PWD:$PWD/scripts python scripts/tests/run_all.py

Or via the run script (if a test target is added there):
    ./run test
"""
from __future__ import annotations

import datetime
import io
import json
import os
import sys
import unittest
from pathlib import Path

# Prevent any test from accidentally hitting live services.
os.environ["PADEA_TEST_MODE"] = "1"

# Ensure the tests directory itself is on sys.path so relative fixture
# imports work regardless of the caller's working directory.
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import test_clarify_dietary
import test_database
import test_email
import test_error_handler
import test_escalate_dietary
import test_evaluate_caterers
import test_execute_caterer_switch
import test_parse_dietary_reply
import test_poll_dietary_inbox
import test_register_orders
import test_send_meals_links
import test_send_orders
import test_send_qr_emails
import test_handle_support_email
import test_substitutions
import test_edge_cases

# EMAIL_LIMIT is a per-run production throttle (set in .env to cap outbound
# mail in manual testing). It must not bleed across tests in the same process:
# load_dotenv() runs during module imports above, so clear it now.
# Also reset the module-level send counter so it never blocks schedule_email.
import support.email as _email_module
os.environ.pop("EMAIL_LIMIT", None)
_email_module._emails_queued_this_run = 0


def suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    s = unittest.TestSuite()
    for module in (
        test_clarify_dietary,
        test_database,
        test_email,
        test_error_handler,
        test_escalate_dietary,
        test_parse_dietary_reply,
        test_poll_dietary_inbox,
        test_register_orders,
        test_send_meals_links,
        test_send_orders,
        test_send_qr_emails,
        test_substitutions,
        test_evaluate_caterers,
        test_execute_caterer_switch,
        test_handle_support_email,
        test_edge_cases,
    ):
        s.addTests(loader.loadTestsFromModule(module))
    return s


_FAILURES_DIR = Path(__file__).resolve().parents[2] / "cache" / "failures"


def _write_test_failure_artifacts(
    result: unittest.TestResult,
    test_output: str,
) -> None:
    """Write failure JSON + patch prompt for failing tests, mirroring the
    operational self_healing_error_handler artifact format so ./run fix
    --latest-error can pick them up automatically."""
    _FAILURES_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    failure_id = f"{timestamp}_test"

    failed = [(str(t), tb) for t, tb in result.failures]
    errored = [(str(t), tb) for t, tb in result.errors]
    failure_count = len(failed)
    error_count = len(errored)
    total_problems = failure_count + error_count

    lines: list[str] = []
    for test_name, tb in failed:
        lines += [f"FAIL: {test_name}", tb, ""]
    for test_name, tb in errored:
        lines += [f"ERROR: {test_name}", tb, ""]
    problems_text = "\n".join(lines)

    payload = {
        "timestamp": datetime.datetime.now().isoformat(),
        "command_name": "test",
        "error": {
            "type": "TestFailure",
            "message": (
                f"{total_problems} test(s) failed or errored "
                f"({failure_count} failures, {error_count} errors)"
            ),
            "traceback": test_output,
        },
        "logged_failures": [],
        "context": {"sys_argv": sys.argv, "cwd": os.getcwd()},
        "state_snapshot": {
            "failed_tests": failed,
            "error_tests": errored,
            "total_tests_run": result.testsRun,
            "failure_count": failure_count,
            "error_count": error_count,
        },
    }

    json_path = _FAILURES_DIR / f"failure_{failure_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    prompt = f"""# Self-Healing Instruction: Resolve Failing Tests in Padea

{total_problems} test(s) failed during `./run test` \
({failure_count} assertion failures, {error_count} errors). \
Use the details below to reproduce, patch, and verify a fix.

## Failure Metadata
- **Workflow**: `test`
- **Failed / Errored Tests**: {total_problems}
- **State Snapshot File**: `{json_path}`

## Failing Tests
```
{problems_text}
```

---

## Instructions for the Self-Healing AI Agent

0. **Load Project Context**:
   - Read `plans/current/principles.md` (design rules + known gaps).
   - Read `plans/current/workflow.md` if the failure is in an action script
     under `scripts/actions/`.
   - For "where is X?" questions, prefer `graphify query "<question>"` over
     raw grep.

1. **Understand the Failure**:
   - Read each failing test and the production code it exercises.
   - Determine whether the bug is in production code (most common) or in the
     test itself (wrong expectation, stale fixture).
   - Do NOT alter a test to silence a real bug — only correct a test if its
     expectation was demonstrably wrong.

2. **Implement Code Patch**:
   - Fix the bug in the appropriate file under `scripts/`.
   - Adhere to `plans/current/principles.md`: validate at DB boundaries
     (Pydantic), type-hint module-boundary signatures, one script = one goal.

3. **Verify the Fix**:
   - Run `./run test` — all tests must pass before declaring success.

4. **Update Documentation (only if you changed a contract)**:
   - If this patch changes a design principle, invariant, decision point, or
     `./run` verb, update the relevant file under `plans/current/` in the
     same change.
   - Pure bugfixes need no doc update — run `graphify update .` after the
     patch to refresh the code map.

5. **Report Back**:
   - Summarize what caused each failure and provide a diff of the changes.
"""

    prompt_path = _FAILURES_DIR / f"patch_prompt_{failure_id}.md"
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    print("\n=============================================================", file=sys.stderr)
    print("[SELF-HEALING ERROR LOGGED]", file=sys.stderr)
    print(f"{total_problems} test(s) failed. Failure artifacts written:", file=sys.stderr)
    print(f"  state:  {json_path}", file=sys.stderr)
    print(f"  prompt: {prompt_path}", file=sys.stderr)
    print("Run `./run fix --latest-error` to attempt automated healing.", file=sys.stderr)
    print("=============================================================\n", file=sys.stderr)


if __name__ == "__main__":
    buf = io.StringIO()
    runner = unittest.TextTestRunner(verbosity=2, stream=buf)
    result = runner.run(suite())
    test_output = buf.getvalue()

    # Always echo the captured output so the user sees it.
    print(test_output, end="", file=sys.stderr)

    if not result.wasSuccessful():
        _write_test_failure_artifacts(result, test_output)
        sys.exit(1)

    sys.exit(0)
