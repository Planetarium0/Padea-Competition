"""
evaluate_caterers.py — Check rolling caterer ratings and propose switches.

For each (session, caterer) pair with enough rated sessions:
  - avg ≤ SWITCH_THRESHOLD and raters ≥ MIN_RATERS  → create a switch proposal
    and queue a notification email to the session's on-site manager
  - avg ≤ WATCH_THRESHOLD (but > SWITCH_THRESHOLD)  → queue a warning email only

Duplicate suppression (per term):
  - Skips pairs that already have a Pending / Approved / Executed proposal.
  - Skips pairs whose most-recent proposal was Rejected during the current
    Queensland school term.

Dietary hard filter: a candidate caterer is only eligible if it has at least
one compatible menu item for EVERY non-opted-out student at the session.

Usage:
  python scripts/actions/evaluate_caterers.py [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from support import (
    Alert,
    Button,
    Card,
    CatererFeedbackFields,
    CatererFields,
    CatererSwitchProposalFields,
    Database,
    Heading,
    List,
    MenuItemFields,
    Meta,
    OnSiteManagerFields,
    Record,
    SchoolFields,
    SessionFields,
    StudentFields,
    Text,
    compose_email,
    log,
    schedule_email,
)
from support.compatibility import (
    DietaryHierarchy,
    build_hierarchy,
    has_opted_out,
    is_item_compatible,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SWITCH_THRESHOLD = 2.5  # propose a caterer switch
WATCH_THRESHOLD  = 3.0  # warn coordinator only (no proposal)
# disable MIN_SESSIONS for now
MIN_SESSIONS     = 2    # minimum distinct sessions with feedback to fire SWITCH
MIN_RATERS       = 4    # minimum unique students rating in the window for SWITCH
ROLLING_WINDOW   = 4    # most-recent N sessions to average over

# Approximate Queensland school term starts for 2026.
QLD_TERM_STARTS = [
    date(2026, 1, 27),
    date(2026, 4, 20),
    date(2026, 7, 14),
    date(2026, 10, 5),
]


# ---------------------------------------------------------------------------
# Data carriers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeedbackEntry:
    date_str:   str
    session_id: str
    rating:     int
    student_id: str


@dataclass(frozen=True)
class RollingStats:
    num_sessions: int
    avg_rating:   float
    num_raters:   int


@dataclass(frozen=True)
class EvaluationData:
    """Raw records loaded from the database for the evaluation pass."""

    sessions:             list[Record[SessionFields]]
    feedback:             list[Record[CatererFeedbackFields]]
    caterers:             list[Record[CatererFields]]
    students:             list[Record[StudentFields]]
    menu_items:           list[Record[MenuItemFields]]
    dietary_restrictions: list[Record]
    proposals:            list[Record[CatererSwitchProposalFields]]
    schools:              list[Record[SchoolFields]]
    managers:             list[Record[OnSiteManagerFields]]

    @classmethod
    def load(cls, db: Database) -> "EvaluationData":
        log.info("Loading data from Supabase...")
        data = cls(
            sessions=             db.Sessions.all(),
            feedback=             db.CatererFeedback.all(),
            caterers=             db.Caterers.all(),
            students=             db.Students.all(),
            menu_items=           db.MenuItems.all(),
            dietary_restrictions= db.DietaryRestrictions.all(),
            proposals=            db.CatererSwitchProposals.all(),
            schools=              db.Schools.all(),
            managers=             db.OnSiteManagers.all(),
        )
        log.info(
            f"Loaded: {len(data.sessions)} sessions, "
            f"{len(data.feedback)} feedback records, "
            f"{len(data.caterers)} caterers"
        )
        return data


@dataclass(frozen=True)
class EvaluationIndex:
    """Pre-computed lookups derived from :class:`EvaluationData`."""

    data:                EvaluationData
    session_to_school:   dict[str, str]
    session_to_caterer:  dict[str, str]
    school_to_sessions:  dict[str, list[str]]
    school_names:        dict[str, str]
    caterer_names:       dict[str, str]
    manager_emails:      dict[str, str | None]
    menu_by_caterer:     dict[str, list[Record[MenuItemFields]]]
    dietary_hierarchy:   DietaryHierarchy
    feedback_index:      dict[tuple[str, str], list[FeedbackEntry]]
    session_to_students: dict[str, list[Record[StudentFields]]]
    session_labels:      dict[str, str]

    @classmethod
    def build(cls, data: EvaluationData) -> "EvaluationIndex":
        session_to_school:  dict[str, str] = {}
        session_to_caterer: dict[str, str] = {}
        school_to_sessions: dict[str, list[str]] = defaultdict(list)

        school_names: dict[str, str] = {r.id: r.fields.get("name", r.id) for r in data.schools}

        for rec in data.sessions:
            f = rec.fields
            school_id  = f.get("school_id")
            caterer_id = f.get("caterer_id")
            if school_id:
                session_to_school[rec.id] = school_id
                school_to_sessions[school_id].append(rec.id)
            if caterer_id:
                session_to_caterer[rec.id] = caterer_id

        menu_by_caterer: dict[str, list[Record[MenuItemFields]]] = defaultdict(list)
        for item in data.menu_items:
            cid = item.fields.get("caterer_id")
            if cid:
                menu_by_caterer[cid].append(item)

        hierarchy = build_hierarchy(data.dietary_restrictions)
        feedback_index = _build_feedback_index(data.feedback)

        # Group students by all their sessions.
        session_to_students: dict[str, list[Record[StudentFields]]] = defaultdict(list)
        for stu in data.students:
            for sid in (stu.fields.get("session_ids") or []):
                session_to_students[sid].append(stu)

        # Build human-readable label for each session.
        session_labels: dict[str, str] = {}
        for rec in data.sessions:
            f = rec.fields
            school_id = f.get("school_id")
            sname = school_names.get(school_id, school_id) if school_id else rec.id
            day   = f.get("day") or ""
            session_labels[rec.id] = f"{sname} — {day}" if day else sname

        return cls(
            data=                data,
            session_to_school=   session_to_school,
            session_to_caterer=  session_to_caterer,
            school_to_sessions=  dict(school_to_sessions),
            school_names=        school_names,
            caterer_names=       {r.id: r.fields.get("name", r.id) for r in data.caterers},
            manager_emails=      {r.id: r.fields.get("email") for r in data.managers},
            menu_by_caterer=     dict(menu_by_caterer),
            dietary_hierarchy=   hierarchy,
            feedback_index=      feedback_index,
            session_to_students= dict(session_to_students),
            session_labels=      session_labels,
        )

    def session_manager_email(self, session_id: str) -> str | None:
        """On-site manager email for the given session."""
        for sess in self.data.sessions:
            if sess.id != session_id:
                continue
            mgr_id = sess.fields.get("on_site_manager_id")
            if mgr_id:
                return self.manager_emails.get(mgr_id)
        return None


def _build_feedback_index(
    feedback_list: list[Record[CatererFeedbackFields]],
) -> dict[tuple[str, str], list[FeedbackEntry]]:
    """Group feedback by (session_id, caterer_id), sorted by date ascending."""
    index: dict[tuple[str, str], list[FeedbackEntry]] = defaultdict(list)
    skipped = 0
    for fb in feedback_list:
        f          = fb.fields
        rating     = f.get("rating")
        caterer_id = f.get("caterer_id")
        student_id = f.get("student_id")
        session_id = f.get("session_id")
        date_str   = f.get("session_date") or ""
        if rating is None or not caterer_id or not session_id or not student_id:
            skipped += 1
            log.verbose(
                f"Skipping feedback {fb.id}: "
                f"rating={rating} caterer={caterer_id} session={session_id}"
            )
            continue
        log.verbose(
            f"Feedback {fb.id}: session={session_id} caterer={caterer_id} "
            f"rating={rating} date={date_str!r}"
        )
        index[(session_id, caterer_id)].append(FeedbackEntry(
            date_str=date_str, session_id=session_id,
            rating=rating, student_id=student_id,
        ))

    for key in index:
        index[key].sort(key=lambda e: e.date_str)

    log.verbose(
        f"Feedback index built: {sum(len(v) for v in index.values())} entries across "
        f"{len(index)} (session, caterer) pair(s); {skipped} skipped"
    )
    return index


# ---------------------------------------------------------------------------
# Term helpers
# ---------------------------------------------------------------------------

def get_term_start(today: date | None = None) -> date:
    """Return the start date of the current QLD school term."""
    if today is None:
        today = date.today()
    term_start = QLD_TERM_STARTS[0]
    for ts in QLD_TERM_STARTS:
        if ts <= today:
            term_start = ts
    return term_start


def get_effective_week() -> date:
    """Return the Monday of the week *after* next — the earliest week the
    switch can affect (next week's order was just generated by
    register_orders).
    """
    today = date.today()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_to_monday)
    return next_monday + timedelta(days=7)


# ---------------------------------------------------------------------------
# Rolling stats
# ---------------------------------------------------------------------------

def get_rolling_stats(entries: list[FeedbackEntry]) -> RollingStats | None:
    """Return rolling-window statistics for the most recent ROLLING_WINDOW
    distinct sessions, or ``None`` if there isn't enough data."""

    @dataclass
    class _Bucket:
        ratings:  list[int]
        students: set[str]
        date:     str

    by_session: dict[str, _Bucket] = {}
    for entry in entries:
        bucket = by_session.get(entry.session_id)
        if bucket is None:
            bucket = _Bucket(ratings=[], students=set(), date="")
            by_session[entry.session_id] = bucket
        bucket.ratings.append(entry.rating)
        bucket.students.add(entry.student_id)
        if entry.date_str > bucket.date:
            bucket.date = entry.date_str

    sessions_sorted = sorted(by_session.items(), key=lambda x: x[1].date)
    log.verbose(
        f"  Sessions with feedback (oldest→newest): "
        + ", ".join(
            f"{sid[:8]}… avg={sum(b.ratings)/len(b.ratings):.1f} "
            f"({len(b.ratings)} ratings, date={b.date!r})"
            for sid, b in sessions_sorted
        )
    )

    window = sessions_sorted[-ROLLING_WINDOW:]
    if len(window) < MIN_SESSIONS:
        log.verbose(f"  Only {len(window)} session(s) in window — need {MIN_SESSIONS}; skipping")
        return None

    all_ratings: list[int] = []
    all_raters:  set[str] = set()
    for sid, bucket in window:
        all_ratings.extend(bucket.ratings)
        all_raters.update(bucket.students)
        log.verbose(
            f"  Window session {sid[:8]}…: "
            f"ratings={bucket.ratings} students={len(bucket.students)}"
        )

    avg = sum(all_ratings) / len(all_ratings)
    log.verbose(
        f"  Rolling window: {len(window)} sessions, "
        f"avg={avg:.2f}, raters={len(all_raters)}"
    )
    return RollingStats(num_sessions=len(window), avg_rating=avg, num_raters=len(all_raters))


