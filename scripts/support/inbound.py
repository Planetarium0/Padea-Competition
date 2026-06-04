"""Inbound email adapter for dietary clarification replies.

The Protocol allows swapping the backend (e.g. SupabaseInboundInbox today,
Postmark / Mailgun / Gmail tomorrow) without touching the poller.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .database import Database


@dataclass
class InboundMessage:
    message_id: str          # email Message-ID header (used for mark_seen)
    in_reply_to: str | None  # email In-Reply-To header
    subject: str | None
    from_address: str
    body_text: str | None
    received_at: datetime.datetime
    request_code: str | None  # extracted from to_address local part


class InboundMailbox(Protocol):
    def fetch_new(self, since: datetime.datetime) -> list[InboundMessage]: ...
    def mark_seen(self, message_id: str) -> None: ...


def extract_request_code(to_address: str | None) -> str | None:
    """Extract request code from dietary-<request_code>@reply.<domain>."""
    if not to_address:
        return None
    local, _, _ = to_address.partition("@")
    prefix = "dietary-"
    if not local.startswith(prefix):
        return None
    code = local[len(prefix):]
    return code or None


class SupabaseInboundInbox:
    """Reads dietary_inbound_messages via the Database wrapper."""

    def __init__(self, db: "Database") -> None:
        self._db = db

    def fetch_new(self, since: datetime.datetime) -> list[InboundMessage]:
        since_str = since.isoformat()
        rows = self._db.DietaryInboundMessages.all(
            filter=lambda q: q.eq("seen", False).gte("received_at", since_str)
        )
        messages: list[InboundMessage] = []
        for row in rows:
            f = row.fields
            raw_ts = f.get("received_at")
            if isinstance(raw_ts, str):
                received_at = datetime.datetime.fromisoformat(
                    raw_ts.replace("Z", "+00:00")
                )
            else:
                received_at = datetime.datetime.now(datetime.timezone.utc)
            messages.append(InboundMessage(
                message_id=f.get("message_id") or row.id,
                in_reply_to=f.get("in_reply_to"),
                subject=f.get("subject"),
                from_address=f.get("from_address", ""),
                body_text=f.get("body_text"),
                received_at=received_at,
                request_code=extract_request_code(f.get("to_address")),
            ))
        return messages

    def mark_seen(self, message_id: str) -> None:
        rows = self._db.DietaryInboundMessages.all(
            filter=lambda q: q.eq("message_id", message_id)
        )
        for row in rows:
            if row.fields.get("message_id") == message_id:
                self._db.DietaryInboundMessages.update(row.id, {"seen": True})


__all__ = [
    "InboundMessage",
    "InboundMailbox",
    "SupabaseInboundInbox",
    "extract_request_code",
]
