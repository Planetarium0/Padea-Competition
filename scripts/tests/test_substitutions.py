"""
Tests for substitute on-site manager support.

Covers:
  - support.database.resolve_manager_id     (unit)
  - support.database.load_substitutions     (unit, via MockDatabase)
  - actions.send_orders.format_email_body   (substitute label)
  - actions.send_orders.load_order_details  (integration, via MockDatabase)
"""
from __future__ import annotations

import unittest

import fixtures
from actions.orders.send_orders import (
    LineItem,
    SessionContext,
    format_email_body,
    load_order_details,
)
from mock_db import MockDatabase
from support import Record
from support.database import load_substitutions, resolve_manager_id


# ---------------------------------------------------------------------------
# resolve_manager_id
# ---------------------------------------------------------------------------

class TestResolveManagerId(unittest.TestCase):

    def _subs(self) -> dict[tuple[str, str], str]:
        return {(fixtures.SESSION_MON_ID, "2026-06-02"): fixtures.MANAGER_B_ID}

    def test_substitute_returned_when_session_and_date_match(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_MON_ID,
            {"on_site_manager_id": fixtures.MANAGER_A_ID},
            "2026-06-02",
            self._subs(),
        )
        self.assertEqual(mgr_id, fixtures.MANAGER_B_ID)
        self.assertTrue(is_sub)

    def test_fallback_to_regular_when_date_differs(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_MON_ID,
            {"on_site_manager_id": fixtures.MANAGER_A_ID},
            "2026-06-09",   # different week
            self._subs(),
        )
        self.assertEqual(mgr_id, fixtures.MANAGER_A_ID)
        self.assertFalse(is_sub)

    def test_fallback_to_regular_when_session_differs(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_WED_ID,   # not the session in subs
            {"on_site_manager_id": fixtures.MANAGER_A_ID},
            "2026-06-02",
            self._subs(),
        )
        self.assertEqual(mgr_id, fixtures.MANAGER_A_ID)
        self.assertFalse(is_sub)

    def test_fallback_to_regular_when_no_date_provided(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_MON_ID,
            {"on_site_manager_id": fixtures.MANAGER_A_ID},
            None,
            self._subs(),
        )
        self.assertEqual(mgr_id, fixtures.MANAGER_A_ID)
        self.assertFalse(is_sub)

    def test_returns_none_when_no_manager_anywhere(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_WED_ID,
            {},             # no on_site_manager_id field
            "2026-06-04",
            {},             # no substitutions
        )
        self.assertIsNone(mgr_id)
        self.assertFalse(is_sub)

    def test_substitute_returned_even_without_regular_manager(self):
        mgr_id, is_sub = resolve_manager_id(
            fixtures.SESSION_MON_ID,
            {},             # session has no regular manager
            "2026-06-02",
            self._subs(),
        )
        self.assertEqual(mgr_id, fixtures.MANAGER_B_ID)
        self.assertTrue(is_sub)


# ---------------------------------------------------------------------------
# load_substitutions
# ---------------------------------------------------------------------------

class TestLoadSubstitutions(unittest.TestCase):

    def test_empty_table_returns_empty_dict(self):
        db = MockDatabase()
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(result, {})

    def test_valid_substitution_parsed(self):
        db = MockDatabase()
        db.ManagerSubstitutions._records = [fixtures.substitution_monday("2026-06-02")]
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(result, {(fixtures.SESSION_MON_ID, "2026-06-02"): fixtures.MANAGER_B_ID})

    def test_multiple_substitutions_all_returned(self):
        db = MockDatabase()
        db.ManagerSubstitutions._records = [
            fixtures.substitution_monday("2026-06-02"),
            Record(id="subWed01", fields={
                "session_id":            fixtures.SESSION_WED_ID,
                "date":                  "2026-06-04",
                "substitute_manager_id": fixtures.MANAGER_A_ID,
            }),
        ]
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[(fixtures.SESSION_MON_ID, "2026-06-02")], fixtures.MANAGER_B_ID)
        self.assertEqual(result[(fixtures.SESSION_WED_ID, "2026-06-04")], fixtures.MANAGER_A_ID)

    def test_record_missing_substitute_manager_is_skipped(self):
        db = MockDatabase()
        db.ManagerSubstitutions._records = [
            Record(id="subBad1", fields={
                "session_id": fixtures.SESSION_MON_ID,
                "date":       "2026-06-02",
                # substitute_manager_id omitted
            }),
        ]
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(result, {})

    def test_record_missing_date_is_skipped(self):
        db = MockDatabase()
        db.ManagerSubstitutions._records = [
            Record(id="subBad2", fields={
                "session_id":            fixtures.SESSION_MON_ID,
                "substitute_manager_id": fixtures.MANAGER_B_ID,
                # date omitted
            }),
        ]
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(result, {})

    def test_record_missing_session_is_skipped(self):
        db = MockDatabase()
        db.ManagerSubstitutions._records = [
            Record(id="subBad3", fields={
                "date":                  "2026-06-02",
                "substitute_manager_id": fixtures.MANAGER_B_ID,
                # session_id omitted
            }),
        ]
        result = load_substitutions(db, "2026-06-02", "2026-06-06")
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# format_email_body — substitute label
# ---------------------------------------------------------------------------