# ---------------------------------------------------------------------------
# Dietary coverage check (hard filter)
# ---------------------------------------------------------------------------

def caterer_covers_all_students(
    caterer_id:      str,
    school_students: list[Record[StudentFields]],
    index:           EvaluationIndex,
) -> tuple[bool, str | None]:
    """Return ``(True, None)`` if every non-opted-out student at the school has
    at least one compatible menu item with this caterer.
    Return ``(False, student_name)`` on the first student who can't be covered.
    """
    caterer_menu = index.menu_by_caterer.get(caterer_id, [])
    if not caterer_menu:
        return False, "(no menu items on record)"

    log.verbose(
        f"  Dietary check: {len(caterer_menu)} menu item(s), "
        f"{len(school_students)} student(s)"
    )
    for stu in school_students:
        dietary_ids = stu.fields.get("dietary_requirement_ids") or []
        if has_opted_out(dietary_ids, index.dietary_hierarchy):
            log.verbose(
                f"    Skipping opted-out student "
                f"'{stu.fields.get('name', stu.id)}'"
            )
            continue
        any_ok = any(
            is_item_compatible(item.fields, dietary_ids, index.dietary_hierarchy)
            for item in caterer_menu
        )
        log.verbose(
            f"    Student '{stu.fields.get('name', stu.id)}' "
            f"({len(dietary_ids)} requirement(s)): {'OK' if any_ok else 'NO MATCH'}"
        )
        if not any_ok:
            return False, stu.fields.get("name", "unknown student")

    return True, None


