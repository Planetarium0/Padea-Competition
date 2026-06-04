"""
Tests for parse_dietary_reply.parse_reply.

All tests use MockDatabase and patch ask_llm in parse_dietary_reply.
No real Supabase or Anthropic API calls are made.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

os.environ.setdefault("PADEA_TEST_MODE", "1")

from support import Record
from support.inbound import InboundMessage
from actions.parse_dietary_reply import parse_reply, _extract_json

from mock_db import MockDatabase
from fixtures import (
    CATERER_A_ID,
    ITEM_CHICKEN_RICE_ID,
    ITEM_VEG_PASTA_ID,
    ITEM_VEGAN_BOWL_ID,
    ITEM_BEEF_BURGER_ID,
    DIET_VEG_ID,
    DIET_VEGAN_ID,
    DIET_NOBEEF_ID,
    SCHOOL_A_ID,
    caterer_a,
    menu_items_caterer_a,
    dietary_records,
    school_alpha,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.datetime(2026, 6, 4, 10, 0, tzinfo=datetime.timezone.utc)


def _make_request(
    request_code: str = "CDR-TEST",
    status: str = "Open",
    clarification_rounds: int = 0,
    question_set: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> Record:
    qs = question_set if question_set is not None else [
        {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        {"menu_item_id": ITEM_VEG_PASTA_ID, "restriction_id": DIET_VEGAN_ID},
    ]
    return Record(
        id="req-" + request_code,
        fields={
            "request_code": request_code,
            "caterer_id": CATERER_A_ID,
            "school_id": SCHOOL_A_ID,
            "sent_at": "2026-06-01T00:00:00+00:00",
            "status": status,
            "clarification_rounds": clarification_rounds,
            "question_set": qs,
            "messages": messages or [],
            "reply_to_address": f"dietary-{request_code}@reply.padea.com.au",
        },
    )


def _make_message(
    message_id: str = "msg-001",
    body_text: str = "Yes, everything is suitable.",
) -> InboundMessage:
    return InboundMessage(
        message_id=message_id,
        in_reply_to=None,
        subject="Re: dietary check",
        from_address="caterer@example.com",
        body_text=body_text,
        received_at=_NOW,
        request_code="CDR-TEST",
    )


def _make_db() -> MockDatabase:
    db = MockDatabase()
    db.Caterers._records = [caterer_a()]
    db.MenuItems._records = menu_items_caterer_a()
    db.DietaryRestrictions._records = dietary_records()
    db.Schools._records = [school_alpha()]
    return db


def _llm_response(
    confident_writes: list[dict] | None = None,
    earned_legends: list[dict] | None = None,
    clarification_questions: list[str] | None = None,
    still_unknown: list[dict] | None = None,
) -> str:
    return json.dumps({
        "confident_writes": confident_writes or [],
        "earned_legends": earned_legends or [],
        "clarification_questions": clarification_questions or [],
        "still_unknown": still_unknown or [],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseReply(unittest.TestCase):

    def _parse(self, db, request, message, llm_text: str, dry_run: bool = False):
        with patch("actions.parse_dietary_reply.ask_llm", return_value=llm_text):
            parse_reply(db, request, message, dry_run=dry_run)

    # 1. Sweeping confirmation → Resolved, all tags written
    def test_sweeping_confirmation_resolved(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        ])
        msg = _make_message(body_text="Chicken Fried Rice is vegetarian-safe.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "compatible"},
            ]
        )
        self._parse(db, request, msg, llm)

        # Status should be Resolved
        updates = db.DietaryClarificationRequests.updates
        final = next((u for _, u in reversed(updates) if "status" in u), None)
        self.assertIsNotNone(final)
        self.assertEqual(final["status"], "Resolved")

        # Dietary tag written
        item_updates = db.MenuItems.updates
        self.assertTrue(any(DIET_VEG_ID in u.get("dietary_tag_ids", []) for _, u in item_updates))

    # 2. All items confirmed 'contains' → Resolved, no positive tags, notes appended
    def test_all_contains_no_tags_notes_appended(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        ])
        msg = _make_message(body_text="Chicken Fried Rice contains chicken — not vegetarian.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "contains"},
            ]
        )
        self._parse(db, request, msg, llm)

        # Status Resolved
        updates = db.DietaryClarificationRequests.updates
        final = next((u for _, u in reversed(updates) if "status" in u), None)
        self.assertEqual(final["status"], "Resolved")

        # No dietary_tag written for the item
        item_updates = [u for _, u in db.MenuItems.updates if DIET_VEG_ID in u.get("dietary_tag_ids", [])]
        self.assertEqual(len(item_updates), 0)

        # Note written
        note_updates = [u for _, u in db.MenuItems.updates if "notes" in u]
        self.assertTrue(len(note_updates) > 0)
        self.assertIn("confirmed contains", note_updates[0]["notes"])

    # 3. Mixed: some compatible, some contains → partial tags
    def test_mixed_partial_tags(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
            {"menu_item_id": ITEM_VEG_PASTA_ID, "restriction_id": DIET_VEGAN_ID},
        ])
        msg = _make_message()
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "contains"},
                {"menu_item_id": ITEM_VEG_PASTA_ID, "restriction_id": DIET_VEGAN_ID, "answer": "compatible"},
            ]
        )
        self._parse(db, request, msg, llm)

        # Veg Pasta got the Vegan tag written (DIET_VEGAN_ID added to its tags)
        veg_pasta_tag_updates = [
            u for rid, u in db.MenuItems.updates
            if rid == ITEM_VEG_PASTA_ID and DIET_VEGAN_ID in u.get("dietary_tag_ids", [])
        ]
        self.assertTrue(len(veg_pasta_tag_updates) > 0)

        # Chicken Rice did NOT have a dietary_tag_ids update (it got 'contains' so no tag written)
        chicken_tag_updates = [
            u for rid, u in db.MenuItems.updates
            if rid == ITEM_CHICKEN_RICE_ID and u.get("dietary_tag_ids") is not None
        ]
        self.assertEqual(len(chicken_tag_updates), 0)

    # 4. Partial answer with unknowns → sends clarification (rounds 0→1, status Clarifying)
    def test_partial_answer_sends_clarification(self):
        db = _make_db()
        caterer = caterer_a()
        db.Caterers._records = [caterer]
        request = _make_request(clarification_rounds=0)
        msg = _make_message()
        llm = _llm_response(
            confident_writes=[],
            clarification_questions=["Could you confirm the Chicken Fried Rice?"],
            still_unknown=[{"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID}],
        )

        with patch("actions.parse_dietary_reply.ask_llm", return_value=llm), \
             patch("actions.parse_dietary_reply.schedule_email") as mock_email:
            parse_reply(db, request, msg)

        # clarification_rounds incremented to 1, status Clarifying
        updates = db.DietaryClarificationRequests.updates
        clar_update = next((u for _, u in updates if "clarification_rounds" in u), None)
        self.assertIsNotNone(clar_update)
        self.assertEqual(clar_update["clarification_rounds"], 1)
        self.assertEqual(clar_update["status"], "Clarifying")

        # Email sent
        mock_email.assert_called_once()

    # 5. Follow-up caterer answers → all resolved after second pass
    def test_follow_up_resolves(self):
        db = _make_db()
        # Simulate a request that already had round 1 of clarification
        request = _make_request(
            clarification_rounds=1,
            status="Clarifying",
            question_set=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
            ],
        )
        msg = _make_message(body_text="Yes, confirmed — Chicken Fried Rice is NOT vegetarian.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "contains"},
            ]
        )
        self._parse(db, request, msg, llm)

        updates = db.DietaryClarificationRequests.updates
        final = next((u for _, u in reversed(updates) if "status" in u), None)
        self.assertEqual(final["status"], "Resolved")

    # 6. Round cap: 2 clarifications sent, still questions → Escalated
    def test_round_cap_escalates(self):
        db = _make_db()
        request = _make_request(clarification_rounds=2, status="Clarifying")
        msg = _make_message(body_text="I don't know what you mean.")
        llm = _llm_response(
            clarification_questions=["Still need clarification on the chicken."],
            still_unknown=[{"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID}],
        )

        with patch("actions.parse_dietary_reply.ask_llm", return_value=llm), \
             patch("actions.parse_dietary_reply.notify_coordinator") as mock_notify:
            parse_reply(db, request, msg)

        mock_notify.assert_called_once()
        updates = db.DietaryClarificationRequests.updates
        final = next((u for _, u in reversed(updates) if "status" in u), None)
        self.assertEqual(final["status"], "Escalated")

    # 7. Earned legend written
    def test_earned_legend_written(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        ])
        msg = _make_message()
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "compatible"},
            ],
            earned_legends=[
                {"restriction_id": DIET_VEG_ID, "rationale": "Caterer confirmed all items"},
            ]
        )
        self._parse(db, request, msg, llm)

        legend_updates = [u for _, u in db.Caterers.updates if "legend_tag_ids" in u]
        self.assertTrue(len(legend_updates) > 0)
        self.assertIn(DIET_VEG_ID, legend_updates[0]["legend_tag_ids"])

    # 8. LLM returns invalid JSON → no state change, no crash
    def test_invalid_json_no_state_change(self):
        db = _make_db()
        request = _make_request()
        msg = _make_message()

        with patch("actions.parse_dietary_reply.ask_llm", return_value="Sorry I can't answer"):
            parse_reply(db, request, msg)

        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)

    # 9. ask_llm returns None → logs failure, no state change
    def test_ask_llm_none_no_state_change(self):
        db = _make_db()
        request = _make_request()
        msg = _make_message()

        with patch("actions.parse_dietary_reply.ask_llm", return_value=None):
            parse_reply(db, request, msg)

        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)

    # 10. Empty body_text → no crash, fallback to clarification
    def test_empty_body_no_crash(self):
        db = _make_db()
        request = _make_request(clarification_rounds=0)
        msg = _make_message(body_text="")
        llm = _llm_response(
            clarification_questions=["Could not understand the reply — please confirm?"],
        )

        with patch("actions.parse_dietary_reply.ask_llm", return_value=llm), \
             patch("actions.parse_dietary_reply.schedule_email"):
            parse_reply(db, request, msg)

        # Should not crash and should send clarification
        updates = db.DietaryClarificationRequests.updates
        clar = next((u for _, u in updates if "clarification_rounds" in u), None)
        self.assertIsNotNone(clar)

    # 11. Typo in confirmation: LLM still identifies as compatible → tag written
    def test_typo_still_extracted(self):
        db = _make_db()
        # Use ITEM_CHICKEN_RICE_ID which has no existing VEG tag, so a new one will be added
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        ])
        msg = _make_message(body_text="The chickhen fride rice is ok for vegetarrians.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "compatible"},
            ]
        )
        self._parse(db, request, msg, llm)

        # Tag written: dietary_tag_ids updated on the chicken rice item
        tag_updates = [
            u for rid, u in db.MenuItems.updates
            if rid == ITEM_CHICKEN_RICE_ID and DIET_VEG_ID in u.get("dietary_tag_ids", [])
        ]
        self.assertTrue(len(tag_updates) > 0)

    # 12. Caterer answers with questions instead of answers → clarification sent
    def test_caterer_asks_questions_sends_clarification(self):
        db = _make_db()
        request = _make_request(clarification_rounds=0)
        msg = _make_message(body_text="Can you tell me which student has vegetarian? What is it for?")
        llm = _llm_response(
            clarification_questions=[
                "To clarify: we need to know if your Chicken Fried Rice contains meat or is suitable for vegetarians."
            ]
        )

        with patch("actions.parse_dietary_reply.ask_llm", return_value=llm), \
             patch("actions.parse_dietary_reply.schedule_email") as mock_email:
            parse_reply(db, request, msg)

        mock_email.assert_called_once()
        updates = db.DietaryClarificationRequests.updates
        clar = next((u for _, u in updates if u.get("status") == "Clarifying"), None)
        self.assertIsNotNone(clar)

    # 13. Threaded quote in reply → LLM parses correctly (mock confirms it)
    def test_threaded_quote_parsed(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID},
        ])
        body = (
            "Yes, confirmed below:\n\n"
            "> Could you confirm if Chicken Fried Rice is vegetarian-safe?\n\n"
            "Chicken Fried Rice contains chicken — not suitable for vegetarians."
        )
        msg = _make_message(body_text=body)
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "contains"},
            ]
        )
        self._parse(db, request, msg, llm)

        updates = db.DietaryClarificationRequests.updates
        final = next((u for _, u in reversed(updates) if "status" in u), None)
        self.assertEqual(final["status"], "Resolved")

    # 14. Notes appended for compatible write
    def test_notes_appended_compatible(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_VEG_PASTA_ID, "restriction_id": DIET_VEG_ID},
        ])
        msg = _make_message(body_text="Vegetarian Pasta is definitely vegetarian.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_VEG_PASTA_ID, "restriction_id": DIET_VEG_ID, "answer": "compatible"},
            ]
        )
        self._parse(db, request, msg, llm)

        note_updates = [u for _, u in db.MenuItems.updates if "notes" in u]
        self.assertTrue(len(note_updates) > 0)
        self.assertIn("confirmed compatible", note_updates[0]["notes"])
        self.assertIn("CDR-TEST", note_updates[0]["notes"])

    # 15. Notes appended for contains write
    def test_notes_appended_contains(self):
        db = _make_db()
        request = _make_request(question_set=[
            {"menu_item_id": ITEM_BEEF_BURGER_ID, "restriction_id": DIET_NOBEEF_ID},
        ])
        msg = _make_message(body_text="The Beef Burger contains beef.")
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_BEEF_BURGER_ID, "restriction_id": DIET_NOBEEF_ID, "answer": "contains"},
            ]
        )
        self._parse(db, request, msg, llm)

        note_updates = [u for _, u in db.MenuItems.updates if "notes" in u]
        self.assertTrue(len(note_updates) > 0)
        self.assertIn("confirmed contains", note_updates[0]["notes"])
        self.assertIn("CDR-TEST", note_updates[0]["notes"])

    # Bonus: dry_run should not write anything
    def test_dry_run_no_writes(self):
        db = _make_db()
        request = _make_request()
        msg = _make_message()
        llm = _llm_response(
            confident_writes=[
                {"menu_item_id": ITEM_CHICKEN_RICE_ID, "restriction_id": DIET_VEG_ID, "answer": "compatible"},
            ]
        )
        self._parse(db, request, msg, llm, dry_run=True)

        self.assertEqual(len(db.DietaryClarificationRequests.updates), 0)
        self.assertEqual(len(db.MenuItems.updates), 0)


class TestExtractJson(unittest.TestCase):

    def test_valid_json(self):
        text = '{"a": 1, "b": [2, 3]}'
        result = _extract_json(text)
        self.assertEqual(result, {"a": 1, "b": [2, 3]})

    def test_json_in_prose(self):
        text = 'Here is my answer: {"x": "y"} — hope that helps!'
        result = _extract_json(text)
        self.assertEqual(result, {"x": "y"})

    def test_no_json_returns_none(self):
        result = _extract_json("No JSON here at all.")
        self.assertIsNone(result)

    def test_malformed_json_returns_none(self):
        result = _extract_json("{not valid json at all}")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
