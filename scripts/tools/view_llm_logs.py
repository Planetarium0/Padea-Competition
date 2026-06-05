#!/usr/bin/env python3
"""Interactive viewer for cache/llm_logs/llm_calls.jsonl."""

import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).parents[2] / "cache" / "llm_logs" / "llm_calls.jsonl"
SEPARATOR = "─" * 80


def _load_entries() -> list[dict]:
    if not LOG_PATH.exists():
        print(f"[ERROR] Log file not found: {LOG_PATH}", file=sys.stderr)
        sys.exit(1)
    entries = []
    with LOG_PATH.open() as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[WARN] Skipping malformed line {lineno}: {exc}", file=sys.stderr)
    return entries


def _fmt_timestamp(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return raw


def _prompt_snippet(prompt: str, width: int = 72) -> str:
    first_line = prompt.strip().splitlines()[0] if prompt.strip() else ""
    return first_line[:width] + ("…" if len(first_line) > width else "")


def _print_menu(entries: list[dict]) -> None:
    print(f"\n  {'#':>3}  {'Timestamp':<22}  {'Source':<8}  Prompt")
    print(f"  {'─'*3}  {'─'*22}  {'─'*8}  {'─'*44}")
    for i, e in enumerate(entries):
        ts = _fmt_timestamp(e.get("timestamp", ""))
        source = e.get("source", "?")[:8]
        snippet = _prompt_snippet(e.get("prompt", ""), 44)
        print(f"  {i:>3}  {ts:<22}  {source:<8}  {snippet}")
    print()


def _wrap(text: str, indent: int = 0) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=100, initial_indent=prefix, subsequent_indent=prefix)


def _print_entry(entry: dict, index: int) -> None:
    ts = _fmt_timestamp(entry.get("timestamp", ""))
    source = entry.get("source", "?")
    print(f"\n{SEPARATOR}")
    print(f"  Entry #{index}  |  {ts}  |  source: {source}")
    print(SEPARATOR)

    prompt = entry.get("prompt", "").strip()
    print("\n── PROMPT " + "─" * 70)
    print(prompt)

    thinking = entry.get("thinking", "").strip() if entry.get("thinking") else ""
    if thinking:
        print("\n── THINKING " + "─" * 68)
        print(thinking)

    response = entry.get("response", "")
    if isinstance(response, dict):
        response_text = json.dumps(response, indent=2)
    else:
        response_text = str(response).strip()
    print("\n── RESPONSE " + "─" * 68)
    print(response_text)
    print(f"\n{SEPARATOR}\n")


def main() -> None:
    entries = _load_entries()
    if not entries:
        print("No log entries found.")
        sys.exit(0)

    # Non-interactive: single index passed as argument
    if len(sys.argv) == 2:
        try:
            idx = int(sys.argv[1])
        except ValueError:
            print(f"[ERROR] Expected an integer index, got: {sys.argv[1]}", file=sys.stderr)
            sys.exit(1)
        if not (0 <= idx < len(entries)):
            print(f"[ERROR] Index {idx} out of range (0–{len(entries)-1})", file=sys.stderr)
            sys.exit(1)
        _print_entry(entries[idx], idx)
        return

    # Interactive loop
    while True:
        _print_menu(entries)
        try:
            raw = input(f"Enter entry number (0–{len(entries)-1}), or 'q' to quit: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if raw.lower() in ("q", "quit", "exit"):
            break
        try:
            idx = int(raw)
        except ValueError:
            print(f"  [!] Not a number: {raw!r}\n")
            continue
        if not (0 <= idx < len(entries)):
            print(f"  [!] {idx} is out of range (0–{len(entries)-1})\n")
            continue

        _print_entry(entries[idx], idx)

        try:
            again = input("View another? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if again not in ("y", "yes"):
            break


if __name__ == "__main__":
    main()
