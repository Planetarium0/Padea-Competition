"""
register_orders.py — Snapshot student meal preferences into the Orders table.

For every session occurring next week, for each attending student (enrolled,
not absent, not excluded):
  1. Uses Meal Preference (set via webapp) if it belongs to the session's
     caterer's menu. Honoured even if it conflicts with the student's declared
     dietary requirements (a warning is logged).
  2. Falls back to a dietary-safe, popularity-weighted assignment otherwise.

After all meals are resolved, enforces caterer min-qty constraints:
  - Items below the per-item minimum are dissolved by proportionally swapping
    students to more popular items that are compatible with their dietary
    requirements.
  - Dietary requirements are always respected during swaps.
  - If no compatible swap target exists for a student, they are left in place.

Idempotent: clears any existing Orders and draft Weekly Orders for next week
before creating fresh records.

Usage:
  python scripts/register_orders.py [--dry-run]
"""

from __future__ import annotations

import argparse
import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from support import (
    AbsenceFields,
    CatererFeedbackFields,
    CatererFields,
    Database,
    DietaryRestrictionFields,
    ExclusionFields,
    MenuItemFields,
    Record,
    SessionFields,
    StudentFields,
    log,
)
from support.compatibility import (
    DietaryHierarchy,
    build_hierarchy,
    has_opted_out,
    is_item_compatible,
    resolve_dietary_names,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

# When fewer than this many students have an explicit preference for a caterer,
# use variety assignment (least-ordered first) instead of popularity weighting,
# so the order doesn't collapse to a single item.
VARIETY_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Per-student assignment record
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Assignment:
    """One student's (session, item) tuple ready to write to Orders."""

    student_id: str
    session_id: str
    item_id: str
    is_explicit: bool

    def with_item(self, item_id: str) -> "Assignment":
        return Assignment(self.student_id, self.session_id, item_id, self.is_explicit)


# ---------------------------------------------------------------------------
# Data bundle + indexes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderingData:
    """Raw records loaded once from Airtable for the order build."""

    sessions:             list[Record[SessionFields]]
    students:             list[Record[StudentFields]]
    caterers:             list[Record[CatererFields]]
    menu_items:           list[Record[MenuItemFields]]
    dietary_restrictions: list[Record[DietaryRestrictionFields]]
    absences:             list[Record[AbsenceFields]]
    exclusions:           list[Record[ExclusionFields]]
    feedback:             list[Record[CatererFeedbackFields]]

    @classmethod
    def load(cls, db: Database) -> "OrderingData":
        log.info("Loading data from Airtable...")
        data = cls(
            sessions=             db.Sessions.all(),
            students=             db.Students.all(),
            caterers=             db.Caterers.all(),
            menu_items=           db.MenuItems.all(),
            dietary_restrictions= db.DietaryRestrictions.all(),
            absences=             db.Absences.all(),
            exclusions=           db.Exclusions.all(),
            feedback=             db.CatererFeedback.all(),
        )
        log.info(
            f"Loaded: {len(data.sessions)} sessions, {len(data.students)} students, "
            f"{len(data.caterers)} caterers, {len(data.menu_items)} menu items"
        )
        return data


@dataclass(frozen=True)
class OrderingIndex:
    """Pre-computed lookups derived from :class:`OrderingData`."""

    data:                 OrderingData
    session_by_id:        dict[str, SessionFields]
    student_by_id:        dict[str, StudentFields]
    caterer_by_id:        dict[str, CatererFields]
    menu_item_by_id:      dict[str, MenuItemFields]
    dietary_hierarchy:    DietaryHierarchy
    menu_items_by_caterer: dict[str, list[Record[MenuItemFields]]]
    students_by_session:  dict[str, list[Record[StudentFields]]]
    absent_pairs:         set[tuple[str, str]]

    @property
    def exclusions(self) -> list[Record[ExclusionFields]]:
        return self.data.exclusions

    @classmethod
    def build(cls, data: OrderingData) -> "OrderingIndex":
        menu_items_by_caterer: dict[str, list[Record[MenuItemFields]]] = defaultdict(list)
        for item in data.menu_items:
            for cid in (item.fields.get("Caterer") or []):
                menu_items_by_caterer[cid].append(item)

        students_by_session: dict[str, list[Record[StudentFields]]] = defaultdict(list)
        for stu in data.students:
            for sid in (stu.fields.get("Sessions") or []):
                students_by_session[sid].append(stu)

        absent_pairs: set[tuple[str, str]] = set()
        for ab in data.absences:
            stu_id  = (ab.fields.get("Student") or [None])[0]
            sess_id = (ab.fields.get("Session") or [None])[0]
            if stu_id and sess_id:
                absent_pairs.add((stu_id, sess_id))

        return cls(
            data=                  data,
            session_by_id=         {r.id: r.fields for r in data.sessions},
            student_by_id=         {r.id: r.fields for r in data.students},
            caterer_by_id=         {r.id: r.fields for r in data.caterers},
            menu_item_by_id=       {r.id: r.fields for r in data.menu_items},
            dietary_hierarchy=     build_hierarchy(data.dietary_restrictions),
            menu_items_by_caterer= dict(menu_items_by_caterer),
            students_by_session=   dict(students_by_session),
            absent_pairs=          absent_pairs,
        )


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def get_next_week_dates() -> dict[str, date]:
    """Return {day_name: date} for Mon–Fri of next week."""
    today = datetime.now().date()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_to_monday)
    return {day: next_monday + timedelta(days=i) for i, day in enumerate(DAY_ORDER)}


