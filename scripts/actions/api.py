"""
api.py — Handler functions for the switch-proposal REST API.

Pure functions (no HTTP plumbing) so they can be tested without spinning up
a server.  host_webapp.py routes incoming requests to these functions.

Endpoints:
  GET  /api/proposal/<id>         — proposal + session + caterer details
  POST /api/proposal/<id>/approve — execute the switch
  POST /api/proposal/<id>/reject  — reject with optional coordinator notes
"""

from __future__ import annotations

import logging

from support import Database
from actions.execute_caterer_switch import execute, reject as _reject_proposal

log = logging.getLogger("PadeaMigration")


# ---------------------------------------------------------------------------
# Public handlers — return (http_status, json_serialisable_dict)
# ---------------------------------------------------------------------------

def api_get_proposal(proposal_id: str, db: Database) -> tuple[int, dict]:
    """Resolve and return all display data for the proposal in one call."""
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


def api_approve_proposal(proposal_id: str, db: Database) -> tuple[int, dict]:
    """Execute the switch; returns 422 if the proposal is not executable."""
    try:
        execute(proposal_id, dry_run=False, db=db)
        return 200, {"ok": True}
    except SystemExit:
        # execute() calls sys.exit(1) for invalid state — surface as 422.
        return 422, {"error": "Proposal cannot be executed — check server logs for details"}
    except Exception as e:
        log.exception("Unexpected error approving proposal %s", proposal_id)
        return 500, {"error": str(e)}


def api_reject_proposal(proposal_id: str, notes: str, db: Database) -> tuple[int, dict]:
    """Reject the proposal with optional coordinator notes."""
    try:
        _reject_proposal(proposal_id, notes=notes, db=db)
        return 200, {"ok": True}
    except Exception as e:
        log.exception("Unexpected error rejecting proposal %s", proposal_id)
        return 500, {"error": str(e)}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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
