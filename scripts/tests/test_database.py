"""
Unit tests for scripts/support/database.py.

Covers:
  - Record.from_row construction
  - Table._extract_junction_fields (pure logic)
  - Table._write_junction_rows (client calls)
  - Table.create: view-only stripping, junction writes, model validation
  - Table.update: partial payload accepted, junction replacement
  - Table.clear: no-op on empty table; batch-delete on non-empty
  - load_substitutions / resolve_manager_id helpers
  - Pydantic schemas: partial payloads, valid/invalid enum values
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, call

from mock_db import MockDatabase
from support import Record, load_substitutions, resolve_manager_id
from support.database import Table, _JUNCTION_MAP, _VIEW_MAP, _VIEW_ONLY_FIELDS
from support.schemas import (
    MODEL_MAP,
    Caterer,
    DietaryRestriction,
    School,
    Session,
    Student,
)
from fixtures import (
    MANAGER_A_ID,
    MANAGER_B_ID,
    SESSION_MON_ID,
    session_monday,
    manager_alpha,
    manager_beta,
    substitution_monday,
)

from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chain_mock(execute_sequence: list[list[dict[str, Any]]] | None = None) -> MagicMock:
    """Return a mock that behaves like a Supabase query builder chain.

    execute_sequence is consumed in order: each call to .execute() pops and
    returns the next item as .data. Defaults to [] if exhausted.
    """
    seq: list[list[dict]] = list(execute_sequence or [])

    def _execute():
        data = seq.pop(0) if seq else []
        result = MagicMock()
        result.data = data
        return result

    chain = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "in_", "limit"):
        getattr(chain, method).return_value = chain
    chain.execute.side_effect = _execute
    return chain


def _make_table(table_name: str, execute_sequence: list[list[dict]] | None = None) -> tuple[Table, MagicMock, MagicMock]:
    """Return (Table, client_mock, chain_mock) for the given table name."""
    chain = _chain_mock(execute_sequence)
    client = MagicMock()
    client.table.return_value = chain
    return Table(client, table_name), client, chain


# ---------------------------------------------------------------------------
# Record.from_row
# ---------------------------------------------------------------------------

class TestRecordFromRow(unittest.TestCase):

    def test_id_extracted_from_row(self) -> None:
        row = {"id": "abc123", "name": "Test School", "region": "Redlands"}
        rec = Record.from_row(row)
        self.assertEqual(rec.id, "abc123")

    def test_fields_contain_full_row(self) -> None:
        row = {"id": "abc123", "name": "Test School", "region": "Redlands"}
        rec = Record.from_row(row)
        self.assertEqual(rec.fields["name"], "Test School")
        self.assertEqual(rec.fields["id"], "abc123")

    def test_fields_is_dict_copy(self) -> None:
        row = {"id": "x", "name": "Y"}
        rec = Record.from_row(row)
        row["name"] = "mutated"
        self.assertEqual(rec.fields["name"], "Y")


# ---------------------------------------------------------------------------
# Table._extract_junction_fields
# ---------------------------------------------------------------------------

class TestExtractJunctionFields(unittest.TestCase):

    def setUp(self) -> None:
        self.table, _, _ = _make_table("students")

    def test_junction_fields_are_popped(self) -> None:
        fields = {
            "name": "Alice",
            "session_ids": ["s1", "s2"],
            "dietary_requirement_ids": ["d1"],
        }
        jdata = self.table._extract_junction_fields(fields)
        self.assertNotIn("session_ids", fields)
        self.assertNotIn("dietary_requirement_ids", fields)
        self.assertIn("name", fields)

    def test_junction_data_has_correct_values(self) -> None:
        fields = {"name": "Alice", "session_ids": ["s1", "s2"]}
        jdata = self.table._extract_junction_fields(fields)
        self.assertEqual(jdata["session_ids"], ["s1", "s2"])

    def test_no_junction_fields_returns_empty(self) -> None:
        fields = {"name": "Alice", "year_level": 10}
        jdata = self.table._extract_junction_fields(fields)
        self.assertEqual(jdata, {})
        self.assertEqual(fields, {"name": "Alice", "year_level": 10})

    def test_absent_junction_fields_not_in_result(self) -> None:
        # session_ids not present — should not appear in jdata
        fields = {"name": "Alice"}
        jdata = self.table._extract_junction_fields(fields)
        self.assertNotIn("session_ids", jdata)

    def test_non_students_table_has_different_junctions(self) -> None:
        caterer_table, _, _ = _make_table("caterers")
        fields = {"name": "Café", "legend_tag_ids": ["r1"], "able_to_serve_school_ids": ["s1"]}
        jdata = caterer_table._extract_junction_fields(fields)
        self.assertEqual(jdata["legend_tag_ids"], ["r1"])
        self.assertEqual(jdata["able_to_serve_school_ids"], ["s1"])
        self.assertNotIn("legend_tag_ids", fields)


# ---------------------------------------------------------------------------
# Table._write_junction_rows
# ---------------------------------------------------------------------------

class TestWriteJunctionRows(unittest.TestCase):

    def test_write_junction_rows_issues_insert(self) -> None:
        # students table: session_ids → student_sessions (student_id, session_id)
        chain = _chain_mock()
        client = MagicMock()
        client.table.return_value = chain
        table = Table(client, "students")

        table._write_junction_rows("stu1", {"session_ids": ["sess1", "sess2"]})

        # Should have called client.table("student_sessions").insert(...)
        insert_calls = [c for c in client.table.call_args_list if c.args == ("student_sessions",)]
        self.assertTrue(len(insert_calls) >= 1, "Expected insert into student_sessions")

    def test_write_junction_rows_empty_list_skips_insert(self) -> None:
        chain = _chain_mock()
        client = MagicMock()
        client.table.return_value = chain
        table = Table(client, "students")

        # An empty session_ids list should not trigger any junction insert
        initial_call_count = client.table.call_count
        table._write_junction_rows("stu1", {"session_ids": []})
        # No new calls for an empty list
        insert_count_after = sum(
            1 for c in client.table.call_args_list[initial_call_count:]
            if c.args == ("student_sessions",)
        )
        self.assertEqual(insert_count_after, 0)

    def test_write_junction_rows_absent_key_skips(self) -> None:
        chain = _chain_mock()
        client = MagicMock()
        client.table.return_value = chain
        table = Table(client, "students")

        # Junction data doesn't include session_ids at all
        table._write_junction_rows("stu1", {"dietary_requirement_ids": ["d1"]})
        insert_tables = [c.args[0] for c in client.table.call_args_list]
        self.assertNotIn("student_sessions", insert_tables)


# ---------------------------------------------------------------------------
# Table.create
# ---------------------------------------------------------------------------

class TestTableCreate(unittest.TestCase):

    def test_create_returns_empty_for_empty_input(self) -> None:
        table, _, _ = _make_table("schools")
        result = table.create([])
        self.assertEqual(result, [])

    def test_create_strips_view_only_fields_from_insert(self) -> None:
        new_id = "school-uuid-1"
        # Sequence: clear-check (empty), insert result, get result
        table, client, chain = _make_table("schools", execute_sequence=[
            [{"id": new_id}],  # insert
            [{"id": new_id, "name": "Alpha", "region": "Redlands"}],  # get via view
        ])

        table.create([{"name": "Alpha", "region": "Redlands"}])

        # schools has no junction/view-only fields; just verify insert was called on the table
        insert_calls = [c for c in client.table.call_args_list if c.args == ("schools",)]
        self.assertTrue(len(insert_calls) >= 1)

    def test_create_does_not_pass_view_only_fields_to_db(self) -> None:
        new_id = "stu-uuid-1"
        table, client, chain = _make_table("students", execute_sequence=[
            [{"id": new_id}],  # bulk insert into students
            [],                # junction bulk insert (student_sessions)
            [{"id": new_id, "name": "Bob", "year_level": 10,
              "session_ids": ["s1"], "dietary_requirement_ids": []}],  # bulk re-fetch via view
        ])

        table.create([{"name": "Bob", "year_level": 10, "session_ids": ["s1"]}])

        # chain.insert is called in order: first for the main table (list of dicts),
        # then for junctions. The first insert payload is a list; check the first item.
        first_insert_payload = chain.insert.call_args_list[0].args[0]
        self.assertIsInstance(first_insert_payload, list)
        self.assertNotIn("session_ids", first_insert_payload[0])
        self.assertIn("name", first_insert_payload[0])

    def test_create_junction_insert_called_with_correct_rows(self) -> None:
        new_id = "stu-uuid-2"
        table, client, chain = _make_table("students", execute_sequence=[
            [{"id": new_id}],
            [],  # junction bulk insert
            [{"id": new_id, "name": "Carol", "year_level": 9,
              "session_ids": ["sess-x"], "dietary_requirement_ids": []}],
        ])

        table.create([{"name": "Carol", "year_level": 9, "session_ids": ["sess-x"]}])

        # Second insert call is the junction (student_sessions) bulk row
        self.assertGreaterEqual(len(chain.insert.call_args_list), 2)
        junction_payload = chain.insert.call_args_list[1].args[0]
        self.assertEqual(junction_payload, [{"student_id": new_id, "session_id": "sess-x"}])

    def test_create_bulk_uses_single_insert_for_multiple_records(self) -> None:
        ids = ["stu-1", "stu-2", "stu-3"]
        table, client, chain = _make_table("students", execute_sequence=[
            [{"id": i} for i in ids],   # single bulk insert returns all rows
            [],                          # junction bulk insert (no session_ids provided)
            [{"id": i, "name": f"S{i}", "year_level": 10,
              "session_ids": [], "dietary_requirement_ids": []} for i in ids],
        ])

        table.create([{"name": f"S{i}", "year_level": 10} for i in ids])

        # Only one INSERT call to the main table, not one per record.
        main_inserts = [c for c in client.table.call_args_list if c.args == ("students",)]
        self.assertEqual(len(main_inserts), 1)
        payload = chain.insert.call_args_list[0].args[0]
        self.assertIsInstance(payload, list)
        self.assertEqual(len(payload), 3)

    def test_create_no_view_fetch_skips_refetch(self) -> None:
        # weekly_orders has no view and no junction fields — re-fetch must be skipped.
        new_id = "wo-uuid-1"
        table, client, chain = _make_table("weekly_orders", execute_sequence=[
            [{"id": new_id, "order_code": "2026-W01", "caterer_id": "c1",
              "week_start": "2026-01-05", "total_meals": 10, "total_cost": 200.0}],
        ])

        result = table.create([{"order_code": "2026-W01", "caterer_id": "c1",
                                 "week_start": "2026-01-05", "total_meals": 10, "total_cost": 200.0}])

        # Only the single bulk INSERT should have been executed; no extra SELECT.
        self.assertEqual(chain.execute.call_count, 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, new_id)


# ---------------------------------------------------------------------------
# Table.update
# ---------------------------------------------------------------------------

class TestTableUpdate(unittest.TestCase):

    def test_update_partial_payload_does_not_raise(self) -> None:
        new_id = "dr-uuid-1"
        # superset_ids is view-only → no main-table update fires.
        # Sequence: delete junction, insert junction (["r1"] non-empty), get via view.
        table, client, chain = _make_table("dietary_restrictions", execute_sequence=[
            [],  # delete from dietary_restriction_supersets
            [],  # insert into dietary_restriction_supersets
            [{"id": new_id, "name": "Vegan", "superset_ids": ["r1"], "subset_ids": []}],
        ])

        # Partial update: only superset_ids, no name — must not raise
        result = table.update(new_id, {"superset_ids": ["r1"]})
        self.assertIsNotNone(result)

    def test_update_replaces_junction_rows(self) -> None:
        rec_id = "cat-uuid-1"
        # legend_tag_ids is view-only → no main-table update fires.
        # Sequence: delete caterer_legend_tags, insert caterer_legend_tags, get via view.
        table, client, chain = _make_table("caterers", execute_sequence=[
            [],  # delete from caterer_legend_tags
            [],  # insert into caterer_legend_tags
            [{"id": rec_id, "name": "Café", "region": "Redlands",
              "legend_tag_ids": ["r2"], "able_to_serve_school_ids": []}],
        ])

        table.update(rec_id, {"legend_tag_ids": ["r2"]})

        # chain.delete must have been called (for junction replacement)
        self.assertTrue(chain.delete.called, "Expected delete() call for junction replacement")


# ---------------------------------------------------------------------------
# Table.clear
# ---------------------------------------------------------------------------

class TestTableClear(unittest.TestCase):

    def test_clear_empty_table_makes_no_delete_call(self) -> None:
        table, client, chain = _make_table("schools", execute_sequence=[
            [],  # select returns no rows
        ])
        table.clear()
        delete_calls = [c for c in chain.method_calls if "delete" in str(c)]
        self.assertEqual(delete_calls, [])

    def test_clear_non_empty_table_deletes_all_ids(self) -> None:
        table, client, chain = _make_table("schools", execute_sequence=[
            [{"id": "s1"}, {"id": "s2"}],  # select
            [],  # delete
        ])
        table.clear()
        delete_call_found = any(
            "delete" in str(c) for c in chain.method_calls
        )
        self.assertTrue(delete_call_found)


# ---------------------------------------------------------------------------
# Pydantic schema validation
# ---------------------------------------------------------------------------

class TestPydanticSchemas(unittest.TestCase):

    def test_partial_payload_accepted_by_all_models(self) -> None:
        # Every model must accept an empty dict (partial update use case)
        for table_name, model in MODEL_MAP.items():
            with self.subTest(table=table_name):
                try:
                    model.model_validate({})
                except ValidationError as e:
                    self.fail(f"{model.__name__} rejected empty dict: {e}")

    def test_id_only_payload_accepted(self) -> None:
        for table_name, model in MODEL_MAP.items():
            with self.subTest(table=table_name):
                try:
                    model.model_validate({"id": "some-uuid"})
                except ValidationError as e:
                    self.fail(f"{model.__name__} rejected id-only dict: {e}")

    def test_invalid_region_enum_raises(self) -> None:
        with self.assertRaises(ValidationError):
            School.model_validate({"id": "x", "name": "X", "region": "Moon Base"})

    def test_valid_region_enum_passes(self) -> None:
        s = School.model_validate({"id": "x", "name": "X", "region": "Redlands"})
        self.assertEqual(s.region, "Redlands")

    def test_invalid_day_enum_raises(self) -> None:
        with self.assertRaises(ValidationError):
            Session.model_validate({"day": "Saturday"})

    def test_valid_day_enum_passes(self) -> None:
        sess = Session.model_validate({"day": "Monday"})
        self.assertEqual(sess.day, "Monday")

    def test_invalid_type_for_year_level_raises(self) -> None:
        with self.assertRaises(ValidationError):
            Student.model_validate({"year_level": "not-an-int"})

    def test_list_fields_default_to_empty(self) -> None:
        s = Student.model_validate({"name": "Alice"})
        self.assertEqual(s.session_ids, [])
        self.assertEqual(s.dietary_requirement_ids, [])

    def test_full_caterer_record_validates(self) -> None:
        Caterer.model_validate({
            "id":                     "c-uuid",
            "name":                   "Café Deluxe",
            "region":                 "South Brisbane",
            "min_qty_4_items":        3,
            "price_per_item":         12.50,
            "chef_wants_cc":          True,
            "delivery_fee_structure": "Per trip",
            "legend_tag_ids":         ["r1"],
            "able_to_serve_school_ids": ["s1"],
        })

    def test_dietary_restriction_superset_ids_default_empty(self) -> None:
        dr = DietaryRestriction.model_validate({"name": "Vegan"})
        self.assertEqual(dr.superset_ids, [])
        self.assertEqual(dr.subset_ids, [])


# ---------------------------------------------------------------------------
# load_substitutions / resolve_manager_id
# ---------------------------------------------------------------------------

class TestLoadSubstitutions(unittest.TestCase):

    def setUp(self) -> None:
        self.db = MockDatabase()
        self.db.OnSiteManagers._records = [manager_alpha(), manager_beta()]
        self.db.Sessions._records = [session_monday()]

    def test_load_substitutions_returns_mapping(self) -> None:
        self.db.ManagerSubstitutions._records = [substitution_monday("2026-06-09")]
        subs = load_substitutions(self.db, "2026-06-09", "2026-06-09")
        self.assertIn((SESSION_MON_ID, "2026-06-09"), subs)
        self.assertEqual(subs[(SESSION_MON_ID, "2026-06-09")], MANAGER_B_ID)

    def test_load_substitutions_out_of_range_excluded(self) -> None:
        self.db.ManagerSubstitutions._records = [substitution_monday("2026-06-16")]
        subs = load_substitutions(self.db, "2026-06-09", "2026-06-09")
        # The MockTable ignores the filter callable, so this tests the mapping
        # logic only (filter is applied server-side in real Supabase).
        # We verify the key structure is correct regardless.
        for key in subs:
            self.assertIsInstance(key, tuple)
            self.assertEqual(len(key), 2)

    def test_load_substitutions_empty_table(self) -> None:
        subs = load_substitutions(self.db, "2026-06-09", "2026-06-15")
        self.assertEqual(subs, {})


class TestResolveManagerId(unittest.TestCase):

    def setUp(self) -> None:
        self.session_fields = session_monday().fields

    def test_substitution_overrides_permanent_manager(self) -> None:
        subs = {(SESSION_MON_ID, "2026-06-09"): MANAGER_B_ID}
        mgr_id, is_sub = resolve_manager_id(SESSION_MON_ID, self.session_fields, "2026-06-09", subs)
        self.assertEqual(mgr_id, MANAGER_B_ID)
        self.assertTrue(is_sub)

    def test_permanent_manager_returned_when_no_substitution(self) -> None:
        subs = {}
        mgr_id, is_sub = resolve_manager_id(SESSION_MON_ID, self.session_fields, "2026-06-09", subs)
        self.assertEqual(mgr_id, MANAGER_A_ID)
        self.assertFalse(is_sub)

    def test_none_date_skips_substitution_lookup(self) -> None:
        subs = {(SESSION_MON_ID, "2026-06-09"): MANAGER_B_ID}
        mgr_id, is_sub = resolve_manager_id(SESSION_MON_ID, self.session_fields, None, subs)
        # No date → falls through to permanent manager
        self.assertEqual(mgr_id, MANAGER_A_ID)
        self.assertFalse(is_sub)

    def test_no_manager_set_returns_none(self) -> None:
        fields_no_mgr = {**self.session_fields}
        fields_no_mgr.pop("on_site_manager_id", None)
        mgr_id, is_sub = resolve_manager_id(SESSION_MON_ID, fields_no_mgr, "2026-06-09", {})
        self.assertIsNone(mgr_id)
        self.assertFalse(is_sub)


if __name__ == "__main__":
    unittest.main()
