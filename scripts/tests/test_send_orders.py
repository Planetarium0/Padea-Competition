"""
Tests for scripts/actions/send_orders.py.

Covers: subtract_minutes, format_email_body (fee structures, chef CC),
and schedule_email (field writing).
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import fixtures
from actions.send_orders import (
    LineItem,
    SessionContext,
    format_email_body,
    subtract_minutes,
)
from support import schedule_email
from mock_db import MockDatabase


# ---------------------------------------------------------------------------
# subtract_minutes
# ---------------------------------------------------------------------------

class TestSubtractMinutes(unittest.TestCase):

    def test_12h_format(self):
        self.assertEqual(subtract_minutes("6:30 PM", 10), "6:20 PM")

    def test_24h_format(self):
        self.assertEqual(subtract_minutes("18:30", 10), "6:20 PM")

    def test_compact_12h_format(self):
        self.assertEqual(subtract_minutes("6:30PM", 10), "6:20 PM")

    def test_crosses_hour_boundary(self):
        self.assertEqual(subtract_minutes("6:05 PM", 10), "5:55 PM")

    def test_invalid_returns_original(self):
        self.assertEqual(subtract_minutes("not a time", 10), "not a time")

    def test_none_returns_question_mark(self):
        self.assertEqual(subtract_minutes(None, 10), "?")

    def test_custom_minutes(self):
        self.assertEqual(subtract_minutes("7:00 PM", 30), "6:30 PM")


# ---------------------------------------------------------------------------
# format_email_body
# ---------------------------------------------------------------------------

def _make_session_context(
    day: str = "Monday",
    session_code: str = "Alpha Academy - Monday",
    manager_email: str | None = "carol@alpha.edu.au",
) -> SessionContext:
    return SessionContext(
        fields={
            "session_code": session_code,
            "day":          day,
            "dinner_time":  "6:30 PM",
            "building":     "Block B",
        },
        school_name    = "Alpha Academy",
        manager_name   = "Carol Manager",
        manager_mobile = "0412345678",
        manager_email  = manager_email,
    )


def _make_line_item(session: SessionContext, item_name: str, qty: int) -> LineItem:
    return LineItem(
        quantity=qty,
        session=session,
        menu_item={"name": item_name},
    )


class TestFormatEmailBody(unittest.TestCase):

    def test_per_trip_fee_single_delivery(self):
        wo_fields = {"week_start": "2026-02-02", "total_meals": 5}
        caterer_fields = {
            "name":                   "Café Deluxe",
            "contact_name":           "Alice Smith",
            "delivery_fee":           20.0,
            "delivery_fee_structure": "Per trip",
        }
        sess = _make_session_context()
        line_items = [_make_line_item(sess, "Chicken Fried Rice", 3),
                      _make_line_item(sess, "Vegan Bowl", 2)]

        body = format_email_body(wo_fields, caterer_fields, line_items)

        self.assertIn("Hi Alice", body)
        self.assertIn("Café Deluxe", body)
        self.assertIn("2 February 2026", body)
        self.assertIn("$20.00", body)
        self.assertIn("per trip", body)
        self.assertIn("Chicken Fried Rice ×3", body)
        self.assertIn("Vegan Bowl ×2", body)

    def test_per_school_per_trip_fee_multiple_deliveries(self):
        wo_fields = {"week_start": "2026-02-02", "total_meals": 6}
        caterer_fields = {
            "name":                   "Fresh Eats",
            "contact_name":           "Bob Jones",
            "delivery_fee":           15.0,
            "delivery_fee_structure": "Per school per trip",
        }
        sess_mon = _make_session_context("Monday", "Alpha Academy - Monday")
        sess_wed = _make_session_context("Wednesday", "Alpha Academy - Wednesday")
        line_items = [
            _make_line_item(sess_mon, "Chicken Fried Rice", 3),
            _make_line_item(sess_wed, "Vegan Bowl", 3),
        ]

        body = format_email_body(wo_fields, caterer_fields, line_items)

        # 2 deliveries × $15 = $30
        self.assertIn("$30.00", body)
        self.assertIn("2 deliveries", body)

    def test_manager_contact_info_included(self):
        wo_fields      = {"week_start": "2026-02-02", "total_meals": 2}
        caterer_fields = {
            "name":         "Café Deluxe",
            "contact_name": "Alice Smith",
            "delivery_fee": 0.0,
        }
        sess = _make_session_context()
        body = format_email_body(wo_fields, caterer_fields, [_make_line_item(sess, "Meal", 2)])

        self.assertIn("Carol Manager", body)
        self.assertIn("0412345678", body)

    def test_building_included(self):
        wo_fields      = {"week_start": "2026-02-02", "total_meals": 1}
        caterer_fields = {"name": "X", "contact_name": "Y", "delivery_fee": 0.0}
        sess = _make_session_context()
        body = format_email_body(wo_fields, caterer_fields, [_make_line_item(sess, "Meal", 1)])
        self.assertIn("Block B", body)

    def test_deliver_by_is_10_min_before_dinner(self):
        wo_fields      = {"week_start": "2026-02-02", "total_meals": 1}
        caterer_fields = {"name": "X", "contact_name": "Y", "delivery_fee": 0.0}
        sess = SessionContext(
            fields={"session_code": "S", "day": "Monday", "dinner_time": "6:30 PM", "building": ""},
            school_name="School", manager_name=None, manager_mobile=None, manager_email=None,
        )
        body = format_email_body(wo_fields, caterer_fields, [_make_line_item(sess, "Meal", 1)])
        self.assertIn("6:20 PM", body)


# ---------------------------------------------------------------------------
# schedule_email — field names written to scheduled_emails table
# ---------------------------------------------------------------------------

class TestScheduleEmail(unittest.TestCase):

    def setUp(self) -> None:
        self._send_patch = mock.patch("support.email._send_via_mailslurp")
        self._send_patch.start()
        self._env_patch = mock.patch.dict(os.environ, {"MAILSLURP_API_KEY": "test-key"}, clear=False)
        self._env_patch.start()

    def tearDown(self) -> None:
        self._send_patch.stop()
        self._env_patch.stop()

    def test_creates_queued_record_with_weekly_order_link(self):
        db = MockDatabase()
        schedule_email(
            db,
            to_email="chef@example.com",
            cc_email=None,
            subject="Order Week",
            body="Body text",
            email_id="EMAIL-001",
            weekly_order_id="recWO001",
        )
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)
        f = db.ScheduledEmails.created_fields[0]
        self.assertEqual(f["to_address"], "chef@example.com")
        self.assertEqual(f["email_code"], "EMAIL-001")
        self.assertEqual(f["status"], "Queued")
        self.assertEqual(f["weekly_order_id"], "recWO001")
        self.assertNotIn("cc_address", f)

    def test_multiple_cc_addresses_joined(self):
        db = MockDatabase()
        schedule_email(
            db,
            to_email="chef@example.com",
            cc_email=["manager@school.edu.au", "deputy@school.edu.au"],
            subject="Order",
            body="Body",
            email_id="EMAIL-002",
            weekly_order_id="recWO002",
        )
        f = db.ScheduledEmails.created_fields[0]
        self.assertEqual(f["cc_address"], "manager@school.edu.au, deputy@school.edu.au")

    def test_creates_record_with_switch_proposal_link(self):
        db = MockDatabase()
        schedule_email(
            db,
            to_email="manager@school.edu.au",
            cc_email=["copy@school.edu.au"],
            subject="Switch Proposal",
            body="Body",
            email_id="SWITCH-001",
            caterer_switch_proposal_id="recPROP01",
        )
        f = db.ScheduledEmails.created_fields[0]
        self.assertEqual(f["caterer_switch_proposal_id"], "recPROP01")
        self.assertEqual(f["cc_address"], "copy@school.edu.au")
        self.assertNotIn("weekly_order_id", f)


if __name__ == "__main__":
    unittest.main()
