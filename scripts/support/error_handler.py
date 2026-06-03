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
from typing import Any, Callable, Dict, Optional, Union


class UnhandledEdgeCaseError(Exception):
    """Raised when an unhandled business logic constraint or assumptions validation fails."""
    pass


class self_healing_error_handler(contextlib.AbstractContextManager):
    """Context manager to catch, serialize, and prompt-heal failures in active workflows."""

    def __init__(
        self,
        command_name: str,
        state_provider: Optional[Union[Dict[str, Any], Callable[[], Dict[str, Any]]]] = None,
    ) -> None:
        self.command_name = command_name
        self.state_provider = state_provider

    def __enter__(self) -> self_healing_error_handler:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        if exc_type is None:
            return False

        # Exclude expected system exits (like sys.exit(0) or keyboard interrupts)
        if exc_type in (SystemExit, KeyboardInterrupt):
            return False

        try:
            self._handle_failure(exc_type, exc_val, exc_tb)
        except Exception as e:
            # If the error handler itself fails, print details but let original exception bubble up
            print(f"[FATAL] Self-healing error handler failed: {e}", file=sys.stderr)
            traceback.print_exc()

        # Let the original exception bubble up to the runtime/cli so it still prints normally
        return False

    def _handle_failure(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        failure_id = f"{timestamp}_{self.command_name}"
        
        # Ensure the failure output directories exist
        failures_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../cache/failures"))
        os.makedirs(failures_dir, exist_ok=True)

        # 1. Resolve State Snapshot
        state_snapshot = {}
        if self.state_provider:
            try:
                if callable(self.state_provider):
                    state_snapshot = self.state_provider()
                else:
                    state_snapshot = self.state_provider
            except Exception as e:
                state_snapshot = {"error_resolving_state": str(e)}

        # Ensure state snapshot is JSON serializable
        serialized_state = self._make_json_serializable(state_snapshot)

        # 2. Build Failure JSON payload
        tb_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
        tb_str = "".join(tb_lines)

        failure_payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "command_name": self.command_name,
            "error": {
                "type": exc_type.__name__,
                "message": str(exc_val),
                "traceback": tb_str,
            },
            "context": {
                "sys_argv": sys.argv,
                "cwd": os.getcwd(),
            },
            "state_snapshot": serialized_state,
        }

        json_filename = f"failure_{failure_id}.json"
        json_path = os.path.join(failures_dir, json_filename)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(failure_payload, f, indent=2, ensure_ascii=False)

        # 3. Build Dynamic Self-Healing Prompt Markdown
        prompt_filename = f"patch_prompt_{failure_id}.md"
        prompt_path = os.path.join(failures_dir, prompt_filename)
        
        self_healing_prompt = self._build_prompt_content(
            failure_id=failure_id,
            error_type=exc_type.__name__,
            error_message=str(exc_val),
            json_filename=json_filename,
            json_path=json_path,
            traceback=tb_str
        )

        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(self_healing_prompt)

        # Log completion message to stderr
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
        return f"""# Self-Healing Instruction: Resolve Catchable Edge Case in Padea

A runtime exception occurred in the active catering operations pipeline. 
Use the attached context and instructions below to automatically reproduce, patch, and test a fix.

## Failure Metadata
- **Workflow**: `{self.command_name}`
- **Error Type**: `{error_type}`
- **Error Message**: `{error_message}`
- **State Snapshot File**: `{json_path}`

## Stack Trace
```python
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

2. **Replicate via Regression Test**:
   - Open `scripts/tests/test_edge_cases.py`.
   - Add a new regression test (e.g., `test_failure_{failure_id}`) to the suite.
   - Use the database snapshot records in the JSON to initialize a `MockDatabase` context via `populate_mock_db`, and call the failing workflow matching sys_argv or the target function.
   - Verify that this test fails with the exact same error: `{error_type}`.

3. **Implement Code Patch**:
   - Identify the source script (indicated by the stack trace) where the failure occurred.
   - Implement a safe, robust, and clean code patch that resolves this edge case (e.g. adding fallback checks, validation, or modifying the logical rules).
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
