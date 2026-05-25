"""
register_orders.py — Snapshot student meal preferences into the Orders table.

For every session occurring next week, for each attending student (enrolled,
not absent, not excluded):
  1. Uses Meal Preference (set via webapp) if it belongs to the session's
     caterer's menu. This is treated as explicit — protected from swapping.
  2. Falls back to a dietary-safe, popularity-weighted assignment otherwise.

After all meals are resolved, enforces caterer min-qty constraints:
  - Items below the per-item minimum are dissolved by proportionally swapping
    non-explicit students to more popular items.
  - Dietary requirements are always respected during swaps.
  - Explicit preferences are never swapped.

Idempotent: clears any existing Orders and draft Weekly Orders for next week
before creating fresh records.

Usage:
  python scripts/register_orders.py [--dry-run]
"""

import argparse
import random
from datetime import datetime, timedelta
from collections import defaultdict
import support as s
from support.compatibility import (
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
# Date helpers
# ---------------------------------------------------------------------------

def get_next_week_dates():
    """Return {day_name: date} for Mon–Fri of next week."""
    today = datetime.now().date()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_to_monday)
    return {day: next_monday + timedelta(days=i) for i, day in enumerate(DAY_ORDER)}


def get_week_label(monday_date):
    iso = monday_date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data():
    s.log.info("Loading data from Airtable...")
    data = {
        "sessions":             s.airtable_get("Sessions"),
        "students":             s.airtable_get("Students"),
        "caterers":             s.airtable_get("Caterers"),
        "menu_items":           s.airtable_get("Menu Items"),
        "dietary_restrictions": s.airtable_get("Dietary Restrictions"),
        "absences":             s.airtable_get("Absences"),
        "exclusions":           s.airtable_get("Exclusions"),
        "feedback":             s.airtable_get("Caterer Feedback"),
    }
    s.log.info(
        f"Loaded: {len(data['sessions'])} sessions, {len(data['students'])} students, "
        f"{len(data['caterers'])} caterers, {len(data['menu_items'])} menu items"
    )
    return data


def build_lookups(data):
    lk = {}
    lk["session_by_id"]      = {r["id"]: r["fields"] for r in data["sessions"]}
    lk["student_by_id"]      = {r["id"]: r["fields"] for r in data["students"]}
    lk["caterer_by_id"]      = {r["id"]: r["fields"] for r in data["caterers"]}
    lk["menu_item_by_id"]    = {r["id"]: r["fields"] for r in data["menu_items"]}
    lk["dietary_hierarchy"] = build_hierarchy(data["dietary_restrictions"])

    lk["menu_items_by_caterer"] = defaultdict(list)
    for item in data["menu_items"]:
        for cid in (item["fields"].get("Caterer") or []):
            lk["menu_items_by_caterer"][cid].append({"id": item["id"], "fields": item["fields"]})

    lk["students_by_session"] = defaultdict(list)
    for stu in data["students"]:
        for sid in (stu["fields"].get("Sessions") or []):
            lk["students_by_session"][sid].append({"id": stu["id"], "fields": stu["fields"]})

    lk["absent_pairs"] = set()
    for ab in data["absences"]:
        stu = (ab["fields"].get("Student") or [None])[0]
        ses = (ab["fields"].get("Session") or [None])[0]
        if stu and ses:
            lk["absent_pairs"].add((stu, ses))

    lk["exclusions"] = data["exclusions"]

    # Average feedback rating per caterer
    caterer_ratings = defaultdict(list)
    for fb in data["feedback"]:
        rating     = fb["fields"].get("Rating")
        caterer_id = (fb["fields"].get("Caterer") or [None])[0]
        if rating is not None and caterer_id:
            caterer_ratings[caterer_id].append(rating)
    lk["caterer_avg_rating"] = {
        cid: sum(rs) / len(rs) for cid, rs in caterer_ratings.items()
    }

    return lk


# ---------------------------------------------------------------------------
# Exclusion checking
# ---------------------------------------------------------------------------

