"""
Tests for scripts/actions/evaluate_caterers.py.

Covers: get_rolling_stats (window selection, insufficient data),
caterer_covers_all_students (hard dietary filter, opted-out skipping),
score_candidate (school vs overall weighting),
has_active_proposal, was_rejected_this_term.
"""
from __future__ import annotations

import types
import unittest
from datetime import date

import fixtures
from actions.caterers.evaluate_caterers import (
    EvaluationData,
    EvaluationIndex,
    FeedbackEntry,
    MIN_RATERS,
    MIN_SESSIONS,
    ROLLING_WINDOW,
    SWITCH_THRESHOLD,
    WATCH_THRESHOLD,
    caterer_covers_all_students,
    find_candidates,
    get_rolling_stats,
    get_term_start,
    has_active_proposal,
    score_candidate,
    was_rejected_this_term,
)
from support import Record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fb(date_str: str, session_id: str, rating: int, student_id: str) -> FeedbackEntry:
    return FeedbackEntry(
        date_str=date_str,
        session_id=session_id,
        rating=rating,
        student_id=student_id
    )


def _make_eval_index(
    menu_by_caterer: dict | None = None,
    hierarchy=None,
    feedback_index: dict | None = None,
    caterer_names: dict | None = None,
    school_to_sessions: dict | None = None,
) -> object:
    """Minimal namespace sufficient for the pure evaluation functions."""
    return types.SimpleNamespace(
        menu_by_caterer   = menu_by_caterer    or {},
        dietary_hierarchy = hierarchy          or fixtures.test_hierarchy(),
        feedback_index    = feedback_index     or {},
        caterer_names     = caterer_names      or {},
        school_to_sessions= school_to_sessions or {},
    )


def _proposal(session_id: str, caterer_id: str, status: str, proposed_on: str) -> Record:
    return Record(id=f"prop-{status[:3]}", fields={
        "session_id":          session_id,
        "outgoing_caterer_id": caterer_id,
        "status":              status,
        "proposed_on":         proposed_on,
    })


# ---------------------------------------------------------------------------
# get_rolling_stats
# ---------------------------------------------------------------------------

class TestGetRollingStats(unittest.TestCase):
    def test_returns_stats_when_at_or_above_min_sessions(self):
        # MIN_SESSIONS is currently 0 (intentionally disabled — see problem 28
        # in plans/problems). Any non-empty entry list produces stats.
        entries = [
            _fb("2026-01-05", "s1", 2, "u1"),
            _fb("2026-01-05", "s1", 3, "u2"),
            _fb("2026-01-12", "s2", 2, "u3"),
        ]
        result = get_rolling_stats(entries)
        self.assertIsNotNone(result)
        self.assertEqual(result.num_sessions, 2)

    def test_returns_stats_with_enough_sessions(self):
        entries = [
            _fb("2026-01-05", "s1", 2, "u1"),
            _fb("2026-01-12", "s2", 3, "u2"),
            _fb("2026-01-19", "s3", 2, "u3"),
            _fb("2026-01-26", "s3", 4, "u4"),  # s3: two ratings
        ]
        result = get_rolling_stats(entries)
        self.assertIsNotNone(result)
        self.assertEqual(result.num_sessions, 3)
        # Ratings: s1=[2], s2=[3], s3=[2,4] → avg = (2+3+2+4)/4 = 2.75
        self.assertAlmostEqual(result.avg_rating, 2.75)
        self.assertEqual(result.num_raters, 4)

    def test_rolling_window_uses_only_most_recent_n_sessions(self):
        # 5 sessions; ROLLING_WINDOW=4 → only last 4 are used.
        # Oldest session (s1) has high ratings — window should exclude it.
        entries = [
            _fb("2026-01-05", "s1", 5, "u1"),   # oldest, excluded from window
            _fb("2026-01-05", "s1", 5, "u2"),
            _fb("2026-01-12", "s2", 2, "u3"),
            _fb("2026-01-19", "s3", 2, "u4"),
            _fb("2026-01-26", "s4", 2, "u5"),
            _fb("2026-02-02", "s5", 2, "u6"),
        ]
        result = get_rolling_stats(entries)
        self.assertIsNotNone(result)
        # Window = s2, s3, s4, s5 — all rated 2 → avg = 2.0
        self.assertAlmostEqual(result.avg_rating, 2.0)
        self.assertEqual(result.num_sessions, ROLLING_WINDOW)

    def test_multiple_students_same_session_counted_as_one_session(self):
        # 10 ratings across only 2 distinct sessions. MIN_SESSIONS=0 lets this
        # through (see problem 28); the assertion verifies the session bucketing
        # is by session_id rather than counting each rating as its own "session".
        entries = [_fb("2026-01-05", "s1", 3, f"u{i}") for i in range(5)]
        entries += [_fb("2026-01-12", "s2", 3, f"u{i+5}") for i in range(5)]
        result = get_rolling_stats(entries)
        self.assertIsNotNone(result)
        self.assertEqual(result.num_sessions, 2)
        self.assertEqual(result.num_raters, 10)

    def test_rater_count_is_unique_students(self):
        # Same student u1 rates twice across two sessions — should count once.
        entries = [
            _fb("2026-01-05", "s1", 3, "u1"),
            _fb("2026-01-12", "s2", 3, "u1"),  # u1 again
            _fb("2026-01-19", "s3", 3, "u2"),
            _fb("2026-01-26", "s4", 3, "u3"),
            _fb("2026-02-02", "s5", 3, "u4"),
        ]
        result = get_rolling_stats(entries)
        self.assertIsNotNone(result)
        # Window = last 4 sessions (s2–s5). u1 appears in s2 → unique raters = {u1, u2, u3, u4}
        self.assertEqual(result.num_raters, 4)


