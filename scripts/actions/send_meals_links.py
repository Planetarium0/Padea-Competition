"""
send_meals_links.py — Email parents or students a personalised meal-preference link.

Useful at the start of term when no session has taken place yet and QR codes
have not been distributed.  Each email contains one link per session the student
is enrolled in, pre-filled with session + student IDs so the recipient lands
straight on the form without picking a name.

Usage:
  python scripts/actions/send_meals_links.py --target {parents|students}
                                              [--immediate]
                                              [--dry-run]
                                              [--limit N]

Requires URL_ORIGIN in .env (or as an environment variable):
  URL_ORIGIN=http://<server-ip>:8000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

from support import (
    CatererFields,
    Database,
    Record,
    SchoolFields,
    SessionFields,
    StudentFields,
    html_email,
    log,
    schedule_email,
)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def meals_url(origin: str, session_id: str, student_id: str, first: bool = False) -> str:
    suffix = "&first=1" if first else ""
    return f"{origin.rstrip('/')}/meals.html?session={session_id}&student={student_id}{suffix}"


def manage_url(origin: str, student_id: str) -> str:
    return f"{origin.rstrip('/')}/manage.html?student={student_id}"


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionLink:
    label: str   # e.g. "Tuesday — ACME School (Caterer Name)"
    url:   str


def format_parent_email(
    parent_name:   str,
    student_name:  str,
    links:         list[SessionLink],
    diet_url:      str,
    first_session: bool = False,
) -> tuple[str, str]:
    greeting = (parent_name.split()[0] if parent_name else None) or "there"
    if first_session:
        subject = f"Padea Meals — set {student_name}'s meal preference for this term"
        intro   = (
            f"It's the start of term! {student_name} can now pick their meal "
            "preference for the coming weeks."
        )
        cta     = "Set preference"
        closing = "These preferences help us order meals your child will actually enjoy."
    else:
        subject = f"Padea Meals — update {student_name}'s meal preference"
        intro   = (
            f"{student_name} can rate their recent meal and update their preference "
            "for next week using the link(s) below."
        )
        cta     = "Rate &amp; update preference"
        closing = "These preferences help us order meals your child will actually enjoy."

    link_blocks = "".join(
        f'<div style="border:1px solid #ECE6E2;border-radius:8px;padding:16px 20px;margin:0 0 12px;">'
        f'<p style="margin:0 0 10px;font-weight:700;color:#1A1614;">{link.label}</p>'
        f'<a href="{link.url}" style="display:inline-block;background-color:#A51C30;color:#FFFFFF;'
        f'padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">{cta}</a>'
        f'</div>'
        for link in links
    )

    content = (
        f'<p style="margin:0 0 16px;">Hi {greeting},</p>'
        f'<p style="margin:0 0 20px;">{intro}</p>'
        f'<div style="background-color:#FAF7F5;border:1px solid #ECE6E2;border-radius:8px;padding:14px 18px;margin:0 0 24px;font-size:15px;">'
        f'<strong>Dietary requirements:</strong> If {student_name} has any dietary requirements we should know about, '
        f'please update them here: <a href="{diet_url}" style="color:#A51C30;">{student_name}\'s dietary requirements</a>'
        f'</div>'
        f'{link_blocks}'
        f'<p style="margin:16px 0 0;color:#6F655F;">{closing}</p>'
        f'<p style="margin:16px 0 0;color:#6F655F;">Thanks,<br>Padea</p>'
    )
    return subject, html_email(content)


def format_student_email(
    student_name:  str,
    links:         list[SessionLink],
    diet_url:      str,
    first_session: bool = False,
) -> tuple[str, str]:
    greeting = (student_name.split()[0] if student_name else None) or "there"
    if first_session:
        subject = "Padea Meals — set your meal preference for this term"
        intro   = "It's the start of term! You can now pick your meal preference for the coming weeks."
        cta     = "Set preference"
        closing = "Your preference helps us order meals you'll actually enjoy."
    else:
        subject = "Padea Meals — update your meal preference"
        intro   = "You can rate your recent meal and update your preference for next week."
        cta     = "Rate &amp; update preference"
        closing = "Your preference helps us order meals you'll actually enjoy."

    link_blocks = "".join(
        f'<div style="border:1px solid #ECE6E2;border-radius:8px;padding:16px 20px;margin:0 0 12px;">'
        f'<p style="margin:0 0 10px;font-weight:700;color:#1A1614;">{link.label}</p>'
        f'<a href="{link.url}" style="display:inline-block;background-color:#A51C30;color:#FFFFFF;'
        f'padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">{cta}</a>'
        f'</div>'
        for link in links
    )

    content = (
        f'<p style="margin:0 0 16px;">Hi {greeting},</p>'
        f'<p style="margin:0 0 20px;">{intro}</p>'
        f'<div style="background-color:#FAF7F5;border:1px solid #ECE6E2;border-radius:8px;padding:14px 18px;margin:0 0 24px;font-size:15px;">'
        f'<strong>Dietary requirements:</strong> Need to update your dietary requirements? '
        f'<a href="{diet_url}" style="color:#A51C30;">Update them here</a>'
        f'</div>'
        f'{link_blocks}'
        f'<p style="margin:16px 0 0;color:#6F655F;">{closing}</p>'
        f'<p style="margin:16px 0 0;color:#6F655F;">Thanks,<br>Padea</p>'
    )
    return subject, html_email(content)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def send_links(
    target:  str,
    dry_run: bool = False,
    first:   bool = False,
    limit:   int | None = None,
    db:      Database | None = None,
) -> None:
    db = db or Database.from_env()

    origin = os.environ.get("URL_ORIGIN", "").rstrip("/")
    if not origin:
        log.error(
            "URL_ORIGIN is not set. Add it to .env or the environment:\n"
            "  URL_ORIGIN=http://<server-ip>:8000"
        )
        sys.exit(1)

    all_students = db.Students.all()
    session_map  = {s.id: s for s in db.Sessions.all()}
    school_map   = {s.id: s for s in db.Schools.all()}
    caterer_map  = {c.id: c for c in db.Caterers.all()}

    if not all_students:
        log.warning("No students found.")
        return

    sent = skipped = 0

    for student in all_students:
        if limit is not None and sent >= limit:
            log.info(f"Reached --limit {limit}; stopping.")
            break
        sf: StudentFields = student.fields
        student_name = sf.get("name") or "(no name)"

        if target == "parents":
            to_email     = sf.get("parent_email") or ""
            display_name = sf.get("parent_name") or ""
        else:
            to_email     = sf.get("email") or ""
            display_name = student_name

        if not to_email:
            log.warning(f"Skipping {student_name}: no {target[:-1]} email")
            skipped += 1
            continue

        session_ids: list[str] = sf.get("session_ids") or []
        if not session_ids:
            log.warning(f"Skipping {student_name}: no sessions enrolled")
            skipped += 1
            continue

        links: list[SessionLink] = []
        for sid in session_ids:
            sess_rec = session_map.get(sid)
            if not sess_rec:
                continue
            sess_f: SessionFields = sess_rec.fields

            school_id   = sess_f.get("school_id")
            school_name = school_map[school_id].fields.get("name", "?") if school_id and school_id in school_map else "?"

            caterer_id   = sess_f.get("caterer_id")
            caterer_name = caterer_map[caterer_id].fields.get("name", "") if caterer_id and caterer_id in caterer_map else ""

            day   = sess_f.get("day", "?")
            label = f"{day} — {school_name}"
            if caterer_name:
                label += f" ({caterer_name})"

            links.append(SessionLink(label=label, url=meals_url(origin, sid, student.id, first=first)))

        if not links:
            log.warning(f"Skipping {student_name}: no resolvable sessions")
            skipped += 1
            continue

        diet_link = manage_url(origin, student.id)
        if target == "parents":
            subject, body = format_parent_email(display_name, student_name, links, diet_link, first_session=first)
        else:
            subject, body = format_student_email(student_name, links, diet_link, first_session=first)

        email_id = f"MEALS-{target[:3].upper()}-{student.id[-8:]}-{int(time.time())}"

        if dry_run:
            log.info(f"[DRY RUN] To: {to_email} ({student_name})")
            log.info(f"           Subject: {subject}")
            for link in links:
                log.info(f"           {link.label}: {link.url}")
        else:
            schedule_email(
                db,
                to_email=to_email,
                cc_email=None,
                subject=subject,
                body=body,
                email_id=email_id,
            )
            log.info(f"Queued → {to_email} ({student_name}, {len(links)} session(s))")

        sent += 1

    log.info(f"\nDone. {sent} email(s) {'would be ' if dry_run else ''}queued, {skipped} skipped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Email parents or students a personalised meal-preference link"
    )
    parser.add_argument(
        "--target",
        choices=["parents", "students"],
        required=True,
        help="Who to send to",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without writing to Airtable",
    )
    parser.add_argument(
        "--first",
        action="store_true",
        help="Append &first=1 to each link, hiding the caterer rating in the webapp",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of emails this run will queue (useful for testing)",
    )
    args = parser.parse_args()

    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "students":         db.Students.all(),
                "sessions":         db.Sessions.all(),
                "schools":          db.Schools.all(),
                "caterers":         db.Caterers.all(),
                "scheduled_emails": db.ScheduledEmails.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    from support import self_healing_error_handler
    with self_healing_error_handler("send_meals_links", state_provider=db_state_provider):
        send_links(target=args.target, dry_run=args.dry_run, first=args.first, limit=args.limit)
