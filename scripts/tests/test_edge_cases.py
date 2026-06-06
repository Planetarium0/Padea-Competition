"""Regression testing suite for catchable edge cases and automated self-healing.

Allows developers and automated agents to quickly replicate and patch system failures
by loading serialized failure JSON states directly into MockDatabase.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest import mock

from mock_db import MockDatabase
from support import Record


def populate_mock_db(db: MockDatabase, state_snapshot: Dict[str, Any]) -> None:
    """Populate a MockDatabase using the serialized 'state_snapshot' dictionary from a failure JSON."""
    key_to_table = {
        "schools": db.Schools,
        "on_site_managers": db.OnSiteManagers,
        "caterers": db.Caterers,
        "menu_items": db.MenuItems,
        "dietary_restrictions": db.DietaryRestrictions,
        "students": db.Students,
        "sessions": db.Sessions,
        "absences": db.Absences,
        "exclusions": db.Exclusions,
        "caterer_feedback": db.CatererFeedback,
        "weekly_orders": db.WeeklyOrders,
        "orders": db.Orders,
        "scheduled_emails": db.ScheduledEmails,
        "manager_substitutions": db.ManagerSubstitutions,
        "caterer_switch_proposals": db.CatererSwitchProposals,
    }
    for key, table in key_to_table.items():
        if key in state_snapshot:
            records = []
            for r in state_snapshot[key]:
                if isinstance(r, dict) and "id" in r and "fields" in r:
                    records.append(Record(id=r["id"], fields=r["fields"]))
            table._records = records


class TestSelfHealingRegression(unittest.TestCase):
    """Base regression test suite demonstrating automated self-healing replication."""

    def load_failure_snapshot(self, relative_path: str) -> Dict[str, Any]:
        """Utility to load a failure JSON snapshot relative to the project root."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        full_path = os.path.join(base_dir, relative_path)
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_mock_validation_edge_case_replication(self) -> None:
        """Concrete example: replicates a validation failure, mock-loads it, and shows regression handling."""
        # 1. Simulate a malformed record failing Pydantic validation
        invalid_student_data = {
            "name": "Incomplete Student",
            "year_level": "NOT_AN_INT",  # Invalid type: Pydantic expects int or null
            "dietary_requirement_ids": [],
        }

        # Verify that Pydantic validation catches this and raises ValidationError
        from pydantic import ValidationError
        from support.schemas import Student as StudentModel

        with self.assertRaises(ValidationError):
            StudentModel.model_validate(invalid_student_data)

        # 2. Demonstrate how MockDatabase is populated from a captured state
        mock_snapshot = {
            "students": [
                {"id": "recStudent01", "fields": {"name": "Good Student", "year_level": 12}},
                {"id": "recStudent02", "fields": {"name": "Another Student", "year_level": 11}}
            ],
            "caterers": [
                {"id": "recCaterer01", "fields": {"name": "Eco Lunch", "able_to_serve_school_ids": []}}
            ]
        }

        db = MockDatabase()
        populate_mock_db(db, mock_snapshot)

        # Assert database was correctly populated in-memory
        self.assertEqual(len(db.Students.all()), 2)
        self.assertEqual(db.Students.all()[0].fields["name"], "Good Student")
        self.assertEqual(db.Students.all()[1].fields["year_level"], 11)
        self.assertEqual(len(db.Caterers.all()), 1)
        self.assertEqual(db.Caterers.all()[0].fields["name"], "Eco Lunch")

    def test_logical_unhandled_edge_case(self) -> None:
        """Concrete example: replicates an unhandled logical exception in ordering logic."""
        # Setup an ordering scenario where a student has a dietary requirement but the caterer menu has NO compatible food.
        # This is a classic business logic edge case!
        mock_snapshot = {
            "students": [
                {
                    "id": "recStudentVegan",
                    "fields": {
                        "name":                    "Vegan Student",
                        "dietary_requirement_ids": ["recDietVeg"],
                        "session_ids":             ["recSessionMon"]
                    }
                }
            ],
            "dietary_restrictions": [
                {"id": "recDietVeg", "fields": {"name": "Vegan", "superset_ids": []}}
            ],
            "sessions": [
                {
                    "id": "recSessionMon",
                    "fields": {
                        "session_code": "Alpha - Mon",
                        "school_id":    "recSchoolA",
                        "caterer_id":   "recCatererMeat Only",
                        "day":          "Monday",
                    }
                }
            ],
            "caterers": [
                {
                    "id": "recCatererMeat Only",
                    "fields": {
                        "name":                     "Meat Masters",
                        "able_to_serve_school_ids": ["recSchoolA"]
                    }
                }
            ],
            "menu_items": [
                # Only a meat option is available - NO VEGAN option!
                {
                    "id": "recMenuBeef",
                    "fields": {
                        "name":            "Beef Burger",
                        "caterer_id":      "recCatererMeat Only",
                        "dietary_tag_ids": []
                    }
                }
            ]
        }

        db = MockDatabase()
        populate_mock_db(db, mock_snapshot)

        # Tracing order generation fallback check logic
        from support.compatibility import build_hierarchy, is_item_compatible
        
        hierarchy = build_hierarchy(db.DietaryRestrictions.all())
        vegan_student = db.Students.all()[0]
        caterer = db.Caterers.all()[0]
        menu_items = db.MenuItems.all()

        # Let's verify that none of the caterer's menu items satisfy this vegan student
        compatible_items = [
            item for item in menu_items
            if is_item_compatible(item.fields, vegan_student.fields["dietary_requirement_ids"], hierarchy)
        ]
        
        # Test assertion replicating the unhandled logic state: No compatible items!
        self.assertEqual(len(compatible_items), 0)