# ---------------------------------------------------------------------------
# Candidate scoring and selection
# ---------------------------------------------------------------------------

def score_candidate(
    caterer_id: str,
    school_id:  str,
    index:      EvaluationIndex,
) -> float:
    """``score = 0.6 * avg_at_this_school + 0.4 * avg_overall`` (or just
    overall when there's no history at this school). Default overall is 3.0
    when no history exists at all.
    """
    # Collect all session IDs that belong to this school.
    school_session_ids = set(index.school_to_sessions.get(school_id, []))

    school_entries = [
        e
        for (sess_id, cid), entries in index.feedback_index.items()
        if cid == caterer_id and sess_id in school_session_ids
        for e in entries
    ]
    all_entries = [
        e
        for (sess_id, cid), entries in index.feedback_index.items()
        if cid == caterer_id
        for e in entries
    ]

    all_ratings    = [e.rating for e in all_entries]
    school_ratings = [e.rating for e in school_entries]

    avg_overall = sum(all_ratings) / len(all_ratings) if all_ratings else 3.0

    if school_ratings:
        avg_school = sum(school_ratings) / len(school_ratings)
        score      = 0.6 * avg_school + 0.4 * avg_overall
        log.verbose(
            f"  Score for '{index.caterer_names.get(caterer_id, caterer_id)}': "
            f"school_avg={avg_school:.2f} ({len(school_ratings)} ratings), "
            f"overall_avg={avg_overall:.2f} ({len(all_ratings)} ratings) → score={score:.2f}"
        )
        return score

    log.verbose(
        f"  Score for '{index.caterer_names.get(caterer_id, caterer_id)}': "
        f"no history at school, overall_avg={avg_overall:.2f} "
        f"({len(all_ratings)} ratings) → score={avg_overall:.2f}"
    )
    return avg_overall


