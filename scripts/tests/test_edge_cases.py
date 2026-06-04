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


class TestSendMealsLinksResendApiKeyMissing(unittest.TestCase):
    """Regression for failure_20260603_201520_send_meals_links.

    Missing RESEND_API_KEY previously produced the opaque error message
    "'RESEND_API_KEY'" (a bare KeyError repr) instead of a clear message.
    After the fix, log.failure emits a human-readable explanation.
    """

    def test_failure_20260603_201520_send_meals_links(self) -> None:
        import support.error_handler as eh_module
        from actions.send_meals_links import send_links
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
                    send_links(target="parents", limit=1, db=db)

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
