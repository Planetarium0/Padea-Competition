"""Tests for the manage-page API endpoints added to scripts/actions/api.py.

Covers:
  GET  /api/manager/<manager_id>/sessions
  GET  /api/session/<session_id>/students-all
  PATCH /api/student/<student_id>/dietary-requirements
  PATCH /api/student/<student_id>/order-override
"""
from __future__ import annotations

import unittest

import fixtures
from actions.api import (
    api_get_manager_sessions,
    api_get_session_students_all,
    api_override_order,
    api_update_dietary_requirements,
)
from mock_db import MockDatabase
from support import Record

# ---------------------------------------------------------------------------
# Extra IDs used only in this module
# ---------------------------------------------------------------------------

ORDER_CHICKEN_ID = "ordChk01"
ORDER_BEEF_ID    = "ordBef01"
STU_OTHER_ID     = "stuOthr1"


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _session_with_students(*student_ids: str) -> Record:
    """Monday session pre-populated with the given student IDs in its Students field."""
    return Record(id=fixtures.SESSION_MON_ID, fields={
        "Session ID":      "Alpha Academy - Monday",
        "School":          [fixtures.SCHOOL_A_ID],
        "Caterer":         [fixtures.CATERER_A_ID],
        "Day":             "Monday",
        "On-Site Manager": [fixtures.MANAGER_A_ID],
        "Students":        list(student_ids),
    })


def _order(order_id: str, menu_item_id: str, student_ids: list[str],
           session_id: str = fixtures.SESSION_MON_ID) -> Record:
    return Record(id=order_id, fields={
        "Order ID":  order_id,
        "Menu Item": [menu_item_id],
        "Session":   [session_id],
        "Student":   list(student_ids),
        "Quantity":  len(student_ids),
    })


# ===========================================================================
# GET /api/manager/<manager_id>/sessions
# ===========================================================================

class TestApiGetManagerSessions(unittest.TestCase):

    def test_returns_sessions_for_manager(self):
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Schools._records  = [fixtures.school_alpha()]
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(status, 200)
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"],    fixtures.SESSION_MON_ID)
        self.assertEqual(body[0]["label"], "Monday — Alpha Academy")

    def test_sorted_by_day_order(self):
        wed = Record(id=fixtures.SESSION_WED_ID, fields={
            "School": [fixtures.SCHOOL_A_ID],
            "Day":    "Wednesday",
        })
        db = MockDatabase()
        # Insert Wednesday first to confirm sorting is applied.
        db.Sessions._records = [wed, fixtures.session_monday()]
        db.Schools._records  = [fixtures.school_alpha()]
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(status, 200)
        self.assertEqual([s["day"] for s in body], ["Monday", "Wednesday"])

    def test_missing_school_falls_back_to_question_mark(self):
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Schools._records  = []   # school record absent
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(status, 200)
        self.assertIn("?", body[0]["label"])

    def test_includes_caterer_and_incoming_caterer_ids(self):
        sess = Record(id=fixtures.SESSION_MON_ID, fields={
            "School":           [fixtures.SCHOOL_A_ID],
            "Day":              "Monday",
            "Caterer":          [fixtures.CATERER_A_ID],
            "Incoming Caterer": [fixtures.CATERER_B_ID],
        })
        db = MockDatabase()
        db.Sessions._records = [sess]
        db.Schools._records  = [fixtures.school_alpha()]
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(body[0]["catererIds"],         [fixtures.CATERER_A_ID])
        self.assertEqual(body[0]["incomingCatererIds"], [fixtures.CATERER_B_ID])

    def test_no_incoming_caterer_returns_empty_list(self):
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Schools._records  = [fixtures.school_alpha()]
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(body[0]["incomingCatererIds"], [])

    def test_returns_empty_list_when_no_sessions(self):
        db = MockDatabase()
        status, body = api_get_manager_sessions(fixtures.MANAGER_A_ID, db=db)
        self.assertEqual(status, 200)
        self.assertEqual(body, [])


# ===========================================================================
# GET /api/session/<session_id>/students-all
# ===========================================================================