# ---------------------------------------------------------------------------
# caterer_covers_all_students
# ---------------------------------------------------------------------------

class TestCatererCoversAllStudents(unittest.TestCase):

    def test_all_students_covered_returns_true(self):
        # Caterer B has Grilled Chicken + Vegetable Curry (vegan-tagged).
        # Students: normal and vegetarian — both coverable.
        school_students = [fixtures.student_normal(), fixtures.student_vegetarian()]
        idx = _make_eval_index(
            menu_by_caterer={fixtures.CATERER_B_ID: fixtures.menu_items_caterer_b()},
        )
        ok, failing = caterer_covers_all_students(fixtures.CATERER_B_ID, school_students, idx)
        self.assertTrue(ok)
        self.assertIsNone(failing)

    def test_uncoverable_vegan_student_returns_false_with_name(self):
        # Meat-only caterer: Chicken Burger + Beef Steak.
        # "chicken" and "beef" both appear in Vegan negative keywords → no match.
        school_students = [fixtures.student_normal(), fixtures.student_vegan()]
        idx = _make_eval_index(
            menu_by_caterer={fixtures.CATERER_MEAT_ID: fixtures.menu_items_meat_only()},
        )
        ok, failing = caterer_covers_all_students(fixtures.CATERER_MEAT_ID, school_students, idx)
        self.assertFalse(ok)
        self.assertEqual(failing, "Vegan Student")

    def test_opted_out_student_is_skipped(self):
        # Opted-out student should not block an otherwise-valid caterer.
        school_students = [fixtures.student_opted_out(), fixtures.student_normal()]
        idx = _make_eval_index(
            menu_by_caterer={fixtures.CATERER_B_ID: fixtures.menu_items_caterer_b()},
        )
        ok, failing = caterer_covers_all_students(fixtures.CATERER_B_ID, school_students, idx)
        self.assertTrue(ok)
        self.assertIsNone(failing)

    def test_caterer_with_no_menu_items_returns_false(self):
        school_students = [fixtures.student_normal()]
        idx = _make_eval_index(menu_by_caterer={})
        ok, failing = caterer_covers_all_students(fixtures.CATERER_B_ID, school_students, idx)
        self.assertFalse(ok)
        self.assertIsNotNone(failing)

    def test_vegetarian_covered_by_vegan_tagged_item(self):
        # Vegan-tagged item satisfies Vegetarian via subset closure.
        vegan_item_only = [Record(id="iV", fields={
            "name":            "Vegan Bowl",
            "caterer_id":      fixtures.CATERER_B_ID,
            "dietary_tag_ids": [fixtures.DIET_VEGAN_ID],
        })]
        school_students = [fixtures.student_vegetarian()]
        idx = _make_eval_index(
            menu_by_caterer={fixtures.CATERER_B_ID: vegan_item_only},
        )
        ok, failing = caterer_covers_all_students(fixtures.CATERER_B_ID, school_students, idx)
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# score_candidate
# ---------------------------------------------------------------------------

