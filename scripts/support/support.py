"""
Shared support module — logger, LLM helper, and re-exports of the typed
:class:`Database` / :class:`Table` / :class:`Record` API.

Importing ``support as s`` gives migration / action scripts everything they
need: ``s.log`` for logging, ``s.ask_llm`` for LLM extraction, and the
top-level types for callers that want to type-annotate function signatures.
"""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

from dotenv import load_dotenv

from .database import Database, Record, Table  # noqa: F401 — re-exported
from .prompt_user import prompt_user


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


# ---------------------------------------------------------------------------
# Custom VERBOSE level — sits below DEBUG (10) at level 5.
# Enabled only when LOG_LEVEL=verbose; invisible at info/warning/error.
# ---------------------------------------------------------------------------

VERBOSE: int = 5
logging.addLevelName(VERBOSE, "VERBOSE")


def _verbose(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    if self.isEnabledFor(VERBOSE):
        self._log(VERBOSE, message, args, **kwargs)


logging.Logger.verbose = _verbose  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# log.failure — error-level logging PLUS registration with the active
# self-healing handler. Use for any error that should trigger an agent-driven
# capture; reserve log.error for human-misuse errors (bad CLI args, etc.)
# raised outside any wrapped workflow. See plans/current/principles.md §2.
# ---------------------------------------------------------------------------

def _failure(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
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


logging.Logger.failure = _failure  # type: ignore[attr-defined]


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
log: logging.Logger = logging.getLogger("PadeaMigration")
log.setLevel(_log_level)


# ---------------------------------------------------------------------------
# LLM helper
# ---------------------------------------------------------------------------

def ask_llm(prompt: str) -> str | None:
    """Send a prompt to Claude (Anthropic SDK) or fall back to a Tk prompt.

    Returns the model's text response, or ``None`` if both routes fail.
    """
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        log.warning("No Claude or Anthropic API key found. LLM queries will try prompt the user.")
        return prompt_user(prompt)
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0]
        return getattr(block, "text", None)
    except Exception as e:
        log.error(f"Error calling Anthropic API: {e}")
        return None


__all__ = [
    "Database",
    "Record",
    "Table",
    "ask_llm",
    "log",
    "VERBOSE",
]
