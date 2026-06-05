"""
clarify_dietary.py — Ask a caterer to confirm dietary information for MAYBE items.

For a given caterer:
  - Finds all sessions it serves (across all schools).
  - Computes the union of dietary restriction IDs for students in those sessions.
  - Computes (item × restriction) pairs where the existing 3-step ladder
    returns MAYBE (no positive tag, no legend block, no keyword hit).
  - Builds a dietary_clarification_requests row recording the open questions.
  - Sends one email to the caterer listing the items and restrictions to confirm.

After the sweep, runs the escalation check so any prior-term requests that
have crossed the 7-day mark are also picked up in the same command.

Usage:
  python scripts/actions/dietary/clarify_dietary.py <caterer_name_or_id>
            [--restriction <name>] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from support import (
    CatererFields,
    Database,
    DietaryRestrictionFields,
    List,
    MenuItemFields,
    Record,
    SessionFields,
    StudentFields,
    Text,
    compose_email,
    log,
    schedule_email,
)
from support.compatibility import OPTED_OUT, build_hierarchy, item_verdict


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

class ClarifyData:
    def __init__(
        self,
        sessions: list[Record[SessionFields]],
        caterers: list[Record[CatererFields]],
        menu_items: list[Record[MenuItemFields]],
        dietary_restrictions: list[Record[DietaryRestrictionFields]],
        students: list[Record[StudentFields]],
        existing_requests: list[Record],
    ) -> None:
        self.sessions = sessions
        self.caterers = caterers
        self.menu_items = menu_items
        self.dietary_restrictions = dietary_restrictions
        self.students = students
        self.existing_requests = existing_requests

    @classmethod
    def load(cls, db: Database) -> "ClarifyData":
        log.info("Loading data for dietary clarification sweep...")
        return cls(
            sessions=db.Sessions.all(),
            caterers=db.Caterers.all(),
            menu_items=db.MenuItems.all(),
            dietary_restrictions=db.DietaryRestrictions.all(),
            students=db.Students.all(),
            existing_requests=db.DietaryClarificationRequests.all(),
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def compute_question_set(
    menu_items: list[Record[MenuItemFields]],
    restriction_ids: set[str],
    hierarchy,
    legend_tag_ids: list[str],
) -> list[dict[str, str]]:
    """Return [{menu_item_id, restriction_id}] for every MAYBE verdict."""
    questions: list[dict[str, str]] = []
    for item in menu_items:
        for rid in restriction_ids:
            verdict = item_verdict(item.fields, rid, hierarchy, legend_tag_ids)
            if verdict == "MAYBE":
                questions.append({"menu_item_id": item.id, "restriction_id": rid})
    return questions


def caterer_restriction_union(
    caterer_session_ids: set[str],
    students: list[Record[StudentFields]],
    hierarchy,
) -> set[str]:
    """Union of dietary restriction IDs for students in the caterer's sessions, minus Opted Out."""
    opted_out_id: str | None = hierarchy.name_to_id.get(OPTED_OUT)
    result: set[str] = set()
    for stu in students:
        session_ids = set(stu.fields.get("session_ids") or [])
        if not (session_ids & caterer_session_ids):
            continue
        for rid in (stu.fields.get("dietary_requirement_ids") or []):
            if opted_out_id and rid == opted_out_id:
                continue
            result.add(rid)
    return result


def has_open_request(
    caterer_id: str,
    existing_requests: list[Record],
) -> bool:
    """True if an Open or Escalated request already exists for this caterer."""
    for req in existing_requests:
        if req.fields.get("caterer_id") != caterer_id:
            continue
        if req.fields.get("status") in ("Open", "Escalated"):
            return True
    return False


