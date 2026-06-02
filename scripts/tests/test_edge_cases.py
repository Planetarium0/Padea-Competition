"""Regression testing suite for catchable edge cases and automated self-healing.

Allows developers and automated agents to quickly replicate and patch system failures
by loading serialized failure JSON states directly into MockDatabase.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any, Dict

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
            "Student Name": "Incomplete Student",
            "Year Level": "NOT_AN_INT",  # Invalid type: Pydantic expects int or null
            "Dietary Requirements": [],
        }

        # Verify that Pydantic validation catches this and raises ValidationError
        from pydantic import ValidationError
        from support.schemas import Student as StudentModel

        with self.assertRaises(ValidationError):
            StudentModel.model_validate(invalid_student_data)

        # 2. Demonstrate how MockDatabase is populated from a captured state
        mock_snapshot = {
            "students": [
                {"id": "recStudent01", "fields": {"Student Name": "Good Student", "Year Level": 12}},
                {"id": "recStudent02", "fields": {"Student Name": "Another Student", "Year Level": 11}}
            ],
            "caterers": [
                {"id": "recCaterer01", "fields": {"Caterer Name": "Eco Lunch", "Able to Serve Schools": []}}
            ]
        }

        db = MockDatabase()
        populate_mock_db(db, mock_snapshot)

        # Assert database was correctly populated in-memory
        self.assertEqual(len(db.Students.all()), 2)
        self.assertEqual(db.Students.all()[0].fields["Student Name"], "Good Student")
        self.assertEqual(db.Students.all()[1].fields["Year Level"], 11)
        self.assertEqual(len(db.Caterers.all()), 1)
        self.assertEqual(db.Caterers.all()[0].fields["Caterer Name"], "Eco Lunch")

    def test_logical_unhandled_edge_case(self) -> None:
        """Concrete example: replicates an unhandled logical exception in ordering logic."""
        # Setup an ordering scenario where a student has a dietary requirement but the caterer menu has NO compatible food.
        # This is a classic business logic edge case!
        mock_snapshot = {
            "students": [
                {
                    "id": "recStudentVegan",
                    "fields": {
                        "Student Name": "Vegan Student",
                        "Dietary Requirements": ["recDietVeg"],
                        "Sessions": ["recSessionMon"]
                    }
                }
            ],
            "dietary_restrictions": [
                {"id": "recDietVeg", "fields": {"Restriction Name": "Vegan", "Supersets": []}}
            ],
            "sessions": [
                {
                    "id": "recSessionMon",
                    "fields": {
                        "Session ID": "Alpha - Mon",
                        "School": ["recSchoolA"],
                        "Caterer": ["recCatererMeat Only"],
                        "Day": "Monday",
                        "Year Levels": ["All"]
                    }
                }
            ],
            "caterers": [
                {
                    "id": "recCatererMeat Only",
                    "fields": {
                        "Caterer Name": "Meat Masters",
                        "Able to Serve Schools": ["recSchoolA"]
                    }
                }
            ],
            "menu_items": [
                # Only a meat option is available - NO VEGAN option!
                {
                    "id": "recMenuBeef",
                    "fields": {
                        "Menu Item Name": "Beef Burger",
                        "Caterer": ["recCatererMeat Only"],
                        "Dietary Tags": []
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
            if is_item_compatible(item.fields, vegan_student.fields["Dietary Requirements"], hierarchy)
        ]
        
        # Test assertion replicating the unhandled logic state: No compatible items!
        self.assertEqual(len(compatible_items), 0)