def get_week_label(monday_date: date) -> str:
    iso = monday_date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ---------------------------------------------------------------------------
# Exclusion checking
# ---------------------------------------------------------------------------

def is_student_excluded(
    student_fields: StudentFields,
    session_fields: SessionFields,
    session_date: date | None,
    index: OrderingIndex,
) -> bool:
    """Check if a student is excluded from this session on this specific date.

    ``session_date`` is the actual date the session occurs next week (sessions
    recur weekly and are matched by Day, not by the Date field on the record).
    """
    sess_school = (session_fields.get("School") or [None])[0]
    if not sess_school or not session_date:
        return False

    sess_date_str = session_date.isoformat()

    for exc in index.exclusions:
        ef = exc.fields
        if (ef.get("School") or [None])[0] != sess_school:
            continue
        if ef.get("Date") != sess_date_str:
            continue
        affected = ef.get("Affected Year Levels") or []
        affected_lower = {a.lower() for a in affected}
        if not affected or "all" in affected_lower:
            return True
        yr = student_fields.get("Year Level")
        if yr is not None and str(int(yr)) in affected:
            return True
    return False


# ---------------------------------------------------------------------------
# Meal assignment (fallback when no valid explicit preference)
# ---------------------------------------------------------------------------

def assign_fallback_meal(
    student_dietary_ids:    list[str],
    caterer_menu:           list[Record[MenuItemFields]],
    item_counts:            dict[str, int],
    index:                  OrderingIndex,
    caterer_legend_tag_ids: list[str] | None = None,
) -> str | None:
    """Pick the best compatible meal weighted by:
      - Current batch popularity (80%)
      - Random variety           (20%)
    """
    compatible = [
        item for item in caterer_menu
        if is_item_compatible(item.fields, student_dietary_ids, index.dietary_hierarchy, caterer_legend_tag_ids)
    ]
    if not compatible:
        return None

    total_orders = sum(item_counts.values()) or 1
    scored: list[tuple[float, Record[MenuItemFields]]] = []
    for item in compatible:
        order_share = item_counts.get(item.id, 0) / total_orders
        variety     = random.uniform(0, 1)
        score       = order_share * 0.8 + variety * 0.2
        scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    return scored[0][1].id