def make_request_code(caterer_name: str) -> str:
    today = datetime.date.today()
    week = today.isocalendar()[1]
    slug = re.sub(r"[^a-z0-9]", "", caterer_name.lower())[:12].upper()
    return f"CDR-{today.year}-W{week:02d}-{slug}"


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_clarification_email(
    caterer_name: str,
    restriction_names: list[str],
) -> str:
    components = [
        Text(f"Hi {caterer_name},"),
        Text(
            "We have students enrolled in our after-school program with dietary requirements "
            "we weren't able to confirm from your current menu."
        ),
        Text("Could you let us know which of your meals are suitable for:"),
        List([f"<strong>{r}</strong>" for r in restriction_names]),
        Text(
            'Just reply to this email and we\'ll handle the rest.'
        ),
        Text(
            "Thanks in advance,\n"
            "— Padea"
        ),
    ]
    return compose_email(components)


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sweep(
    db: Database,
    caterer_id: str,
    caterer_name: str | None = None,
    *,
    restriction_name_filter: str | None = None,
    dry_run: bool = False,
) -> int:
    """Run the clarification sweep for one caterer.

    Returns the number of new requests created (or that would be created
    in dry-run mode).
    """
    data = ClarifyData.load(db)
    hierarchy = build_hierarchy(data.dietary_restrictions)

    caterer = next((c for c in data.caterers if c.id == caterer_id), None)
    if caterer is None:
        log.warning(f"Caterer {caterer_id!r} not found")
        return 0
    caterer_name = caterer_name or caterer.fields.get("name", caterer_id)

    caterer_sessions = [s for s in data.sessions if s.fields.get("caterer_id") == caterer_id]
    caterer_session_ids = {s.id for s in caterer_sessions}
    if not caterer_sessions:
        log.warning(f"No sessions found for caterer {caterer_name!r}")
        return 0

    restriction_ids = caterer_restriction_union(caterer_session_ids, data.students, hierarchy)
    if not restriction_ids:
        log.info("No dietary restrictions in caterer sessions — nothing to clarify.")
        return 0

    if restriction_name_filter:
        filtered_id = hierarchy.name_to_id.get(restriction_name_filter)
        if not filtered_id:
            log.error(f"Unknown restriction name: {restriction_name_filter!r}")
            sys.exit(1)
        restriction_ids = {filtered_id} & restriction_ids
        if not restriction_ids:
            log.info(
                f"No students served by {caterer_name!r} have restriction "
                f"{restriction_name_filter!r}."
            )
            return 0

    log.info(
        f"Restriction union for {caterer_name!r}: "
        + ", ".join(
            hierarchy.id_to_name.get(r, r)
            for r in sorted(restriction_ids)
        )
    )

    if has_open_request(caterer_id, data.existing_requests):
        log.info(f"  {caterer_name}: open request already exists — skipping")
        return 0

    legend_tag_ids: list[str] = caterer.fields.get("legend_tag_ids") or []

    items_by_caterer: dict[str, list[Record[MenuItemFields]]] = {}
    for item in data.menu_items:
        cid = item.fields.get("caterer_id")
        if cid:
            items_by_caterer.setdefault(cid, []).append(item)

    caterer_items = items_by_caterer.get(caterer_id, [])
    if not caterer_items:
        log.info(f"  {caterer_name}: no menu items — skipping")
        return 0

    question_set = compute_question_set(
        caterer_items, restriction_ids, hierarchy, legend_tag_ids
    )
    if not question_set:
        log.info(f"  {caterer_name}: no MAYBE items — nothing to ask")
        return 0

    log.info(f"  {caterer_name}: {len(question_set)} open question(s)")
    request_code = make_request_code(caterer_name)
    sent_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if dry_run:
        log.info(
            f"  [DRY RUN] Would create request {request_code} and email "
            f"{caterer_name}"
        )
        return 1

    created = db.DietaryClarificationRequests.create([{
        "request_code": request_code,
        "caterer_id": caterer.id,
        "sent_at": sent_at,
        "status": "Open",
        "question_set": question_set,
    }])
    log.info(f"  Created request {request_code}")

    reply_domain = f"reply.{os.environ.get('APP_DOMAIN', 'padea.com.au')}"
    reply_to_address = f"replies+{request_code}@{reply_domain}"
    db.DietaryClarificationRequests.update(
        created[0].id, {"reply_to_address": reply_to_address}
    )

    restriction_name_map = {
        r.id: r.fields.get("name", r.id)
        for r in data.dietary_restrictions
    }

    contact_email = caterer.fields.get("contact_email")
    if not contact_email:
        log.warning(f"  {caterer_name}: no contact_email — skipping email")
    else:
        restriction_ids_asked = {q["restriction_id"] for q in question_set}
        restriction_names_asked = sorted(
            restriction_name_map.get(rid, rid) for rid in restriction_ids_asked
        )

        body = format_clarification_email(
            caterer_name=caterer_name,
            restriction_names=restriction_names_asked,
        )

        subject = f"[{request_code}] Padea dietary check — {caterer_name}"
        schedule_email(
            db,
            to_email=contact_email,
            cc_email=None,
            subject=subject,
            body=body,
            email_id=request_code,
            reply_to=reply_to_address,
        )

    log.info(f"Sweep complete: request created for {caterer_name!r}.")
    return 1


# ---------------------------------------------------------------------------
# Caterer resolution helper
# ---------------------------------------------------------------------------

def resolve_caterer(
    ref: str,
    caterers: list[Record[CatererFields]],
) -> tuple[str, str | None]:
    """Return (caterer_id, caterer_name) for a name or raw UUID.

    Matches case-insensitively on the ``name`` field; falls back to treating
    ``ref`` as a record UUID.
    """
    needle = ref.strip().lower()
    matches = [c for c in caterers if (c.fields.get("name") or "").lower() == needle]
    if len(matches) == 1:
        return matches[0].id, matches[0].fields.get("name")
    if len(matches) > 1:
        names = ", ".join(c.fields.get("name", c.id) for c in matches)
        log.error(f"Ambiguous caterer name {ref!r} — matched: {names}")
        sys.exit(1)
    for c in caterers:
        if c.id == ref:
            return c.id, c.fields.get("name")
    log.error(
        f"No caterer found matching {ref!r}. "
        "Pass the caterer name (e.g. 'Café Deluxe') or its record UUID."
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from support import self_healing_error_handler

    parser = argparse.ArgumentParser(
        description="Ask a caterer to confirm dietary information for MAYBE items",
    )
    parser.add_argument(
        "caterer",
        help="Caterer name (e.g. 'Café Deluxe') or record UUID",
    )
    parser.add_argument(
        "--restriction",
        dest="restriction_name",
        default=None,
        help="Limit sweep to one restriction (e.g. 'Vegan')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to the database",
    )
    args = parser.parse_args()

    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "sessions": db.Sessions.all(),
                "caterers": db.Caterers.all(),
                "menu_items": db.MenuItems.all(),
                "dietary_restrictions": db.DietaryRestrictions.all(),
                "students": db.Students.all(),
                "dietary_clarification_requests": db.DietaryClarificationRequests.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("clarify_dietary", state_provider=db_state_provider):
        db = Database.from_env()
        caterers = db.Caterers.all()
        caterer_id, caterer_name = resolve_caterer(args.caterer, caterers)

        run_sweep(
            db,
            caterer_id=caterer_id,
            caterer_name=caterer_name,
            restriction_name_filter=args.restriction_name,
            dry_run=args.dry_run,
        )

        # Run escalation sweep so prior-term open requests that have crossed
        # the 7-day mark are also picked up in the same command.
        if not args.dry_run:
            from actions.dietary.escalate_dietary import run_escalation
            run_escalation(db)