class TestSendOrdersDuplicateEmailCode(unittest.TestCase):
    """Regression for failure_20260605_091650_send_orders.

    Re-running send_orders when the caterer email was already sent produced a
    Postgres unique constraint violation (duplicate email_code). After the fix,
    schedule_email detects the pre-existing row and returns it without inserting
    or re-sending.
    """

    def test_failure_20260605_091650_send_orders(self) -> None:
        import support.email as email_module
        from support.email import schedule_email

        db = MockDatabase()

        # Simulate the row that was already inserted on the previous run
        existing_email_code = "EMAIL-2026-06-08-ae58638f"
        existing_record = Record(
            id="rec_existing_email",
            fields={
                "email_code": existing_email_code,
                "to_address": "caterer@lakehouse.com",
                "subject": "Padea Meal Order — Week of 8 June 2026",
                "body": "<p>Existing body</p>",
                "status": "Sent",
                "weekly_order_id": "ae58638f-190e-4c05-91fe-7d7e16ada6e8",
            },
        )
        db.ScheduledEmails._records = [existing_record]

        with mock.patch.object(email_module, "_send_via_sendgrid") as mock_send:
            result = schedule_email(
                db=db,
                to_email="caterer@lakehouse.com",
                cc_email=None,
                subject="Padea Meal Order — Week of 8 June 2026",
                body="<p>Re-run body</p>",
                email_id=existing_email_code,
                weekly_order_id="ae58638f-190e-4c05-91fe-7d7e16ada6e8",
            )

        # Returns the existing record, not a newly inserted duplicate
        self.assertIsNotNone(result)
        self.assertEqual(result.fields.get("email_code"), existing_email_code)
        # No second row was inserted
        self.assertEqual(len(db.ScheduledEmails._records), 1)
        # Email was not re-sent
        mock_send.assert_not_called()