def _ctx(manager_is_sub: bool = False) -> SessionContext:
    return SessionContext(
        fields={"session_code": "Alpha Academy - Monday", "day": "Monday",
                "dinner_time": "6:30 PM", "building": "Block B"},
        school_name="Alpha Academy",
        manager_name="Dave Substitute",
        manager_mobile="0499999999",
        manager_email="dave@beta.edu.au",
        manager_is_sub=manager_is_sub,
    )


def _simple_body(manager_is_sub: bool) -> str:
    wo  = {"week_start": "2026-06-02", "total_meals": 1}
    cat = {"name": "Café Deluxe", "contact_name": "Alice Smith", "delivery_fee": 0.0}
    li  = LineItem(quantity=1, session=_ctx(manager_is_sub), menu_item={"name": "Pasta"})
    return format_email_body(wo, cat, [li])


class TestFormatEmailBodySubstituteLabel(unittest.TestCase):

    def test_regular_manager_uses_plain_label(self):
        body = _simple_body(manager_is_sub=False)
        self.assertIn("On-site manager:", body)
        self.assertNotIn("(substitute)", body)

    def test_substitute_manager_uses_substitute_label(self):
        body = _simple_body(manager_is_sub=True)
        self.assertIn("On-site manager (substitute):", body)

    def test_substitute_mobile_included_in_label(self):
        body = _simple_body(manager_is_sub=True)
        self.assertIn("0499999999", body)


# ---------------------------------------------------------------------------
# load_order_details — integration via MockDatabase
# ---------------------------------------------------------------------------

WO_ID    = "recWO0601"
ORDER_ID = "recOR0601"
WEEK     = "2026-06-02"


def _build_db(with_substitution: bool) -> MockDatabase:
    db = MockDatabase()

    db.Caterers._records      = [fixtures.caterer_a()]
    db.Schools._records       = [fixtures.school_alpha()]
    db.Sessions._records      = [fixtures.session_monday()]
    db.OnSiteManagers._records = [fixtures.manager_alpha(), fixtures.manager_beta()]
    db.MenuItems._records     = [fixtures.menu_items_caterer_a()[0]]  # Chicken Fried Rice

    db.WeeklyOrders._records = [
        Record(id=WO_ID, fields={
            "order_code":  "Café Deluxe — 2026-W23",
            "caterer_id":  fixtures.CATERER_A_ID,
            "week_start":  WEEK,
            "total_meals": 5,
        }),
    ]
    db.Orders._records = [
        Record(id=ORDER_ID, fields={
            "weekly_order_id": WO_ID,
            "session_id":      fixtures.SESSION_MON_ID,
            "menu_item_id":    fixtures.ITEM_CHICKEN_RICE_ID,
            "date":            WEEK,
            "quantity":        5,
        }),
    ]

    if with_substitution:
        db.ManagerSubstitutions._records = [fixtures.substitution_monday(WEEK)]

    return db


class TestLoadOrderDetailsSubstitution(unittest.TestCase):

    def test_regular_manager_used_when_no_substitution(self):
        db = _build_db(with_substitution=False)
        wo_rec = db.WeeklyOrders._records[0]
        _caterer_fields, line_items = load_order_details(db, wo_rec)

        self.assertEqual(len(line_items), 1)
        ctx = line_items[0].session
        self.assertEqual(ctx.manager_name, "Carol Manager")
        self.assertEqual(ctx.manager_mobile, "0412345678")
        self.assertFalse(ctx.manager_is_sub)

    def test_substitute_manager_used_when_substitution_exists(self):
        db = _build_db(with_substitution=True)
        wo_rec = db.WeeklyOrders._records[0]
        _caterer_fields, line_items = load_order_details(db, wo_rec)

        self.assertEqual(len(line_items), 1)
        ctx = line_items[0].session
        self.assertEqual(ctx.manager_name, "Dave Substitute")
        self.assertEqual(ctx.manager_mobile, "0499999999")
        self.assertTrue(ctx.manager_is_sub)

    def test_substitute_email_included_in_cc_list(self):
        """The substitute's email should appear in the CC list for the order email."""
        db = _build_db(with_substitution=True)
        wo_rec = db.WeeklyOrders._records[0]
        _caterer_fields, line_items = load_order_details(db, wo_rec)

        emails = [li.session.manager_email for li in line_items if li.session.manager_email]
        self.assertIn("dave@beta.edu.au", emails)
        self.assertNotIn("carol@alpha.edu.au", emails)


if __name__ == "__main__":
    unittest.main()