def find_candidates(
    session_id:          str,
    outgoing_caterer_id: str,
    session_students:    list[Record[StudentFields]],
    index:               EvaluationIndex,
) -> list[tuple[float, str, str]]:
    """Return sorted ``(score, caterer_id, caterer_name)`` for eligible
    replacement caterers."""
    school_id = index.session_to_school.get(session_id)
    candidates: list[tuple[float, str, str]] = []
    for cat in index.data.caterers:
        cid = cat.id
        if cid == outgoing_caterer_id:
            continue
        able = cat.fields.get("able_to_serve_school_ids") or []
        if school_id not in able:
            continue

        covered, failing = caterer_covers_all_students(cid, session_students, index)
        if not covered:
            log.info(
                f"  Candidate '{index.caterer_names[cid]}' excluded: "
                f"no compatible meal for '{failing}'"
            )
            continue

        score = score_candidate(cid, school_id, index)
        candidates.append((score, cid, index.caterer_names[cid]))

    candidates.sort(key=lambda x: -x[0])
    return candidates


# ---------------------------------------------------------------------------
# Existing-proposal checks
# ---------------------------------------------------------------------------

def has_active_proposal(
    session_id: str,
    caterer_id: str,
    proposals:  list[Record[CatererSwitchProposalFields]],
) -> bool:
    """True if a Pending / Approved / Executed proposal already exists."""
    for p in proposals:
        f = p.fields
        if f.get("session_id") != session_id:
            continue
        if f.get("outgoing_caterer_id") != caterer_id:
            continue
        if f.get("status") in ("Pending", "Approved", "Executed"):
            return True
    return False


