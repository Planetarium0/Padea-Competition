"""
register_edge_case.py — Register a new edge case or requirement for human-gated implementation.

Flow:
  1. Generate a plan ID and draft an implementation plan via LLM.
  2. Persist the plan to cache/plans/<plan_id>.json.
  3. Email the coordinator with the plan for APPROVE / REJECT.

Usage:
  python scripts/actions/system/register_edge_case.py --description "..." [--source manual|email|failure] [--dry-run]
  python scripts/actions/system/register_edge_case.py --from-failure [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from support import ask_llm_json, log, self_healing_error_handler
from support.email import (
    Alert,
    Card,
    Divider,
    Heading,
    Text,
    _send_via_sendgrid,
    _support_from,
    _support_reply_to,
    compose_email,
)

_PLANS_DIR = Path(__file__).resolve().parents[3] / "cache" / "plans"


# ---------------------------------------------------------------------------
# Pydantic model for LLM plan draft response
# ---------------------------------------------------------------------------

class _PlanDraftResponse(BaseModel):
    title: str = "Edge case"
    summary_markdown: str = ""
    plan_markdown: str = ""


# ---------------------------------------------------------------------------
# Plan I/O
# ---------------------------------------------------------------------------

def _plan_path(plan_id: str) -> Path:
    return _PLANS_DIR / f"{plan_id}.json"


def load_plan(plan_id: str) -> dict[str, Any]:
    return json.loads(_plan_path(plan_id).read_text(encoding="utf-8"))


def save_plan(plan: dict[str, Any]) -> None:
    _PLANS_DIR.mkdir(parents=True, exist_ok=True)
    _plan_path(plan["id"]).write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def update_plan(plan_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    plan = load_plan(plan_id)
    plan.update(updates)
    save_plan(plan)
    return plan


def find_plan_by_message_id(message_id: str) -> dict[str, Any] | None:
    """Return the plan whose notification_message_id matches, or None."""
    if not _PLANS_DIR.exists():
        return None
    for path in sorted(_PLANS_DIR.glob("*.json"), reverse=True):
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
            if plan.get("notification_message_id") == message_id:
                return plan
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Plan ID helpers
# ---------------------------------------------------------------------------

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:40].strip("_")


def _make_plan_id(description: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"plan_{ts}_{_slug(description)}"


def _notification_message_id(plan_id: str) -> str:
    domain = os.environ.get("APP_DOMAIN", "padea.com.au")
    return f"<plan-{plan_id}@{domain}>"


# ---------------------------------------------------------------------------
# Plan drafting via LLM
# ---------------------------------------------------------------------------

def _read_doc(filename: str) -> str:
    path = Path(__file__).resolve().parents[3] / "plans" / "current" / filename
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return f"({filename} not found)"


def draft_plan(description: str) -> tuple[str, str, str]:
    """Use LLM to draft a title, summary, and full implementation plan.

    Returns (title, summary_markdown, plan_markdown).
    summary_markdown is 3-5 bullet points for the coordinator email.
    plan_markdown is the full detailed plan stored in cache and fed to the agent.
    """
    principles = _read_doc("principles.md")

    prompt = (
        "You are a senior software architect for the Padea after-school tutoring catering system.\n\n"
        "A new edge case or requirement needs to be implemented in the codebase.\n\n"
        "## Project Principles\n"
        f"{principles}\n\n"
        "## Edge Case / Requirement\n"
        f"{description}\n\n"
        "## Your Task\n"
        "Draft an implementation plan. You must produce two versions:\n"
        "1. summary_markdown: 3-5 concise bullet points covering what will change and why.\n"
        "   This is shown to the coordinator in the approval email — keep it scannable.\n"
        "2. plan_markdown: a full, detailed implementation plan with all context the\n"
        "   implementing agent needs. Write mostly in natural language; include code\n"
        "   only when directly relevant.\n\n"
        "Respond with ONLY a JSON object (no markdown fences, no other text):\n"
        '{"title": "Short descriptive title (max 8 words)", '
        '"summary_markdown": "- bullet 1\\n- bullet 2\\n- bullet 3", '
        '"plan_markdown": "## Summary\\n...\\n\\n## Code Changes\\n...\\n\\n'
        '## Tests\\n...\\n\\n## Documentation Updates\\nNone or list changes\\n\\n'
        '## Webapp Impact\\nNone or describe impact and changes needed"}'
    )

    result = ask_llm_json(prompt, _PlanDraftResponse)
    if result is None:
        fallback_summary = f"- {description}\n- *(LLM unavailable — plan must be written manually)*"
        fallback_plan = f"## Summary\n{description}\n\n*(LLM unavailable — plan must be written manually)*"
        return "Edge case", fallback_summary, fallback_plan

    return result.title or "Edge case", result.summary_markdown or f"- {description}", result.plan_markdown or f"## Summary\n{description}"


# ---------------------------------------------------------------------------
# Approval email
# ---------------------------------------------------------------------------

def send_approval_email(plan: dict[str, Any], *, dry_run: bool = False) -> None:
    """Send the plan approval email to the coordinator."""
    coordinator_email = os.environ.get("COORDINATOR_EMAIL") or os.environ.get(
        "DEV_NOTIFICATION_EMAIL"
    )
    if not coordinator_email:
        log.error("[PLAN] Cannot send approval email: COORDINATOR_EMAIL not set")
        return

    plan_id = plan["id"]
    title = plan["title"]
    description = plan["description"]
    summary_markdown = plan.get("summary_markdown") or plan["plan_markdown"]
    source_labels = {
        "manual": "manual entry",
        "email": "support email",
        "failure": "runtime failure",
    }
    source_label = source_labels.get(plan.get("source", "manual"), "unknown source")

    subject = f"[Padea] Implementation Plan: {title} [PLAN-{plan_id}]"

    body = compose_email([
        Heading(f"Implementation Plan: {title}", accent=True),
        Text(f"A new edge case has been registered from {source_label}."),
        Divider(),
        Card([
            Heading("Edge Case"),
            Text(description),
        ]),
        Card([
            Heading("Proposed Implementation"),
            Text(summary_markdown),
        ]),
        Divider(),
        Alert([
            Heading("Your Action Required"),
            Text(
                "Reply to this email with one of:\n"
                "• APPROVE — proceed with implementation as planned\n"
                "• APPROVE: your comments — proceed with specific guidance\n"
                "• REJECT: reason — dismiss this edge case"
            ),
        ], variant="amber"),
        Text(f"Plan ID: {plan_id}"),
    ])

    message_id = _notification_message_id(plan_id)

    if dry_run:
        log.info(
            f"[DRY RUN] Would send plan approval email to {coordinator_email}: {subject}"
        )
        return

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
            reply_to=_support_reply_to(),
            message_id_header=message_id,
        )
        log.info(f"[PLAN] Approval email sent to {actual_to}, plan_id={plan_id}")
    except Exception as e:
        log.failure(f"[PLAN] Failed to send approval email: {e}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def register_edge_case(
    description: str,
    source: str = "manual",
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Draft, persist, and send a plan email for a new edge case. Returns the plan dict."""
    plan_id = _make_plan_id(description)
    log.info(f"[PLAN] Registering edge case as {plan_id}")

    log.info("[PLAN] Drafting implementation plan via LLM...")
    title, summary_markdown, plan_markdown = draft_plan(description)
    log.info(f"[PLAN] Drafted: {title!r}")

    plan: dict[str, Any] = {
        "id": plan_id,
        "status": "pending",
        "source": source,
        "description": description,
        "title": title,
        "summary_markdown": summary_markdown,
        "plan_markdown": plan_markdown,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notification_message_id": _notification_message_id(plan_id),
        "approved_at": None,
        "approval_comments": None,
        "implemented_at": None,
        "rejection_reason": None,
        "implementation_log": None,
    }

    save_plan(plan)
    log.info(f"[PLAN] Saved to {_plan_path(plan_id)}")

    send_approval_email(plan, dry_run=dry_run)
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register a new edge case for human-gated implementation"
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--description", help="Edge case description")
    source_group.add_argument(
        "--from-failure",
        action="store_true",
        help="Read description from the latest captured failure in cache/failures/",
    )
    parser.add_argument(
        "--source",
        default="manual",
        choices=["manual", "email", "failure"],
        help="Origin of this edge case",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Draft and save the plan but do not send the email",
    )
    args = parser.parse_args()

    def _state_provider() -> dict[str, Any]:
        return {"plans_dir": str(_PLANS_DIR)}

    with self_healing_error_handler("register_edge_case", state_provider=_state_provider):
        if args.from_failure:
            failures_dir = Path(__file__).resolve().parents[3] / "cache" / "failures"
            prompts = sorted(
                failures_dir.glob("patch_prompt_*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not prompts:
                log.error("No failure prompts found in cache/failures/")
                raise SystemExit(1)
            failure_id = prompts[0].stem.removeprefix("patch_prompt_")
            failure_json = failures_dir / f"failure_{failure_id}.json"
            if failure_json.exists():
                data = json.loads(failure_json.read_text(encoding="utf-8"))
                err = data.get("error", {})
                description = (
                    f"Runtime failure in {data.get('command_name', 'workflow')}: "
                    f"{err.get('message', 'unknown error')}"
                )
            else:
                description = f"Runtime failure: {failure_id}"
            source = "failure"
        else:
            description = args.description
            source = args.source

        register_edge_case(description, source, dry_run=args.dry_run)