def compute_max_variety(caterer_fields: CatererFields, total_students: int) -> int:
    """Return the most distinct items we can order while still satisfying the
    caterer's min-qty constraint.

    Checks Min Qty 6/5/4 Items in descending order and returns the highest n
    where ``total_students >= n * min_qty_for_n``.

    Falls back to ``total_students // 3`` (minimum 3 orders per item) when no
    explicit constraint is set, so variety never spreads so thin that items
    are ordered with qty 1 or 2.
    """
    for n in range(6, 3, -1):
        min_qty = caterer_fields.get(f"Min Qty {n} Items")
        if min_qty is not None and int(min_qty) > 0 and total_students >= n * int(min_qty):
            return n
    return max(1, total_students // 3)


def assign_variety_meal(
    student_dietary_ids:    list[str],
    caterer_menu:           list[Record[MenuItemFields]],
    item_counts:            dict[str, int],
    index:                  OrderingIndex,
    max_items:              int | None = None,
    caterer_legend_tag_ids: list[str] | None = None,
) -> str | None:
    """Pick the least-ordered compatible meal to spread variety across the
    batch. Used when few students have set an explicit preference.

    ``max_items``: if set, once that many distinct items are already in
    ``item_counts``, only pick from those existing items (avoids spreading
    too thin and violating min-qty constraints). Dietary exceptions can still
    introduce a new item.
    """
    compatible = [
        item for item in caterer_menu
        if is_item_compatible(item.fields, student_dietary_ids, index.dietary_hierarchy, caterer_legend_tag_ids)
    ]
    if not compatible:
        return None

    if max_items is not None:
        active_ids = {iid for iid, cnt in item_counts.items() if cnt > 0}
        if len(active_ids) >= max_items:
            capped = [item for item in compatible if item.id in active_ids]
            if capped:
                compatible = capped
            # else: all active items are dietarily incompatible — allow a new item

    compatible.sort(key=lambda item: (
        item_counts.get(item.id, 0),
        random.uniform(0, 1),
    ))
    return compatible[0].id


# ---------------------------------------------------------------------------
# Min-qty enforcement
# ---------------------------------------------------------------------------

def _find_min_qty(caterer_fields: CatererFields, num_distinct_items: int) -> int | None:
    """Return the per-item minimum quantity for the given number of distinct
    items, or ``None`` if no constraint applies.
    ``Min Qty N Items`` = each item must have at least this many portions.
    """
    for n in range(num_distinct_items, 3, -1):
        val = caterer_fields.get(f"Min Qty {n} Items")
        if val is not None:
            return int(val)
    return None


def enforce_min_qty(
    caterer_fields: CatererFields,
    assignments:    list[Assignment],
    index:          OrderingIndex,
) -> list[Assignment]:
    """Enforce caterer per-item min-qty by dissolving under-populated items.

    For each violating item, first checks that *every* student on it has at
    least one dietarily compatible target among the non-violating items. Only
    if all students pass this check is the item dissolved; otherwise the item
    is left in place. This avoids partially dissolving an item that cannot be
    fully removed — which would displace students from their meals while still
    leaving the same violation behind.
    """
    caterer_name   = caterer_fields.get("Caterer Name", "?")
    legend_tag_ids = list(caterer_fields.get("Dietary Legend Tags") or [])
    assignments    = list(assignments)

    for _iteration in range(30):  # safety cap
        item_to_indices: dict[str, list[int]] = defaultdict(list)
        for idx, a in enumerate(assignments):
            item_to_indices[a.item_id].append(idx)

        item_counts = {iid: len(idxs) for iid, idxs in item_to_indices.items()}
        num_items   = len(item_counts)
        min_qty     = _find_min_qty(caterer_fields, num_items)

        if min_qty is None:
            break

        violating = {iid for iid, cnt in item_counts.items() if cnt < min_qty}
        if not violating:
            break

        valid_items = {iid: cnt for iid, cnt in item_counts.items() if iid not in violating}
        if not valid_items:
            log.warning(f"Caterer '{caterer_name}': all items violate min-qty constraint.")
            break

        made_change = False
        for viol_item_id in list(violating):
            indices_on_item = item_to_indices[viol_item_id]
            viol_item_name  = index.menu_item_by_id.get(viol_item_id, {}).get("Menu Item Name", "?")

            # First pass: verify every student on this item has a compatible target.
            # If any student is blocked, leave the whole item in place.
            dissolvable = True
            for idx in indices_on_item:
                a           = assignments[idx]
                stu_fields  = index.student_by_id.get(a.student_id, {})
                dietary_ids = stu_fields.get("Dietary Requirements") or []
                has_target  = any(
                    is_item_compatible(
                        index.menu_item_by_id.get(iid, {}), dietary_ids, index.dietary_hierarchy, legend_tag_ids,
                    )
                    for iid in valid_items
                )
                if not has_target:
                    stu_name = stu_fields.get("Student Name", "?")
                    log.warning(
                        f"  Item '{viol_item_name}' cannot be dissolved — "
                        f"{stu_name} has no dietarily compatible swap target."
                    )
                    dissolvable = False
                    break

            if not dissolvable:
                continue

            # Second pass: dissolve the item — reassign each student proportionally.
            for idx in indices_on_item:
                a           = assignments[idx]
                stu_fields  = index.student_by_id.get(a.student_id, {})
                dietary_ids = stu_fields.get("Dietary Requirements") or []

                compat = {
                    iid: cnt for iid, cnt in valid_items.items()
                    if is_item_compatible(
                        index.menu_item_by_id.get(iid, {}), dietary_ids, index.dietary_hierarchy, legend_tag_ids,
                    )
                }

                total      = sum(compat.values()) or 1
                rand_val   = random.uniform(0, total)
                cumulative = 0.0
                chosen_id  = next(iter(compat))
                for iid, cnt in sorted(compat.items(), key=lambda x: -x[1]):
                    cumulative += cnt
                    if rand_val <= cumulative:
                        chosen_id = iid
                        break

                assignments[idx] = a.with_item(chosen_id)
                valid_items[chosen_id] = valid_items.get(chosen_id, 0) + 1

                stu_name = stu_fields.get("Student Name", "?")
                old_name = index.menu_item_by_id.get(a.item_id, {}).get("Menu Item Name", "?")
                new_name = index.menu_item_by_id.get(chosen_id, {}).get("Menu Item Name", "?")
                log.info(f"  Min-qty swap: {stu_name}: {old_name} → {new_name}")
                made_change = True

        if not made_change:
            break

    return assignments


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def clear_existing_orders(
    db:         Database,
    week_dates: dict[str, date],
    dry_run:    bool = False,
) -> None:
    """Delete any existing Orders and draft Weekly Orders for next week."""
    dates    = list(week_dates.values())
    min_date = min(dates).isoformat()
    max_date = max(dates).isoformat()

    existing = db.Orders.all(
        formula=f"AND({{Date}} >= '{min_date}', {{Date}} <= '{max_date}')",
    )
    if existing:
        log.info(f"Clearing {len(existing)} existing Orders for next week...")
        if not dry_run:
            db.Orders.batch_delete([r.id for r in existing])

    existing_wo = db.WeeklyOrders.all(
        formula=f"AND({{Week Start}} >= '{min_date}', {{Week Start}} <= '{max_date}')",
    )
    if existing_wo:
        log.info(f"Clearing {len(existing_wo)} existing draft Weekly Orders for next week...")
        if not dry_run:
            db.WeeklyOrders.batch_delete([r.id for r in existing_wo])


# ---------------------------------------------------------------------------
# Caterer switch helpers
# ---------------------------------------------------------------------------

def flip_incoming_caterers(db: Database, dry_run: bool = False) -> None:
    """Commit any pending caterer switches before this week's order is built.

    If a session has Incoming Caterer set (placed there by
    ``execute_caterer_switch.py`` when the coordinator approved a switch),
    flip Caterer = Incoming Caterer and clear Incoming Caterer so the rest
    of this run sees the new caterer as the active one.

    Also marks the corresponding Caterer Switch Proposal Status='Executed'
    (proposals are Status='Approved' between coordinator approval and here).
    """
    sessions = db.Sessions.all()
    to_flip = [r for r in sessions if r.fields.get("Incoming Caterer")]
    if not to_flip:
        return

    proposals = db.CatererSwitchProposals.all()

    log.info(f"Committing {len(to_flip)} pending caterer switch(es)...")
    if dry_run:
        for r in to_flip:
            incoming = (r.fields.get("Incoming Caterer") or [None])[0]
            log.info(f"  [DRY RUN] Would flip session {r.id}: Caterer → {incoming}")
        return

    for r in to_flip:
        incoming = r.fields.get("Incoming Caterer") or []
        db.Sessions.update(r.id, {"Caterer": incoming, "Incoming Caterer": []})
        log.info(f"  Flipped session {r.id} to caterer {incoming[0] if incoming else '?'}")

        for p in proposals:
            pf = p.fields
            if r.id in (pf.get("Session") or []) and pf.get("Status") == "Approved":
                db.CatererSwitchProposals.update(p.id, {"Status": "Executed"})
                log.info(f"  Marked proposal {p.id} as Executed")


# ---------------------------------------------------------------------------
# Caterer-scoped batch assigner
# ---------------------------------------------------------------------------

@dataclass
class _CatererBatch:
    """Mutable working set of assignments + popularity counts for one caterer."""

    assignments: list[Assignment] = field(default_factory=list)
    item_counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, assignment: Assignment) -> None:
        self.assignments.append(assignment)
        self.item_counts[assignment.item_id] += 1


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def register_orders(db: Database | None = None, dry_run: bool = False) -> None:
    db = db or Database.from_env()

    week_dates  = get_next_week_dates()
    next_monday = week_dates["Monday"]
    week_label  = get_week_label(next_monday)

    log.info(f"=== Registering orders for {week_label} (week of {next_monday}) ===")

    flip_incoming_caterers(db, dry_run=dry_run)

    data  = OrderingData.load(db)
    index = OrderingIndex.build(data)

    clear_existing_orders(db, week_dates, dry_run)

    # Sessions for next week — matched by Day field (sessions recur weekly)
    next_week_sessions = [
        sess for sess in data.sessions
        if sess.fields.get("Day") in week_dates
    ]
    log.info(f"Found {len(next_week_sessions)} sessions for next week")

    if not next_week_sessions:
        log.warning("No sessions found for next week.")
        return

    # Pre-scan: count *eligible* students (not absent / excluded / opted out)
    # and explicit preferences per caterer. Used to pick fallback assignment
    # mode and to cap variety so items aren't spread too thin.
    explicit_pref_counts:   dict[str, int] = defaultdict(int)
    caterer_student_counts: dict[str, int] = defaultdict(int)
    for sess_rec in next_week_sessions:
        sess_id     = sess_rec.id
        sess_fields = sess_rec.fields
        cid = (sess_fields.get("Caterer") or [None])[0]
        if not cid:
            continue
        session_date = week_dates.get(sess_fields.get("Day", ""))
        menu_ids = {item.id for item in index.menu_items_by_caterer.get(cid, [])}
        for stu in index.students_by_session.get(sess_id, []):
            if (stu.id, sess_id) in index.absent_pairs:
                continue
            if is_student_excluded(stu.fields, sess_fields, session_date, index):
                continue
            dietary_ids = stu.fields.get("Dietary Requirements") or []
            if has_opted_out(dietary_ids, index.dietary_hierarchy):
                continue
            caterer_student_counts[cid] += 1
            pref_ids = stu.fields.get("Meal Preference") or []
            if pref_ids and pref_ids[0] in menu_ids:
                explicit_pref_counts[cid] += 1

    caterer_max_variety = {
        cid: compute_max_variety(index.caterer_by_id.get(cid, {}), total)
        for cid, total in caterer_student_counts.items()
    }

    for cid, count in explicit_pref_counts.items():
        caterer_name = index.caterer_by_id.get(cid, {}).get("Caterer Name", cid)
        mode    = "popularity" if count >= VARIETY_THRESHOLD else "variety"
        max_v   = caterer_max_variety.get(cid)
        cap_str = f", capped at {max_v} items" if (mode == "variety" and max_v) else ""
        log.info(
            f"Caterer '{caterer_name}': {count} explicit preferences — "
            f"using {mode} fallback{cap_str}"
        )

    # -----------------------------------------------------------------------
    # Build per-caterer assignment list
    # -----------------------------------------------------------------------
    caterer_batches: dict[str, _CatererBatch] = defaultdict(_CatererBatch)
    stats = {"assigned": 0, "absent": 0, "excluded": 0, "opted_out": 0, "no_meal": 0}

    for sess_rec in next_week_sessions:
        sess_id      = sess_rec.id
        sess_fields  = sess_rec.fields
        sess_label   = sess_fields.get("Session ID", sess_id)
        day          = sess_fields.get("Day", "?")
        session_date = week_dates.get(day)

        caterer_links = sess_fields.get("Caterer") or []
        if not caterer_links:
            log.warning(f"Session '{sess_label}' has no caterer — skipping.")
            continue
        caterer_id = caterer_links[0]

        caterer_menu = index.menu_items_by_caterer.get(caterer_id, [])
        if not caterer_menu:
            log.warning(f"Session '{sess_label}': caterer has no menu items — skipping.")
            continue

        caterer_menu_ids = {item.id for item in caterer_menu}
        enrolled = index.students_by_session.get(sess_id, [])
        log.info(f"Session '{sess_label}' ({day}): {len(enrolled)} enrolled students")

        batch          = caterer_batches[caterer_id]
        legend_tag_ids = list(index.caterer_by_id.get(caterer_id, {}).get("Dietary Legend Tags") or [])

        for stu in enrolled:
            stu_id     = stu.id
            stu_fields = stu.fields
            stu_name   = stu_fields.get("Student Name", "?")

            if (stu_id, sess_id) in index.absent_pairs:
                stats["absent"] += 1
                continue

            if is_student_excluded(stu_fields, sess_fields, session_date, index):
                stats["excluded"] += 1
                continue

            dietary_ids = stu_fields.get("Dietary Requirements") or []

            if has_opted_out(dietary_ids, index.dietary_hierarchy):
                stats["opted_out"] += 1
                continue

            # --- Try explicit Meal Preference ---
            pref_ids    = stu_fields.get("Meal Preference") or []
            item_id: str | None = None
            is_explicit = False

            if pref_ids:
                pref_id = pref_ids[0]
                if pref_id in caterer_menu_ids:
                    pref_fields = index.menu_item_by_id.get(pref_id, {})
                    pref_name   = pref_fields.get("Menu Item Name", "?")
                    if not is_item_compatible(pref_fields, dietary_ids, index.dietary_hierarchy, legend_tag_ids):
                        # Definite incompatibility — refuse the override and
                        # force-swap to a compatible fallback below.
                        dietary_names = resolve_dietary_names(dietary_ids, index.dietary_hierarchy)
                        log.warning(
                            f"  {stu_name}: REFUSING explicit preference '{pref_name}' — "
                            f"definitely incompatible with dietary {dietary_names}. "
                            "Forcing dietary-safe fallback."
                        )
                    else:
                        item_id     = pref_id
                        is_explicit = True
                else:
                    log.debug(f"  {stu_name}: preference not on this caterer's menu.")

            # --- Fallback assignment ---
            if item_id is None:
                use_variety = explicit_pref_counts[caterer_id] < VARIETY_THRESHOLD
                if use_variety:
                    item_id = assign_variety_meal(
                        dietary_ids, caterer_menu, batch.item_counts, index,
                        max_items=caterer_max_variety.get(caterer_id),
                        caterer_legend_tag_ids=legend_tag_ids,
                    )
                else:
                    item_id = assign_fallback_meal(
                        dietary_ids, caterer_menu, batch.item_counts, index,
                        caterer_legend_tag_ids=legend_tag_ids,
                    )
                if item_id is None:
                    log.warning(f"  {stu_name}: no compatible meal found — skipping.")
                    stats["no_meal"] += 1
                    continue

            batch.add(Assignment(
                student_id=stu_id, session_id=sess_id,
                item_id=item_id, is_explicit=is_explicit,
            ))
            stats["assigned"] += 1

            item_name = index.menu_item_by_id.get(item_id, {}).get("Menu Item Name", "?")
            if is_explicit:
                source = "explicit"
            elif explicit_pref_counts[caterer_id] < VARIETY_THRESHOLD:
                source = "variety"
            else:
                source = "assigned"
            log.debug(f"  {stu_name} → {item_name} [{source}]")

    log.info(
        f"\nAssigned {stats['assigned']} meals. "
        f"Skipped: {stats['absent']} absent, {stats['excluded']} excluded, "
        f"{stats['opted_out']} opted out, {stats['no_meal']} no compatible meal."
    )

    # -----------------------------------------------------------------------
    # Enforce min-qty per caterer
    # -----------------------------------------------------------------------
    for caterer_id, batch in caterer_batches.items():
        caterer_fields = index.caterer_by_id.get(caterer_id, {})
        caterer_name   = caterer_fields.get("Caterer Name", "?")
        log.info(f"\nEnforcing min-qty for '{caterer_name}'...")
        batch.assignments = enforce_min_qty(caterer_fields, batch.assignments, index)

    # -----------------------------------------------------------------------
    # Dry-run summary or write to Airtable
    # -----------------------------------------------------------------------
    if dry_run:
        log.info("\n=== DRY RUN — not writing to Airtable ===")
        _print_summary(caterer_batches, index, week_dates)
        return

    log.info("\nWriting to Airtable...")

    for caterer_id, batch in caterer_batches.items():
        if not batch.assignments:
            continue

        caterer_fields = index.caterer_by_id.get(caterer_id, {})
        caterer_name   = caterer_fields.get("Caterer Name", "?")
        price_per_item = caterer_fields.get("Price per Item") or 0
        delivery_fee   = caterer_fields.get("Delivery Fee") or 0
        fee_structure  = caterer_fields.get("Delivery Fee Structure", "Per trip")

        total_meals     = len(batch.assignments)
        unique_sessions = len({a.session_id for a in batch.assignments})
        delivery_total  = (
            delivery_fee * unique_sessions
            if fee_structure == "Per school per trip"
            else delivery_fee
        )
        total_cost = total_meals * price_per_item + delivery_total

        wo_id = f"{caterer_name} — {week_label}"
        log.info(f"Creating Weekly Order: {wo_id} ({total_meals} meals, ${total_cost:.2f})")

        created_wo = db.WeeklyOrders.create([{
            "Order ID":    wo_id,
            "Caterer":     [caterer_id],
            "Week Start":  next_monday.isoformat(),
            "Total Meals": total_meals,
            "Total Cost":  total_cost,
        }])
        if not created_wo:
            log.error(f"Failed to create Weekly Order for '{caterer_name}' — skipping.")
            continue

        wo_airtable_id = created_wo[0].id

        # One Order row per (session, item) pair — all students sharing that
        # meal are linked in the Student field. Quantity = number of students.
        # send_orders.py sums Quantity; the ticket API uses FIND in ARRAYJOIN
        # to locate a student's row, both of which work with this shape.
        grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
        for a in batch.assignments:
            grouped[(a.session_id, a.item_id)].append(a.student_id)

        order_records: list[dict[str, Any]] = []
        for (sess_id, item_id), student_ids in grouped.items():
            sess_fields  = index.session_by_id.get(sess_id, {})
            day          = sess_fields.get("Day", "")
            session_date = week_dates.get(day, next_monday)
            sess_label   = sess_fields.get("Session ID", sess_id)
            item_name    = index.menu_item_by_id.get(item_id, {}).get("Menu Item Name", "?")
            order_records.append({
                "Order ID":     f"{sess_label} — {item_name} — {week_label}",
                "Weekly Order": [wo_airtable_id],
                "Menu Item":    [item_id],
                "Session":      [sess_id],
                "Student":      student_ids,
                "Date":         session_date.isoformat(),
                "Quantity":     len(student_ids),
            })

        log.info(f"  Creating {len(order_records)} Order records ({total_meals} meals)...")
        db.Orders.create(order_records)

    log.info("\nOrder registration complete!")


