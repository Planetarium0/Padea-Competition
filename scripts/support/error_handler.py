"""Centralized error handling and self-healing state-capture.

Intercepts exceptions across active workflows, serializes state to machine-readable
JSON, and creates detailed AI instruction prompts to enable automated self-healing.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from .support import _active_handler


class UnhandledEdgeCaseError(Exception):
    """Raised when an unhandled business logic constraint or assumptions validation fails."""
    pass


class LoggedFailureBatch(Exception):
    """Marker type for the synthetic failure constructed when a wrapped
    workflow completes without raising but accumulated ``log.failure(...)``
    calls during execution. Never actually raised — used only as the
    ``error.type`` field in the captured artifact.
    """
    pass


# Module-level so tests can monkey-patch it without touching env / cwd.
_FAILURES_DIR: Path = Path(__file__).resolve().parents[2] / "cache" / "failures"


class self_healing_error_handler(contextlib.AbstractContextManager):
    """Context manager to catch, serialize, and prompt-heal failures in active workflows.

    Captures two kinds of failures:

    1. **Escaping exceptions** — any unhandled exception inside the block.
    2. **Logged failures** — any call to ``log.failure(...)`` while this
       handler is active. Even if no exception escapes, those accumulate
       and trigger the same artifact-writing path at ``__exit__``.

    Either path produces a matching pair of files under
    ``cache/failures/``:

    - ``failure_<ts>_<workflow>.json`` — machine-readable state snapshot.
    - ``patch_prompt_<ts>_<workflow>.md`` — preformatted instructions for
      an AI patcher (Claude Code, etc.).
    """

    def __init__(
        self,
        command_name: str,
        state_provider: Optional[Union[Dict[str, Any], Callable[[], Dict[str, Any]]]] = None,
    ) -> None:
        self.command_name = command_name
        self.state_provider = state_provider
        self._logged_failures: List[str] = []
        self._token: Optional[Any] = None

    def __enter__(self) -> self_healing_error_handler:
        # Register as the active handler so log.failure(...) routes here.
        self._token = _active_handler.set(self)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        # Always deregister, even if the exception path fails.
        if self._token is not None:
            try:
                _active_handler.reset(self._token)
            except (LookupError, ValueError):
                # Token from a different Context — fall back to clearing.
                _active_handler.set(None)
            self._token = None

        has_exception = exc_type is not None
        is_pass_through = has_exception and exc_type in (SystemExit, KeyboardInterrupt)

        # Path 1: a real exception escaped (not sys.exit / Ctrl+C).
        # Capture it — logged failures are bundled into the same payload.
        if has_exception and not is_pass_through:
            try:
                self._handle_exception_failure(exc_type, exc_val, exc_tb)
            except Exception as e:
                print(f"[FATAL] Self-healing error handler failed: {e}", file=sys.stderr)
                traceback.print_exc()
            return False

        # Path 2: clean exit OR pass-through exit. In both cases, any
        # log.failure() calls accumulated during the block still deserve a
        # capture — sys.exit doesn't unregister them.
        if self._logged_failures:
            try:
                self._handle_logged_failure_batch()
            except Exception as e:
                print(f"[FATAL] Self-healing error handler failed: {e}", file=sys.stderr)
                traceback.print_exc()

        return False

    # ------------------------------------------------------------------
    # log.failure registration (called from support.support._failure)
    # ------------------------------------------------------------------

    def register_failure(self, message: str) -> None:
        """Append a failure message to the in-flight list. Idempotent on the
        same message? No — duplicates are kept because each call site is a
        signal in its own right (e.g. 3 emails failing to send is different
        from 1)."""
        self._logged_failures.append(message)

    # ------------------------------------------------------------------
    # Capture paths — both end up calling _write_failure_artifacts
    # ------------------------------------------------------------------

    def _handle_exception_failure(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
        tb_str = "".join(tb_lines)
        self._write_failure_artifacts(
            error_type=exc_type.__name__,
            error_message=str(exc_val),
            traceback_text=tb_str,
        )

    def _handle_logged_failure_batch(self) -> None:
        count = len(self._logged_failures)
        message = (
            f"{count} failure(s) registered via log.failure during "
            f"'{self.command_name}'"
        )
        # The "traceback" slot carries the bulleted failure list so the
        # patch-prompt template still has something concrete to show.
        body_lines = [
            "(no exception was raised — the following messages were registered",
            "via log.failure(...) during the wrapped workflow.)",
            "",
        ]
        body_lines.extend(f"- {m}" for m in self._logged_failures)
        self._write_failure_artifacts(
            error_type=LoggedFailureBatch.__name__,
            error_message=message,
            traceback_text="\n".join(body_lines),
        )

    def _write_failure_artifacts(
        self,
        error_type:     str,
        error_message:  str,
        traceback_text: str,
    ) -> None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        failure_id = f"{timestamp}_{self.command_name}"

        _FAILURES_DIR.mkdir(parents=True, exist_ok=True)

        # Resolve State Snapshot
        state_snapshot: Any = {}
        if self.state_provider:
            try:
                if callable(self.state_provider):
                    state_snapshot = self.state_provider()
                else:
                    state_snapshot = self.state_provider
            except Exception as e:
                state_snapshot = {"error_resolving_state": str(e)}

        serialized_state = self._make_json_serializable(state_snapshot)

        failure_payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "command_name": self.command_name,
            "error": {
                "type": error_type,
                "message": error_message,
                "traceback": traceback_text,
            },
            "logged_failures": list(self._logged_failures),
            "context": {
                "sys_argv": sys.argv,
                "cwd": os.getcwd(),
            },
            "state_snapshot": serialized_state,
        }

        json_filename = f"failure_{failure_id}.json"
        json_path = _FAILURES_DIR / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(failure_payload, f, indent=2, ensure_ascii=False)

        prompt_filename = f"patch_prompt_{failure_id}.md"
        prompt_path = _FAILURES_DIR / prompt_filename
        self_healing_prompt = self._build_prompt_content(
            failure_id=failure_id,
            error_type=error_type,
            error_message=error_message,
            json_filename=json_filename,
            json_path=str(json_path),
            traceback=traceback_text,
        )
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(self_healing_prompt)

        print(f"\n=============================================================", file=sys.stderr)
        print(f"[SELF-HEALING ERROR LOGGED]", file=sys.stderr)
        print(f"A failure was caught in the active workflow '{self.command_name}'.", file=sys.stderr)
        print(f"1. Machine-readable failure state logged to:", file=sys.stderr)
        print(f"   {json_path}", file=sys.stderr)
        print(f"2. Auto-generated LLM self-healing prompt written to:", file=sys.stderr)
        print(f"   {prompt_path}", file=sys.stderr)
        print(f"Provide the prompt file contents directly to an AI coder to patch this edge case.", file=sys.stderr)
        print(f"=============================================================\n", file=sys.stderr)

    def _build_prompt_content(
        self,
        failure_id: str,
        error_type: str,
        error_message: str,
        json_filename: str,
        json_path: str,
        traceback: str
    ) -> str:
        is_batch = error_type == LoggedFailureBatch.__name__
        if is_batch:
            intro = (
                "One or more soft errors were registered via `log.failure(...)` "
                "during this workflow. No exception escaped, but each registered "
                "message represents an issue that the workflow author flagged "
                "for capture. Review each, decide whether it is a bug or expected "
                "noise, and patch accordingly."
            )
            evidence_heading = "## Registered Failures"
            evidence_lang = ""  # plain text — no Python traceback
            patch_target_hint = (
                "Identify the source of each registered failure (each call site is "
                "a `log.failure(...)` in `scripts/`). Decide per site whether to "
                "fix the underlying issue, downgrade to `log.error` (genuine soft "
                "warning), or promote to `raise` (contract violation)."
            )
        else:
            intro = (
                "A runtime exception occurred in the active catering operations "
                "pipeline. Use the attached context and instructions below to "
                "automatically reproduce, patch, and test a fix."
            )
            evidence_heading = "## Stack Trace"
            evidence_lang = "python"
            patch_target_hint = (
                "Identify the source script (indicated by the stack trace) where "
                "the failure occurred. Implement a safe, robust, and clean code "
                "patch that resolves this edge case (e.g. adding fallback checks, "
                "validation, or modifying the logical rules)."
            )

        return f"""# Self-Healing Instruction: Resolve Catchable Edge Case in Padea