class TestScoreCandidate(unittest.TestCase):
    """Feedback index is keyed by (session_id, caterer_id); the school-scoped
    average is computed by filtering on the session IDs that belong to the
    school via index.school_to_sessions."""

    def test_school_history_blended_with_overall(self):
        # School A session 's1' has a 4-rating; school B session 's2' has 2.
        # Overall avg = (4+2)/2 = 3.0
        # Score at school A = 0.6*4.0 + 0.4*3.0 = 3.6
        idx = _make_eval_index(
            feedback_index={
                ("s1", fixtures.CATERER_A_ID): [_fb("2026-01-01", "s1", 4, "u1")],
                ("s2", fixtures.CATERER_A_ID): [_fb("2026-01-01", "s2", 2, "u2")],
            },
            school_to_sessions={
                fixtures.SCHOOL_A_ID: ["s1"],
                fixtures.SCHOOL_B_ID: ["s2"],
            },
            caterer_names={fixtures.CATERER_A_ID: "Café Deluxe"},
        )
        score = score_candidate(fixtures.CATERER_A_ID, fixtures.SCHOOL_A_ID, idx)
        self.assertAlmostEqual(score, 3.6)

    def test_no_school_history_uses_overall_only(self):
        # School B has no sessions of its own with this caterer.
        # Overall avg from school A's sessions = 4.0.
        idx = _make_eval_index(
            feedback_index={
                ("s1", fixtures.CATERER_A_ID): [
                    _fb("2026-01-01", "s1", 4, "u1"),
                    _fb("2026-01-08", "s2", 4, "u2"),
                ],
            },
            school_to_sessions={
                fixtures.SCHOOL_A_ID: ["s1", "s2"],
                fixtures.SCHOOL_B_ID: [],
            },
            caterer_names={fixtures.CATERER_A_ID: "Café Deluxe"},
        )
        score = score_candidate(fixtures.CATERER_A_ID, fixtures.SCHOOL_B_ID, idx)
        self.assertAlmostEqual(score, 4.0)

    def test_no_history_anywhere_defaults_to_3(self):
        idx = _make_eval_index(
            feedback_index={},
            school_to_sessions={fixtures.SCHOOL_A_ID: ["s1"]},
            caterer_names={fixtures.CATERER_B_ID: "Fresh Eats"},
        )
        score = score_candidate(fixtures.CATERER_B_ID, fixtures.SCHOOL_A_ID, idx)
        self.assertAlmostEqual(score, 3.0)


# ---------------------------------------------------------------------------
# has_active_proposal
# ---------------------------------------------------------------------------

class TestHasActiveProposal(unittest.TestCase):

    def test_pending_proposal_blocks(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Pending", "2026-02-01")]
        self.assertTrue(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals))

    def test_approved_proposal_blocks(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Approved", "2026-02-01")]
        self.assertTrue(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals))

    def test_executed_proposal_blocks(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Executed", "2026-02-01")]
        self.assertTrue(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals))

    def test_rejected_proposal_does_not_block(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Rejected", "2026-02-01")]
        self.assertFalse(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals))

    def test_different_session_does_not_block(self):
        proposals = [_proposal(fixtures.SESSION_WED_ID, fixtures.CATERER_A_ID, "Pending", "2026-02-01")]
        self.assertFalse(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals))

    def test_no_proposals(self):
        self.assertFalse(has_active_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, []))


