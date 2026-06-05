"""
Tests for scripts/actions/clarify_dietary.py.

Covers: compute_question_set (OK/NO/MAYBE filtering), caterer_restriction_union,
has_open_request, make_request_code, run_sweep (creates request and email only
when MAYBE items exist; skips OK/NO items; skips when open request exists;
skips when no dietary restrictions in enrolment).
"""
from __future__ import annotations

import unittest

import fixtures
from actions.dietary.clarify_dietary import (
    caterer_restriction_union,
    compute_question_set,
    has_open_request,
    run_sweep,
)
from mock_db import MockDatabase
from support import Record
from support.compatibility import build_hierarchy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(
    sessions=None,
    caterers=None,
    menu_items=None,
    students=None,
    existing_requests=None,
) -> MockDatabase:
    db = MockDatabase()
    db.Sessions._records = sessions or [fixtures.session_monday()]
    db.Caterers._records = caterers or [fixtures.caterer_a()]
    db.MenuItems._records = menu_items or fixtures.menu_items_caterer_a()
    db.DietaryRestrictions._records = fixtures.dietary_records()
    db.Students._records = students or [
        fixtures.student_vegetarian(),
        fixtures.student_normal(),
    ]
    db.DietaryClarificationRequests._records = existing_requests or []
    db.ScheduledEmails._records = []
    return db


# ---------------------------------------------------------------------------
# compute_question_set
# ---------------------------------------------------------------------------