def was_rejected_this_term(
    session_id: str,
    caterer_id: str,
    proposals:  list[Record[CatererSwitchProposalFields]],
    term_start: date,
) -> bool:
    """True if a Rejected proposal for this pair exists since ``term_start``."""
    term_start_str = term_start.isoformat()
    for p in proposals:
        f = p.fields
        if f.get("session_id") != session_id:
            continue
        if f.get("outgoing_caterer_id") != caterer_id:
            continue
        if f.get("status") != "Rejected":
            continue
        if (f.get("proposed_on") or "") >= term_start_str:
            return True
    return False


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_proposal_email(
    session_name:   str,
    outgoing_name:  str,
    incoming_name:  str,
    avg_rating:     float,
    num_sessions:   int,
    num_raters:     int,
    effective_week: date,
    proposal_url:   str | None,
    forced:         bool = False,
) -> str:
    action_component = (
        Button("Review, approve, or reject this proposal", href=proposal_url)
        if proposal_url
        else Text("Open the Padea admin portal to approve or reject.")
    )

    if forced:
        trigger = Alert([
            Text("This proposal was manually created by a coordinator, bypassing the automated rating check.")
        ], variant="amber")
    else:
        trigger = Alert([
            Text(
                f"The automated rating check has flagged <strong>{outgoing_name}</strong> "
                f"for session <strong>{session_name}</strong>."
            ),
            Meta("Rolling average", f"{avg_rating:.1f}/5 over the last {num_sessions} sessions"),
            Meta("Sampled from", f"{num_raters} students"),
        ])

    return compose_email([
        Text("Hi,"),
        trigger,
        Card([
            Meta("Session", session_name),
            Meta("Outgoing caterer", outgoing_name),
            Meta("Proposed replacement", incoming_name),
            Meta("Effective week", effective_week.strftime("%-d %B %Y")),
        ], shaded=True),
        action_component,
        Text(
            "Approving will schedule the switch for the effective week above. "
            "Rejecting means you won't be reminded about this caterer again this term."
        ),
        Text("— Padea automation"),
    ])


def format_no_candidate_email(
    session_name:  str,
    outgoing_name: str,
    avg_rating:    float,
    num_sessions:  int,
    num_raters:    int,
) -> str:
    return compose_email([
        Text("Hi,"),
        Alert([
            Text(
                f"The automated rating check has flagged <strong>{outgoing_name}</strong> for "
                f"session <strong>{session_name}</strong> (average {avg_rating:.1f}/5 over "
                f"{num_sessions} sessions, {num_raters} raters), but "
                f"<strong>no eligible replacement caterer was found</strong>."
            )
        ]),
        Text("Please review the situation manually:", bold=True),
        List([
            "Check whether any caterer's <em>Able to Serve Schools</em> list needs updating.",
            "Check whether any menu items need to be added for existing caterers.",
        ]),
        Text("— Padea automation"),
    ])


def format_watch_email(
    session_name: str,
    caterer_name: str,
    avg_rating:   float,
    num_sessions: int,
    num_raters:   int,
) -> str:
    return compose_email([
        Text("Hi,"),
        Alert([
            Text(
                f"<strong>{caterer_name}</strong> for session <strong>{session_name}</strong> has a rolling "
                f"average of <strong>{avg_rating:.1f}/5</strong> over the last {num_sessions} sessions "
                f"({num_raters} raters). This is below the watch threshold of {WATCH_THRESHOLD}/5."
            )
        ], variant="amber"),
        Text(
            f"No action has been taken yet. If ratings continue to fall "
            f"below {SWITCH_THRESHOLD}/5, a switch proposal will be generated automatically."
        ),
        Text("— Padea automation"),
    ])


# ---------------------------------------------------------------------------
# Proposal and email creation
# ---------------------------------------------------------------------------

