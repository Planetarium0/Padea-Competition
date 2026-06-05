"""
MockTable and MockDatabase for testing Padea action scripts without
connecting to Supabase. Every write is tracked on the table object so
tests can assert on what was created, updated, or deleted.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from support import Record


class MockTable:
    """In-memory replacement for support.database.Table.

    ``all()`` ignores the filter parameter — tests should pre-populate only
    the records they expect to appear, matching the Python-side filtering the
    calling code performs after fetching.
    """

    def __init__(self, records: list[Record] | None = None) -> None:
        self._records: list[Record] = list(records or [])
        self._next_id: int = 1
        # Mutation log — inspect these in test assertions
        self.created_fields: list[dict[str, Any]] = []
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.batch_update_calls: list[list[dict[str, Any]]] = []
        self.deleted_ids: list[str] = []

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def all(self, filter=None) -> list[Record]:
        return list(self._records)

    def get(self, record_id: str) -> Record | None:
        for r in self._records:
            if r.id == record_id:
                return r
        return None

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def _next_record_id(self) -> str:
        rid = f"rec{self._next_id:08d}"
        self._next_id += 1
        return rid

    def create(self, records: Iterable[Mapping[str, Any]]) -> list[Record]:
        inserted: list[Record] = []
        for r in records:
            # Unwrap {"fields": ...} envelopes for compatibility
            if isinstance(r, dict) and set(r.keys()) <= {"fields"}:
                fdict = dict(r.get("fields", {}))
            else:
                fdict = dict(r)
            rid = self._next_record_id()
            new_rec: Record = Record(id=rid, fields=fdict)
            self._records.append(new_rec)
            self.created_fields.append(fdict)
            inserted.append(new_rec)
        return inserted

    def update(self, record_id: str, fields: Mapping[str, Any]) -> Record:
        self.updates.append((record_id, dict(fields)))
        for i, r in enumerate(self._records):
            if r.id == record_id:
                merged = {**r.fields, **fields}
                new_rec: Record = Record(id=record_id, fields=merged)
                self._records[i] = new_rec
                return new_rec
        # Record not pre-populated; return a stub so callers don't crash.
        return Record(id=record_id, fields=dict(fields))

    def batch_update(self, updates: Iterable[Mapping[str, Any]]) -> list[Record]:
        updates_list = list(updates)
        self.batch_update_calls.append(updates_list)
        results = []
        for entry in updates_list:
            entry = dict(entry)
            record_id = entry.pop("id")
            results.append(self.update(record_id, entry))
        return results

    def delete(self, record_id: str) -> None:
        self.deleted_ids.append(record_id)
        self._records = [r for r in self._records if r.id != record_id]

    def batch_delete(self, record_ids: Iterable[str]) -> None:
        for rid in record_ids:
            self.delete(rid)

    def clear(self) -> None:
        self.deleted_ids.extend(r.id for r in self._records)
        self._records = []


class MockDatabase:
    """In-memory replacement for support.database.Database.

    Instantiate once per test (or per setUp), then pass to the function
    under test in place of a real Database object.
    """

    def __init__(self) -> None:
        self.Schools:                       MockTable = MockTable()
        self.OnSiteManagers:                MockTable = MockTable()
        self.Caterers:                      MockTable = MockTable()
        self.MenuItems:                     MockTable = MockTable()
        self.DietaryRestrictions:           MockTable = MockTable()
        self.Students:                      MockTable = MockTable()
        self.Sessions:                      MockTable = MockTable()
        self.Absences:                      MockTable = MockTable()
        self.Exclusions:                    MockTable = MockTable()
        self.CatererFeedback:               MockTable = MockTable()
        self.WeeklyOrders:                  MockTable = MockTable()
        self.Orders:                        MockTable = MockTable()
        self.ScheduledEmails:               MockTable = MockTable()
        self.ManagerSubstitutions:          MockTable = MockTable()
        self.CatererSwitchProposals:        MockTable = MockTable()
        self.DietaryClarificationRequests:  MockTable = MockTable()
        self.DietaryInboundMessages:        MockTable = MockTable()
        self.SupportInboundMessages:        MockTable = MockTable()
        self.SupportCases:                  MockTable = MockTable()
        self.PendingChanges:                MockTable = MockTable()
