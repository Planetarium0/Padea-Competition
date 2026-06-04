"""
Database — thin, typed wrapper around the supabase-py client.

Provides ``Record``, ``Table``, and ``Database`` with the same public interface
as the previous Airtable implementation so all existing callers need only minor
updates (field name accesses and formula → filter callables).

Usage::

    from support import Database

    db = Database.from_env()
    sessions = db.Sessions.all()            # list[Record[SessionFields]]
    db.Caterers.create([{"name": "Foo", "region": "Redlands"}])
    db.Orders.clear()

Filter syntax (replaces Airtable formula strings)::

    db.Orders.all(filter=lambda q: q.gte("date", "2024-01-08").lte("date", "2024-01-14"))
    db.Students.all(filter=lambda q: q.in_("id", student_ids))
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, Mapping, TypeVar, cast

from supabase import Client, create_client

from .schemas import MODEL_MAP
from .records import (
    AbsenceFields,
    CatererFeedbackFields,
    CatererFields,
    CatererSwitchProposalFields,
    DietaryClarificationRequestFields,
    DietaryRestrictionFields,
    ExclusionFields,
    ManagerSubstitutionFields,
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

_log = logging.getLogger("PadeaDatabase")

# Tables that have aggregated views (used for reads).
# Maps write-table-name → read-view-name.
_VIEW_MAP: dict[str, str] = {
    "students":            "students_view",
    "sessions":            "sessions_view",
    "caterers":            "caterers_view",
    "menu_items":          "menu_items_view",
    "dietary_restrictions": "dietary_restrictions_view",
    "orders":              "orders_view",
    "exclusions":          "exclusions_view",
}

# Junction table config: for each parent table, the list-typed fields that
# map to junction tables.  Each entry is (field_name, junction_table, parent_fk, child_fk).
_JUNCTION_MAP: dict[str, list[tuple[str, str, str, str]]] = {
    "students": [
        ("dietary_requirement_ids", "student_dietary_restrictions", "student_id", "restriction_id"),
        ("session_ids",             "student_sessions",              "student_id", "session_id"),
    ],
    "sessions": [
        ("year_levels", "session_year_levels", "session_id", "year_level"),
    ],
    "caterers": [
        ("legend_tag_ids",            "caterer_legend_tags", "caterer_id", "restriction_id"),
        ("able_to_serve_school_ids",  "caterer_schools",     "caterer_id", "school_id"),
    ],
    "menu_items": [
        ("dietary_tag_ids", "menu_item_dietary_tags", "menu_item_id", "restriction_id"),
    ],
    "dietary_restrictions": [
        ("superset_ids", "dietary_restriction_supersets", "restriction_id", "superset_id"),
    ],
    "orders": [
        ("student_ids", "order_students", "order_id", "student_id"),
    ],
    "exclusions": [
        ("year_levels", "exclusion_year_levels", "exclusion_id", "year_level"),
    ],
}

# Fields that exist in the view but not in the underlying table (view-only fields)
_VIEW_ONLY_FIELDS: dict[str, set[str]] = {
    "students":            {"dietary_requirement_ids", "session_ids"},
    "sessions":            {"year_levels"},
    "caterers":            {"legend_tag_ids", "able_to_serve_school_ids"},
    "menu_items":          {"dietary_tag_ids"},
    "dietary_restrictions": {"superset_ids", "subset_ids"},
    "orders":              {"student_ids"},
    "exclusions":          {"year_levels"},
}


@dataclass(frozen=True)
class Record(Generic[FieldsT]):
    """A read-only database record envelope with typed ``fields``."""

    id: str
    fields: FieldsT

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Record[FieldsT]":
        return cls(id=row["id"], fields=cast(FieldsT, dict(row)))


class Table(Generic[FieldsT]):
    """Typed wrapper around a single Supabase table/view pair."""

    def __init__(self, client: Client, table_name: str) -> None:
        self._client = client
        self._table = table_name
        self._view = _VIEW_MAP.get(table_name, table_name)
        self._junction_fields = _JUNCTION_MAP.get(table_name, [])
        self._view_only = _VIEW_ONLY_FIELDS.get(table_name, set())

    @property
    def name(self) -> str:
        return self._table

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all(
        self,
        filter: Callable[[Any], Any] | None = None,
    ) -> list["Record[FieldsT]"]:
        try:
            query = self._client.table(self._view).select("*")
            if filter is not None:
                query = filter(query)
            result = query.execute()
        except Exception as e:
            _log.failure("Error fetching from %s: %s", self._view, e)
            return []

        model = MODEL_MAP.get(self._table)
        records: list[Record[FieldsT]] = []
        for row in result.data:
            if model:
                model.model_validate(row)
            records.append(Record.from_row(row))
        return records

    def get(self, record_id: str) -> "Record[FieldsT] | None":
        try:
            result = (
                self._client.table(self._view)
                .select("*")
                .eq("id", record_id)
                .limit(1)
                .execute()
            )
        except Exception as e:
            _log.failure("Error fetching %s from %s: %s", record_id, self._view, e)
            return None
        if not result.data:
            return None

        model = MODEL_MAP.get(self._table)
        row = result.data[0]
        if model:
            model.model_validate(row)
        return Record.from_row(row)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def create(
        self,
        records: Iterable[FieldsT | Mapping[str, Any]],
    ) -> list["Record[FieldsT]"]:
        records_list = list(records)
        if not records_list:
            return []

        model = MODEL_MAP.get(self._table)

        inserted: list[Record[FieldsT]] = []
        for fields in records_list:
            fields = dict(fields)
            if model:
                model.model_validate(fields)

            # Strip view-only / junction fields from the main insert payload
            junction_data = self._extract_junction_fields(fields)
            main_fields = {k: v for k, v in fields.items() if k not in self._view_only}

            try:
                result = self._client.table(self._table).insert(main_fields).execute()
            except Exception as e:
                _log.error("Error inserting into %s: %s", self._table, e)
                raise
            row = result.data[0]
            row_id = row["id"]

            # Write junction rows
            self._write_junction_rows(row_id, junction_data)

            # Re-fetch through view to get aggregated fields
            full = self.get(row_id)
            if full:
                inserted.append(full)
        return inserted

    def update(self, record_id: str, fields: Mapping[str, Any]) -> "Record[FieldsT]":
        fields = dict(fields)
        model = MODEL_MAP.get(self._table)
        if model:
            model.model_validate(fields)

        junction_data = self._extract_junction_fields(fields)
        main_fields = {k: v for k, v in fields.items() if k not in self._view_only}

        if main_fields:
            self._client.table(self._table).update(main_fields).eq("id", record_id).execute()

        # Replace junction rows where lists were provided
        for field_name, junction_table, parent_fk, child_fk in self._junction_fields:
            if field_name in junction_data:
                self._client.table(junction_table).delete().eq(parent_fk, record_id).execute()
                rows = [
                    {parent_fk: record_id, child_fk: val}
                    for val in junction_data[field_name]
                ]
                if rows:
                    self._client.table(junction_table).insert(rows).execute()

        result = self.get(record_id)
        if result is None:
            raise RuntimeError(f"Record {record_id} not found after update in {self._table}")
        return result

    def batch_update(
        self,
        updates: Iterable[Mapping[str, Any]],
    ) -> list["Record[FieldsT]"]:
        results: list[Record[FieldsT]] = []
        for entry in updates:
            entry = dict(entry)
            record_id = entry.pop("id")
            results.append(self.update(record_id, entry))
        return results

    def delete(self, record_id: str) -> None:
        self._client.table(self._table).delete().eq("id", record_id).execute()

    def batch_delete(self, record_ids: Iterable[str]) -> None:
        ids = list(record_ids)
        if not ids:
            return
        self._client.table(self._table).delete().in_("id", ids).execute()

    def clear(self) -> None:
        try:
            result = self._client.table(self._table).select("id").execute()
            if not result.data:
                return
            ids = [r["id"] for r in result.data]
            _log.info("Clearing %d records from %s", len(ids), self._table)
            self.batch_delete(ids)
        except Exception as e:
            _log.warning("Failed to clear table %s: %s", self._table, e)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_junction_fields(
        self, fields: dict[str, Any]
    ) -> dict[str, list[Any]]:
        """Pop view-only junction fields from fields dict; return them separately."""
        junction: dict[str, list[Any]] = {}
        for field_name, _, _, _ in self._junction_fields:
            if field_name in fields:
                junction[field_name] = fields.pop(field_name)
        return junction

    def _write_junction_rows(
        self, record_id: str, junction_data: dict[str, list[Any]]
    ) -> None:
        for field_name, junction_table, parent_fk, child_fk in self._junction_fields:
            if field_name not in junction_data:
                continue
            rows = [
                {parent_fk: record_id, child_fk: val}
                for val in junction_data[field_name]
            ]
            if rows:
                self._client.table(junction_table).insert(rows).execute()


class Database:
    """Strongly-typed view over the Padea Supabase database.

    Construct directly or via :meth:`from_env` which reads
    ``SUPABASE_URL`` and ``SUPABASE_SERVICE_KEY`` from the environment.
    The service key is used so Python backend scripts bypass RLS.
    """

    def __init__(self, url: str, key: str) -> None:
        self._client: Client = create_client(url, key)
        self._cache: dict[str, Table[Any]] = {}

    @classmethod
    def from_env(cls) -> "Database":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError(
                "Missing Supabase configuration. Set SUPABASE_URL and "
                "SUPABASE_SERVICE_KEY in .env or the process environment."
            )
        return cls(url, key)

    def _table(self, name: str) -> Table[Any]:
        if name not in self._cache:
            self._cache[name] = Table(self._client, name)
        return self._cache[name]

    # ------------------------------------------------------------------
    # Table properties (one per database table)
    # ------------------------------------------------------------------

    @property
    def Schools(self) -> Table[SchoolFields]:
        return self._table("schools")

    @property
    def OnSiteManagers(self) -> Table[OnSiteManagerFields]:
        return self._table("on_site_managers")

    @property
    def Caterers(self) -> Table[CatererFields]:
        return self._table("caterers")

    @property
    def MenuItems(self) -> Table[MenuItemFields]:
        return self._table("menu_items")

    @property
    def DietaryRestrictions(self) -> Table[DietaryRestrictionFields]:
        return self._table("dietary_restrictions")

    @property
    def Students(self) -> Table[StudentFields]:
        return self._table("students")

    @property
    def Sessions(self) -> Table[SessionFields]:
        return self._table("sessions")

    @property
    def Absences(self) -> Table[AbsenceFields]:
        return self._table("absences")

    @property
    def Exclusions(self) -> Table[ExclusionFields]:
        return self._table("exclusions")

    @property
    def CatererFeedback(self) -> Table[CatererFeedbackFields]:
        return self._table("caterer_feedback")

    @property
    def WeeklyOrders(self) -> Table[WeeklyOrderFields]:
        return self._table("weekly_orders")

    @property
    def Orders(self) -> Table[OrderFields]:
        return self._table("orders")

    @property
    def ScheduledEmails(self) -> Table[ScheduledEmailFields]:
        return self._table("scheduled_emails")

    @property
    def ManagerSubstitutions(self) -> Table[ManagerSubstitutionFields]:
        return self._table("manager_substitutions")

    @property
    def CatererSwitchProposals(self) -> Table[CatererSwitchProposalFields]:
        return self._table("caterer_switch_proposals")

    @property
    def DietaryClarificationRequests(self) -> Table[DietaryClarificationRequestFields]:
        return self._table("dietary_clarification_requests")


# ---------------------------------------------------------------------------
# Manager resolution helpers
# ---------------------------------------------------------------------------

def load_substitutions(
    db: Database,
    date_from: str,
    date_to: str,
) -> dict[tuple[str, str], str]:
    """Return a (session_id, date) → substitute_manager_id mapping.

    Queries manager_substitutions for the given inclusive date range so
    callers can resolve effective managers for an entire week in one round-trip.
    """
    subs = db.ManagerSubstitutions.all(
        filter=lambda q: q.gte("date", date_from).lte("date", date_to)
    )
    result: dict[tuple[str, str], str] = {}
    for sub in subs:
        session_id = sub.fields.get("session_id")
        date       = sub.fields.get("date")
        mgr_id     = sub.fields.get("substitute_manager_id")
        if session_id and date and mgr_id:
            result[(session_id, date)] = mgr_id
    return result


def resolve_manager_id(
    session_id:     str,
    session_fields: SessionFields,
    date_str:       str | None,
    substitutions:  dict[tuple[str, str], str],
) -> tuple[str | None, bool]:
    """Return the effective on-site manager ID and whether it is a substitute.

    Checks *substitutions* (keyed by (session_id, date)) first. Falls back to
    the session's permanent on_site_manager_id. Returns (None, False) when no
    manager is set at all.
    """
    if date_str:
        sub_id = substitutions.get((session_id, date_str))
        if sub_id:
            return sub_id, True
    return session_fields.get("on_site_manager_id"), False


__all__ = [
    "Database",
    "Record",
    "Table",
    "load_substitutions",
    "resolve_manager_id",
]