def create_proposal_and_email(
    db:                  Database,
    session_id:          str,
    session_name:        str,
    outgoing_caterer_id: str,
    outgoing_name:       str,
    incoming_caterer_id: str,
    incoming_name:       str,
    avg_rating:          float,
    num_sessions:        int,
    num_raters:          int,
    effective_week:      date,
    recipient_email:     str | None,
    dry_run:             bool,
    forced:              bool = False,
) -> None:
    today = date.today()
    proposal_id = (
        f"PROP-{session_name[:10].upper().replace(' ', '')}"
        f"-{today.isoformat()}"
    )

    proposal_fields: CatererSwitchProposalFields = {
        "proposal_code":      proposal_id,
        "session_id":         session_id,
        "outgoing_caterer_id": outgoing_caterer_id,
        "incoming_caterer_id": incoming_caterer_id,
        "proposed_on":        today.isoformat(),
        "effective_week":     effective_week.isoformat(),
        "status":             "Pending",
    }
    if not forced:
        proposal_fields["avg_rating"]       = round(avg_rating, 2)
        proposal_fields["sessions_sampled"] = num_sessions
        proposal_fields["unique_raters"]    = num_raters

    subject = f"[Padea] Caterer switch proposed — {session_name}"

    if dry_run:
        url_origin = os.environ.get("URL_ORIGIN", "").rstrip("/")
        fake_url   = f"{url_origin}/switch-proposal.html?id=<record_id>" if url_origin else None
        format_proposal_email(
            session_name, outgoing_name, incoming_name,
            avg_rating, num_sessions, num_raters,
            effective_week, fake_url, forced=forced,
        )
        log.info(f"[DRY RUN] Would create proposal: {proposal_id}")
        log.info(f"[DRY RUN] Would queue email to {recipient_email}: {subject}")
        log.info(f"[DRY RUN] Proposal URL would be: {fake_url}")
        return

    result = db.CatererSwitchProposals.create([proposal_fields])
    rec_id = result[0].id if result else None
    log.info(f"Created proposal: {proposal_id} (record {rec_id})")

    if rec_id:
        url_origin   = os.environ.get("URL_ORIGIN", "").rstrip("/")
        proposal_url = (
            f"{url_origin}/switch-proposal.html?id={rec_id}"
            if url_origin else None
        )
        if not url_origin:
            log.warning(
                "URL_ORIGIN not set in .env — proposal email will not include a link"
            )

        body = format_proposal_email(
            session_name, outgoing_name, incoming_name,
            avg_rating, num_sessions, num_raters,
            effective_week, proposal_url, forced=forced,
        )

        if recipient_email:
            schedule_email(
                db,
                to_email=recipient_email,
                cc_email=None,
                subject=subject,
                body=body,
                email_id=f"SWITCH-{proposal_id}",
                caterer_switch_proposal_id=rec_id,
            )


def queue_alert_email(
    db:              Database,
    subject:         str,
    body:            str,
    recipient_email: str | None,
    email_id:        str,
    dry_run:         bool,
) -> None:
    if dry_run:
        log.info(f"[DRY RUN] Would send alert email: {subject}")
        return
    if not recipient_email:
        log.warning("No on-site manager email found — skipping alert email")
        return
    schedule_email(
        db,
        to_email=recipient_email,
        cc_email=None,
        subject=subject,
        body=body,
        email_id=email_id,
    )


# ---------------------------------------------------------------------------
# Main evaluation loop
# ---------------------------------------------------------------------------

