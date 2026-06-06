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
from typing import Any, TypeVar

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

def ask_llm(prompt: str) -> str | None:
    """Send a prompt to Claude via the Claude CLI.

    Returns the model's text response, or ``None`` if the CLI call fails.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=500,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        log.error(f"Claude CLI returned exit code {result.returncode}: {result.stderr[:200]}")
        return None
    except FileNotFoundError:
        log.error("Claude CLI not found.")
        return None
    except Exception as e:
        log.error(f"Error calling Claude CLI: {e}")
        return None


T = TypeVar("T")

def _extract_llm_json(text: str) -> Any:
    """Strip markdown fences and return the first parseable JSON value, or raise ValueError."""
    import re as _re
    cleaned = _re.sub(r"```(?:json)?\n?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = _re.search(r"[\[{].*[\]}", cleaned, _re.DOTALL)
        if m:
            return json.loads(m.group(0))
    raise ValueError(f"No JSON found in LLM response: {cleaned[:200]!r}")


def ask_llm_json(prompt: str, response_type: "type[T]") -> "T | None":
    """Ask the LLM for a JSON response and validate it with Pydantic.

    Returns a validated model instance, or None if the LLM call fails or the
    response can't be parsed/validated.  ``response_type`` must be a
    ``pydantic.BaseModel`` subclass or a type accepted by ``pydantic.TypeAdapter``
    (e.g. ``list[SomeModel]``).
    """
    from pydantic import BaseModel, TypeAdapter, ValidationError

    text = ask_llm(prompt)
    if text is None:
        return None
    try:
        data = _extract_llm_json(text)
    except (ValueError, json.JSONDecodeError):
        log.warning(f"Could not parse LLM response as JSON: {text[:200]!r}")
        return None
    try:
        if isinstance(response_type, type) and issubclass(response_type, BaseModel):
            return response_type.model_validate(data)
        return TypeAdapter(response_type).validate_python(data)
    except ValidationError as exc:
        log.warning(f"LLM response failed Pydantic validation ({response_type.__name__ if hasattr(response_type, '__name__') else response_type}): {exc}")
        return None


__all__ = [
    "Database",
    "Record",
    "Table",
    "ask_llm",
    "ask_llm_json",
    "log",
    "VERBOSE",
]
