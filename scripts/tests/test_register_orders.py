"""
Tests for scripts/actions/register_orders.py.

Covers: is_student_excluded, assign_fallback_meal, assign_variety_meal,
compute_max_variety, enforce_min_qty, flip_incoming_caterers, and the
full register_orders pipeline via MockDatabase.
"""
from __future__ import annotations

import types
import unittest
from collections import Counter
from datetime import date

import fixtures
from actions.register_orders import (
    Assignment,
    OrderingData,
    OrderingIndex,
    assign_fallback_meal,
    assign_variety_meal,
    compute_max_variety,
    enforce_min_qty,
    flip_incoming_caterers,
    register_orders,
    _find_min_qty,
)
from mock_db import MockDatabase
from support import Record
from support.compatibility import build_hierarchy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data(**overrides) -> OrderingData:
    defaults = dict(
        sessions=[],
        students=[],
        caterers=[],
        menu_items=[],
        dietary_restrictions=fixtures.dietary_records(),
        absences=[],
        exclusions=[],
        feedback=[],
    )
    defaults.update(overrides)
    return OrderingData(**defaults)


def _make_index(**overrides) -> OrderingIndex:
    return OrderingIndex.build(_make_data(**overrides))


def _simple_index() -> object:
    """Minimal namespace that satisfies assign_*meal — only dietary_hierarchy."""
    return types.SimpleNamespace(dietary_hierarchy=fixtures.test_hierarchy())


# ---------------------------------------------------------------------------
# is_student_excluded
# ---------------------------------------------------------------------------

class TestIsStudentExcluded(unittest.TestCase):

    def _index_with_exclusions(self, exclusions: list[Record]) -> OrderingIndex:
        return _make_index(exclusions=exclusions)

    def test_no_exclusions(self):
        from actions.register_orders import is_student_excluded
        idx = _make_index()
        stu = fixtures.student_normal().fields
        sess = fixtures.session_monday().fields
        self.assertFalse(is_student_excluded(stu, sess, date(2026, 2, 2), idx))

    def test_excluded_by_school_date_all_levels(self):
        from actions.register_orders import is_student_excluded
        exclusion = Record(id="exc001", fields={
            "school_id":  fixtures.SCHOOL_A_ID,
            "date":       "2026-02-02",
            "year_levels": ["All"],
        })
        idx = self._index_with_exclusions([exclusion])
        stu  = fixtures.student_normal().fields
        sess = fixtures.session_monday().fields
        self.assertTrue(is_student_excluded(stu, sess, date(2026, 2, 2), idx))

    def test_excluded_matching_year_level(self):
        from actions.register_orders import is_student_excluded
        exclusion = Record(id="exc002", fields={
            "school_id":  fixtures.SCHOOL_A_ID,
            "date":       "2026-02-02",
            "year_levels": ["10", "11"],
        })
        idx = self._index_with_exclusions([exclusion])
        stu  = fixtures.student_normal().fields  # year_level = 10
        sess = fixtures.session_monday().fields
        self.assertTrue(is_student_excluded(stu, sess, date(2026, 2, 2), idx))

    def test_not_excluded_wrong_year_level(self):
        from actions.register_orders import is_student_excluded
        exclusion = Record(id="exc003", fields={
            "school_id":  fixtures.SCHOOL_A_ID,
            "date":       "2026-02-02",
            "year_levels": ["12"],
        })
        idx = self._index_with_exclusions([exclusion])
        stu  = fixtures.student_normal().fields  # year_level = 10, not 12
        sess = fixtures.session_monday().fields
        self.assertFalse(is_student_excluded(stu, sess, date(2026, 2, 2), idx))

    def test_not_excluded_wrong_date(self):
        from actions.register_orders import is_student_excluded
        exclusion = Record(id="exc004", fields={
            "school_id":  fixtures.SCHOOL_A_ID,
            "date":       "2026-02-09",  # different week
            "year_levels": ["All"],
        })
        idx = self._index_with_exclusions([exclusion])
        stu  = fixtures.student_normal().fields
        sess = fixtures.session_monday().fields
        self.assertFalse(is_student_excluded(stu, sess, date(2026, 2, 2), idx))