def evaluate(
    db:      Database | None = None,
    dry_run: bool = False,
    limit:   int | None = None,
) -> None:
    db = db or Database.from_env()

    data  = EvaluationData.load(db)
    index = EvaluationIndex.build(data)

    term_start     = get_term_start()
    effective_week = get_effective_week()

    log.info(
        f"Term start: {term_start}  |  Effective week if switched: {effective_week}"
    )

    evaluated      = 0
    emails_queued  = 0
    for (session_id, caterer_id), entries in index.feedback_index.items():
        if limit is not None and emails_queued >= limit:
            log.info(f"Reached --limit {limit}; stopping evaluation.")
            break
        session_name = index.session_labels.get(session_id, session_id)
        caterer_name = index.caterer_names.get(caterer_id, caterer_id)

        log.verbose(f"Evaluating: {session_name} / {caterer_name} ({len(entries)} feedback entries)")
        stats = get_rolling_stats(entries)
        if stats is None:
            log.verbose(
                f"Skipping {session_name} / {caterer_name}: "
                f"insufficient data (< {MIN_SESSIONS} sessions)"
            )
            continue

        evaluated += 1
        log.info(
            f"{session_name} / {caterer_name}: "
            f"avg={stats.avg_rating:.2f} over {stats.num_sessions} sessions, "
            f"{stats.num_raters} raters"
        )

        if stats.avg_rating > WATCH_THRESHOLD:
            continue

        # --- Watch threshold only ---
        if stats.avg_rating > SWITCH_THRESHOLD:
            recipient = index.session_manager_email(session_id)
            subject   = f"[Padea] Caterer watch — {session_name}"
            body      = format_watch_email(
                session_name, caterer_name,
                stats.avg_rating, stats.num_sessions, stats.num_raters,
            )
            email_id = f"WATCH-{session_id[:6]}-{caterer_id[:6]}-{date.today().isoformat()}"
            queue_alert_email(db, subject, body, recipient, email_id, dry_run)
            emails_queued += 1
            continue

        # --- Switch threshold ---
        if stats.num_raters < MIN_RATERS:
            log.info(
                f"  Rating {stats.avg_rating:.2f} below switch threshold but only "
                f"{stats.num_raters}/{MIN_RATERS} raters — not enough data to propose switch"
            )
            continue

        current_caterer = index.session_to_caterer.get(session_id)
        if current_caterer != caterer_id:
            log.info(
                f"  {caterer_name} is no longer the active caterer for "
                f"{session_name} — skipping"
            )
            continue

        log.verbose(
            f"  Checking {len(data.proposals)} existing proposal(s) for dedup"
        )
        if has_active_proposal(session_id, caterer_id, data.proposals):
            log.info(
                f"  Active proposal already exists for {session_name} / "
                f"{caterer_name} — skipping"
            )
            continue
        if was_rejected_this_term(session_id, caterer_id, data.proposals, term_start):
            log.info(
                f"  Proposal for {session_name} / {caterer_name} was rejected "
                f"this term — skipping"
            )
            continue
        log.verbose(f"  No blocking proposals found — proceeding with candidate search")

        log.info(
            f"  *** Rating {stats.avg_rating:.2f} below switch threshold — "
            f"finding candidates ***"
        )

        session_students = index.session_to_students.get(session_id, [])
        candidates = find_candidates(session_id, caterer_id, session_students, index)

        recipient = index.session_manager_email(session_id)
        if not recipient:
            log.warning(
                f"  No on-site manager email for {session_name} — "
                "proposals will be created but no email queued"
            )

        if not candidates:
            log.warning(
                f"  No eligible replacement for {caterer_name} for session {session_name}"
            )
            subject  = (
                f"[Padea] Caterer alert — no replacement for "
                f"{caterer_name} for session {session_name}"
            )
            body     = format_no_candidate_email(
                session_name, caterer_name,
                stats.avg_rating, stats.num_sessions, stats.num_raters,
            )
            email_id = f"NOCAND-{session_id[:6]}-{caterer_id[:6]}-{date.today().isoformat()}"
            queue_alert_email(db, subject, body, recipient, email_id, dry_run)
            emails_queued += 1
            continue

        best_score, best_id, best_name = candidates[0]
        log.info(f"  Best candidate: {best_name} (score {best_score:.2f})")

        create_proposal_and_email(
            db=db,
            session_id=session_id,
            session_name=session_name,
            outgoing_caterer_id=caterer_id,
            outgoing_name=caterer_name,
            incoming_caterer_id=best_id,
            incoming_name=best_name,
            avg_rating=stats.avg_rating,
            num_sessions=stats.num_sessions,
            num_raters=stats.num_raters,
            effective_week=effective_week,
            recipient_email=recipient,
            dry_run=dry_run,
        )
        emails_queued += 1

    log.info(
        f"Evaluation complete. {evaluated} (session, caterer) pair(s) had sufficient data; "
        f"{emails_queued} email(s) queued."
    )


# ---------------------------------------------------------------------------
# Force a proposal for testing
# ---------------------------------------------------------------------------

def _resolve_session_ref(
    ref:      str,
    sessions: list[Record],
) -> str | None:
    """Return the record ID for a session matched by name or record ID.

    Matches the ``Session ID`` field case-insensitively.  Falls back to
    treating ``ref`` as a raw record ID if no name match is found.
    """
    needle = ref.strip().lower()
    matches = [s for s in sessions if s.fields.get("session_code", "").lower() == needle]
    if len(matches) == 1:
        return matches[0].id
    if len(matches) > 1:
        names = ", ".join(s.fields.get("session_code", s.id) for s in matches)
        log.error(f"Ambiguous session name {ref!r} — matched: {names}")
        return None
    # No name match — try as a raw record ID.
    for s in sessions:
        if s.id == ref:
            return s.id
    return None

