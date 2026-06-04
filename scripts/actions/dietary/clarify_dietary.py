"""
clarify_dietary.py — Ask caterers to confirm dietary information for MAYBE items.

For each caterer serving a school:
  - Computes (item × restriction) pairs where the existing 3-step ladder
    returns MAYBE (no positive tag, no legend block, no keyword hit).
  - Builds a dietary_clarification_requests row recording the open questions.
  - Sends one email per caterer listing the items and restrictions to confirm.

After the sweep, runs the escalation check so any prior-term requests that
have crossed the 7-day mark are also picked up in the same command.

Usage:
  python scripts/actions/dietary/clarify_dietary.py <school_name_or_id>
            [--caterer <id>] [--restriction <name>] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from collections import defaultdict


from support import (
    Alert,
    Card,
    CatererFields,
    Database,
    DietaryRestrictionFields,
    Heading,
    List,
    MenuItemFields,
    Record,
    SchoolFields,
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
        schools: list[Record[SchoolFields]],
        sessions: list[Record[SessionFields]],
        caterers: list[Record[CatererFields]],
        menu_items: list[Record[MenuItemFields]],
        dietary_restrictions: list[Record[DietaryRestrictionFields]],
        students: list[Record[StudentFields]],
        existing_requests: list[Record],
    ) -> None:
        self.schools = schools
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
            schools=db.Schools.all(),
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


def school_restriction_union(
    school_session_ids: set[str],
    students: list[Record[StudentFields]],
    hierarchy,
) -> set[str]:
    """Union of dietary restriction IDs for students at school, minus Opted Out."""
    opted_out_id: str | None = hierarchy.name_to_id.get(OPTED_OUT)
    result: set[str] = set()
    for stu in students:
        session_ids = set(stu.fields.get("session_ids") or [])
        if not (session_ids & school_session_ids):
            continue
        for rid in (stu.fields.get("dietary_requirement_ids") or []):
            if opted_out_id and rid == opted_out_id:
                continue
            result.add(rid)
    return result


def has_open_request(
    caterer_id: str,
    school_id: str | None,
    existing_requests: list[Record],
) -> bool:
    """True if an Open or Escalated request already exists for (caterer, school)."""
    for req in existing_requests:
        if req.fields.get("caterer_id") != caterer_id:
            continue
        if req.fields.get("school_id") != school_id:
            continue
        if req.fields.get("status") in ("Open", "Escalated"):
            return True
    return False


def make_request_code(caterer_name: str, school_id: str | None) -> str:
    today = datetime.date.today()
    week = today.isocalendar()[1]
    slug = re.sub(r"[^a-z0-9]", "", caterer_name.lower())[:12].upper()
    school_suffix = (school_id or "")[:6]
    return f"CDR-{today.year}-W{week:02d}-{slug}-{school_suffix}"


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_clarification_email(
    caterer_name: str,
    school_name: str | None,
    questions_by_item: dict[str, list[str]],
    item_name_map: dict[str, str],
    restriction_name_map: dict[str, str],
) -> str:
    school_text = f" for {school_name}" if school_name else ""
    components = [
        Text(f"Hi {caterer_name},"),
        Alert([
            Text(
                f"We have students{school_text} with specific dietary requirements. "
                f"Please help us confirm which of your menu items are safe for them to eat."
            ),
        ], variant="amber"),
        Text(
            "For each item below, please reply to this email with "
            '"Yes, this item is suitable" or "No, this item contains [ingredient]" '
            "for each requirement listed.",
        ),
    ]

    for item_id, rids in sorted(
        questions_by_item.items(),
        key=lambda kv: item_name_map.get(kv[0], kv[0]),
    ):
        item_name = item_name_map.get(item_id, item_id)
        rnames = [restriction_name_map.get(rid, rid) for rid in rids]
        components.append(Card([
            Heading(item_name, accent=True),
            Text("Please confirm suitability for:"),
            List([f"<strong>{r}</strong>" for r in rnames]),
        ]))

    components.append(Text("If you have any questions, please reply to this email."))
    components.append(Text("— Padea"))
    return compose_email(components)


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sweep(
    db: Database,
    school_id: str,
    school_name: str | None = None,
    *,
    caterer_id_filter: str | None = None,
    restriction_name_filter: str | None = None,
    dry_run: bool = False,
) -> int:
    """Run the clarification sweep for one school.

    Returns the number of new requests created (or that would be created
    in dry-run mode).
    """
    data = ClarifyData.load(db)
    hierarchy = build_hierarchy(data.dietary_restrictions)

    school_sessions = [s for s in data.sessions if s.fields.get("school_id") == school_id]
    school_session_ids = {s.id for s in school_sessions}
    if not school_sessions:
        log.warning(f"No sessions found for school {school_name or school_id!r}")
        return 0

    restriction_ids = school_restriction_union(school_session_ids, data.students, hierarchy)
    if not restriction_ids:
        log.info("No dietary restrictions in enrolment — nothing to clarify.")
        return 0

    if restriction_name_filter:
        filtered_id = hierarchy.name_to_id.get(restriction_name_filter)
        if not filtered_id:
            log.error(f"Unknown restriction name: {restriction_name_filter!r}")
            sys.exit(1)
        restriction_ids = {filtered_id} & restriction_ids
        if not restriction_ids:
            log.info(
                f"No students at {school_name!r} have restriction "
                f"{restriction_name_filter!r}."
            )
            return 0

    log.info(
        f"Restriction union for {school_name!r}: "
        + ", ".join(
            hierarchy.id_to_name.get(r, r)
            for r in sorted(restriction_ids)
        )
    )

    caterer_ids_at_school: set[str] = {
        s.fields["caterer_id"]
        for s in school_sessions
        if s.fields.get("caterer_id")
    }
    caterers_at_school = [c for c in data.caterers if c.id in caterer_ids_at_school]
    if caterer_id_filter:
        caterers_at_school = [c for c in caterers_at_school if c.id == caterer_id_filter]
        if not caterers_at_school:
            log.error(
                f"Caterer {caterer_id_filter!r} does not serve school "
                f"{school_name!r}."
            )
            sys.exit(1)

    items_by_caterer: dict[str, list[Record[MenuItemFields]]] = defaultdict(list)
    for item in data.menu_items:
        cid = item.fields.get("caterer_id")
        if cid:
            items_by_caterer[cid].append(item)

    restriction_name_map = {
        r.id: r.fields.get("name", r.id)
        for r in data.dietary_restrictions
    }
    requests_created = 0

    for caterer in caterers_at_school:
        caterer_name = caterer.fields.get("name", caterer.id)
        legend_tag_ids: list[str] = caterer.fields.get("legend_tag_ids") or []
        caterer_items = items_by_caterer.get(caterer.id, [])

        if not caterer_items:
            log.info(f"  {caterer_name}: no menu items — skipping")
            continue

        if has_open_request(caterer.id, school_id, data.existing_requests):
            log.info(f"  {caterer_name}: open request already exists — skipping")
            continue

        question_set = compute_question_set(
            caterer_items, restriction_ids, hierarchy, legend_tag_ids
        )
        if not question_set:
            log.info(f"  {caterer_name}: no MAYBE items — nothing to ask")
            continue

        log.info(f"  {caterer_name}: {len(question_set)} open question(s)")
        request_code = make_request_code(caterer_name, school_id)
        sent_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if dry_run:
            log.info(
                f"  [DRY RUN] Would create request {request_code} and email "
                f"{caterer_name}"
            )
            requests_created += 1
            continue

        created = db.DietaryClarificationRequests.create([{
            "request_code": request_code,
            "caterer_id": caterer.id,
            "school_id": school_id,
            "sent_at": sent_at,
            "status": "Open",
            "question_set": question_set,
        }])
        log.info(f"  Created request {request_code}")

        # Compute the Reply-To address for this request and persist it.
        reply_domain = f"reply.{os.environ.get('APP_DOMAIN', 'padea.com.au')}"
        reply_to_address = f"dietary-{request_code}@{reply_domain}"
        db.DietaryClarificationRequests.update(
            created[0].id, {"reply_to_address": reply_to_address}
        )

        contact_email = caterer.fields.get("contact_email")
        if not contact_email:
            log.warning(f"  {caterer_name}: no contact_email — skipping email")
        else:
            questions_by_item: dict[str, list[str]] = defaultdict(list)
            for q in question_set:
                questions_by_item[q["menu_item_id"]].append(q["restriction_id"])

            item_name_map = {
                item.id: item.fields.get("name", item.id)
                for item in caterer_items
            }

            body = format_clarification_email(
                caterer_name=caterer_name,
                school_name=school_name,
                questions_by_item=dict(questions_by_item),
                item_name_map=item_name_map,
                restriction_name_map=restriction_name_map,
            )

            school_label = school_name or school_id
            subject = (
                f"[{request_code}] Padea dietary check — {caterer_name}"
            )
            schedule_email(
                db,
                to_email=contact_email,
                cc_email=None,
                subject=subject,
                body=body,
                email_id=request_code,
                reply_to=reply_to_address,
            )

        requests_created += 1

    log.info(
        f"Sweep complete: {requests_created} request(s) created for "
        f"{school_name or school_id!r}."
    )
    return requests_created


# ---------------------------------------------------------------------------
# School resolution helper
# ---------------------------------------------------------------------------

def resolve_school(
    ref: str,
    schools: list[Record[SchoolFields]],
) -> tuple[str, str | None]:
    """Return (school_id, school_name) for a name or raw UUID.

    Matches case-insensitively on the ``name`` field; falls back to treating
    ``ref`` as a record UUID.
    """
    needle = ref.strip().lower()
    matches = [s for s in schools if (s.fields.get("name") or "").lower() == needle]
    if len(matches) == 1:
        return matches[0].id, matches[0].fields.get("name")
    if len(matches) > 1:
        names = ", ".join(s.fields.get("name", s.id) for s in matches)
        log.error(f"Ambiguous school name {ref!r} — matched: {names}")
        sys.exit(1)
    # No name match — try raw UUID
    for s in schools:
        if s.id == ref:
            return s.id, s.fields.get("name")
    log.error(
        f"No school found matching {ref!r}. "
        "Pass the school name (e.g. 'Alpha Academy') or its record UUID."
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from support import self_healing_error_handler

    parser = argparse.ArgumentParser(
        description="Ask caterers to confirm dietary information for MAYBE items",
    )
    parser.add_argument(
        "school",
        help="School name (e.g. 'Alpha Academy') or record UUID",
    )
    parser.add_argument(
        "--caterer",
        dest="caterer_id",
        default=None,
        help="Limit sweep to one caterer (record UUID)",
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
        schools = db.Schools.all()
        school_id, school_name = resolve_school(args.school, schools)

        run_sweep(
            db,
            school_id=school_id,
            school_name=school_name,
            caterer_id_filter=args.caterer_id,
            restriction_name_filter=args.restriction_name,
            dry_run=args.dry_run,
        )

        # Run escalation sweep so prior-term open requests that have crossed
        # the 7-day mark are also picked up in the same command.
        if not args.dry_run:
            from actions.dietary.escalate_dietary import run_escalation
            run_escalation(db)
