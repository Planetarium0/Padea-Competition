"""
Database — thin, typed wrapper around the pyairtable client.

Replaces the old free functions (``get_table``, ``airtable_get``,
``airtable_post``, ``clear_table``) with a single object whose properties
expose each Airtable table as a strongly-typed :class:`Table`.

Usage::

    from support import Database

    db = Database.from_env()
    sessions = db.Sessions.all()        # list[Record[SessionFields]]
    db.Caterers.create([{"Caterer Name": "Foo", "Region": "Redlands"}])
    db.Orders.clear()
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Generic, Iterable, Mapping, TypeVar, cast

from pyairtable import Api
from pyairtable.api.base import Base as PyAirtableBase
from pyairtable.api.table import Table as PyAirtableTable

from .records import (
    AbsenceFields,
    CatererFeedbackFields,
    CatererFields,
    CatererSwitchProposalFields,
    DietaryRestrictionFields,
    ExclusionFields,
    MenuItemFields,
    OnSiteManagerFields,
    OrderFields,
    SchoolFields,
    ScheduledEmailFields,
    SessionFields,
    StudentFields,
    WeeklyOrderFields,
)

FieldsT = TypeVar("FieldsT", bound=Mapping[str, Any])

_log = logging.getLogger("PadeaMigration")

# Airtable's REST API rejects batches larger than 10 records per request.
_BATCH_SIZE = 10


@dataclass(frozen=True)
class Record(Generic[FieldsT]):
    """A read-only Airtable record envelope with typed ``fields``.

    Construct via :meth:`from_raw` when adapting a raw pyairtable dict; the
    dataclass form gives callers ``record.id`` / ``record.fields`` instead of
    ``record["id"]`` / ``record["fields"]``.
    """

    id: str
    fields: FieldsT

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> "Record[FieldsT]":
        return cls(id=raw["id"], fields=cast(FieldsT, raw.get("fields", {})))


class Table(Generic[FieldsT]):
    """Typed wrapper around a single pyairtable ``Table``.

    The TypedDict parameter is purely a static hint — the runtime simply
    forwards dicts to pyairtable as-is.
    """

    def __init__(self, raw_table: PyAirtableTable) -> None:
        self._raw = raw_table

    @property
    def name(self) -> str:
        return self._raw.name

    @property
    def raw(self) -> PyAirtableTable:
        """Escape hatch for pyairtable APIs not surfaced on :class:`Table`."""
        return self._raw

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all(self, formula: str | None = None) -> list[Record[FieldsT]]:
        try:
            raw = self._raw.all(formula=formula) if formula else self._raw.all()
        except Exception as e:
            _log.error(f"Error fetching from Airtable table {self.name}: {e}")
            return []
        return [Record[FieldsT].from_raw(r) for r in raw]

    def get(self, record_id: str) -> Record[FieldsT] | None:
        try:
            raw = self._raw.get(record_id)
        except Exception as e:
            _log.error(f"Error fetching record {record_id} from {self.name}: {e}")
            return None
        if not raw:
            return None
        return Record[FieldsT].from_raw(raw)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self,
        records: Iterable[FieldsT | Mapping[str, Any]],
    ) -> list[Record[FieldsT]]:
        """Batch-create records. Accepts plain field dicts; ``{"fields": ...}``
        envelopes are unwrapped for compatibility with the old API."""
        formatted: list[Mapping[str, Any]] = []
        for r in records:
            if isinstance(r, dict) and "fields" in r and set(r.keys()) <= {"fields"}:
                formatted.append(r["fields"])
            else:
                formatted.append(r)
        if not formatted:
            return []

        inserted: list[Record[FieldsT]] = []
        for i in range(0, len(formatted), _BATCH_SIZE):
            batch = formatted[i:i + _BATCH_SIZE]
            try:
                # pyairtable expects a more restrictive payload type than
                # Mapping[str, Any]; in practice any JSON-serializable dict
                # works at runtime.
                res = self._raw.batch_create(cast(Any, batch))
            except Exception as e:
                _log.error(f"Error posting batch to table {self.name}: {e}")
                raise
            inserted.extend(Record[FieldsT].from_raw(r) for r in res)
        return inserted

    def update(self, record_id: str, fields: Mapping[str, Any]) -> Record[FieldsT]:
        raw = self._raw.update(record_id, dict(fields))
        return Record[FieldsT].from_raw(raw)

    def batch_update(
        self,
        updates: Iterable[Mapping[str, Any]],
    ) -> list[Record[FieldsT]]:
        """Batch-update records. Each entry should be ``{"id": ..., "fields": ...}``."""
        updates_list = list(updates)
        if not updates_list:
            return []
        results: list[Record[FieldsT]] = []
        for i in range(0, len(updates_list), _BATCH_SIZE):
            batch = updates_list[i:i + _BATCH_SIZE]
            res = self._raw.batch_update(cast(Any, batch))
            results.extend(Record[FieldsT].from_raw(r) for r in res)
        return results

    def delete(self, record_id: str) -> None:
        self._raw.delete(record_id)

    def batch_delete(self, record_ids: Iterable[str]) -> None:
        ids = list(record_ids)
        for i in range(0, len(ids), _BATCH_SIZE):
            self._raw.batch_delete(ids[i:i + _BATCH_SIZE])

    def clear(self) -> None:
        """Delete every record in the table. Logged at INFO; failures warn-only."""
        try:
            records = self._raw.all()
            if not records:
                return
            ids = [r["id"] for r in records]
            _log.info(f"Clearing {len(ids)} records from {self.name}")
            self.batch_delete(ids)
        except Exception as e:
            _log.warning(f"Failed to clear table {self.name}: {e}")


class Database:
    """Strongly-typed view over the Padea Airtable base.

    Construct directly with explicit credentials, or via :meth:`from_env`
    which reads ``AIRTABLE_API_KEY`` and ``AIRTABLE_ID`` from the
    environment.
    """

    def __init__(self, api_key: str, base_id: str) -> None:
        self._api = Api(api_key)
        self._base = self._api.base(base_id)
        self._cache: dict[str, Table[Any]] = {}

    @classmethod
    def from_env(cls) -> "Database":
        api_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_ID")
        if not api_key or not base_id:
            raise RuntimeError(
                "Missing Airtable configuration. Set AIRTABLE_API_KEY and "
                "AIRTABLE_ID in .env or the process environment."
            )
        return cls(api_key, base_id)

    @property
    def base(self) -> PyAirtableBase:
        """Raw pyairtable ``Base`` — only used by schema-management code."""
        return self._base

    def _table(self, name: str) -> Table[Any]:
        if name not in self._cache:
            self._cache[name] = Table(self._base.table(name))
        return self._cache[name]

    # ------------------------------------------------------------------
    # Table properties (one per Airtable table)
    # ------------------------------------------------------------------

    @property
    def Schools(self) -> Table[SchoolFields]:
        return self._table("Schools")

    @property
    def OnSiteManagers(self) -> Table[OnSiteManagerFields]:
        return self._table("On-Site Managers")

    @property
    def Caterers(self) -> Table[CatererFields]:
        return self._table("Caterers")

    @property
    def MenuItems(self) -> Table[MenuItemFields]:
        return self._table("Menu Items")

    @property
    def DietaryRestrictions(self) -> Table[DietaryRestrictionFields]:
        return self._table("Dietary Restrictions")

    @property
    def Students(self) -> Table[StudentFields]:
        return self._table("Students")

    @property
    def Sessions(self) -> Table[SessionFields]:
        return self._table("Sessions")

    @property
    def Absences(self) -> Table[AbsenceFields]:
        return self._table("Absences")

    @property
    def Exclusions(self) -> Table[ExclusionFields]:
        return self._table("Exclusions")

    @property
    def CatererFeedback(self) -> Table[CatererFeedbackFields]:
        return self._table("Caterer Feedback")

    @property
    def WeeklyOrders(self) -> Table[WeeklyOrderFields]:
        return self._table("Weekly Orders")

    @property
    def Orders(self) -> Table[OrderFields]:
        return self._table("Orders")

    @property
    def ScheduledEmails(self) -> Table[ScheduledEmailFields]:
        return self._table("Scheduled Emails")

    @property
    def CatererSwitchProposals(self) -> Table[CatererSwitchProposalFields]:
        return self._table("Caterer Switch Proposals")


__all__ = ["Database", "Record", "Table"]