# ---------------------------------------------------------------------------
# was_rejected_this_term
# ---------------------------------------------------------------------------

class TestWasRejectedThisTerm(unittest.TestCase):

    TERM_START = date(2026, 4, 20)

    def test_rejected_after_term_start(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Rejected", "2026-05-01")]
        self.assertTrue(was_rejected_this_term(
            fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals, self.TERM_START,
        ))

    def test_rejected_on_term_start_day(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Rejected", "2026-04-20")]
        self.assertTrue(was_rejected_this_term(
            fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals, self.TERM_START,
        ))

    def test_rejected_before_term_start_not_suppressed(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Rejected", "2026-04-15")]
        self.assertFalse(was_rejected_this_term(
            fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals, self.TERM_START,
        ))

    def test_pending_not_treated_as_rejected(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, "Pending", "2026-05-01")]
        self.assertFalse(was_rejected_this_term(
            fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals, self.TERM_START,
        ))

    def test_different_caterer_not_matched(self):
        proposals = [_proposal(fixtures.SESSION_MON_ID, fixtures.CATERER_B_ID, "Rejected", "2026-05-01")]
        self.assertFalse(was_rejected_this_term(
            fixtures.SESSION_MON_ID, fixtures.CATERER_A_ID, proposals, self.TERM_START,
        ))


# ---------------------------------------------------------------------------
# get_term_start
# ---------------------------------------------------------------------------

class TestGetTermStart(unittest.TestCase):

    def test_during_first_term(self):
        self.assertEqual(get_term_start(date(2026, 2, 1)), date(2026, 1, 27))

    def test_exactly_on_term_start(self):
        self.assertEqual(get_term_start(date(2026, 4, 20)), date(2026, 4, 20))

    def test_during_second_term(self):
        self.assertEqual(get_term_start(date(2026, 5, 15)), date(2026, 4, 20))

    def test_before_all_term_starts_falls_back_to_first(self):
        # Date earlier than the first term start returns the first term.
        self.assertEqual(get_term_start(date(2026, 1, 1)), date(2026, 1, 27))


# ---------------------------------------------------------------------------
# find_candidates — dietary hard filter integration
# ---------------------------------------------------------------------------

def _build_eval_index(
    caterers: list[Record],
    menu_items: list[Record],
    students: list[Record] | None = None,
    sessions: list[Record] | None = None,
) -> EvaluationIndex:
    """Build a real EvaluationIndex from minimal test data."""
    data = EvaluationData(
        sessions=             sessions if sessions is not None else [fixtures.session_monday()],
        feedback=             [],
        caterers=             caterers,
        students=             students or [],
        menu_items=           menu_items,
        dietary_restrictions= fixtures.dietary_records(),
        proposals=            [],
        schools=              [fixtures.school_alpha(), fixtures.school_beta()],
        managers=             [],
    )
    return EvaluationIndex.build(data)


class TestFindCandidates(unittest.TestCase):
    """Verify find_candidates applies the dietary hard filter end-to-end,
    not just that caterer_covers_all_students works in isolation."""

    def test_caterer_without_vegan_option_excluded(self):
        # School A has a vegan student.  Meat Masters can serve but has
        # only chicken and beef items — neither is compatible with Vegan.
        # A second caterer ("Good Eats") has a vegan-tagged item and should
        # be the sole candidate returned.
        good_caterer_id = "cGood0001"
        good_caterer = Record(id=good_caterer_id, fields={
            "name":                     "Good Eats",
            "able_to_serve_school_ids": [fixtures.SCHOOL_A_ID],
        })
        good_menu_item = Record(id="iGoodVgn", fields={
            "name":            "Vegan Curry",
            "caterer_id":      good_caterer_id,
            "dietary_tag_ids": [fixtures.DIET_VEGAN_ID],
        })

        index = _build_eval_index(
            caterers=[fixtures.caterer_meat_only(), good_caterer],
            menu_items=fixtures.menu_items_meat_only() + [good_menu_item],
        )
        school_students = [fixtures.student_vegan()]

        candidates = find_candidates(
            session_id=          fixtures.SESSION_MON_ID,
            outgoing_caterer_id= "cOutgoing",
            session_students=    school_students,
            index=               index,
        )

        candidate_ids = [cid for _, cid, _ in candidates]
        self.assertNotIn(fixtures.CATERER_MEAT_ID, candidate_ids,
                         "Meat-only caterer should be excluded (can't cover vegan student)")
        self.assertIn(good_caterer_id, candidate_ids,
                      "Caterer with vegan item should be included")

    def test_all_candidates_excluded_returns_empty_list(self):
        # Both available caterers are meat-only — no valid replacement exists.
        caterer_2 = Record(id="cMeat0002", fields={
            "name":                     "Burger Palace",
            "able_to_serve_school_ids": [fixtures.SCHOOL_A_ID],
        })
        burger_item = Record(id="iBurger", fields={
            "name":            "Beef Burger",
            "caterer_id":      "cMeat0002",
            "dietary_tag_ids": [],
        })

        index = _build_eval_index(
            caterers=[fixtures.caterer_meat_only(), caterer_2],
            menu_items=fixtures.menu_items_meat_only() + [burger_item],
        )
        school_students = [fixtures.student_vegan()]

        candidates = find_candidates(
            session_id=          fixtures.SESSION_MON_ID,
            outgoing_caterer_id= "cOutgoing",
            session_students=    school_students,
            index=               index,
        )
        self.assertEqual(candidates, [])

    def test_outgoing_caterer_not_listed_as_candidate(self):
        # The caterer being replaced must never appear in the candidate list,
        # even if it's on Able to Serve and would otherwise be valid.
        outgoing_id = fixtures.CATERER_A_ID
        index = _build_eval_index(
            caterers=[fixtures.caterer_a()],
            menu_items=fixtures.menu_items_caterer_a(),
        )
        # caterer_a has Able to Serve = [] so it wouldn't pass the able check
        # anyway, but we explicitly test the skip-self logic with a caterer
        # that IS able to serve.
        caterer_self_able = Record(id=outgoing_id, fields={
            "name":                     "Self Caterer",
            "able_to_serve_school_ids": [fixtures.SCHOOL_A_ID],
        })
        index2 = _build_eval_index(
            caterers=[caterer_self_able],
            menu_items=fixtures.menu_items_caterer_a(),
        )
        candidates = find_candidates(
            session_id=          fixtures.SESSION_MON_ID,
            outgoing_caterer_id= outgoing_id,
            session_students=    [fixtures.student_normal()],
            index=               index2,
        )
        candidate_ids = [cid for _, cid, _ in candidates]
        self.assertNotIn(outgoing_id, candidate_ids)

    def test_caterer_not_able_to_serve_school_excluded(self):
        # Even a caterer with a perfect menu is excluded if the school isn't
        # in its Able to Serve Schools list.
        caterer_wrong_area = Record(id="cFarAway", fields={
            "name":                     "Far Away Foods",
            "able_to_serve_school_ids": [fixtures.SCHOOL_B_ID],  # wrong school
        })
        far_menu = [Record(id="iFarVgn", fields={
            "name":            "Vegan Delight",
            "caterer_id":      "cFarAway",
            "dietary_tag_ids": [fixtures.DIET_VEGAN_ID],
        })]
        index = _build_eval_index(
            caterers=[caterer_wrong_area],
            menu_items=far_menu,
        )
        candidates = find_candidates(
            session_id=          fixtures.SESSION_MON_ID,
            outgoing_caterer_id= "cOutgoing",
            session_students=    [fixtures.student_normal()],
            index=               index,
        )
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
