#!/usr/bin/env python3
"""
Python automation harness for Claude Code (run_claude_agent.py).
- Restricts edits to allowed folders using a Git Guard.
- Uses dynamic PATH isolation to restrict bash commands to a strict allowlist.
- Runs post-execution tests to verify correctness.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ==================== CONFIGURATION ====================
# Folders Claude is permitted to modify/create files in (relative to project root)
ALLOWED_EDIT_DIRS = [
    "scripts",
    "supabase",
    "webapp",
    "plans"
]

# Strict allowlist of binaries that Claude's bash tool is permitted to run
ALLOWED_BINARIES = [
    "git",
    "./run",
    ".venv/bin/python",
    "python",
    "python3",
    "uv",
    "node",        # Required for Claude CLI itself to run
    "cat",
    "grep",
    "mkdir",
    "rm",
    "pytest",
]

# The validation test command to run after completion
TEST_COMMAND = ["./run", "test"]
# =======================================================


def get_git_modified_files() -> list[str]:
    """Returns a list of all modified, untracked, or deleted files in the git workspace."""
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True
        )
        files = []
        for line in res.stdout.strip().split("\n"):
            if not line:
                continue
            # Format: XY path/to/file (e.g. M scripts/support/db.py or ?? newfile.py)
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                files.append(parts[1])
        return files
    except subprocess.CalledProcessError as e:
        print(f"[-] Git status check failed: {e}", file=sys.stderr)
        return []


def is_file_allowed(filepath: str) -> bool:
    """Checks if a modified file path is inside one of the allowed directories."""
    path = Path(filepath)
    for allowed in ALLOWED_EDIT_DIRS:
        allowed_path = Path(allowed)
        try:
            # Check if file path is relative to the allowed path
            path.relative_to(allowed_path)
            return True
        except ValueError:
            # Not a subpath
            pass
    return False


def revert_unauthorized_changes(unauthorized_files: list[str]):
    """Reverts files modified or created outside allowed directories."""
    print("[!] Reverting unauthorized edits to the following files:")
    for file in unauthorized_files:
        print(f"  - {file}")
        # Revert modified files
        subprocess.run(["git", "checkout", "--", file], capture_output=True)
        # Remove untracked files/directories
        subprocess.run(["git", "clean", "-fd", "--", file], capture_output=True)


def setup_restricted_path(temp_dir_path: Path) -> dict[str, str]:
    """Sets up a safe bin directory containing symlinks only to allowed commands."""
    print(f"[+] Creating restricted PATH environment in {temp_dir_path}")
    
    # Check for local virtual environment
    venv_bin = Path("./.venv/bin").resolve()
    has_venv = venv_bin.exists()
    if has_venv:
        print(f"[+] Local virtual environment detected at {venv_bin}")
    
    # 1. Symlink allowed system binaries
    for binary in ALLOWED_BINARIES:
        binary_path = None
        if has_venv:
            # Prioritize venv binaries (like python, pip, pytest)
            potential_path = venv_bin / binary
            if potential_path.exists():
                binary_path = str(potential_path)
                
        if not binary_path:
            binary_path = shutil.which(binary)
            
        if binary_path:
            link_target = temp_dir_path / binary
            if not link_target.exists():
                link_target.symlink_to(binary_path)
        else:
            print(f"[?] Warning: Allowed binary '{binary}' was not found on your system PATH or local venv.")

    # 2. Symlink local project executable `./run`
    project_run = Path("./run").resolve()
    if project_run.exists():
        link_target = temp_dir_path / "run"
        if not link_target.exists():
            link_target.symlink_to(project_run)

    # 3. Create a clean environment dictionary
    new_env = os.environ.copy()
    
    # Set PATH to contain only our safe_bin folder
    new_env["PATH"] = str(temp_dir_path)
    
    return new_env


def run_claude(prompt: str, env: dict[str, str]) -> bool:
    """Invokes Claude Code in the restricted environment."""
    claude_path = shutil.which("claude")
    if not claude_path:
        # If 'claude' is not in the restricted PATH, find it in the host PATH
        claude_path = shutil.which("claude", path=os.environ.get("PATH"))
    
    if not claude_path:
        print("[-] Error: 'claude' command-line interface was not found.", file=sys.stderr)
        return False

    claude_cmd = [
        claude_path,
        "-p", prompt,
        "--permission-mode", "acceptEdits"
    ]

    print(f"[+] Launching Claude Code...")
    print(f"    Command: {' '.join(claude_cmd)}")
    
    # Run the process, keeping standard stdin/stdout connected for interactive TTY prompts
    process = subprocess.Popen(
        claude_cmd,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env
    )
    
    process.wait()
    return process.returncode == 0


def run_test_suite() -> bool:
    """Runs the post-execution test suite."""
    print("[+] Running test suite to verify system stability...")
    res = subprocess.run(TEST_COMMAND)
    return res.returncode == 0


def get_latest_error_prompt() -> tuple[str, Path] | None:
    """Finds the most recent patch_prompt_*.md in cache/failures/ and returns its content and path."""
    failures_dir = Path("./cache/failures")
    if not failures_dir.exists():
        return None
    prompts = list(failures_dir.glob("patch_prompt_*.md"))
    if not prompts:
        return None
    # Sort by modification time to find the latest
    prompts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest_prompt_path = prompts[0]
    try:
        content = latest_prompt_path.read_text(encoding="utf-8")
        return content, latest_prompt_path
    except Exception as e:
        print(f"[-] Error reading prompt file {latest_prompt_path}: {e}", file=sys.stderr)
        return None


def get_latest_failure_id() -> str | None:
    """Return the failure_id from the most recent patch_prompt_*.md filename, or None."""
    failures_dir = Path("./cache/failures")
    if not failures_dir.exists():
        return None
    prompts = list(failures_dir.glob("patch_prompt_*.md"))
    if not prompts:
        return None
    prompts.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # patch_prompt_<YYYYMMDD_HHMMSS>_<workflow>.md  →  <YYYYMMDD_HHMMSS>_<workflow>
    return prompts[0].stem.removeprefix("patch_prompt_")


def escalate_latest_failure(reason: str, suggested_action: str | None = None) -> int:
    """Write an escalation artifact + best-effort notify for the latest failure.

    Returns 0 on success (artifact written), 1 if no failure was found.
    """
    failure_id = get_latest_failure_id()
    if not failure_id:
        print(
            "[-] No recent failure found under cache/failures/ — nothing to escalate.",
            file=sys.stderr,
        )
        return 1

    workflow = failure_id.split("_", 2)[-1] if "_" in failure_id else None

    # Pull the traceback from the captured failure JSON if available.
    traceback_text: str | None = None
    failure_json = Path("./cache/failures") / f"failure_{failure_id}.json"
    if failure_json.exists():
        try:
            import json
            data = json.loads(failure_json.read_text(encoding="utf-8"))
            traceback_text = data.get("error", {}).get("traceback")
        except Exception:
            pass

    # Import lazily so this harness still runs in environments without
    # the full support package installed.
    sys.path.insert(0, str(Path("./scripts").resolve()))
    from support.email import escalate_to_dev  # noqa: WPS433

    path = escalate_to_dev(
        failure_id=failure_id,
        reason=reason,
        workflow=workflow,
        suggested_action=suggested_action,
        traceback_text=traceback_text,
    )
    print(f"[+] Escalation artifact: {path}")
    return 0


def orchestrate_self_healing(prompt: str, modified_before: list[str]) -> bool:
    """Orchestrates the sandbox environment execution, file audit, and test runs."""
    # Create temporary directory for restricted PATH
    with tempfile.TemporaryDirectory(prefix="claude_safe_bin_") as temp_dir:
        temp_dir_path = Path(temp_dir)
        restricted_env = setup_restricted_path(temp_dir_path)

        # 1. Run Claude Code inside the restricted sandbox environment
        success = run_claude(prompt, restricted_env)
        if not success:
            print("[-] Claude Code completed with errors or was interrupted.")

    # 2. Audit modified files
    modified_after = get_git_modified_files()
    new_modifications = [f for f in modified_after if f not in modified_before]

    unauthorized_edits = []
    for file in new_modifications:
        if not is_file_allowed(file):
            unauthorized_edits.append(file)

    if unauthorized_edits:
        print("\n[!] SECURITY ALERT: Claude attempted to edit files outside allowed directories!")
        revert_unauthorized_changes(unauthorized_edits)
        return False
    else:
        print("\n[+] Verification: All file modifications were within authorized directories.")

    # 3. Run validation tests
    test_success = run_test_suite()
    if test_success:
        print("\n[+] Success: Test suite passed successfully!")
        return True
    else:
        print("\n[-] Error: Test suite failed after edits.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Secure Claude Code Harness via Git-Guard and PATH isolation with self-healing."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("prompt", nargs="?", default=None, help="The prompt to feed to Claude Code")
    group.add_argument(
        "--latest-error",
        action="store_true",
        help="Find and resolve the latest generated self-healing prompt in cache/failures/"
    )
    group.add_argument(
        "--run-and-heal",
        metavar="COMMAND",
        help="Run a command, and if it fails, auto-heal using the captured failure state"
    )
    group.add_argument(
        "--escalate",
        metavar="REASON",
        help=(
            "Escalate the most recent captured failure to the developer "
            "(writes cache/failures/escalation_<id>.md and best-effort emails). "
            "Use only after ruling out logical fixes per principles.md §2."
        ),
    )
    parser.add_argument(
        "--suggested-action",
        metavar="TEXT",
        default=None,
        help="Optional concrete instruction for the developer (paired with --escalate).",
    )
    args = parser.parse_args()

    # --escalate exits without running Claude; no working-directory check needed.
    if args.escalate:
        sys.exit(escalate_latest_failure(args.escalate, args.suggested_action))

    # Pre-flight check: ensure clean working directory
    modified_before = get_git_modified_files()
    if modified_before:
        print("[!] Warning: You have uncommitted changes in your repository:")
        for f in modified_before:
            print(f"  - {f}")
        confirm = input("Do you want to proceed anyway? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            sys.exit(1)

    target_prompt = None

    if args.prompt:
        target_prompt = args.prompt
    elif args.latest_error:
        latest = get_latest_error_prompt()
        if not latest:
            print("[-] Error: No logged self-healing prompts were found in cache/failures/.", file=sys.stderr)
            sys.exit(1)
        target_prompt, prompt_path = latest
        print(f"[+] Found latest error prompt: {prompt_path.name}")
    elif args.run_and_heal:
        print(f"[+] Running command in monitored self-healing environment: {args.run_and_heal}")
        # Run command in project directory
        res = subprocess.run(args.run_and_heal, shell=True)
        if res.returncode == 0:
            print("[+] Command completed successfully! No self-healing required.")
            sys.exit(0)
            
        print(f"[-] Command failed with status {res.returncode}. Initiating self-healing...")
        # Brief pause to ensure OS writes files to cache/failures/
        import time
        time.sleep(0.5)
        
        latest = get_latest_error_prompt()
        if not latest:
            print("[-] Error: Command failed, but no self-healing prompt was found under cache/failures/.", file=sys.stderr)
            sys.exit(res.returncode)
            
        target_prompt, prompt_path = latest
        print(f"[+] Located self-healing prompt: {prompt_path.name}")

    if target_prompt:
        success = orchestrate_self_healing(target_prompt, modified_before)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