{intro}

## Failure Metadata
- **Workflow**: `{self.command_name}`
- **Error Type**: `{error_type}`
- **Error Message**: `{error_message}`
- **State Snapshot File**: `{json_path}`

{evidence_heading}
```{evidence_lang}
{traceback}
```

---

## Instructions for the Self-Healing AI Agent:

0. **Load Project Context**:
   - Read `plans/current/principles.md` (design rules + known gaps).
   - Read `plans/current/workflow.md` if the failure is in an action script
     under `scripts/actions/` (it maps the weekly rhythm + decision points).
   - For "where is X?" questions, prefer `graphify query "<question>"`
     over raw grep.

1. **Load State Snapshot**:
   - Read the serialized state from [failure_{failure_id}.json](file://{json_path}).
   - Use the variables and database records captured under the `"state_snapshot"` key to understand the exact runtime state at the moment of failure.
   - The `"logged_failures"` key lists every `log.failure(...)` message that fired during the workflow (may be empty for pure exception captures).

2. **Replicate via Regression Test**:
   - Open `scripts/tests/test_edge_cases.py`.
   - Add a new regression test (e.g., `test_failure_{failure_id}`) to the suite.
   - Use the database snapshot records in the JSON to initialize a `MockDatabase` context via `populate_mock_db`, and call the failing workflow matching sys_argv or the target function.
   - Verify that this test fails (or, for a logged-failure batch, that the same `log.failure` messages are emitted).

3. **Implement Code Patch**:
   - {patch_target_hint}
   - Adhere to the principles in `plans/current/principles.md` — especially:
     validate at DB boundaries (Pydantic), one script = one goal, type-hint
     module-boundary signatures, every failing branch has a test.

4. **Verify the Fix**:
   - Run the regression test suite: `./run test test_edge_cases` (or the full suite: `./run test`).
   - Confirm that the new test passes successfully.

5. **Update Documentation (only if you changed a contract)**:
   - If this patch changes a design principle, invariant, decision point,
     or `./run` verb, update the relevant file under `plans/current/`
     (`principles.md`, `workflow.md`, or `dev-guide.md`) in the same change.
   - If it surfaces a previously-unknown gap, add a one-line bullet to
     `principles.md §6 (Known gaps)`.
   - Pure bugfixes that don't move a contract need no doc update —
     `graphify update .` after the patch will refresh the code map.

6. **Report Back**:
   - Once successfully healed, summarize what caused the error and provide a diff of the code changes made.
"""

    def _make_json_serializable(self, obj: Any) -> Any:
        """Coerce complex objects (like Dataclasses, Sets, custom Records) to JSON-serializable types."""
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple, set)):
            return [self._make_json_serializable(x) for x in obj]
        elif hasattr(obj, "__dict__"):
            return self._make_json_serializable(obj.__dict__)
        elif hasattr(obj, "to_dict"):
            return self._make_json_serializable(obj.to_dict())
        # Custom Record envelope support
        elif hasattr(obj, "id") and hasattr(obj, "fields"):
            return {"id": obj.id, "fields": self._make_json_serializable(obj.fields)}
        elif isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        try:
            json.dumps(obj)
            return obj
        except TypeError:
            return str(obj)
