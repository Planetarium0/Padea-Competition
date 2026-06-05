"""
implement_plan.py — Execute an approved implementation plan via the Claude Code agent.

Spawned as a detached background process when the coordinator approves a plan.
Loads the plan, builds a rich implementation prompt, runs Claude Code via the
existing sandboxed harness, updates the plan status, and notifies the coordinator.

Usage:
  python scripts/actions/system/implement_plan.py --plan-id <plan_id> [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import sys
from pathlib import Path
from typing import Any

# Ensure the project root and scripts/ are importable regardless of how we were spawned.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_TOOLS_DIR = _SCRIPTS_DIR / "tools"
for _p in [str(_SCRIPTS_DIR), str(_PROJECT_ROOT), str(_TOOLS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.chdir(_PROJECT_ROOT)

from support import log, self_healing_error_handler  # noqa: E402
from support.email import (  # noqa: E402
    Card,
    Heading,
    Text,
    _send_via_sendgrid,
    _support_from,
    compose_email,
)
from actions.system.register_edge_case import load_plan, update_plan  # noqa: E402

import run_claude_agent  # noqa: E402


# ---------------------------------------------------------------------------
# Implementation prompt
# ---------------------------------------------------------------------------

def _build_prompt(plan: dict[str, Any]) -> str:
    description = plan["description"]
    plan_markdown = plan["plan_markdown"]
    comments = plan.get("approval_comments") or "None — proceed as planned."

    return f"""You are implementing an approved edge case for the Padea catering system.

## Edge Case Description
{description}

## Implementation Plan
{plan_markdown}

## Coordinator Approval Comments
{comments}

## Required Steps — complete ALL of these in order

1. **Read project context first**: Read `plans/current/principles.md`, `plans/current/workflow.md`, and `plans/current/dev-guide.md` before writing any code.

2. **Implement all code changes** described in the plan. Follow the coding standards in `plans/current/principles.md`:
   - Type-hint every function signature crossing a module boundary
   - Use `support.log` (not `print`)
   - Validate at every database boundary via Pydantic schemas
   - One script = one operational goal
   - Write no comments unless the WHY is non-obvious

3. **Add regression tests for every backend change**:
   - Add tests to `scripts/tests/test_edge_cases.py` using `MockDatabase` / `populate_mock_db`
   - No real Supabase calls in the test suite
   - Every new code path must have a test

4. **If the webapp is affected**:
   - Make all necessary changes to webapp files — do not just flag them, fix them
   - Add tests under `webapp/tests/` for the webapp changes
   - Pay extra attention to correctness: webapp test coverage is less comprehensive

5. **Update `plans/current/` documentation** if and only if a contract changed (new workflow step, changed principle, new `./run` verb). Do not update docs for pure bugfixes.

6. **Run all tests and confirm they pass**:
   ```
   ./run test
   ```
   If you changed any webapp files, also run:
   ```
   ./run test webapp
   ```
   Fix every failure before proceeding to the commit step.

7. **Commit all changes** in a single git commit:
   - Stage all modified files: code, tests, and docs
   - Write a clear commit message that names the edge case and summarises what was implemented

8. **Report**: After the commit, summarise:
   - What was changed and why
   - Which files were modified
   - Which tests were added
   - Whether and how the webapp was affected
"""


# ---------------------------------------------------------------------------
# Completion notification
# ---------------------------------------------------------------------------

def _send_completion_email(
    plan: dict[str, Any], *, success: bool, agent_log: str = ""
) -> None:
    coordinator_email = os.environ.get("COORDINATOR_EMAIL") or os.environ.get(
        "DEV_NOTIFICATION_EMAIL"
    )
    if not coordinator_email:
        log.error("[PLAN] Cannot send completion email: COORDINATOR_EMAIL not set")
        return

    plan_id = plan["id"]
    title = plan["title"]

    if success:
        subject = f"[Padea] Implemented: {title} [PLAN-{plan_id}]"
        heading = f"Implementation Complete: {title}"
        status = "The approved plan has been fully applied, tested, and committed."
    else:
        subject = f"[Padea] Implementation Failed: {title} [PLAN-{plan_id}]"
        heading = f"Implementation Failed: {title}"
        status = (
            "The implementation agent encountered an issue. "
            "Manual intervention may be required."
        )

    components = [
        Heading(heading, accent=True),
        Text(status),
    ]

    tail = agent_log[-2000:].strip() if agent_log else ""
    if tail:
        components.append(Card([Heading("Agent Summary"), Text(tail)], shaded=True))

    components.append(Text(f"Plan ID: {plan_id}"))

    body = compose_email(components)

    dev_env = os.environ.get("APP_ENV") == "development"
    actual_to = (
        os.environ.get("DEV_NOTIFICATION_EMAIL") or coordinator_email
        if dev_env
        else coordinator_email
    )

    try:
        _send_via_sendgrid(
            to=[actual_to],
            subject=subject,
            body=body,
            from_email=_support_from(),
        )
        log.info(f"[PLAN] Completion email sent to {actual_to}")
    except Exception as e:
        log.error(f"[PLAN] Failed to send completion email: {e}")


# ---------------------------------------------------------------------------
# Implementation orchestrator
# ---------------------------------------------------------------------------

def implement_plan(plan_id: str, *, dry_run: bool = False) -> bool:
    """Run the Claude Code agent to implement the approved plan. Returns True on success."""
    plan = load_plan(plan_id)

    if plan.get("status") != "approved":
        log.error(
            f"[PLAN] Plan {plan_id!r} is not in 'approved' status "
            f"(got {plan.get('status')!r})"
        )
        return False

    update_plan(plan_id, {"status": "implementing"})
    log.info(f"[PLAN] Starting implementation of {plan_id!r}: {plan['title']!r}")

    prompt = _build_prompt(plan)

    if dry_run:
        log.info("[DRY RUN] Would run Claude Code agent with implementation prompt")
        log.info(f"[DRY RUN] Prompt preview:\n{prompt[:600]}...")
        update_plan(plan_id, {"status": "approved", "implementation_log": "[dry-run]"})
        return True

    success, agent_log = run_claude_agent.orchestrate_self_healing(
        prompt, modified_before=[]
    )

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if success:
        update_plan(
            plan_id,
            {
                "status": "implemented",
                "implemented_at": now,
                "implementation_log": agent_log[:10000],
            },
        )
        log.info(f"[PLAN] Implementation succeeded for {plan_id!r}")
    else:
        update_plan(
            plan_id,
            {
                "status": "failed",
                "implemented_at": now,
                "implementation_log": agent_log[:10000],
            },
        )
        log.error(f"[PLAN] Implementation failed for {plan_id!r}")

    _send_completion_email(plan, success=success, agent_log=agent_log)
    return success


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Implement an approved edge case plan via Claude Code agent"
    )
    parser.add_argument("--plan-id", required=True, help="The plan ID to implement")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the prompt without running the agent",
    )
    args = parser.parse_args()

    def _state_provider() -> dict[str, Any]:
        try:
            return {"plan": load_plan(args.plan_id)}
        except Exception as e:
            return {"error": str(e)}

    with self_healing_error_handler("implement_plan", state_provider=_state_provider):
        ok = implement_plan(args.plan_id, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)
