"""
send_qr_emails.py — Email each on-site manager their sessions' QR codes.

Groups all sessions by on-site manager. Each manager with an email address
receives a single email containing a QR code image and direct link for every
session they run.  QR code images are rendered inline via api.qrserver.com so
no attachment handling is needed.

Usage:
  python scripts/actions/send_qr_emails.py [--immediate] [--dry-run] [--first] [--limit N]

Requires URL_ORIGIN in .env (or as an environment variable):
  URL_ORIGIN=http://<server-ip>:8000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from urllib.parse import quote as url_quote

from support import (
    Database,
    OnSiteManagerFields,
    Record,
    SchoolFields,
    SessionFields,
    html_email,
    log,
    schedule_email,
)

_DAY_ORDER = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def session_url(origin: str, session_id: str, first: bool = False) -> str:
    suffix = "&first=1" if first else ""
    return f"{origin.rstrip('/')}/meals.html?session={session_id}{suffix}"



def qr_image_url(data: str, size: int = 250) -> str:
    """URL that generates a QR code PNG via the qrserver.com public API."""
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={url_quote(data)}"


def manage_url(origin: str, manager_id: str) -> str:
    return f"{origin.rstrip('/')}/manage.html?manager={manager_id}"


@dataclass(frozen=True)
class SessionEntry:
    label: str
    url:   str


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_manager_email(
    manager_name: str,
    entries:      list[SessionEntry],
    manager_id:   str,
    origin:       str,
) -> tuple[str, str]:
    first   = (manager_name.split()[0] if manager_name else None) or "there"
    subject = "Padea Meals — QR codes for this term's sessions"

    qr_blocks = "".join(
        f'<div style="border:1px solid #ECE6E2;border-radius:8px;padding:16px 20px;margin:0 0 16px;text-align:center;">'
        f'<h2 style="margin:0 0 12px;font-size:17px;font-weight:700;color:#1A1614;text-align:left;">{entry.label}</h2>'
        f'<a href="{entry.url}"><img src="{qr_image_url(entry.url)}" alt="QR Code" width="200" height="200"'
        f' style="width:200px;height:200px;display:block;margin:0 auto 12px;"></a>'
        f'<p style="margin:0;font-size:14px;"><a href="{entry.url}" style="color:#A51C30;">{entry.url}</a></p>'
        f'</div>'
        for entry in entries
    )

    mgr_url = manage_url(origin, manager_id)

    content = (
        f'<p style="margin:0 0 16px;">Hi {first},</p>'
        f'<p style="margin:0 0 24px;">Please find the QR codes for your sessions this term below. '
        f'Display them at the venue so students can set their meal preferences.</p>'
        f'{qr_blocks}'
        f'<div style="padding-top:20px;margin-top:8px;">'
        f'<p style="margin:0 0 8px;font-weight:700;">Student management</p>'
        f'<p style="margin:0 0 16px;color:#6F655F;">Use this link to update dietary requirements or override meal '
        f'assignments for any student across all your sessions:</p>'
        f'<a href="{mgr_url}" style="display:inline-block;background-color:#A51C30;color:#FFFFFF;'
        f'padding:10px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:15px;">Manage your students</a>'
        f'</div>'
        f'<p style="margin:24px 0 0;color:#6F655F;">Thanks,<br>Padea</p>'
    )
    return subject, html_email(content)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def send_qr_emails(
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

    all_sessions = db.Sessions.all()
    school_map   = {s.id: s for s in db.Schools.all()}
    manager_map  = {m.id: m for m in db.OnSiteManagers.all()}

    # Build manager_id → [SessionEntry] — skipping sessions with no manager or no email
    by_manager: dict[str, list[SessionEntry]] = {}

    for sess_rec in all_sessions:
        sf: SessionFields = sess_rec.fields
        sess_label = sf.get("session_code", sess_rec.id)

        mgr_id = sf.get("on_site_manager_id")
        if not mgr_id:
            log.warning(f"Session {sess_label!r}: no on-site manager — skipping")
            continue

        mgr_rec = manager_map.get(mgr_id)
        if not mgr_rec or not mgr_rec.fields.get("email"):
            mgr_name = mgr_rec.fields.get("name", mgr_id) if mgr_rec else mgr_id
            log.warning(f"Manager {mgr_name!r} has no email — skipping their sessions")
            continue

        school_id   = sf.get("school_id")
        school_name = school_map[school_id].fields.get("name", "?") if school_id and school_id in school_map else "?"
        day         = sf.get("day", "?")

        by_manager.setdefault(mgr_id, []).append(
            SessionEntry(
                label = f"{day} — {school_name}",
                url   = session_url(origin, sess_rec.id, first=first),
            )
        )

    if not by_manager:
        log.warning("No sessions with on-site manager emails found.")
        return

    sent = 0

    for mgr_id, entries in by_manager.items():
        if limit is not None and sent >= limit:
            log.info(f"Reached --limit {limit}; stopping.")
            break
        mgr_fields: OnSiteManagerFields = manager_map[mgr_id].fields
        mgr_name  = mgr_fields.get("name") or ""
        mgr_email = mgr_fields.get("email", "")

        entries.sort(key=lambda e: _DAY_ORDER.get(e.label.split(" — ")[0], 99))

        subject, body = format_manager_email(mgr_name, entries, mgr_id, origin)
        email_id      = f"MEALS-QR-{mgr_id[-8:]}-{int(time.time())}"

        if dry_run:
            log.info(f"[DRY RUN] To: {mgr_email} ({mgr_name or '?'}, {len(entries)} session(s))")
            for e in entries:
                log.info(f"  {e.label}: {e.url}")
        else:
            schedule_email(
                db,
                to_email=mgr_email,
                cc_email=None,
                subject=subject,
                body=body,
                email_id=email_id,
            )
            log.info(f"Queued → {mgr_email} ({mgr_name or '?'}, {len(entries)} session(s))")

        sent += 1

    log.info(f"\nDone. {sent} email(s) {'would be ' if dry_run else ''}queued.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from support import self_healing_error_handler

    parser = argparse.ArgumentParser(
        description="Email site managers their sessions' QR codes"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent without writing to Airtable",
    )
    parser.add_argument(
        "--first",
        action="store_true",
        help="Append &first=1 to each link, hiding the caterer rating card in the webapp",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of manager emails this run will queue (useful for testing)",
    )
    args = parser.parse_args()

    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "sessions":          db.Sessions.all(),
                "schools":           db.Schools.all(),
                "on_site_managers":  db.OnSiteManagers.all(),
                "scheduled_emails":  db.ScheduledEmails.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("send_qr_emails", state_provider=db_state_provider):
        send_qr_emails(dry_run=args.dry_run, first=args.first, limit=args.limit)
