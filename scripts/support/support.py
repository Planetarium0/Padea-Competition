"""
Shared support module — logger, LLM helper, and re-exports of the typed
:class:`Database` / :class:`Table` / :class:`Record` API.

Importing ``support as s`` gives migration / action scripts everything they
need: ``s.log`` for logging, ``s.ask_llm`` for LLM extraction, and the
top-level types for callers that want to type-annotate function signatures.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .database import Database, Record, Table  # noqa: F401 — re-exported


# ---------------------------------------------------------------------------
# Active self-healing handler — read by log.failure to register soft errors
# with the currently-wrapped workflow. ContextVar (not a thread-local) so
# nested handlers and future async code both work.
# ---------------------------------------------------------------------------

# Holds the active ``self_healing_error_handler`` instance (or ``None`` outside
# any wrapped workflow). Typed as ``Any`` because the handler class lives in a
# sibling module that imports back from here; using the concrete type would
# require a forward reference and adds nothing at runtime.
_active_handler: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "_active_handler", default=None
)

# Initialise dotenv first so LOG_LEVEL can be read from .env.
load_dotenv()


VERBOSE: int = 5
logging.addLevelName(VERBOSE, "VERBOSE")


class CustomLogger(logging.Logger):
    # ---------------------------------------------------------------------------
    # Custom VERBOSE level — sits below DEBUG (10) at level 5.
    # Enabled only when LOG_LEVEL=verbose; invisible at info/warning/error.
    # ---------------------------------------------------------------------------

    def verbose(self, message: str, *args: Any, **kwargs: Any) -> None:
        if self.isEnabledFor(VERBOSE):
            self._log(VERBOSE, message, args, **kwargs)

    # ---------------------------------------------------------------------------
    # log.failure — error-level logging PLUS registration with the active
    # self-healing handler. Use for any error that should trigger an agent-driven
    # capture; reserve log.error for human-misuse errors (bad CLI args, etc.)
    # raised outside any wrapped workflow. See plans/current/principles.md §2.
    # ---------------------------------------------------------------------------

    def failure(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log at ERROR and register with the active self_healing_error_handler.

        Execution continues exactly as ``log.error`` would — only the capture
        behaviour changes. Outside a wrapped workflow the registration is a
        no-op, so calling ``log.failure`` from helper code (migrations, REPL)
        is always safe.
        """
        self.error(message, *args, **kwargs)
        try:
            formatted = message % args if args else message
        except Exception:
            formatted = message
        handler = _active_handler.get()
        if handler is not None:
            handler.register_failure(formatted)



logging.Logger.verbose = CustomLogger.verbose  # type: ignore[attr-defined]
logging.Logger.failure = CustomLogger.failure  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Resolve level from LOG_LEVEL env var.
# Accepted values (case-insensitive): verbose, info, warning, error
# ---------------------------------------------------------------------------

_LOG_LEVEL_MAP: dict[str, int] = {
    "verbose": VERBOSE,
    "info":    logging.INFO,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
}
_log_level: int = _LOG_LEVEL_MAP.get(
    os.environ.get("LOG_LEVEL", "info").lower(),
    logging.INFO,
)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log: CustomLogger = logging.getLogger("PadeaMigration")  # type: ignore
log.setLevel(_log_level)


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

_LLM_LOG_FILE = Path(__file__).parents[2] / "cache" / "llm_logs" / "llm_calls.jsonl"


def _log_llm_call(prompt: str, response: str | None, thinking: str | None, source: str) -> None:
    _LLM_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "prompt": prompt,
        "thinking": thinking,
        "response": response,
    }
    with _LLM_LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def ask_llm(prompt: str) -> str | None:
    """Send a prompt to Claude via the Anthropic SDK, or fall back to the Claude CLI.

    Returns the model's text response, or ``None`` if both routes fail.
    Logs every call (prompt, thinking, response) to cache/llm_logs/llm_calls.jsonl.
    """
    import subprocess

    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=key)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            text: str | None = None
            thinking_text: str | None = None
            for block in response.content:
                if block.type == "thinking":
                    thinking_text = getattr(block, "thinking", None)
                elif block.type == "text":
                    text = getattr(block, "text", None)
            _log_llm_call(prompt, text, thinking_text, source="api")
            return text
        except Exception as e:
            log.error(f"Error calling Anthropic API: {e}")
            _log_llm_call(prompt, None, None, source="api-error")
            return None
    else:
        log.warning("No Claude or Anthropic API key found. Falling back to Claude CLI.")
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                text = result.stdout.strip() or None
                _log_llm_call(prompt, text, None, source="cli")
                return text
            log.error(f"Claude CLI returned exit code {result.returncode}: {result.stderr[:200]}")
            _log_llm_call(prompt, None, None, source="cli-error")
            return None
        except FileNotFoundError:
            log.error("Claude CLI not found. Install it or set ANTHROPIC_API_KEY.")
            _log_llm_call(prompt, None, None, source="cli-missing")
            return None
        except Exception as e:
            log.failure(f"Error calling Claude CLI: {e}")
            _log_llm_call(prompt, None, None, source="cli-error")
            return None