class TestApiGetSessionStudentsAll(unittest.TestCase):

    def test_returns_404_for_unknown_session(self):
        db = MockDatabase()
        status, body = api_get_session_students_all("recMissing", db=db)
        self.assertEqual(status, 404)
        self.assertIn("error", body)

    def test_returns_empty_list_when_session_has_no_students(self):
        db = MockDatabase()
        db.Sessions._records = [_session_with_students()]
        status, body = api_get_session_students_all(fixtures.SESSION_MON_ID, db=db)
        self.assertEqual(status, 200)
        self.assertEqual(body, [])

    def test_returns_student_list_sorted_by_name(self):
        db = MockDatabase()
        db.Sessions._records = [_session_with_students(fixtures.STU_VEG_ID, fixtures.STU_NORMAL_ID)]
        db.Students._records = [fixtures.student_normal(), fixtures.student_vegetarian()]
        status, body = api_get_session_students_all(fixtures.SESSION_MON_ID, db=db)
        self.assertEqual(status, 200)
        self.assertEqual(len(body), 2)
        names = [s["name"] for s in body]
        self.assertEqual(names, sorted(names))

    def test_each_entry_has_id_and_name(self):
        db = MockDatabase()
        db.Sessions._records = [_session_with_students(fixtures.STU_NORMAL_ID)]
        db.Students._records = [fixtures.student_normal()]
        status, body = api_get_session_students_all(fixtures.SESSION_MON_ID, db=db)
        self.assertEqual(body[0]["id"],   fixtures.STU_NORMAL_ID)
        self.assertEqual(body[0]["name"], "Normal Student")

    def test_nameless_student_shown_as_placeholder(self):
        nameless = Record(id="stuNoNm1", fields={"Student Name": None, "Sessions": [fixtures.SESSION_MON_ID]})
        db = MockDatabase()
        db.Sessions._records = [_session_with_students("stuNoNm1")]
        db.Students._records = [nameless]
        status, body = api_get_session_students_all(fixtures.SESSION_MON_ID, db=db)
        self.assertEqual(body[0]["name"], "(no name)")


# ===========================================================================
# PATCH /api/student/<student_id>/dietary-requirements
# ===========================================================================

