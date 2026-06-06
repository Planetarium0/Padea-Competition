"""
parse_dietary_reply.py — LLM-driven parser for caterer dietary clarification replies.

Receives an inbound message threaded to an active DietaryClarificationRequest,
calls ask_llm to extract structured answers, and then:

  - Writes confident tags (menu_item_dietary_tags, caterer_legend_tags).
  - If the LLM needs clarification and rounds < 2, sends a clarifying reply
    and increments clarification_rounds (status → Clarifying).
  - If the round cap is hit with questions still open, escalates to coordinator.
  - If the LLM returns unusable JSON, logs without mutating state.

Usage (CLI):
  python scripts/actions/dietary/parse_dietary_reply.py \\
      --request-id <uuid> --message-id <message_id>
"""

from __future__ import annotations

import argparse
import datetime
import os
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from support import (
    Database,
    Record,
    ask_llm_json,
    log,
    notify_coordinator,
    schedule_email,
)
from support.inbound import InboundMessage

if TYPE_CHECKING:
    pass

MAX_CLARIFICATION_ROUNDS = 2


# ---------------------------------------------------------------------------
# Pydantic models for LLM responses
# ---------------------------------------------------------------------------

class _ConfidentWrite(BaseModel):
    item_name: str
    restriction_name: str
    answer: Literal["compatible", "contains"]

class _EarnedLegend(BaseModel):
    restriction_name: str
    rationale: str = ""

class _StillUnknown(BaseModel):
    item_name: str
    restriction_name: str

class _DietaryReplyExtraction(BaseModel):
    confident_writes: list[_ConfidentWrite] = []
    earned_legends: list[_EarnedLegend] = []
    clarification_questions: list[str] = []
    still_unknown: list[_StillUnknown] = []


# ---------------------------------------------------------------------------
# LLM prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(
    request: Record,
    message: InboundMessage,
    item_name_map: dict[str, str],
    restriction_name_map: dict[str, str],
    caterer_name: str,
    all_caterer_items: list[Record],
) -> str:
    """Build the LLM extraction prompt."""
    question_set: list[dict] = request.fields.get("question_set") or []
    existing_messages: list[dict] = request.fields.get("messages") or []

    # Open questions only (no answer yet)
    open_questions = [
        q for q in question_set
        if q.get("answer") is None
    ]

    questions_text = "\n".join(
        f"  - Item: {item_name_map.get(q.get('menu_item_id', ''), 'Unknown')}"
        f" | Restriction: {restriction_name_map.get(q.get('restriction_id', ''), 'Unknown')}"
        for q in open_questions
    )

    # Build full menu item list with variant context
    item_by_id = {item.id: item for item in all_caterer_items}
    menu_lines: list[str] = []
    for item in all_caterer_items:
        name = item.fields.get("name", item.id)
        if item.fields.get("is_variant") and item.fields.get("variant_of_id"):
            parent_name = item_name_map.get(item.fields["variant_of_id"], item.fields["variant_of_id"])
            menu_lines.append(f"  - {name} (variant of '{parent_name}')")
        else:
            menu_lines.append(f"  - {name}")
    menu_text = "\n".join(menu_lines) if menu_lines else "  (no items on record)"

    # Build thread context
    thread_parts: list[str] = []
    for m in existing_messages:
        direction = m.get("direction", "unknown")
        sent_at = m.get("sent_at", "")
        body = m.get("body", "")
        thread_parts.append(f"[{direction.upper()} {sent_at[:10] if sent_at else ''}]\n{body}")

    # Append the new inbound message
    thread_parts.append(
        f"[INBOUND {message.received_at.date() if message.received_at else ''}]\n"
        f"{message.body_text or '(no body)'}"
    )
    thread_text = "\n\n---\n\n".join(thread_parts)

    prompt = f"""You are a dietary information assistant for Padea, an after-school tutoring program.

A caterer ({caterer_name}) has replied to our dietary clarification request. Your job is to
extract structured answers from their reply.

ALL MENU ITEMS FROM THIS CATERER:
{menu_text}

Variants are alternate preparations of the same base dish (e.g. a gluten-free version of a
regular item). A caterer's answer about a base item does not automatically apply to its
variants — treat each item independently unless the caterer explicitly says otherwise.

OPEN QUESTIONS (items we still need answers for):
{questions_text if questions_text else '  (none — all questions already answered)'}

FULL CONVERSATION THREAD:
{thread_text}

For each open question, determine whether the caterer has answered it:
- "compatible": the menu item is safe / suitable for that dietary restriction
- "contains": the menu item contains an ingredient that violates the restriction
- Leave it out of confident_writes if the caterer has not answered clearly

The caterer may mention items that were not in the open questions list (e.g. they answer
about additional items proactively). Include those in confident_writes too if their answer
is clear.

Also determine if the caterer's reply, taken together with the conversation,
gives you enough information to award a "legend": the caterer has explicitly
accounted for ALL menu items under a single restriction column (either compatible
or contains, with no unknowns remaining). If so, include it in earned_legends.

If some answers are ambiguous or missing, compose a SHORT clarifying question
(one paragraph maximum) in clarification_questions. Keep it polite and specific.
Leave clarification_questions empty if everything is now clear.

IMPORTANT: You must respond with ONLY a JSON object, no other text. Use item and restriction
names exactly as they appear in the lists above. The JSON must have exactly these keys:

{{
  "confident_writes": [
    {{"item_name": "...", "restriction_name": "...", "answer": "compatible|contains"}}
  ],
  "earned_legends": [
    {{"restriction_name": "...", "rationale": "..."}}
  ],
  "clarification_questions": [
    "..."
  ],
  "still_unknown": [
    {{"item_name": "...", "restriction_name": "..."}}
  ]
}}

Return only valid JSON. Do not include any explanatory text before or after the JSON.
"""
    return prompt


