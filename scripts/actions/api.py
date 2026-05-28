"""
api.py — Handler functions for the webapp REST API.

Endpoints are registered with @route(method, url_pattern). Named capture
groups in the pattern are passed to the handler as kwargs; query-string /
body keys are also injected by name; `db` is always keyword-only and
injected by the dispatcher.

Switch-proposal endpoints:
  GET  /api/proposal/<proposal_id>                  — proposal details
  POST /api/proposal/<proposal_id>/approve           — execute the switch
  POST /api/proposal/<proposal_id>/reject            — reject with notes

Webapp data endpoints:
  GET   /api/session/<session_id>                    — session fields
  GET   /api/session/<session_id>/students           — [{id, name}] picker list
  GET   /api/student/<student_id>                    — student fields
  GET   /api/caterer/<caterer_id>/menu               — menu items for a caterer
  GET   /api/dietary-restrictions                    — all restrictions
  GET   /api/feedback?student_id=&caterer_id=        — existing feedback
  POST  /api/feedback                                — create or update feedback
  PATCH /api/student/<student_id>/meal-preference    — update meal preference
"""

from __future__ import annotations

import inspect
import logging
import re
import threading
import time
from datetime import date
from typing import Any

from support import Database
from actions.execute_caterer_switch import execute, reject as _reject_proposal

log = logging.getLogger("PadeaMigration")

# ---------------------------------------------------------------------------
# Server-side cache
# ---------------------------------------------------------------------------

_FOREVER = float("inf")