def ask_llm_with_tools(
    prompt: str,
    system: str,
    executor: Any,          # callable (tool_name, tool_input) -> str
    tools: list[dict],
    *,
    parent_email: str | None = None,
    case_id: str | None = None,
) -> bool | None:
    """Run a multi-turn LLM conversation with tool calling.

    Uses the Anthropic SDK when an API key is present (SDK path), or falls back
    to the Claude CLI with an MCP server (CLI path) when no key is found.

    Returns ``True`` on success, ``None`` on total failure.
    Logs every call to cache/llm_logs/llm_calls.jsonl (source "api-tools" / "cli-mcp").
    """
    import json as _json
    import subprocess

    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    logged_prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}"

    if key:
        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=key)
            messages: list[dict] = [{"role": "user", "content": prompt}]
            tool_call_log: list[dict] = []
            response = None

            while True:
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4000,
                    system=system,
                    messages=messages,
                    tools=tools,
                )
                messages.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        tool_result = executor(block.name, block.input)
                        tool_call_log.append({
                            "tool": block.name,
                            "input": block.input,
                            "result": tool_result,
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": tool_result,
                        })

                if not tool_results:
                    break  # no more tool calls, done

                messages.append({"role": "user", "content": tool_results})

            final_text: str | None = None
            if response is not None:
                for block in response.content:
                    if hasattr(block, "text"):
                        final_text = block.text
                        break
            response_log = _json.dumps({"tool_calls": tool_call_log, "final_text": final_text})
            _log_llm_call(logged_prompt, response_log, None, source="api-tools")
            return True

        except Exception as e:
            log.error(f"Error calling Anthropic API (with tools): {e}")
            _log_llm_call(logged_prompt, None, None, source="api-tools-error")
            return None

    # ------------------------------------------------------------------
    # CLI path — Claude CLI with MCP server
    # ------------------------------------------------------------------
    log.warning("No Claude or Anthropic API key found. Falling back to Claude CLI (MCP).")

    import os as _os
    import tempfile

    mcp_server = Path(__file__).resolve().parent / "mcp_server.py"
    python = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as log_f:
        log_path = log_f.name

    config = {
        "mcpServers": {
            "padea-support": {
                "command": str(python),
                "args": [
                    str(mcp_server),
                    "--parent-email", parent_email or "",
                    "--case-id", case_id or "",
                    "--log-file", log_path,
                ],
            }
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as cfg_f:
        _json.dump(config, cfg_f)
        cfg_path = cfg_f.name

    try:
        result = subprocess.run(
            ["claude", "-p", f"{system}\n\n{prompt}", "--mcp-config", cfg_path],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            log.error(
                f"Claude CLI (MCP) returned {result.returncode}: {result.stderr[:200]}"
            )
            _log_llm_call(logged_prompt, None, None, source="cli-mcp-error")
            return None

        # Read back the tool log and replay send_reply to update executor state
        tool_calls: list[dict] = []
        try:
            with open(log_path) as f:
                log_data = _json.load(f)
            tool_calls = log_data.get("tool_calls", [])
            for entry in tool_calls:
                if entry["tool"] == "send_reply":
                    executor.reply_sent[0] = True
        except Exception:
            pass

        final_text = result.stdout.strip() or None
        response_log = _json.dumps({"tool_calls": tool_calls, "final_text": final_text})
        _log_llm_call(logged_prompt, response_log, None, source="cli-mcp")
        return True

    except FileNotFoundError:
        log.error("Claude CLI not found. Install it or set ANTHROPIC_API_KEY.")
        _log_llm_call(logged_prompt, None, None, source="cli-mcp-missing")
        return None
    except Exception as e:
        log.failure(f"Error calling Claude CLI (MCP): {e}")
        _log_llm_call(logged_prompt, None, None, source="cli-mcp-error")
        return None
    finally:
        try:
            _os.unlink(cfg_path)
        except FileNotFoundError:
            pass
        try:
            _os.unlink(log_path)
        except FileNotFoundError:
            pass


__all__ = [
    "Database",
    "Record",
    "Table",
    "ask_llm",
    "ask_llm_with_tools",
    "log",
    "VERBOSE",
]