def force_proposal(
    session_ref:         str,
    incoming_caterer_id: str | None = None,
    db:                  Database | None = None,
    dry_run:             bool = False,
) -> None:
    """Create a switch proposal directly, bypassing rating thresholds.

    Intended for development and testing: lets you produce a real proposal
    record (and its notification email) for any session without needing
    enough feedback data to trigger the automated path.

    ``session_ref`` can be a human-readable session name
    (e.g. "MacGregor State High School - Thursday") or a raw record ID.
    If ``incoming_caterer_id`` is omitted the best candidate from
    ``find_candidates`` is used.  All duplicate-suppression checks
    (active proposals, rejected-this-term) are skipped.
    """
    db = db or Database.from_env()
    data  = EvaluationData.load(db)
    index = EvaluationIndex.build(data)

    session_id = _resolve_session_ref(session_ref, data.sessions)
    if not session_id:
        log.error(
            f"No session found matching {session_ref!r}. "
            "Pass the session_code field value (e.g. 'MacGregor State High School - Thursday') "
            "or the record UUID."
        )
        sys.exit(1)

    session_name = index.session_labels.get(session_id, session_id)
    outgoing_caterer_id = index.session_to_caterer.get(session_id)
    if not outgoing_caterer_id:
        log.failure(f"Session {session_name!r} has no current caterer — cannot create proposal.")
        sys.exit(1)

    outgoing_name = index.caterer_names.get(outgoing_caterer_id, outgoing_caterer_id)

    if incoming_caterer_id:
        incoming_name = index.caterer_names.get(incoming_caterer_id, incoming_caterer_id)
    else:
        session_students = index.session_to_students.get(session_id, [])
        candidates       = find_candidates(session_id, outgoing_caterer_id, session_students, index)
        if not candidates:
            log.failure(
                f"No eligible replacement caterer found for session {session_name!r}. "
                "Pass --incoming <caterer_id> to specify one explicitly."
            )
            sys.exit(1)
        _, incoming_caterer_id, incoming_name = candidates[0]
        log.info(f"Auto-selected best candidate: {incoming_name}")

    effective_week = get_effective_week()
    recipient      = index.session_manager_email(session_id)

    log.info(
        f"Force-creating proposal: {outgoing_name} → {incoming_name} "
        f"for {session_name}"
        + (" [DRY RUN]" if dry_run else "")
    )

    create_proposal_and_email(
        db=db,
        session_id=session_id,
        session_name=session_name,
        outgoing_caterer_id=outgoing_caterer_id,
        outgoing_name=outgoing_name,
        incoming_caterer_id=incoming_caterer_id,
        incoming_name=incoming_name,
        avg_rating=0.0,
        num_sessions=0,
        num_raters=0,
        effective_week=effective_week,
        recipient_email=recipient,
        dry_run=dry_run,
        forced=True,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from support import self_healing_error_handler, Database

    parser = argparse.ArgumentParser(
        description="Evaluate caterer ratings and propose switches",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log what would happen without writing to the database",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force-create a proposal for a given session, bypassing rating thresholds",
    )
    parser.add_argument(
        "--session",
        help="Session name (e.g. 'MacGregor State High School - Thursday') or record ID, for use with --force",
    )
    parser.add_argument(
        "--incoming",
        help="Incoming caterer record ID (optional with --force; auto-selected if omitted)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of emails this run will queue (useful for testing)",
    )
    args = parser.parse_args()

    # Dynamic database state provider to serialize DB context if an edge case fails
    def db_state_provider():
        try:
            db = Database.from_env()
            return {
                "caterer_feedback": db.CatererFeedback.all(),
                "sessions": db.Sessions.all(),
                "caterers": db.Caterers.all(),
                "menu_items": db.MenuItems.all(),
                "dietary_restrictions": db.DietaryRestrictions.all(),
                "students": db.Students.all(),
                "caterer_switch_proposals": db.CatererSwitchProposals.all(),
            }
        except Exception as e:
            return {"error_loading_db_state": str(e)}

    with self_healing_error_handler("evaluate_caterers", state_provider=db_state_provider):
        if args.force:
            if not args.session:
                parser.error("--force requires --session <record_id>")
            if args.limit == 0:
                log.info("--limit 0 set; skipping forced proposal email.")
            else:
                force_proposal(
                    session_ref=args.session,
                    incoming_caterer_id=args.incoming,
                    dry_run=args.dry_run,
                )
        else:
            evaluate(dry_run=args.dry_run, limit=args.limit)