class _ServerCache:
    """Thread-safe in-memory cache. Entries persist until TTL expires or bust() is called."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, data = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return data

    def set(self, key: str, data: Any, ttl: float = _FOREVER) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl, data)

    def bust(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


_cache = _ServerCache()
_TTL_STABLE   = 86_400.0   # 24 h — dietary restrictions, menus (rarely change)
_TTL_SESSION  =  3_600.0   # 1 h  — session record, student list
_TTL_FEEDBACK =     60.0   # 60 s — full feedback table (also bust on write)

# ---------------------------------------------------------------------------
# Routing infrastructure
# ---------------------------------------------------------------------------

_routes: list[tuple[str, re.Pattern[str], Any]] = []


def route(method: str, pattern: str):
    """Register the decorated function as a handler for *method* + *pattern*."""
    def decorator(func):
        _routes.append((method, re.compile(pattern), func))
        return func
    return decorator


def dispatch(func, match: re.Match, payload: dict, db: Database) -> tuple[int, Any]:
    """Invoke *func* with kwargs built from URL groups, payload, and db.

    Named capture groups from *match* are injected first, then any remaining
    parameters are filled from *payload* by name.  ``db`` is always injected
    as a keyword argument.
    """
    sig = inspect.signature(func)
    kwargs: dict[str, Any] = {"db": db}
    kwargs.update(match.groupdict())
    for name in sig.parameters:
        if name not in kwargs and name in payload:
            kwargs[name] = payload[name]
    return func(**kwargs)


# ---------------------------------------------------------------------------
# Switch-proposal handlers
# ---------------------------------------------------------------------------

@route("GET", r"^/api/proposal/(?P<proposal_id>[^/?]+)$")
def api_get_proposal(proposal_id: str, *, db: Database) -> tuple[int, dict]:
    proposal = db.CatererSwitchProposals.get(proposal_id)
    if not proposal:
        return 404, {"error": f"Proposal {proposal_id!r} not found"}
    f           = proposal.fields
    session_id  = (f.get("Session")          or [None])[0]
    outgoing_id = (f.get("Outgoing Caterer") or [None])[0]
    incoming_id = (f.get("Incoming Caterer") or [None])[0]
    return 200, {
        "id":              proposal_id,
        "status":          f.get("Status") or "Pending",
        "sessionName":     _session_name(db, session_id),
        "outgoingName":    _caterer_name(db, outgoing_id),
        "incomingName":    _caterer_name(db, incoming_id),
        "avgRating":       f.get("Avg Rating"),
        "sessionsSampled": f.get("Sessions Sampled"),
        "uniqueRaters":    f.get("Unique Raters"),
        "effectiveWeek":   f.get("Effective Week"),
        "notes":           f.get("Notes") or "",
    }


@route("POST", r"^/api/proposal/(?P<proposal_id>[^/?]+)/approve$")
def api_approve_proposal(proposal_id: str, *, db: Database) -> tuple[int, dict]:
    try:
        execute(proposal_id, dry_run=False, approve=True, db=db)
        return 200, {"ok": True}
    except SystemExit:
        return 422, {"error": "Proposal cannot be executed — check server logs for details"}
    except Exception as e:
        log.exception("Unexpected error approving proposal %s", proposal_id)
        return 500, {"error": str(e)}


@route("POST", r"^/api/proposal/(?P<proposal_id>[^/?]+)/reject$")
def api_reject_proposal(proposal_id: str, notes: str = "", *, db: Database) -> tuple[int, dict]:
    try:
        _reject_proposal(proposal_id, notes=notes, db=db)
        return 200, {"ok": True}
    except Exception as e:
        log.exception("Unexpected error rejecting proposal %s", proposal_id)
        return 500, {"error": str(e)}


# ---------------------------------------------------------------------------
# Webapp data handlers
# ---------------------------------------------------------------------------

@route("GET", r"^/api/session/(?P<session_id>[^/?]+)/students$")
def api_get_session_students(session_id: str, *, db: Database) -> tuple[int, list | dict]:
    key = f"students:{session_id}"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    session = db.Sessions.get(session_id)
    if not session:
        return 404, {"error": f"Session {session_id!r} not found"}
    # "Students" is the backlink from Students.Sessions — not in SessionFields
    # TypedDict but present at runtime.
    student_ids: list[str] = list(session.fields.get("Students") or [])  # type: ignore[attr-defined]
    if not student_ids:
        _cache.set(key, [], _TTL_SESSION)
        return 200, []
    students = db.Students.all(formula=_id_formula(student_ids))
    result = sorted(
        [{"id": s.id, "name": s.fields.get("Student Name") or "(no name)"} for s in students],
        key=lambda s: s["name"],
    )
    _cache.set(key, result, _TTL_SESSION)
    return 200, result


@route("GET", r"^/api/session/(?P<session_id>[^/?]+)$")
def api_get_session(session_id: str, *, db: Database) -> tuple[int, dict]:
    key = f"session:{session_id}"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    rec = db.Sessions.get(session_id)
    if not rec:
        return 404, {"error": f"Session {session_id!r} not found"}
    f = rec.fields
    data = {
        "id": rec.id,
        "fields": {
            "Session ID":       f.get("Session ID", ""),
            "Caterer":          f.get("Caterer") or [],
            "Incoming Caterer": f.get("Incoming Caterer") or [],
        },
    }
    _cache.set(key, data, _TTL_SESSION)
    return 200, data


@route("GET", r"^/api/student/(?P<student_id>[^/?]+)$")
def api_get_student(student_id: str, *, db: Database) -> tuple[int, dict]:
    key = f"student:{student_id}"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    rec = db.Students.get(student_id)
    if not rec:
        return 404, {"error": f"Student {student_id!r} not found"}
    f = rec.fields
    data = {
        "id": rec.id,
        "fields": {
            "Student Name":         f.get("Student Name", ""),
            "Dietary Requirements": f.get("Dietary Requirements") or [],
            "Meal Preference":      f.get("Meal Preference") or [],
        },
    }
    _cache.set(key, data)  # no TTL — busted when meal preference is updated
    return 200, data


@route("GET", r"^/api/caterer/(?P<caterer_id>[^/?]+)$")
def api_get_caterer(caterer_id: str, *, db: Database) -> tuple[int, dict]:
    key = f"caterer:{caterer_id}"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    caterer = db.Caterers.get(caterer_id)
    if not caterer:
        return 404, {"error": f"Caterer {caterer_id!r} not found"}
    data = {
        "id": caterer_id,
        "legendTagIds": caterer.fields.get("Dietary Legend Tags") or [],
    }
    _cache.set(key, data, _TTL_STABLE)
    return 200, data


@route("GET", r"^/api/caterer/(?P<caterer_id>[^/?]+)/menu$")
def api_get_caterer_menu(caterer_id: str, *, db: Database) -> tuple[int, list | dict]:
    key = f"menu:{caterer_id}"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    caterer = db.Caterers.get(caterer_id)
    if not caterer:
        return 404, {"error": f"Caterer {caterer_id!r} not found"}
    # "Menu Items" is a backlink — not in CatererFields TypedDict but present at runtime.
    menu_ids: list[str] = list(caterer.fields.get("Menu Items") or [])  # type: ignore[attr-defined]
    if not menu_ids:
        _cache.set(key, [], _TTL_STABLE)
        return 200, []
    items = db.MenuItems.all(formula=_id_formula(menu_ids))
    result = [
        {
            "id": item.id,
            "fields": {
                "Menu Item Name": item.fields.get("Menu Item Name", ""),
                "Dietary Tags":   item.fields.get("Dietary Tags") or [],
                "Is Variant":     item.fields.get("Is Variant") or False,
                "Variant Of":     item.fields.get("Variant Of") or [],
            },
        }
        for item in items
    ]
    _cache.set(key, result, _TTL_STABLE)
    return 200, result


@route("GET", r"^/api/dietary-restrictions$")
def api_get_dietary_restrictions(*, db: Database) -> tuple[int, list]:
    key = "diet"
    cached = _cache.get(key)
    if cached is not None:
        return 200, cached
    data = [
        {
            "id":        r.id,
            "name":      r.fields.get("Restriction Name", ""),
            "supersets": r.fields.get("Supersets") or [],
        }
        for r in db.DietaryRestrictions.all()
    ]
    _cache.set(key, data, _TTL_STABLE)
    return 200, data


@route("GET", r"^/api/feedback$")
def api_get_feedback(student_id: str = "", caterer_id: str = "", *, db: Database) -> tuple[int, dict]:
    # Cache the full table so every student on the same session night benefits from
    # the same scan. Busted immediately after any write; 60s TTL as a fallback.
    table_key = "feedback_table"
    all_feedback = _cache.get(table_key)
    if all_feedback is None:
        all_feedback = list(db.CatererFeedback.all())
        _cache.set(table_key, all_feedback, _TTL_FEEDBACK)
    match = next(
        (r for r in all_feedback
         if student_id in (r.fields.get("Student") or [])
         and (not caterer_id or caterer_id in (r.fields.get("Caterer") or []))),
        None,
    )
    if match:
        return 200, {
            "recordId": match.id,
            "rating":   match.fields.get("Rating") or 0,
            "comment":  match.fields.get("Comment") or "",
        }
    return 200, {"recordId": None, "rating": 0, "comment": ""}


@route("POST", r"^/api/feedback$")
def api_upsert_feedback(
    student_id: str,
    session_id: str,
    caterer_id: str,
    rating: int,
    comment: str,
    feedback_record_id: str | None = None,
    *,
    db: Database,
) -> tuple[int, dict]:
    fields: dict = {
        "Student":      [student_id],
        "Session":      [session_id],
        "Rating":       int(rating),
        "Comment":      str(comment).strip(),
        "Session Date": date.today().isoformat(),
    }
    if caterer_id:
        fields["Caterer"] = [caterer_id]
    try:
        record_id = feedback_record_id or None  # coerce "" → None
        if record_id:
            rec = db.CatererFeedback.update(record_id, fields)
        else:
            fields["Feedback ID"] = (
                f"FB-{student_id[-6:]}-{(caterer_id or session_id)[-6:]}"
                f"-{int(time.time() * 1000)}"
            )
            rec = db.CatererFeedback.create([fields])[0]
        _cache.bust("feedback_table")
        return 200, {"recordId": rec.id}
    except Exception as e:
        log.exception("Error upserting feedback")
        return 500, {"error": str(e)}


@route("PATCH", r"^/api/student/(?P<student_id>[^/?]+)/meal-preference$")
def api_update_meal_preference(student_id: str, meal_item_id: str, *, db: Database) -> tuple[int, dict]:
    try:
        db.Students.update(student_id, {"Meal Preference": [meal_item_id]})
        _cache.bust(f"student:{student_id}")
        return 200, {"ok": True}
    except Exception as e:
        log.exception("Error updating meal preference for student %s", student_id)
        return 500, {"error": str(e)}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _id_formula(ids: list[str]) -> str:
    """Airtable formula that matches any record whose ID is in *ids*."""
    return "OR(" + ",".join(f"RECORD_ID()='{i}'" for i in ids) + ")"


def _session_name(db: Database, session_id: str | None) -> str:
    if not session_id:
        return "—"
    try:
        rec = db.Sessions.get(session_id)
        if not rec:
            return session_id
        school_id = (rec.fields.get("School") or [None])[0]
        day       = rec.fields.get("Day") or ""
        school    = _school_name(db, school_id) if school_id else "—"
        return f"{school} — {day}" if day else school
    except Exception:
        return session_id


def _school_name(db: Database, school_id: str) -> str:
    try:
        rec = db.Schools.get(school_id)
        return rec.fields.get("School Name", school_id) if rec else school_id
    except Exception:
        return school_id


def _caterer_name(db: Database, caterer_id: str | None) -> str:
    if not caterer_id:
        return "—"
    try:
        rec = db.Caterers.get(caterer_id)
        return rec.fields.get("Caterer Name", caterer_id) if rec else "—"
    except Exception:
        return "—"