class TestApiUpdateDietaryRequirements(unittest.TestCase):

    def test_writes_restriction_ids_to_student(self):
        db = MockDatabase()
        db.Students._records = [fixtures.student_normal()]
        status, body = api_update_dietary_requirements(
            fixtures.STU_NORMAL_ID,
            restriction_ids=[fixtures.DIET_VEG_ID],
            db=db,
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        updates = {uid: f for uid, f in db.Students.updates}
        self.assertEqual(updates[fixtures.STU_NORMAL_ID]["Dietary Requirements"], [fixtures.DIET_VEG_ID])

    def test_clears_restrictions_with_empty_list(self):
        db = MockDatabase()
        db.Students._records = [fixtures.student_vegetarian()]
        api_update_dietary_requirements(
            fixtures.STU_VEG_ID, restriction_ids=[], db=db,
        )
        updates = {uid: f for uid, f in db.Students.updates}
        self.assertEqual(updates[fixtures.STU_VEG_ID]["Dietary Requirements"], [])

    def test_sets_multiple_restrictions(self):
        db = MockDatabase()
        db.Students._records = [fixtures.student_normal()]
        api_update_dietary_requirements(
            fixtures.STU_NORMAL_ID,
            restriction_ids=[fixtures.DIET_VEG_ID, fixtures.DIET_NOBEEF_ID],
            db=db,
        )
        updates = {uid: f for uid, f in db.Students.updates}
        self.assertCountEqual(
            updates[fixtures.STU_NORMAL_ID]["Dietary Requirements"],
            [fixtures.DIET_VEG_ID, fixtures.DIET_NOBEEF_ID],
        )


# ===========================================================================
# PATCH /api/student/<student_id>/order-override
# ===========================================================================

class TestApiOverrideOrder(unittest.TestCase):

    # -- No-op when the requested meal is already assigned ------------------

    def test_noop_when_meal_unchanged(self):
        db = MockDatabase()
        db.Orders._records = [_order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID])]
        status, body = api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_CHICKEN_RICE_ID,
            db=db,
        )
        self.assertEqual(status, 200)
        self.assertFalse(body["changed"])
        self.assertEqual(db.Orders.updates, [])
        self.assertEqual(db.Orders.deleted_ids, [])

    # -- Student is the sole occupant of the old order ----------------------

    def test_deletes_old_order_when_student_is_sole_occupant(self):
        db = MockDatabase()
        db.Orders._records = [_order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID])]
        api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertIn(ORDER_CHICKEN_ID, db.Orders.deleted_ids)

    def test_creates_new_order_when_target_meal_has_no_existing_order(self):
        db = MockDatabase()
        db.Orders._records = [_order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID])]
        api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertEqual(len(db.Orders.created_fields), 1)
        created = db.Orders.created_fields[0]
        self.assertEqual(created["Menu Item"], [fixtures.ITEM_BEEF_BURGER_ID])
        self.assertEqual(created["Student"],   [fixtures.STU_NORMAL_ID])
        self.assertEqual(created["Session"],   [fixtures.SESSION_MON_ID])
        self.assertEqual(created["Quantity"],  1)

    def test_adds_student_to_existing_target_order(self):
        db = MockDatabase()
        db.Orders._records = [
            _order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID]),
            _order(ORDER_BEEF_ID,    fixtures.ITEM_BEEF_BURGER_ID,   [STU_OTHER_ID]),
        ]
        api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        beef_updates = [f for uid, f in db.Orders.updates if uid == ORDER_BEEF_ID]
        self.assertTrue(beef_updates)
        self.assertIn(fixtures.STU_NORMAL_ID, beef_updates[-1]["Student"])
        self.assertEqual(beef_updates[-1]["Quantity"], 2)

    # -- Student shares the old order with other students -------------------

    def test_updates_shared_old_order_without_deleting_it(self):
        db = MockDatabase()
        db.Orders._records = [
            _order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID, STU_OTHER_ID]),
        ]
        api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertNotIn(ORDER_CHICKEN_ID, db.Orders.deleted_ids)
        chicken_updates = [f for uid, f in db.Orders.updates if uid == ORDER_CHICKEN_ID]
        self.assertTrue(chicken_updates)
        self.assertNotIn(fixtures.STU_NORMAL_ID, chicken_updates[-1]["Student"])
        self.assertEqual(chicken_updates[-1]["Quantity"], 1)

    # -- Student has no prior order -----------------------------------------

    def test_creates_order_for_student_with_no_prior_order(self):
        db = MockDatabase()
        db.Orders._records = []   # nothing today
        status, body = api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["changed"])
        self.assertEqual(len(db.Orders.created_fields), 1)
        self.assertEqual(db.Orders.created_fields[0]["Student"], [fixtures.STU_NORMAL_ID])

    def test_appends_to_existing_target_when_student_has_no_prior_order(self):
        db = MockDatabase()
        db.Orders._records = [_order(ORDER_BEEF_ID, fixtures.ITEM_BEEF_BURGER_ID, [STU_OTHER_ID])]
        api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertEqual(db.Orders.created_fields, [])
        beef_updates = [f for uid, f in db.Orders.updates if uid == ORDER_BEEF_ID]
        self.assertIn(fixtures.STU_NORMAL_ID, beef_updates[-1]["Student"])

    # -- Return shape -------------------------------------------------------

    def test_returns_ok_true_changed_true_on_success(self):
        db = MockDatabase()
        db.Orders._records = [_order(ORDER_CHICKEN_ID, fixtures.ITEM_CHICKEN_RICE_ID, [fixtures.STU_NORMAL_ID])]
        status, body = api_override_order(
            fixtures.STU_NORMAL_ID,
            session_id=fixtures.SESSION_MON_ID,
            new_meal_item_id=fixtures.ITEM_BEEF_BURGER_ID,
            db=db,
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["changed"])


if __name__ == "__main__":
    unittest.main()