# ---------------------------------------------------------------------------
# Tag writers
# ---------------------------------------------------------------------------

def _write_dietary_tag(
    db: Database,
    menu_item_id: str,
    restriction_id: str,
) -> None:
    """Insert a menu_item_dietary_tags row (INSERT ON CONFLICT DO NOTHING via upsert)."""
    # Load the item's existing tags
    item_record = db.MenuItems.get(menu_item_id)
    if item_record is None:
        log.warning(f"  Menu item {menu_item_id!r} not found — skipping tag write")
        return
    existing_tags: list[str] = list(item_record.fields.get("dietary_tag_ids") or [])
    if restriction_id not in existing_tags:
        existing_tags.append(restriction_id)
        db.MenuItems.update(menu_item_id, {"dietary_tag_ids": existing_tags})


def _write_legend_tag(
    db: Database,
    caterer_id: str,
    restriction_id: str,
) -> None:
    """Add (caterer_id, restriction_id) to caterer_legend_tags."""
    caterer_record = db.Caterers.get(caterer_id)
    if caterer_record is None:
        log.warning(f"  Caterer {caterer_id!r} not found — skipping legend write")
        return
    existing_legends: list[str] = list(caterer_record.fields.get("legend_tag_ids") or [])
    if restriction_id not in existing_legends:
        existing_legends.append(restriction_id)
        db.Caterers.update(caterer_id, {"legend_tag_ids": existing_legends})


def _append_item_note(
    db: Database,
    menu_item_id: str,
    restriction_name: str,
    compatible: bool,
    today: str,
    request_code: str,
) -> None:
    """Append a provenance note to menu_items.notes."""
    item_record = db.MenuItems.get(menu_item_id)
    if item_record is None:
        return
    verb = "confirmed compatible" if compatible else "confirmed contains"
    note_line = (
        f"{restriction_name} {verb} by caterer {today} "
        f"via clarification {request_code}"
    )
    existing_notes = item_record.fields.get("notes") or ""
    new_notes = (existing_notes.rstrip() + "\n" + note_line).lstrip()
    db.MenuItems.update(menu_item_id, {"notes": new_notes})