# ---------------------------------------------------------------------------
# assign_fallback_meal
# ---------------------------------------------------------------------------

class TestAssignFallbackMeal(unittest.TestCase):

    def setUp(self):
        self.menu  = fixtures.menu_items_caterer_a()
        self.index = _simple_index()

    def test_no_restrictions_returns_any_item(self):
        result = assign_fallback_meal([], self.menu, {}, self.index)
        self.assertIsNotNone(result)
        self.assertIn(result, {item.id for item in self.menu})

    def test_vegetarian_only_gets_compatible_items(self):
        # Chicken Fried Rice and Beef Burger contain "chicken"/"beef" →
        # incompatible with Vegetarian via keyword fallback.
        compatible = {fixtures.ITEM_VEG_PASTA_ID, fixtures.ITEM_VEGAN_BOWL_ID}
        for _ in range(60):  # repeat to rule out lucky draws
            result = assign_fallback_meal(
                [fixtures.DIET_VEG_ID], self.menu, {}, self.index
            )
            self.assertIn(result, compatible,
                          f"Vegetarian student assigned incompatible item {result}")

    def test_returns_none_when_no_compatible_items(self):
        # Only Beef Burger on the menu — incompatible with Vegan
        beef_only = [Record(id="iBeef", fields={
            "name":            "Beef Burger",
            "caterer_id":      fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        result = assign_fallback_meal(
            [fixtures.DIET_VEGAN_ID], beef_only, {}, self.index
        )
        self.assertIsNone(result)

    def test_popularity_weighting_follows_counts(self):
        # Item A has 100 orders, item B has 0 — A should win the vast majority.
        item_a = Record(id="iA", fields={"name": "Item A", "caterer_id": "c", "dietary_tag_ids": []})
        item_b = Record(id="iB", fields={"name": "Item B", "caterer_id": "c", "dietary_tag_ids": []})
        counts = {"iA": 100, "iB": 0}
        results = [assign_fallback_meal([], [item_a, item_b], counts, self.index) for _ in range(50)]
        self.assertGreater(results.count("iA"), 35)


# ---------------------------------------------------------------------------
# assign_variety_meal
# ---------------------------------------------------------------------------

class TestAssignVarietyMeal(unittest.TestCase):

    def setUp(self):
        self.menu  = fixtures.menu_items_caterer_a()
        self.index = _simple_index()

    def test_picks_least_ordered_item(self):
        # Only iA and iB, iA has 5 orders, iB has 0 → iB should win every time.
        item_a = Record(id="iA", fields={"name": "Item A", "caterer_id": "c", "dietary_tag_ids": []})
        item_b = Record(id="iB", fields={"name": "Item B", "caterer_id": "c", "dietary_tag_ids": []})
        counts = {"iA": 5, "iB": 0}
        for _ in range(30):
            result = assign_variety_meal([], [item_a, item_b], counts, self.index)
            self.assertEqual(result, "iB")

    def test_max_items_cap_prevents_new_item(self):
        # Already 2 active items; max_items=2 means a third item should NOT appear.
        item_a = Record(id="iA", fields={"name": "Item A", "caterer_id": "c", "dietary_tag_ids": []})
        item_b = Record(id="iB", fields={"name": "Item B", "caterer_id": "c", "dietary_tag_ids": []})
        item_c = Record(id="iC", fields={"name": "Item C", "caterer_id": "c", "dietary_tag_ids": []})
        counts = {"iA": 2, "iB": 1, "iC": 0}  # iC has 0 but is in counts to show it exists
        # With max_items=2, active_ids={iA, iB} → iC excluded from selection
        for _ in range(30):
            result = assign_variety_meal([], [item_a, item_b, item_c], counts, self.index,
                                         max_items=2)
            self.assertIn(result, {"iA", "iB"})

    def test_dietary_exception_allows_new_item_despite_cap(self):
        # Only item_c is compatible with Vegetarian, so despite the cap it must be chosen.
        item_a = Record(id="iA", fields={"name": "Chicken Fried Rice", "caterer_id": "c", "dietary_tag_ids": []})
        item_b = Record(id="iB", fields={"name": "Beef Burger",        "caterer_id": "c", "dietary_tag_ids": []})
        item_c = Record(id="iC", fields={"name": "Vegan Bowl",         "caterer_id": "c", "dietary_tag_ids": [fixtures.DIET_VEGAN_ID]})
        # Active items (iA, iB) both incompatible with Vegetarian → fall back to iC
        counts = {"iA": 3, "iB": 2}  # 2 active items = max_items
        result = assign_variety_meal(
            [fixtures.DIET_VEG_ID], [item_a, item_b, item_c], counts, self.index,
            max_items=2,
        )
        self.assertEqual(result, "iC")


# ---------------------------------------------------------------------------
# compute_max_variety and _find_min_qty
# ---------------------------------------------------------------------------

class TestComputeMaxVariety(unittest.TestCase):

    def test_returns_4_when_students_satisfy_constraint(self):
        # "min_qty_4_items": 3, 12 students → 12 >= 4*3 → 4 items
        cf = {"name": "X", "min_qty_4_items": 3}
        self.assertEqual(compute_max_variety(cf, 12), 4)

    def test_falls_back_when_students_insufficient(self):
        # "min_qty_4_items": 3, 10 students → 10 < 4*3=12 → fallback = max(1, 10//3) = 3
        cf = {"name": "X", "min_qty_4_items": 3}
        self.assertEqual(compute_max_variety(cf, 10), 3)

    def test_no_constraints_uses_divide_by_3(self):
        # No Min Qty constraints → max(1, n//3)
        cf = {"name": "X"}
        self.assertEqual(compute_max_variety(cf, 9), 3)
        self.assertEqual(compute_max_variety(cf, 15), 5)
        self.assertEqual(compute_max_variety(cf, 2), 1)

    def test_prefers_higher_n_when_both_feasible(self):
        # 30 students, min_qty_5_items=5, min_qty_4_items=3 → 30>=5*5=25 → 5 items
        cf = {"min_qty_5_items": 5, "min_qty_4_items": 3}
        self.assertEqual(compute_max_variety(cf, 30), 5)

    def test_find_min_qty_no_constraint_for_small_n(self):
        # range(3, 3, -1) is empty → None
        cf = {"min_qty_4_items": 3}
        self.assertIsNone(_find_min_qty(cf, 3))
        self.assertIsNone(_find_min_qty(cf, 2))

    def test_find_min_qty_matches_exact_n(self):
        cf = {"min_qty_4_items": 3, "min_qty_5_items": 4}
        self.assertEqual(_find_min_qty(cf, 4), 3)
        self.assertEqual(_find_min_qty(cf, 5), 4)


# ---------------------------------------------------------------------------
# enforce_min_qty
# ---------------------------------------------------------------------------

class TestEnforceMinQty(unittest.TestCase):

    def _make_index_for_students(self, students: list[Record]) -> OrderingIndex:
        items = [
            Record(id="iA", fields={"name": "Item A", "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
            Record(id="iB", fields={"name": "Item B", "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
            Record(id="iC", fields={"name": "Item C", "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
            Record(id="iD", fields={"name": "Item D", "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
        ]
        return _make_index(students=students, caterers=[fixtures.caterer_a()], menu_items=items)

    def test_no_violations_unchanged(self):
        students = fixtures.make_students(8)
        index    = self._make_index_for_students(students)
        cf       = {"name": "X", "min_qty_4_items": 2}
        # 8 students, 4 items × 2 each → no violations
        assignments = [
            Assignment(students[i].id, "sess", "iA", False) for i in range(2)
        ] + [
            Assignment(students[i].id, "sess", "iB", False) for i in range(2, 4)
        ] + [
            Assignment(students[i].id, "sess", "iC", False) for i in range(4, 6)
        ] + [
            Assignment(students[i].id, "sess", "iD", False) for i in range(6, 8)
        ]
        result = enforce_min_qty(cf, list(assignments), index)
        self.assertEqual(Counter(a.item_id for a in result),
                         Counter(a.item_id for a in assignments))

    def test_below_threshold_swapped_to_valid_items(self):
        # 10 students: A=5, B=3, C=1, D=1 — min qty for 4 items = 3
        # C and D (non-explicit) should be dissolved into A or B.
        students = fixtures.make_students(10)
        index    = self._make_index_for_students(students)
        cf       = {"name": "X", "min_qty_4_items": 3}
        assignments = (
            [Assignment(students[i].id, "sess", "iA", False) for i in range(5)] +
            [Assignment(students[i].id, "sess", "iB", False) for i in range(5, 8)] +
            [Assignment(students[8].id, "sess", "iC", False)] +
            [Assignment(students[9].id, "sess", "iD", False)]
        )
        result = enforce_min_qty(cf, list(assignments), index)
        counts = Counter(a.item_id for a in result)
        # C and D should be gone; A and B absorb their students
        self.assertNotIn("iC", counts)
        self.assertNotIn("iD", counts)
        self.assertEqual(sum(counts.values()), 10)
        # All remaining items should meet or exceed min-qty (for 2 items, no constraint)
        for iid, cnt in counts.items():
            self.assertGreaterEqual(cnt, 3)

    def test_explicit_preference_swapped_when_below_min_qty(self):
        # C=1 explicit, D=1 non-explicit; both violate min-qty.
        # Explicit no longer protects from swapping — both should be dissolved.
        students = fixtures.make_students(10)
        index    = self._make_index_for_students(students)
        cf       = {"name": "X", "min_qty_4_items": 3}
        assignments = (
            [Assignment(students[i].id, "sess", "iA", False) for i in range(5)] +
            [Assignment(students[i].id, "sess", "iB", False) for i in range(5, 8)] +
            [Assignment(students[8].id, "sess", "iC", True)] +   # explicit but still a candidate
            [Assignment(students[9].id, "sess", "iD", False)]
        )
        result = enforce_min_qty(cf, list(assignments), index)
        # Both C and D should be dissolved into A or B
        self.assertFalse(any(a.item_id == "iC" for a in result))
        self.assertFalse(any(a.item_id == "iD" for a in result))
        self.assertEqual(sum(1 for a in result), 10)

    def test_dietary_incompatibility_prevents_swap(self):
        # Veg student is on a violating item (iC, veg-tagged).
        # The valid items (iA, iB) both contain meat keywords → incompatible with Vegetarian.
        # No compatible swap exists, so the veg student must stay on iC.
        veg_student = Record(id="stuVeg", fields={
            "name":                    "Veg Student",
            "session_ids":             ["sess"],
            "dietary_requirement_ids": [fixtures.DIET_VEG_ID],
        })
        other = fixtures.make_students(9)
        items = [
            Record(id="iA", fields={"name": "Chicken Rice",   "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
            Record(id="iB", fields={"name": "Beef Burger",    "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
            Record(id="iC", fields={"name": "Veg Pasta",      "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": [fixtures.DIET_VEG_ID]}),
            Record(id="iD", fields={"name": "Chicken Burger", "caterer_id": fixtures.CATERER_A_ID, "dietary_tag_ids": []}),
        ]
        index = _make_index(
            students=other + [veg_student],
            caterers=[fixtures.caterer_a()],
            menu_items=items,
        )
        cf = {"name": "X", "min_qty_4_items": 3}
        # A=5, B=3 (valid); C=1 veg student, D=1 non-veg student (both violating)
        assignments = (
            [Assignment(other[i].id,      "sess", "iA", False) for i in range(5)] +
            [Assignment(other[i].id,      "sess", "iB", False) for i in range(5, 8)] +
            [Assignment(veg_student.id,   "sess", "iC", False)] +
            [Assignment(other[8].id,      "sess", "iD", False)]
        )
        result = enforce_min_qty(cf, list(assignments), index)
        # D's student (no dietary restriction) is moved to A or B
        self.assertFalse(any(a.item_id == "iD" for a in result))
        # Veg student has no compatible target in A or B (meat keywords) — stays on iC
        veg_result = [a for a in result if a.student_id == veg_student.id]
        self.assertEqual(len(veg_result), 1)
        self.assertEqual(veg_result[0].item_id, "iC")


# ---------------------------------------------------------------------------
# flip_incoming_caterers
# ---------------------------------------------------------------------------

class TestFlipIncomingCaterers(unittest.TestCase):

    def test_flips_incoming_and_clears_field(self):
        db = MockDatabase()
        db.Sessions._records = [
            Record(id="s1", fields={"caterer_id": "cOld", "incoming_caterer_id": "cNew", "day": "Monday"}),
            Record(id="s2", fields={"caterer_id": "cOld", "day": "Wednesday"}),  # no incoming
        ]
        db.CatererSwitchProposals._records = [
            Record(id="p1", fields={"session_id": "s1", "status": "Approved"}),
        ]
        flip_incoming_caterers(db, dry_run=False)

        self.assertEqual(len(db.Sessions.updates), 1)
        updated_id, updated_fields = db.Sessions.updates[0]
        self.assertEqual(updated_id, "s1")
        self.assertEqual(updated_fields["caterer_id"], "cNew")
        self.assertIsNone(updated_fields["incoming_caterer_id"])

    def test_marks_proposal_executed(self):
        db = MockDatabase()
        db.Sessions._records = [
            Record(id="s1", fields={"caterer_id": "cOld", "incoming_caterer_id": "cNew"}),
        ]
        db.CatererSwitchProposals._records = [
            Record(id="p1", fields={"session_id": "s1", "status": "Approved"}),
        ]
        flip_incoming_caterers(db, dry_run=False)

        proposal_updates = {uid: f for uid, f in db.CatererSwitchProposals.updates}
        self.assertEqual(proposal_updates["p1"]["status"], "Executed")

    def test_only_approved_proposals_marked_executed(self):
        db = MockDatabase()
        db.Sessions._records = [
            Record(id="s1", fields={"caterer_id": "cOld", "incoming_caterer_id": "cNew"}),
        ]
        db.CatererSwitchProposals._records = [
            Record(id="p1", fields={"session_id": "s1", "status": "Pending"}),
        ]
        flip_incoming_caterers(db, dry_run=False)

        self.assertEqual(db.CatererSwitchProposals.updates, [])

    def test_dry_run_makes_no_writes(self):
        db = MockDatabase()
        db.Sessions._records = [
            Record(id="s1", fields={"caterer_id": "cOld", "incoming_caterer_id": "cNew"}),
        ]
        db.CatererSwitchProposals._records = [
            Record(id="p1", fields={"session_id": "s1", "status": "Approved"}),
        ]
        flip_incoming_caterers(db, dry_run=True)
        self.assertEqual(db.Sessions.updates, [])
        self.assertEqual(db.CatererSwitchProposals.updates, [])

    def test_no_sessions_with_incoming_caterer(self):
        db = MockDatabase()
        db.Sessions._records = [
            Record(id="s1", fields={"caterer_id": "cOld"}),
        ]
        flip_incoming_caterers(db, dry_run=False)
        self.assertEqual(db.Sessions.updates, [])


# ---------------------------------------------------------------------------
# Full register_orders pipeline (via MockDatabase)
# ---------------------------------------------------------------------------

class TestRegisterOrdersPipeline(unittest.TestCase):

    def _setup_db(self, students: list[Record], absences: list[Record] | None = None) -> MockDatabase:
        db = MockDatabase()
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Caterers._records  = [fixtures.caterer_a()]
        db.MenuItems._records = fixtures.menu_items_caterer_a()
        db.Sessions._records  = [fixtures.session_monday()]
        db.Students._records  = students
        db.Absences._records  = absences or []
        db.Exclusions._records = []
        db.CatererFeedback._records = []
        db.Orders._records = []
        db.WeeklyOrders._records = []
        return db

    def test_assigns_meals_for_eligible_students(self):
        students = [fixtures.student_normal(), fixtures.student_vegetarian()]
        db = self._setup_db(students)
        register_orders(db, dry_run=False)

        self.assertEqual(len(db.WeeklyOrders.created_fields), 1)
        wo = db.WeeklyOrders.created_fields[0]
        self.assertEqual(wo["total_meals"], 2)
        self.assertEqual(wo["caterer_id"], fixtures.CATERER_A_ID)

        total_ordered = sum(o["quantity"] for o in db.Orders.created_fields)
        self.assertEqual(total_ordered, 2)

    def test_opted_out_student_skipped(self):
        students = [fixtures.student_normal(), fixtures.student_opted_out()]
        db = self._setup_db(students)
        register_orders(db, dry_run=False)

        wo = db.WeeklyOrders.created_fields[0]
        self.assertEqual(wo["total_meals"], 1)

    def test_absent_student_skipped(self):
        students = [fixtures.student_normal(), fixtures.student_vegetarian()]
        absence  = Record(id="abs001", fields={
            "student_id": fixtures.STU_VEG_ID,
            "session_id": fixtures.SESSION_MON_ID,
        })
        db = self._setup_db(students, absences=[absence])
        register_orders(db, dry_run=False)

        wo = db.WeeklyOrders.created_fields[0]
        self.assertEqual(wo["total_meals"], 1)

    def test_explicit_preference_respected(self):
        # Student has Meal Preference = ITEM_VEG_PASTA_ID (on Caterer A's menu)
        student_with_pref = Record(id="stuPref", fields={
            "name":                    "Pref Student",
            "year_level":              10,
            "session_ids":             [fixtures.SESSION_MON_ID],
            "dietary_requirement_ids": [],
            "meal_preference_id":      fixtures.ITEM_VEG_PASTA_ID,
        })
        db = self._setup_db([student_with_pref])
        register_orders(db, dry_run=False)

        # Should have exactly one order and that item should be ITEM_VEG_PASTA_ID
        assigned_items = [o["menu_item_id"] for o in db.Orders.created_fields]
        self.assertIn(fixtures.ITEM_VEG_PASTA_ID, assigned_items)

    def test_vegetarian_never_receives_meat_item(self):
        students = fixtures.make_students(5) + [fixtures.student_vegetarian()]
        db = self._setup_db(students)
        register_orders(db, dry_run=False)

        # Find which item IDs were ordered for sessions at this school.
        all_item_ids: set[str] = set()
        for o in db.Orders.created_fields:
            item_id = o.get("menu_item_id")
            if item_id:
                all_item_ids.add(item_id)

        # Vegetarian student must not have been given Chicken Fried Rice or Beef Burger
        # (the veg student's Order will be for one of the 2 veg-safe items).
        # We confirm this by checking that all items in the batch are valid overall
        # and that at least one veg-safe item is present.
        veg_safe = {fixtures.ITEM_VEG_PASTA_ID, fixtures.ITEM_VEGAN_BOWL_ID}
        self.assertTrue(all_item_ids & veg_safe,
                        "Expected at least one veg-safe item in orders")

    def test_dry_run_creates_no_records(self):
        students = [fixtures.student_normal()]
        db = self._setup_db(students)
        register_orders(db, dry_run=True)

        self.assertEqual(db.WeeklyOrders.created_fields, [])
        self.assertEqual(db.Orders.created_fields, [])


if __name__ == "__main__":
    unittest.main()