def is_student_excluded(student_fields, session_fields, session_date, lk):
    """Check if a student is excluded from this session on this specific date.

    session_date is the actual date the session occurs next week (sessions
    recur weekly and are matched by Day, not by the Date field on the record).
    """
    sess_school = (session_fields.get("School") or [None])[0]
    if not sess_school or not session_date:
        return False

    sess_date_str = session_date.isoformat()

    for exc in lk["exclusions"]:
        ef = exc["fields"]
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

def assign_fallback_meal(student_dietary_ids, caterer_menu, item_counts, lk):
    """
    Pick the best compatible meal weighted by:
      - Current batch popularity (80%)
      - Random variety           (20%)
    """
    compatible = [
        item for item in caterer_menu
        if is_item_compatible(item["fields"], student_dietary_ids, lk["dietary_hierarchy"])
    ]
    if not compatible:
        return None

    total_orders = sum(item_counts.values()) or 1
    scored = []
    for item in compatible:
        iid         = item["id"]
        order_share = item_counts.get(iid, 0) / total_orders
        variety     = random.uniform(0, 1)
        score       = order_share * 0.8 + variety * 0.2
        scored.append((score, item))

    scored.sort(key=lambda x: -x[0])
    return scored[0][1]["id"]


def compute_max_variety(caterer_fields, total_students):
    """
    Return the most distinct items we can order while still satisfying the
    caterer's min-qty constraint.

    Checks Min Qty 6/5/4 Items in descending order and returns the highest n
    where total_students >= n * min_qty_for_n.

    Falls back to total_students // 3 (minimum 3 orders per item) when no
    explicit constraint is set, so variety never spreads so thin that items
    are ordered with qty 1 or 2.
    """
    for n in range(6, 3, -1):
        min_qty = caterer_fields.get(f"Min Qty {n} Items")
        if min_qty is not None and int(min_qty) > 0 and total_students >= n * int(min_qty):
            return n
    return max(1, total_students // 3)


def assign_variety_meal(student_dietary_ids, caterer_menu, item_counts, lk,
                        max_items=None):
    """
    Pick the least-ordered compatible meal to spread variety across the batch.
    Used when few students have set an explicit preference.

    max_items: if set, once that many distinct items are already in item_counts,
    only pick from those existing items (avoids spreading too thin and violating
    min-qty constraints). Dietary exceptions can still introduce a new item.
    """
    compatible = [
        item for item in caterer_menu
        if is_item_compatible(item["fields"], student_dietary_ids, lk["dietary_hierarchy"])
    ]
    if not compatible:
        return None

    if max_items is not None:
        active_ids = {iid for iid, cnt in item_counts.items() if cnt > 0}
        if len(active_ids) >= max_items:
            capped = [item for item in compatible if item["id"] in active_ids]
            if capped:
                compatible = capped
            # else: all active items are dietarily incompatible — allow a new item

    compatible.sort(key=lambda item: (
        item_counts.get(item["id"], 0),
        random.uniform(0, 1),
    ))
    return compatible[0]["id"]


# ---------------------------------------------------------------------------
# Min-qty enforcement
# ---------------------------------------------------------------------------

def _find_min_qty(caterer_fields, num_distinct_items):
    """
    Return the per-item minimum quantity for the given number of distinct
    items, or None if no constraint applies.
    'Min Qty N Items' = each item must have at least this many portions.
    """
    for n in range(num_distinct_items, 3, -1):
        val = caterer_fields.get(f"Min Qty {n} Items")
        if val is not None:
            return int(val)
    return None


def enforce_min_qty(caterer_fields, assignments, lk):
    """
    Enforce caterer per-item min-qty by swapping non-explicit students from
    under-represented items to more popular ones, proportionally.

    assignments: list of (student_id, session_id, item_id, is_explicit)
    Returns updated list.
    """
    caterer_name = caterer_fields.get("Caterer Name", "?")
    assignments  = list(assignments)

    for _iteration in range(30):  # safety cap
        # Map item → indices in assignments list
        item_to_indices = defaultdict(list)
        for idx, (_, _, item_id, _) in enumerate(assignments):
            item_to_indices[item_id].append(idx)

        item_counts = {iid: len(idxs) for iid, idxs in item_to_indices.items()}
        num_items   = len(item_counts)
        min_qty     = _find_min_qty(caterer_fields, num_items)

        if min_qty is None:
            break

        violating = {iid for iid, cnt in item_counts.items() if cnt < min_qty}
        if not violating:
            break

        # Non-explicit students on violating items — eligible for swap
        swap_indices = [
            idx
            for iid in violating
            for idx in item_to_indices[iid]
            if not assignments[idx][3]  # not is_explicit
        ]

        if not swap_indices:
            s.log.warning(
                f"Caterer '{caterer_name}': min-qty violation cannot be fixed — "
                f"all affected students have explicit preferences."
            )
            break

        # Valid target items: non-violating (i.e. already at or above min_qty)
        valid_items = {iid: cnt for iid, cnt in item_counts.items() if iid not in violating}
        if not valid_items:
            s.log.warning(f"Caterer '{caterer_name}': all items violate min-qty constraint.")
            break

        made_change = False
        for idx in swap_indices:
            stu_id, sess_id, old_item_id, _ = assignments[idx]
            stu_fields  = lk["student_by_id"].get(stu_id, {})
            dietary_ids = stu_fields.get("Dietary Requirements") or []

            # Prefer compatible items from valid (non-violating) set
            compat = {
                iid: cnt for iid, cnt in valid_items.items()
                if is_item_compatible(
                    lk["menu_item_by_id"].get(iid, {}), dietary_ids, lk["dietary_hierarchy"]
                )
            }
            if not compat:
                # Fall back: any compatible item, including violating ones
                compat = {
                    iid: cnt for iid, cnt in item_counts.items()
                    if iid != old_item_id and is_item_compatible(
                        lk["menu_item_by_id"].get(iid, {}), dietary_ids, lk["dietary_hierarchy"]
                    )
                }
            if not compat:
                stu_name = stu_fields.get("Student Name", "?")
                s.log.warning(f"  No compatible swap for {stu_name} — leaving as-is.")
                continue

            # Proportional weighted selection
            total     = sum(compat.values()) or 1
            rand_val  = random.uniform(0, total)
            cumulative = 0.0
            chosen_id  = next(iter(compat))
            for iid, cnt in sorted(compat.items(), key=lambda x: -x[1]):
                cumulative += cnt
                if rand_val <= cumulative:
                    chosen_id = iid
                    break

            assignments[idx] = (stu_id, sess_id, chosen_id, False)
            valid_items[chosen_id] = valid_items.get(chosen_id, 0) + 1

            stu_name  = stu_fields.get("Student Name", "?")
            old_name  = lk["menu_item_by_id"].get(old_item_id, {}).get("Menu Item Name", "?")
            new_name  = lk["menu_item_by_id"].get(chosen_id, {}).get("Menu Item Name", "?")
            s.log.info(f"  Min-qty swap: {stu_name}: {old_name} → {new_name}")
            made_change = True

        if not made_change:
            break

    return assignments


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def clear_existing_orders(week_dates, dry_run=False):
    """Delete any existing Orders and draft Weekly Orders for next week."""
    dates    = list(week_dates.values())
    min_date = min(dates).isoformat()
    max_date = max(dates).isoformat()

    existing = s.airtable_get(
        "Orders",
        filter_formula=f"AND({{Date}} >= '{min_date}', {{Date}} <= '{max_date}')"
    )
    if existing:
        s.log.info(f"Clearing {len(existing)} existing Orders for next week...")
        if not dry_run:
            tbl = s.get_table("Orders")
            for i in range(0, len(existing), 10):
                tbl.batch_delete([r["id"] for r in existing[i:i+10]])

    existing_wo = s.airtable_get(
        "Weekly Orders",
        filter_formula=f"AND({{Week Start}} >= '{min_date}', {{Week Start}} <= '{max_date}')"
    )
    if existing_wo:
        s.log.info(f"Clearing {len(existing_wo)} existing draft Weekly Orders for next week...")
        if not dry_run:
            tbl = s.get_table("Weekly Orders")
            for i in range(0, len(existing_wo), 10):
                tbl.batch_delete([r["id"] for r in existing_wo[i:i+10]])


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def register_orders(dry_run=False):
    week_dates   = get_next_week_dates()
    next_monday  = week_dates["Monday"]
    week_label   = get_week_label(next_monday)

    s.log.info(f"=== Registering orders for {week_label} (week of {next_monday}) ===")

    data = load_all_data()
    lk   = build_lookups(data)

    clear_existing_orders(week_dates, dry_run)

    # Sessions for next week — matched by Day field (sessions recur weekly)
    next_week_sessions = [
        sess for sess in data["sessions"]
        if sess["fields"].get("Day") in week_dates
    ]
    s.log.info(f"Found {len(next_week_sessions)} sessions for next week")

    if not next_week_sessions:
        s.log.warning("No sessions found for next week.")
        return

    # Pre-scan: count *eligible* students (not absent / excluded / opted out)
    # and explicit preferences per caterer. Used to pick fallback assignment
    # mode and to cap variety so items aren't spread too thin.
    explicit_pref_counts:   defaultdict = defaultdict(int)
    caterer_student_counts: defaultdict = defaultdict(int)
    for sess_rec in next_week_sessions:
        sess_id      = sess_rec["id"]
        sess_fields  = sess_rec["fields"]
        cid = (sess_fields.get("Caterer") or [None])[0]
        if not cid:
            continue
        session_date = week_dates.get(sess_fields.get("Day"))
        menu_ids = {item["id"] for item in lk["menu_items_by_caterer"].get(cid, [])}
        for stu in lk["students_by_session"].get(sess_id, []):
            stu_id     = stu["id"]
            stu_fields = stu["fields"]
            if (stu_id, sess_id) in lk["absent_pairs"]:
                continue
            if is_student_excluded(stu_fields, sess_fields, session_date, lk):
                continue
            dietary_ids = stu_fields.get("Dietary Requirements") or []
            if has_opted_out(dietary_ids, lk["dietary_hierarchy"]):
                continue
            caterer_student_counts[cid] += 1
            pref_ids = stu_fields.get("Meal Preference") or []
            if pref_ids and pref_ids[0] in menu_ids:
                explicit_pref_counts[cid] += 1

    caterer_max_variety = {
        cid: compute_max_variety(lk["caterer_by_id"].get(cid, {}), total)
        for cid, total in caterer_student_counts.items()
    }

    for cid, count in explicit_pref_counts.items():
        caterer_name = lk["caterer_by_id"].get(cid, {}).get("Caterer Name", cid)
        mode     = "popularity" if count >= VARIETY_THRESHOLD else "variety"
        max_v    = caterer_max_variety.get(cid)
        cap_str  = f", capped at {max_v} items" if (mode == "variety" and max_v) else ""
        s.log.info(f"Caterer '{caterer_name}': {count} explicit preferences — using {mode} fallback{cap_str}")

    # -----------------------------------------------------------------------
    # Build per-caterer assignment list
    # (student_id, session_id, item_id, is_explicit)
    # -----------------------------------------------------------------------
    caterer_assignments = defaultdict(list)
    caterer_item_counts = defaultdict(lambda: defaultdict(int))  # for popularity fallback

    stats = {"assigned": 0, "absent": 0, "excluded": 0, "opted_out": 0, "no_meal": 0}

    for sess_rec in next_week_sessions:
        sess_id      = sess_rec["id"]
        sess_fields  = sess_rec["fields"]
        sess_label   = sess_fields.get("Session ID", sess_id)
        day          = sess_fields.get("Day", "?")
        session_date = week_dates.get(day)

        caterer_links = sess_fields.get("Caterer") or []
        if not caterer_links:
            s.log.warning(f"Session '{sess_label}' has no caterer — skipping.")
            continue
        caterer_id = caterer_links[0]

        caterer_menu = lk["menu_items_by_caterer"].get(caterer_id, [])
        if not caterer_menu:
            s.log.warning(f"Session '{sess_label}': caterer has no menu items — skipping.")
            continue

        caterer_menu_ids = {item["id"] for item in caterer_menu}
        enrolled         = lk["students_by_session"].get(sess_id, [])
        s.log.info(f"Session '{sess_label}' ({day}): {len(enrolled)} enrolled students")

        for stu in enrolled:
            stu_id     = stu["id"]
            stu_fields = stu["fields"]
            stu_name   = stu_fields.get("Student Name", "?")

            if (stu_id, sess_id) in lk["absent_pairs"]:
                stats["absent"] += 1
                continue

            if is_student_excluded(stu_fields, sess_fields, session_date, lk):
                stats["excluded"] += 1
                continue

            dietary_ids = stu_fields.get("Dietary Requirements") or []

            if has_opted_out(dietary_ids, lk["dietary_hierarchy"]):
                stats["opted_out"] += 1
                continue

            # --- Try explicit Meal Preference ---
            pref_ids    = stu_fields.get("Meal Preference") or []
            item_id     = None
            is_explicit = False

            if pref_ids:
                pref_id = pref_ids[0]
                if pref_id in caterer_menu_ids:
                    pref_fields = lk["menu_item_by_id"].get(pref_id, {})
                    pref_name   = pref_fields.get("Menu Item Name", "?")
                    # Honour explicit preference even if it violates dietary requirements
                    if not is_item_compatible(pref_fields, dietary_ids, lk["dietary_hierarchy"]):
                        dietary_names = resolve_dietary_names(dietary_ids, lk["dietary_hierarchy"])
                        s.log.warning(
                            f"  {stu_name}: explicit preference '{pref_name}' conflicts with "
                            f"dietary {dietary_names} — honouring explicit choice."
                        )
                    item_id     = pref_id
                    is_explicit = True
                else:
                    s.log.debug(f"  {stu_name}: preference not on this caterer's menu.")

            # --- Fallback assignment ---
            if item_id is None:
                use_variety = explicit_pref_counts[caterer_id] < VARIETY_THRESHOLD
                assign_fn   = assign_variety_meal if use_variety else assign_fallback_meal
                kwargs      = {"max_items": caterer_max_variety.get(caterer_id)} if use_variety else {}
                item_id     = assign_fn(
                    dietary_ids, caterer_menu, caterer_item_counts[caterer_id], lk, **kwargs
                )
                if item_id is None:
                    s.log.warning(f"  {stu_name}: no compatible meal found — skipping.")
                    stats["no_meal"] += 1
                    continue

            caterer_assignments[caterer_id].append((stu_id, sess_id, item_id, is_explicit))
            caterer_item_counts[caterer_id][item_id] += 1
            stats["assigned"] += 1

            item_name = lk["menu_item_by_id"].get(item_id, {}).get("Menu Item Name", "?")
            if is_explicit:
                source = "explicit"
            elif explicit_pref_counts[caterer_id] < VARIETY_THRESHOLD:
                source = "variety"
            else:
                source = "assigned"
            s.log.debug(f"  {stu_name} → {item_name} [{source}]")

    s.log.info(
        f"\nAssigned {stats['assigned']} meals. "
        f"Skipped: {stats['absent']} absent, {stats['excluded']} excluded, "
        f"{stats['opted_out']} opted out, {stats['no_meal']} no compatible meal."
    )

    # -----------------------------------------------------------------------
    # Enforce min-qty per caterer
    # -----------------------------------------------------------------------
    for caterer_id in caterer_assignments:
        caterer_fields = lk["caterer_by_id"].get(caterer_id, {})
        caterer_name   = caterer_fields.get("Caterer Name", "?")
        s.log.info(f"\nEnforcing min-qty for '{caterer_name}'...")
        caterer_assignments[caterer_id] = enforce_min_qty(
            caterer_fields, caterer_assignments[caterer_id], lk
        )

    # -----------------------------------------------------------------------
    # Dry-run summary or write to Airtable
    # -----------------------------------------------------------------------
    if dry_run:
        s.log.info("\n=== DRY RUN — not writing to Airtable ===")
        _print_summary(caterer_assignments, lk, week_dates)
        return

    s.log.info("\nWriting to Airtable...")

    for caterer_id, assignments in caterer_assignments.items():
        if not assignments:
            continue

        caterer_fields = lk["caterer_by_id"].get(caterer_id, {})
        caterer_name   = caterer_fields.get("Caterer Name", "?")
        price_per_item = caterer_fields.get("Price per Item") or 0
        delivery_fee   = caterer_fields.get("Delivery Fee") or 0
        fee_structure  = caterer_fields.get("Delivery Fee Structure", "Per trip")

        total_meals     = len(assignments)
        unique_sessions = len({sess_id for _, sess_id, _, _ in assignments})
        delivery_total  = (
            delivery_fee * unique_sessions
            if fee_structure == "Per school per trip"
            else delivery_fee
        )
        total_cost = total_meals * price_per_item + delivery_total

        wo_id = f"{caterer_name} — {week_label}"
        s.log.info(f"Creating Weekly Order: {wo_id} ({total_meals} meals, ${total_cost:.2f})")

        created_wo = s.airtable_post("Weekly Orders", [{
            "Order ID":    wo_id,
            "Caterer":     [caterer_id],
            "Week Start":  next_monday.isoformat(),
            "Total Meals": total_meals,
            "Total Cost":  total_cost,
        }])
        if not created_wo:
            s.log.error(f"Failed to create Weekly Order for '{caterer_name}' — skipping.")
            continue

        wo_airtable_id = created_wo[0]["id"]

        # Aggregate to (session, item) → quantity
        session_item_counts = defaultdict(lambda: defaultdict(int))
        for _, sess_id, item_id, _ in assignments:
            session_item_counts[sess_id][item_id] += 1

        order_records = []
        for sess_id, item_counts in session_item_counts.items():
            sess_fields  = lk["session_by_id"].get(sess_id, {})
            day          = sess_fields.get("Day", "")
            session_date = week_dates.get(day, next_monday)
            sess_label   = sess_fields.get("Session ID", sess_id)

            for item_id, quantity in item_counts.items():
                item_name = lk["menu_item_by_id"].get(item_id, {}).get("Menu Item Name", "?")
                order_records.append({
                    "Order ID":     f"{sess_label} — {item_name} — {week_label}",
                    "Weekly Order": [wo_airtable_id],
                    "Menu Item":    [item_id],
                    "Session":      [sess_id],
                    "Date":         session_date.isoformat(),
                    "Quantity":     quantity,
                })

        s.log.info(f"  Creating {len(order_records)} Order records...")
        s.airtable_post("Orders", order_records)

    s.log.info("\nOrder registration complete!")


def _print_summary(caterer_assignments, lk, week_dates):
    """Print a human-readable dry-run summary."""
    for caterer_id, assignments in caterer_assignments.items():
        caterer_name = lk["caterer_by_id"].get(caterer_id, {}).get("Caterer Name", "?")
        print(f"\n{'='*60}")
        print(f"  {caterer_name} — {len(assignments)} meals")
        print(f"{'='*60}")

        by_session = defaultdict(list)
        for stu_id, sess_id, item_id, is_explicit in assignments:
            by_session[sess_id].append((stu_id, item_id, is_explicit))

        for sess_id, orders in by_session.items():
            sf         = lk["session_by_id"].get(sess_id, {})
            sess_label = sf.get("Session ID", sess_id)
            day        = sf.get("Day", "?")
            date       = week_dates.get(day, "?")
            print(f"\n  {day} {date} — {sess_label}")

            item_counts = defaultdict(int)
            for _, item_id, _ in orders:
                item_counts[item_id] += 1

            for item_id, count in sorted(item_counts.items(), key=lambda x: -x[1]):
                item_name = lk["menu_item_by_id"].get(item_id, {}).get("Menu Item Name", "?")
                print(f"    {item_name:40s} ×{count}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Register weekly meal orders from student preferences"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing to Airtable")
    args = parser.parse_args()
    register_orders(dry_run=args.dry_run)