# ---------------------------------------------------------------------------
# Core parse function
# ---------------------------------------------------------------------------

def parse_reply(
    db: Database,
    request: Record,
    message: InboundMessage,
    *,
    dry_run: bool = False,
) -> None:
    """Parse a caterer reply and update the clarification request accordingly.

    This is the main entry point called by the inbox poller.
    """
    request_code: str = request.fields.get("request_code") or request.id
    caterer_id: str = request.fields.get("caterer_id") or ""
    school_id: str | None = request.fields.get("school_id")
    clarification_rounds: int = request.fields.get("clarification_rounds") or 0
    reply_to_address: str | None = request.fields.get("reply_to_address")

    log.info(
        f"parse_reply: request={request_code!r}, rounds={clarification_rounds}, "
        f"from={message.from_address!r}"
    )

    # ------------------------------------------------------------------
    # Build lookup maps
    # ------------------------------------------------------------------
    caterer_record = db.Caterers.get(caterer_id) if caterer_id else None
    caterer_name = (
        caterer_record.fields.get("name", caterer_id) if caterer_record else caterer_id
    )
    school_record = db.Schools.get(school_id) if school_id else None
    school_name = school_record.fields.get("name") if school_record else None

    restrictions = db.DietaryRestrictions.all()
    restriction_name_map = {r.id: r.fields.get("name", r.id) for r in restrictions}
    restriction_id_map = {v: k for k, v in restriction_name_map.items()}

    items = db.MenuItems.all()
    item_name_map = {i.id: i.fields.get("name", i.id) for i in items}
    item_id_map = {v: k for k, v in item_name_map.items()}

    # All items belonging to this caterer (for the full menu context in the prompt)
    caterer_items = [i for i in items if i.fields.get("caterer_id") == caterer_id]

    # ------------------------------------------------------------------
    # Call LLM
    # ------------------------------------------------------------------
    prompt = _build_prompt(
        request=request,
        message=message,
        item_name_map=item_name_map,
        restriction_name_map=restriction_name_map,
        caterer_name=caterer_name,
        all_caterer_items=caterer_items,
    )

    extraction = ask_llm_json(prompt, _DietaryReplyExtraction)
    if extraction is None:
        log.failure(
            f"parse_reply: LLM returned no parseable response for request {request_code!r} — no state change"
        )
        return

    # Map name-keyed LLM output back to IDs
    def _resolve_write(w: _ConfidentWrite | _StillUnknown) -> dict | None:
        mid = item_id_map.get(w.item_name)
        rid = restriction_id_map.get(w.restriction_name)
        if not mid or not rid:
            log.warning(f"  parse_reply: could not resolve name→id for item={w.item_name!r} restriction={w.restriction_name!r} — skipping")
            return None
        answer = w.answer if isinstance(w, _ConfidentWrite) else None
        return {"menu_item_id": mid, "restriction_id": rid, "answer": answer}

    def _resolve_legend(leg: _EarnedLegend) -> dict | None:
        rid = restriction_id_map.get(leg.restriction_name)
        if not rid:
            log.warning(f"  parse_reply: could not resolve restriction name→id for {leg.restriction_name!r} — skipping legend")
            return None
        return {"restriction_id": rid, "rationale": leg.rationale}

    confident_writes: list[dict] = [r for w in extraction.confident_writes if (r := _resolve_write(w)) is not None]
    earned_legends: list[dict] = [r for leg in extraction.earned_legends if (r := _resolve_legend(leg)) is not None]
    clarification_questions: list[str] = extraction.clarification_questions
    still_unknown: list[dict] = [r for w in extraction.still_unknown if (r := _resolve_write(w)) is not None]

    today_str = datetime.date.today().isoformat()
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Existing messages JSONB array
    existing_messages: list[dict] = list(request.fields.get("messages") or [])

    if dry_run:
        log.info(
            f"[DRY RUN] parse_reply for {request_code!r}: "
            f"confident_writes={len(confident_writes)}, "
            f"earned_legends={len(earned_legends)}, "
            f"clarification_questions={len(clarification_questions)}, "
            f"still_unknown={len(still_unknown)}"
        )
        return

    # ------------------------------------------------------------------
    # Append inbound message to the JSONB thread
    # ------------------------------------------------------------------
    inbound_entry: dict = {
        "direction": "inbound",
        "sent_at": message.received_at.isoformat() if message.received_at else now_str,
        "message_id": message.message_id,
        "body": message.body_text or "",
        "parsed_extraction": extraction.model_dump(),
    }
    updated_messages = existing_messages + [inbound_entry]

    # ------------------------------------------------------------------
    # Branch A: clarification needed and rounds < cap
    # ------------------------------------------------------------------
    if clarification_questions and clarification_rounds < MAX_CLARIFICATION_ROUNDS:
        clarification_text = "\n\n".join(clarification_questions)
        log.info(
            f"  Sending clarification round {clarification_rounds + 1} "
            f"for {request_code!r}"
        )

        # Append our outbound clarification to messages
        outbound_entry: dict = {
            "direction": "outbound",
            "sent_at": now_str,
            "message_id": None,  # will be set when SendGrid assigns a Message-ID
            "body": clarification_text,
            "parsed_extraction": None,
        }
        updated_messages = updated_messages + [outbound_entry]

        # Update request state
        db.DietaryClarificationRequests.update(request.id, {
            "clarification_rounds": clarification_rounds + 1,
            "status": "Clarifying",
            "messages": updated_messages,
        })

        # Send the clarifying email in-thread
        if reply_to_address:
            contact_email = (
                caterer_record.fields.get("contact_email") if caterer_record else None
            )
            if contact_email:
                email_id = f"{request_code}-clar-{clarification_rounds + 1}"
                subject = (
                    f"[{request_code}] Padea dietary follow-up — {caterer_name}"
                )
                schedule_email(
                    db,
                    to_email=contact_email,
                    cc_email=None,
                    subject=subject,
                    body=clarification_text,
                    email_id=email_id,
                    reply_to=reply_to_address,
                    in_reply_to_header=message.message_id,
                )
            else:
                log.warning(
                    f"  {caterer_name}: no contact_email — cannot send clarification"
                )
        else:
            log.warning(
                f"  Request {request_code!r}: no reply_to_address — cannot send "
                f"clarification"
            )
        return

    # ------------------------------------------------------------------
    # Branch B: all confident (no clarification questions)
    # ------------------------------------------------------------------
    if not clarification_questions:
        # Write confident dietary tags
        for write in confident_writes:
            mid = write.get("menu_item_id")
            rid = write.get("restriction_id")
            answer = write.get("answer")
            if not mid or not rid or not answer:
                continue
            if answer == "compatible":
                _write_dietary_tag(db, mid, rid)
                _append_item_note(
                    db, mid,
                    restriction_name=restriction_name_map.get(rid, rid),
                    compatible=True,
                    today=today_str,
                    request_code=request_code,
                )
                log.info(
                    f"  Tag written: item={item_name_map.get(mid, mid)!r} "
                    f"restriction={restriction_name_map.get(rid, rid)!r} compatible"
                )
            else:
                # 'contains' — no positive tag, just log provenance
                _append_item_note(
                    db, mid,
                    restriction_name=restriction_name_map.get(rid, rid),
                    compatible=False,
                    today=today_str,
                    request_code=request_code,
                )
                log.info(
                    f"  Contains noted: item={item_name_map.get(mid, mid)!r} "
                    f"restriction={restriction_name_map.get(rid, rid)!r} contains"
                )

        # Write earned legend tags
        for legend in earned_legends:
            rid = legend.get("restriction_id")
            if not rid or not caterer_id:
                continue
            _write_legend_tag(db, caterer_id, rid)
            log.info(
                f"  Legend earned: caterer={caterer_name!r} "
                f"restriction={restriction_name_map.get(rid, rid)!r}"
            )

        # Update question_set answers
        answered_pairs = {
            (w["menu_item_id"], w["restriction_id"]): w["answer"]
            for w in confident_writes
            if w.get("menu_item_id") and w.get("restriction_id") and w.get("answer")
        }
        question_set: list[dict] = list(request.fields.get("question_set") or [])
        for q in question_set:
            key = (q.get("menu_item_id"), q.get("restriction_id"))
            if key in answered_pairs:
                q["answer"] = answered_pairs[key]

        # Determine new status
        all_answered = all(q.get("answer") is not None for q in question_set)
        new_status = "Resolved" if all_answered else "Open"

        db.DietaryClarificationRequests.update(request.id, {
            "responded_at": now_str,
            "status": new_status,
            "question_set": question_set,
            "messages": updated_messages,
        })
        log.info(
            f"  Request {request_code!r} → {new_status} "
            f"({'all' if all_answered else 'partial'} questions answered)"
        )
        return

    # ------------------------------------------------------------------
    # Branch C: round cap hit — escalate
    # ------------------------------------------------------------------
    # clarification_questions is non-empty AND rounds >= MAX_CLARIFICATION_ROUNDS
    log.warning(
        f"  Round cap reached for {request_code!r} with unresolved questions — "
        f"escalating"
    )
    db.DietaryClarificationRequests.update(request.id, {
        "status": "Escalated",
        "messages": updated_messages,
    })

    num_open = len(still_unknown) or len(
        [q for q in (request.fields.get("question_set") or []) if q.get("answer") is None]
    )
    notify_coordinator(
        request.id,
        reason=caterer_name,
        school_name=school_name,
        num_open_questions=num_open,
        sent_at_str=request.fields.get("sent_at") or "",
        notify_email=None,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Parse a caterer dietary reply against an open request",
    )
    parser.add_argument(
        "--request-id",
        required=True,
        help="UUID of the dietary_clarification_requests row",
    )
    parser.add_argument(
        "--message-id",
        required=True,
        help="message_id of the dietary_inbound_messages row to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to the database",
    )
    args = parser.parse_args()

    from support import self_healing_error_handler

    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "dietary_clarification_requests": db.DietaryClarificationRequests.all(),
                "dietary_inbound_messages": db.DietaryInboundMessages.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("parse_dietary_reply", state_provider=db_state_provider):
        db = Database.from_env()
        request_record = db.DietaryClarificationRequests.get(args.request_id)
        if request_record is None:
            log.error(f"No request found with id={args.request_id!r}")
            raise SystemExit(1)

        # Find the inbound message by message_id
        rows = db.DietaryInboundMessages.all(
            filter=lambda q: q.eq("message_id", args.message_id)
        )
        if not rows:
            log.error(f"No inbound message found with message_id={args.message_id!r}")
            raise SystemExit(1)
        msg_row = rows[0]

        import datetime as _dt
        raw_ts = msg_row.fields.get("received_at")
        if isinstance(raw_ts, str):
            received_at = _dt.datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        else:
            received_at = _dt.datetime.now(_dt.timezone.utc)

        inbound = InboundMessage(
            message_id=msg_row.fields.get("message_id") or msg_row.id,
            in_reply_to=msg_row.fields.get("in_reply_to"),
            subject=msg_row.fields.get("subject"),
            from_address=msg_row.fields.get("from_address", ""),
            body_text=msg_row.fields.get("body_text"),
            received_at=received_at,
            request_code=request_record.fields.get("request_code"),
        )

        parse_reply(db, request_record, inbound, dry_run=args.dry_run)