class TestDayBlockedMenuItems(unittest.TestCase):
    """Regression tests for day-specific menu item availability (Big Chicken edge case).

    Crispy Chicken Taco is unavailable on Tuesdays;
    Cali Burrito is unavailable on Mondays.
    """

    _CATERER_ID = "recBigChicken"
    _SESSION_ID = "recSession01"
    _STU_ID     = "recStudent01"
    _TACO_ID    = "recTaco0001"
    _BURRITO_ID = "recBurrito01"
    _WRAP_ID    = "recWrap00001"

    def _make_db(
        self,
        session_day: str,
        *,
        taco_unavailable_days: list | None = None,
        burrito_unavailable_days: list | None = None,
        student_preference_id: str | None = None,
        extra_students: list | None = None,
    ) -> "MockDatabase":
        db = MockDatabase()
        db.DietaryRestrictions._records = []
        db.Caterers._records = [Record(id=self._CATERER_ID, fields={
            "name": "Big Chicken",
            "able_to_serve_school_ids": ["recSchool01"],
        })]
        db.MenuItems._records = [
            Record(id=self._TACO_ID, fields={
                "name": "Crispy Chicken Taco",
                "caterer_id": self._CATERER_ID,
                "dietary_tag_ids": [],
                "unavailable_days": taco_unavailable_days if taco_unavailable_days is not None else [],
            }),
            Record(id=self._BURRITO_ID, fields={
                "name": "Cali Burrito",
                "caterer_id": self._CATERER_ID,
                "dietary_tag_ids": [],
                "unavailable_days": burrito_unavailable_days if burrito_unavailable_days is not None else [],
            }),
            Record(id=self._WRAP_ID, fields={
                "name": "Chicken Wrap",
                "caterer_id": self._CATERER_ID,
                "dietary_tag_ids": [],
                "unavailable_days": [],
            }),
        ]
        db.Sessions._records = [Record(id=self._SESSION_ID, fields={
            "session_code": "BigChicken-Session",
            "school_id": "recSchool01",
            "caterer_id": self._CATERER_ID,
            "day": session_day,
        })]
        students = [Record(id=self._STU_ID, fields={
            "name": "Test Student",
            "dietary_requirement_ids": [],
            "session_ids": [self._SESSION_ID],
            "meal_preference_id": student_preference_id,
        })]
        if extra_students:
            students.extend(extra_students)
        db.Students._records = students
        db.Absences._records = []
        db.Exclusions._records = []
        db.CatererFeedback._records = []
        db.Orders._records = []
        db.WeeklyOrders._records = []
        return db

    def _assigned_item_ids(self, db: "MockDatabase") -> list:
        return [o.get("menu_item_id") for o in db.Orders.created_fields]

    def test_available_items_for_day_filters_blocked_items(self) -> None:
        from actions.orders.register_orders import available_items_for_day
        from support import Record

        taco    = Record(id=self._TACO_ID,    fields={"name": "Taco",    "unavailable_days": ["Tuesday"]})
        burrito = Record(id=self._BURRITO_ID, fields={"name": "Burrito", "unavailable_days": ["Monday"]})
        wrap    = Record(id=self._WRAP_ID,    fields={"name": "Wrap",    "unavailable_days": []})

        tuesday_menu = available_items_for_day([taco, burrito, wrap], "Tuesday")
        self.assertNotIn(self._TACO_ID, {i.id for i in tuesday_menu})
        self.assertIn(self._BURRITO_ID, {i.id for i in tuesday_menu})
        self.assertIn(self._WRAP_ID,    {i.id for i in tuesday_menu})

        monday_menu = available_items_for_day([taco, burrito, wrap], "Monday")
        self.assertIn(self._TACO_ID,       {i.id for i in monday_menu})
        self.assertNotIn(self._BURRITO_ID, {i.id for i in monday_menu})

    def test_day_blocked_item_excluded_from_fallback_tuesday(self) -> None:
        """Taco blocked on Tuesdays — student fallback must not assign the Taco."""
        from actions.orders.register_orders import register_orders

        db = self._make_db("Tuesday", taco_unavailable_days=["Tuesday"])
        register_orders(db, dry_run=False)

        assigned = self._assigned_item_ids(db)
        self.assertGreater(len(assigned), 0, "Student should be assigned a meal")
        self.assertNotIn(self._TACO_ID, assigned,
            "Taco must not be assigned on Tuesday when it is day-blocked")

    def test_same_item_available_on_other_day(self) -> None:
        """Taco unavailable Tuesday but available Monday — Monday fallback may use it."""
        from actions.orders.register_orders import register_orders

        db = self._make_db("Monday", taco_unavailable_days=["Tuesday"])
        register_orders(db, dry_run=False)

        # With no preference and variety fallback, the Taco is a valid candidate
        # on Monday. We can't assert it IS assigned (random pick), but we verify
        # the pipeline completes and assigns something (not an error).
        assigned = self._assigned_item_ids(db)
        self.assertEqual(len(assigned), 1, "Student on Monday should receive a meal")
        self.assertIn(assigned[0], {self._TACO_ID, self._BURRITO_ID, self._WRAP_ID})

    def test_explicit_preference_blocked_by_day_falls_back_and_logs_failure(self) -> None:
        """Student's explicit preference is day-blocked → fallback + log.failure recorded."""
        import support.error_handler as eh_module
        import tempfile, shutil
        from pathlib import Path
        from actions.orders.register_orders import register_orders
        from support.error_handler import self_healing_error_handler

        db = self._make_db(
            "Tuesday",
            taco_unavailable_days=["Tuesday"],
            student_preference_id=self._TACO_ID,  # preference is the blocked item
        )

        tmp = Path(tempfile.mkdtemp(prefix="padea_regression_dayblock_"))
        try:
            with mock.patch.object(eh_module, "_FAILURES_DIR", tmp):
                with self_healing_error_handler("register_orders_day_block_test"):
                    register_orders(db, dry_run=False)

            # A failure artifact must have been written because the preference was blocked.
            jsons = sorted(tmp.glob("failure_*.json"))
            self.assertEqual(len(jsons), 1,
                "Day-blocked preference should write a failure artifact")

            import json as _json
            payload = _json.loads(jsons[0].read_text(encoding="utf-8"))
            self.assertTrue(len(payload["logged_failures"]) >= 1,
                "At least one logged_failure for the blocked preference")
            failure_msg = payload["logged_failures"][0]
            self.assertIn("Tuesday", failure_msg)

            # Student should still receive a meal (fell back to an available item).
            assigned = self._assigned_item_ids(db)
            self.assertEqual(len(assigned), 1, "Fallback must assign a meal even when preference blocked")
            self.assertNotIn(self._TACO_ID, assigned)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_min_qty_enforcement_only_considers_day_available_items(self) -> None:
        """After day filtering, enforce_min_qty swap targets are all day-available.

        Setup: Tuesday session, Taco blocked. 5 students assigned — the pipeline
        must produce assignments with only Burrito/Wrap, and min-qty enforcement
        (if triggered) must not reintroduce the Taco.
        """
        from actions.orders.register_orders import register_orders

        extra = [
            Record(id=f"recStu0{i}", fields={
                "name": f"Student {i}",
                "dietary_requirement_ids": [],
                "session_ids": [self._SESSION_ID],
                "meal_preference_id": None,
            })
            for i in range(2, 6)
        ]
        db = self._make_db(
            "Tuesday",
            taco_unavailable_days=["Tuesday"],
            extra_students=extra,
        )
        register_orders(db, dry_run=False)

        # Orders are grouped by item, so assert on total quantity and item IDs used.
        total_meals = sum(o.get("quantity", 0) for o in db.Orders.created_fields)
        self.assertEqual(total_meals, 5, "All 5 students should be assigned a meal")
        assigned_items = self._assigned_item_ids(db)
        for item_id in assigned_items:
            self.assertNotEqual(item_id, self._TACO_ID,
                "Day-blocked Taco must not appear in any assignment after min-qty enforcement")