def _print_summary(
    caterer_batches: dict[str, _CatererBatch],
    index:           OrderingIndex,
    week_dates:      dict[str, date],
) -> None:
    """Print a human-readable dry-run summary."""
    for caterer_id, batch in caterer_batches.items():
        caterer_name = index.caterer_by_id.get(caterer_id, {}).get("Caterer Name", "?")
        print(f"\n{'='*60}")
        print(f"  {caterer_name} — {len(batch.assignments)} meals")
        print(f"{'='*60}")

        by_session: dict[str, list[Assignment]] = defaultdict(list)
        for a in batch.assignments:
            by_session[a.session_id].append(a)

        for sess_id, orders in by_session.items():
            sf         = index.session_by_id.get(sess_id, {})
            sess_label = sf.get("Session ID", sess_id)
            day        = sf.get("Day", "?")
            date_      = week_dates.get(day, "?")
            print(f"\n  {day} {date_} — {sess_label}")

            item_counts: dict[str, int] = defaultdict(int)
            for a in orders:
                item_counts[a.item_id] += 1

            for item_id, count in sorted(item_counts.items(), key=lambda x: -x[1]):
                item_name = index.menu_item_by_id.get(item_id, {}).get("Menu Item Name", "?")
                print(f"    {item_name:40s} ×{count}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register weekly meal orders from student preferences",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview without writing to Airtable",
    )
    args = parser.parse_args()
    register_orders(dry_run=args.dry_run)