class TestComputeQuestionSet(unittest.TestCase):

    def setUp(self):
        self.hierarchy = fixtures.test_hierarchy()

    def test_tagged_item_is_ok_not_maybe(self):
        """An item with a matching tag → OK, not in the question set."""
        items = [Record(id="iVgnBowl", fields={
            "name": "Vegan Bowl",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [fixtures.DIET_VEGAN_ID],
        })]
        questions = compute_question_set(
            items, {fixtures.DIET_VEGAN_ID}, self.hierarchy, []
        )
        self.assertEqual(questions, [])

    def test_keyword_item_is_no_not_maybe(self):
        """An item whose name triggers a negative keyword → NO, not in question set."""
        items = [Record(id="iBeef", fields={
            "name": "Beef Burger",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        questions = compute_question_set(
            items, {fixtures.DIET_NOBEEF_ID}, self.hierarchy, []
        )
        self.assertEqual(questions, [])

    def test_untagged_no_keyword_item_is_maybe(self):
        """An item with no tag and no keyword → MAYBE, included in question set."""
        items = [Record(id="iPasta", fields={
            "name": "Pasta Bake",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        questions = compute_question_set(
            items, {fixtures.DIET_VEG_ID}, self.hierarchy, []
        )
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["menu_item_id"], "iPasta")
        self.assertEqual(questions[0]["restriction_id"], fixtures.DIET_VEG_ID)

    def test_multiple_restrictions_multiple_maybes(self):
        """Each MAYBE (item, restriction) pair is a separate entry."""
        items = [Record(id="iPlain", fields={
            "name": "Plain Rice",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        questions = compute_question_set(
            items,
            {fixtures.DIET_VEG_ID, fixtures.DIET_VEGAN_ID},
            self.hierarchy,
            [],
        )
        self.assertEqual(len(questions), 2)
        item_ids = {q["menu_item_id"] for q in questions}
        self.assertEqual(item_ids, {"iPlain"})
        restriction_ids = {q["restriction_id"] for q in questions}
        self.assertEqual(restriction_ids, {fixtures.DIET_VEG_ID, fixtures.DIET_VEGAN_ID})

    def test_legend_blocked_item_is_no(self):
        """An item blocked by caterer legend → NO, not in question set."""
        items = [Record(id="iAnon", fields={
            "name": "Mystery Dish",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        questions = compute_question_set(
            items,
            {fixtures.DIET_VEGAN_ID},
            self.hierarchy,
            [fixtures.DIET_VEG_ID],  # legend tracks Vegetarian
        )
        self.assertEqual(questions, [])

    def test_empty_restriction_set_returns_nothing(self):
        questions = compute_question_set(
            fixtures.menu_items_caterer_a(), set(), self.hierarchy, []
        )
        self.assertEqual(questions, [])

    def test_empty_menu_returns_nothing(self):
        questions = compute_question_set(
            [], {fixtures.DIET_VEG_ID}, self.hierarchy, []
        )
        self.assertEqual(questions, [])


# ---------------------------------------------------------------------------
# caterer_restriction_union
# ---------------------------------------------------------------------------

class TestCatererRestrictionUnion(unittest.TestCase):

    def setUp(self):
        self.hierarchy = fixtures.test_hierarchy()
        self.caterer_session_ids = {fixtures.SESSION_MON_ID}

    def test_collects_restrictions_from_enrolled_students(self):
        students = [
            fixtures.student_vegetarian(),
            fixtures.student_vegan(),
            fixtures.student_normal(),
        ]
        result = caterer_restriction_union(
            self.caterer_session_ids, students, self.hierarchy
        )
        self.assertIn(fixtures.DIET_VEG_ID, result)
        self.assertIn(fixtures.DIET_VEGAN_ID, result)

    def test_excludes_opted_out_restriction(self):
        students = [fixtures.student_opted_out()]
        result = caterer_restriction_union(
            self.caterer_session_ids, students, self.hierarchy
        )
        self.assertNotIn(fixtures.DIET_OPT_ID, result)

    def test_excludes_students_not_in_caterer_sessions(self):
        student_other_session = Record(id="stuOther", fields={
            "name": "Other Student",
            "session_ids": ["sessOther"],
            "dietary_requirement_ids": [fixtures.DIET_NOBEEF_ID],
        })
        result = caterer_restriction_union(
            self.caterer_session_ids, [student_other_session], self.hierarchy
        )
        self.assertEqual(result, set())

    def test_unions_across_multiple_sessions(self):
        """Students in different sessions for the same caterer are all included."""
        student_mon = Record(id="stuMon", fields={
            "name": "Monday Student",
            "session_ids": [fixtures.SESSION_MON_ID],
            "dietary_requirement_ids": [fixtures.DIET_VEG_ID],
        })
        student_wed = Record(id="stuWed", fields={
            "name": "Wednesday Student",
            "session_ids": [fixtures.SESSION_WED_ID],
            "dietary_requirement_ids": [fixtures.DIET_NOBEEF_ID],
        })
        result = caterer_restriction_union(
            {fixtures.SESSION_MON_ID, fixtures.SESSION_WED_ID},
            [student_mon, student_wed],
            self.hierarchy,
        )
        self.assertIn(fixtures.DIET_VEG_ID, result)
        self.assertIn(fixtures.DIET_NOBEEF_ID, result)

    def test_empty_students_returns_empty(self):
        result = caterer_restriction_union(self.caterer_session_ids, [], self.hierarchy)
        self.assertEqual(result, set())


# ---------------------------------------------------------------------------
# has_open_request
# ---------------------------------------------------------------------------

class TestHasOpenRequest(unittest.TestCase):

    def test_open_request_blocks(self):
        existing = [Record(id="req1", fields={
            "caterer_id": fixtures.CATERER_A_ID,
            "status": "Open",
        })]
        self.assertTrue(has_open_request(fixtures.CATERER_A_ID, existing))

    def test_escalated_request_blocks(self):
        existing = [Record(id="req1", fields={
            "caterer_id": fixtures.CATERER_A_ID,
            "status": "Escalated",
        })]
        self.assertTrue(has_open_request(fixtures.CATERER_A_ID, existing))

    def test_resolved_request_does_not_block(self):
        existing = [Record(id="req1", fields={
            "caterer_id": fixtures.CATERER_A_ID,
            "status": "Resolved",
        })]
        self.assertFalse(has_open_request(fixtures.CATERER_A_ID, existing))

    def test_different_caterer_does_not_block(self):
        existing = [Record(id="req1", fields={
            "caterer_id": fixtures.CATERER_B_ID,
            "status": "Open",
        })]
        self.assertFalse(has_open_request(fixtures.CATERER_A_ID, existing))

    def test_caterer_with_open_request_from_any_school_blocks(self):
        """An open request for a caterer blocks regardless of which school it came from."""
        existing = [Record(id="req1", fields={
            "caterer_id": fixtures.CATERER_A_ID,
            "school_id": fixtures.SCHOOL_B_ID,  # different school
            "status": "Open",
        })]
        self.assertTrue(has_open_request(fixtures.CATERER_A_ID, existing))

    def test_no_existing_requests(self):
        self.assertFalse(has_open_request(fixtures.CATERER_A_ID, []))


# ---------------------------------------------------------------------------
# run_sweep (integration-style using MockDatabase)
# ---------------------------------------------------------------------------

class TestRunSweep(unittest.TestCase):

    def test_creates_request_for_maybe_items(self):
        """Caterer with MAYBE items gets a request created and email sent."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": "cafe@deluxe.com",
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [Record(id="iRice", fields={
            "name": "Plain Rice",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegetarian()]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        count = run_sweep(
            db,
            caterer_id=fixtures.CATERER_A_ID,
            caterer_name="Café Deluxe",
        )

        self.assertEqual(count, 1)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 1)
        req_fields = db.DietaryClarificationRequests.created_fields[0]
        self.assertEqual(req_fields["caterer_id"], fixtures.CATERER_A_ID)
        self.assertNotIn("school_id", req_fields)
        self.assertEqual(req_fields["status"], "Open")
        question_set = req_fields["question_set"]
        self.assertTrue(len(question_set) >= 1)
        self.assertTrue(all(
            {"menu_item_id", "restriction_id"} <= set(q.keys())
            for q in question_set
        ))
        self.assertEqual(len(db.ScheduledEmails.created_fields), 1)

    def test_unions_restrictions_across_schools(self):
        """Restriction union spans all sessions, not just one school."""
        session_school_b = Record(id="sessBeta", fields={
            "session_code": "Beta College - Monday",
            "school_id": fixtures.SCHOOL_B_ID,
            "caterer_id": fixtures.CATERER_A_ID,
            "day": "Monday",
        })
        student_beta = Record(id="stuBeta", fields={
            "name": "Beta Student",
            "session_ids": ["sessBeta"],
            "dietary_requirement_ids": [fixtures.DIET_NOBEEF_ID],
        })
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday(), session_school_b]
        db.Caterers._records = [fixtures.caterer_a()]
        db.MenuItems._records = [Record(id="iPlain", fields={
            "name": "Plain Dish",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegetarian(), student_beta]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        run_sweep(db, caterer_id=fixtures.CATERER_A_ID)

        req_fields = db.DietaryClarificationRequests.created_fields[0]
        restriction_ids = {q["restriction_id"] for q in req_fields["question_set"]}
        # Both VEG (from Alpha) and NOBEEF (from Beta) should be in the question set
        self.assertIn(fixtures.DIET_VEG_ID, restriction_ids)
        self.assertIn(fixtures.DIET_NOBEEF_ID, restriction_ids)

    def test_no_request_when_all_items_are_ok_or_no(self):
        """No request created when every verdict is OK or NO."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": "cafe@deluxe.com",
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [Record(id="iVgan", fields={
            "name": "Vegan Bowl",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [fixtures.DIET_VEGAN_ID],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegan()]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        count = run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        self.assertEqual(count, 0)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 0)

    def test_no_request_when_no_dietary_restrictions(self):
        """No request when enrolled students have no dietary restrictions."""
        db = _make_db(students=[fixtures.student_normal()])

        count = run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        self.assertEqual(count, 0)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 0)

    def test_skips_caterer_with_open_request(self):
        """Does not create a second request if one is already Open."""
        existing_req = Record(id="req-existing", fields={
            "caterer_id": fixtures.CATERER_A_ID,
            "status": "Open",
            "question_set": [],
        })
        db = _make_db(existing_requests=[existing_req])

        count = run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        self.assertEqual(count, 0)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 0)

    def test_no_sessions_for_caterer(self):
        """Returns 0 and creates nothing when no sessions exist for the caterer."""
        db = _make_db(sessions=[])

        count = run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        self.assertEqual(count, 0)

    def test_dry_run_does_not_write(self):
        """Dry run returns count but writes nothing."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": "cafe@deluxe.com",
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [Record(id="iRice", fields={
            "name": "Plain Rice",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegetarian()]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        count = run_sweep(
            db,
            caterer_id=fixtures.CATERER_A_ID,
            caterer_name="Café Deluxe",
            dry_run=True,
        )

        self.assertEqual(count, 1)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 0)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)

    def test_ok_items_excluded_from_question_set(self):
        """OK items (tagged) are not included in the question_set."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": "cafe@deluxe.com",
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [
            Record(id="iTagged", fields={
                "name": "Vegetarian Pasta",
                "caterer_id": fixtures.CATERER_A_ID,
                "dietary_tag_ids": [fixtures.DIET_VEG_ID],
            }),
            Record(id="iUntagged", fields={
                "name": "Plain Soup",
                "caterer_id": fixtures.CATERER_A_ID,
                "dietary_tag_ids": [],
            }),
        ]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegetarian()]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        req_fields = db.DietaryClarificationRequests.created_fields[0]
        question_set = req_fields["question_set"]
        item_ids = {q["menu_item_id"] for q in question_set}
        self.assertIn("iUntagged", item_ids)
        self.assertNotIn("iTagged", item_ids)

    def test_restriction_filter_limits_questions(self):
        """--restriction flag limits the sweep to one restriction."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": "cafe@deluxe.com",
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [Record(id="iPlain", fields={
            "name": "Plain Dish",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [
            fixtures.student_vegetarian(),
            fixtures.student_no_beef(),
        ]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        run_sweep(
            db,
            caterer_id=fixtures.CATERER_A_ID,
            caterer_name="Café Deluxe",
            restriction_name_filter="Vegetarian",
        )

        req_fields = db.DietaryClarificationRequests.created_fields[0]
        question_set = req_fields["question_set"]
        restriction_ids = {q["restriction_id"] for q in question_set}
        self.assertIn(fixtures.DIET_VEG_ID, restriction_ids)
        self.assertNotIn(fixtures.DIET_NOBEEF_ID, restriction_ids)

    def test_no_email_when_no_contact_email(self):
        """When caterer has no contact_email, request is still created but no email."""
        db = MockDatabase()
        db.Sessions._records = [fixtures.session_monday()]
        db.Caterers._records = [Record(id=fixtures.CATERER_A_ID, fields={
            "name": "Café Deluxe",
            "contact_email": None,
            "legend_tag_ids": [],
            "able_to_serve_school_ids": [],
        })]
        db.MenuItems._records = [Record(id="iRice", fields={
            "name": "Plain Rice",
            "caterer_id": fixtures.CATERER_A_ID,
            "dietary_tag_ids": [],
        })]
        db.DietaryRestrictions._records = fixtures.dietary_records()
        db.Students._records = [fixtures.student_vegetarian()]
        db.DietaryClarificationRequests._records = []
        db.ScheduledEmails._records = []

        count = run_sweep(db, caterer_id=fixtures.CATERER_A_ID, caterer_name="Café Deluxe")

        self.assertEqual(count, 1)
        self.assertEqual(len(db.DietaryClarificationRequests.created_fields), 1)
        self.assertEqual(len(db.ScheduledEmails.created_fields), 0)


if __name__ == "__main__":
    unittest.main()