class TestSendMealsLinksResendApiKeyMissing(unittest.TestCase):
    """Regression for failure_20260603_201520_send_meals_links.

    Missing RESEND_API_KEY previously produced the opaque error message
    "'RESEND_API_KEY'" (a bare KeyError repr) instead of a clear message.
    After the fix, log.failure emits a human-readable explanation.
    """

    def test_failure_20260603_201520_send_meals_links(self) -> None:
        import support.error_handler as eh_module
        from actions.forms.send_meals_links import send_links
        from support.error_handler import self_healing_error_handler

        # Minimal state derived from the captured snapshot.
        snapshot: Dict[str, Any] = {
            "students": [{
                "id": "0074c290-1f3a-4a55-9596-d62dd1cc52c4",
                "fields": {
                    "name": "Phoebe Harris",
                    "year_level": 9,
                    "email": "phoebeharris@eq.edu.au",
                    "parent_name": "Hudson Harris",
                    "parent_email": "hudsonharris@gmail.com",
                    "parent_mobile": "0415 285 648",
                    "meal_preference_id": None,
                    "last_submitted": None,
                    "dietary_requirement_ids": [],
                    "session_ids": ["9bdb3fa9-60ff-42b9-919b-0cc631f0af27"],
                }
            }],
            "sessions": [{
                "id": "9bdb3fa9-60ff-42b9-919b-0cc631f0af27",
                "fields": {
                    "day": "Tuesday",
                    "school_id": "school-test-1",
                    "caterer_id": None,
                }
            }],
            "schools": [{
                "id": "school-test-1",
                "fields": {"name": "Test School"}
            }],
        }

        db = MockDatabase()
        populate_mock_db(db, snapshot)

        tmp = Path(tempfile.mkdtemp(prefix="padea_regression_smtp_"))
        try:
            with mock.patch.object(eh_module, "_FAILURES_DIR", tmp), \
                 mock.patch.dict(os.environ, {"URL_ORIGIN": "http://test:8000"}, clear=False), \
                 contextlib.redirect_stderr(io.StringIO()):
                os.environ.pop("SENDGRID_API_KEY", None)
                os.environ.pop("APP_ENV", None)
                with self_healing_error_handler("send_meals_links"):
                    send_links(target="parents", db=db)

            jsons = sorted(tmp.glob("failure_*.json"))
            self.assertEqual(len(jsons), 1,
                "Missing SENDGRID_API_KEY should write a failure artifact")

            payload = json.loads(jsons[0].read_text(encoding="utf-8"))
            self.assertEqual(len(payload["logged_failures"]), 1)
            failure_msg = payload["logged_failures"][0]

            # After fix: clear, human-readable message
            self.assertIn("SENDGRID_API_KEY", failure_msg)
            self.assertIn("not configured", failure_msg,
                "Message should say the key is not configured")

            # Audit record must be marked Failed
            self.assertTrue(
                any(v.get("status") == "Failed" for _, v in db.ScheduledEmails.updates),
                "ScheduledEmails record should be updated to Failed",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
