"""
generate_orders.py — Compiles weekly meal orders from student selections.

Two ordering rounds:
  Round 1 (compiled Thursday): sessions on Mon, Tue, Wed of next week
  Round 2 (compiled Saturday): sessions on Thu, Fri of next week

For each session, resolves every attending student's meal:
  1. Explicit Meal Selection for that session
  2. Fallback to their selection from the same session in previous weeks
  3. AI-assigned meal (dietary-filtered, rating-weighted)

Validates minimum order quantities per caterer and writes results to
Airtable (Weekly Orders + Order Line Items).

Usage:
  python scripts/generate_orders.py [--dry-run] [--round 1|2]
"""

import os
import sys
import json
import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Add repository root to system path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts import support as s

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
ROUND_1_DAYS = {"Monday", "Tuesday", "Wednesday"}
ROUND_2_DAYS = {"Thursday", "Friday"}

# Negative dietary requirements that map to ingredient keywords in item names
NEGATIVE_DIETARY_KEYWORDS = {
    "No Beef": ["beef", "bulgogi"],
    "No Pork": ["pork", "bacon", "ham"],
    "No Seafood": ["seafood", "shrimp", "prawn", "fish", "salmon", "tuna", "shellfish", "crab", "lobster"],
    "No Shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
    "No Fish": ["fish", "salmon", "tuna"],
    "No Red Meat": ["beef", "lamb", "pork", "bulgogi"],
}

# Positive dietary requirements — item must have the matching tag
POSITIVE_DIETARY_TAGS = {
    "Gluten Free": "Gluten Free",
    "Dairy Free": "Dairy Free",
    "Nut Free": "Nut Free",
    "Vegetarian": "Vegetarian",
    "Halal": "Halal",
}


def is_item_compatible(item_fields, student_dietary):
    """Check if a menu item is compatible with a student's dietary requirements."""
    if not student_dietary:
        return True

    item_tags = set(item_fields.get("Dietary Tags", []) or [])
    item_name_lower = item_fields.get("Menu Item Name", "").lower()

    for req in student_dietary:
        if req == "Opted out of Catering":
            return False

        # Positive requirements: item must have the tag
        if req in POSITIVE_DIETARY_TAGS:
            required_tag = POSITIVE_DIETARY_TAGS[req]
            if required_tag not in item_tags:
                return False

        # Negative requirements: item name must not contain keywords
        if req in NEGATIVE_DIETARY_KEYWORDS:
            for keyword in NEGATIVE_DIETARY_KEYWORDS[req]:
                if keyword in item_name_lower:
                    return False

    return True


def get_next_week_monday():
    """Get the Monday of next week."""
    today = datetime.now().date()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    return today + timedelta(days=days_until_monday)


def get_week_label(monday_date):
    """e.g. '2026-W19'"""
    iso = monday_date.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_all_data():
    """Load all required data from Airtable."""
    s.log.info("Loading data from Airtable...")

    data = {}
    data["sessions"] = s.airtable_get("Sessions")
    data["students"] = s.airtable_get("Students")
    data["caterers"] = s.airtable_get("Caterers")
    data["menu_items"] = s.airtable_get("Menu Items")
    data["absences"] = s.airtable_get("Absences")
    data["exclusions"] = s.airtable_get("Exclusions")
    data["selections"] = s.airtable_get("Meal Selections")
    data["feedback"] = s.airtable_get("Meal Feedback")
    data["schools"] = s.airtable_get("Schools")

    s.log.info(
        f"Loaded: {len(data['sessions'])} sessions, "
        f"{len(data['students'])} students, "
        f"{len(data['caterers'])} caterers, "
        f"{len(data['menu_items'])} menu items, "
        f"{len(data['selections'])} selections, "
        f"{len(data['feedback'])} feedback records"
    )
    return data


def build_lookups(data):
    """Build lookup dictionaries for efficient access."""
    lookups = {}

    # Record ID → fields
    lookups["session_by_id"] = {r["id"]: r["fields"] for r in data["sessions"]}
    lookups["student_by_id"] = {r["id"]: r["fields"] for r in data["students"]}
    lookups["caterer_by_id"] = {r["id"]: r["fields"] for r in data["caterers"]}
    lookups["menu_item_by_id"] = {r["id"]: r["fields"] for r in data["menu_items"]}
    lookups["school_by_id"] = {r["id"]: r["fields"] for r in data["schools"]}

    # Menu items grouped by caterer record ID
    lookups["menu_items_by_caterer"] = defaultdict(list)
    for item in data["menu_items"]:
        caterer_links = item["fields"].get("Caterer", [])
        for cid in caterer_links:
            lookups["menu_items_by_caterer"][cid].append(
                {"id": item["id"], "fields": item["fields"]}
            )

    # Students enrolled in each session (session_id → [student records])
    lookups["students_by_session"] = defaultdict(list)
    for stu in data["students"]:
        session_links = stu["fields"].get("Sessions", [])
        for sid in session_links:
            lookups["students_by_session"][sid].append(
                {"id": stu["id"], "fields": stu["fields"]}
            )

    # Selections indexed by (student_id, session_id)
    lookups["selection_by_student_session"] = {}
    for sel in data["selections"]:
        stu_links = sel["fields"].get("Student", [])
        sess_links = sel["fields"].get("Session", [])
        if stu_links and sess_links:
            key = (stu_links[0], sess_links[0])
            lookups["selection_by_student_session"][key] = sel["fields"]

    # Absences: set of (student_id, session_id)
    lookups["absent_pairs"] = set()
    for ab in data["absences"]:
        stu_links = ab["fields"].get("Student", [])
        sess_links = ab["fields"].get("Session", [])
        if stu_links and sess_links:
            lookups["absent_pairs"].add((stu_links[0], sess_links[0]))

    # Exclusions: session_id → exclusion info (we need school + date matching)
    lookups["exclusions"] = data["exclusions"]

    # Feedback: (student_id, menu_item_id) → list of ratings
    lookups["feedback_ratings"] = defaultdict(list)
    # Also global per-item ratings
    lookups["item_global_ratings"] = defaultdict(list)
    for fb in data["feedback"]:
        stu_links = fb["fields"].get("Student", [])
        item_links = fb["fields"].get("Menu Item", [])
        rating = fb["fields"].get("Rating")
        if rating is not None and item_links:
            item_id = item_links[0]
            lookups["item_global_ratings"][item_id].append(rating)
            if stu_links:
                lookups["feedback_ratings"][(stu_links[0], item_id)].append(rating)

    # Sessions grouped by (school_id, day) for fallback lookups
    lookups["sessions_by_school_day"] = defaultdict(list)
    for sess in data["sessions"]:
        school_links = sess["fields"].get("School", [])
        day = sess["fields"].get("Day")
        if school_links and day:
            lookups["sessions_by_school_day"][(school_links[0], day)].append(sess)

    return lookups


# ---------------------------------------------------------------------------
# Meal resolution
# ---------------------------------------------------------------------------

def find_previous_selection(student_id, session_fields, lookups):
    """
    Look for the student's meal selection from previous equivalent sessions
    (same school + same day of week), going back up to 8 weeks.
    Returns the menu item record ID if found, else None.
    """
    school_links = session_fields.get("School", [])
    day = session_fields.get("Day")
    current_date_str = session_fields.get("Date")

    if not school_links or not day or not current_date_str:
        return None

    try:
        current_date = datetime.strptime(current_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None

    # Get all sessions for the same school + day, sorted by date descending
    equivalent_sessions = lookups["sessions_by_school_day"].get(
        (school_links[0], day), []
    )

    # Sort by date descending, filter to before current session
    past_sessions = []
    for sess in equivalent_sessions:
        sess_date_str = sess["fields"].get("Date")
        if not sess_date_str:
            continue
        try:
            sess_date = datetime.strptime(sess_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if sess_date < current_date:
            past_sessions.append((sess_date, sess["id"]))

    past_sessions.sort(key=lambda x: x[0], reverse=True)

    # Check up to 8 previous weeks
    for _, prev_session_id in past_sessions[:8]:
        sel = lookups["selection_by_student_session"].get(
            (student_id, prev_session_id)
        )
        if sel:
            item_links = sel.get("Menu Item", [])
            if item_links:
                return item_links[0]

    return None


def ai_assign_meal(student_id, student_dietary, compatible_items, lookups):
    """
    Pick the best meal for a non-respondent student using:
      - Personal rating history (weight 0.5)
      - Global popularity (weight 0.3)
      - Random variety factor (weight 0.2)
    """
    if not compatible_items:
        return None

    scored = []
    for item in compatible_items:
        item_id = item["id"]

        # Personal average rating
        personal_ratings = lookups["feedback_ratings"].get(
            (student_id, item_id), []
        )
        personal_avg = sum(personal_ratings) / len(personal_ratings) if personal_ratings else 3.0

        # Global average rating
        global_ratings = lookups["item_global_ratings"].get(item_id, [])
        global_avg = sum(global_ratings) / len(global_ratings) if global_ratings else 3.0

        # Random variety factor
        variety = random.uniform(0, 1)

        score = personal_avg * 0.5 + global_avg * 0.3 + variety * 0.2
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def resolve_student_meal(student_id, student_fields, session_id, session_fields,
                         caterer_menu_items, lookups):
    """
    Resolve what meal a student should get for a given session.
    Returns (menu_item_id, menu_item_fields, source) or (None, None, "opted_out")
    """
    dietary = student_fields.get("Dietary Requirements", []) or []

    # Skip students who opted out
    if "Opted out of Catering" in dietary:
        return None, None, "opted_out"

    # Filter caterer's menu to compatible items
    compatible = [
        item for item in caterer_menu_items
        if is_item_compatible(item["fields"], dietary)
    ]

    if not compatible:
        s.log.warning(
            f"No compatible items for student '{student_fields.get('Student Name')}' "
            f"with dietary {dietary}. Skipping."
        )
        return None, None, "no_compatible"

    # 1. Explicit selection for this session
    sel = lookups["selection_by_student_session"].get((student_id, session_id))
    if sel:
        item_links = sel.get("Menu Item", [])
        if item_links:
            item_id = item_links[0]
            item_fields = lookups["menu_item_by_id"].get(item_id)
            if item_fields and is_item_compatible(item_fields, dietary):
                return item_id, item_fields, "selected"

    # 2. Fallback to previous week's selection
    prev_item_id = find_previous_selection(student_id, session_fields, lookups)
    if prev_item_id:
        prev_fields = lookups["menu_item_by_id"].get(prev_item_id)
        if prev_fields and is_item_compatible(prev_fields, dietary):
            # Verify item is still on the current caterer's menu
            if any(item["id"] == prev_item_id for item in caterer_menu_items):
                return prev_item_id, prev_fields, "previous_week"

    # 3. AI-assigned meal
    best = ai_assign_meal(student_id, dietary, compatible, lookups)
    if best:
        return best["id"], best["fields"], "ai_assigned"

    return None, None, "fallback_failed"


# ---------------------------------------------------------------------------
# Exclusion checking
# ---------------------------------------------------------------------------

def is_student_excluded(student_fields, session_fields, lookups):
    """Check if a student is excluded from a session via Exclusions table."""
    session_school_links = session_fields.get("School", [])
    session_date = session_fields.get("Date")

    if not session_school_links or not session_date:
        return False

    for exc in lookups["exclusions"]:
        exc_fields = exc["fields"]
        exc_school_links = exc_fields.get("School", [])
        exc_date = exc_fields.get("Date")
        affected_levels = exc_fields.get("Affected Year Levels", "")

        if not exc_school_links or not exc_date:
            continue

        # Check school and date match
        if exc_school_links[0] != session_school_links[0]:
            continue
        if exc_date != session_date:
            continue

        # Check year level
        if "all" in affected_levels.lower():
            return True

        student_year = student_fields.get("Year Level")
        if student_year and str(student_year) in affected_levels:
            return True

    return False


# ---------------------------------------------------------------------------
# Min qty enforcement
# ---------------------------------------------------------------------------

def enforce_min_qty(caterer_fields, item_counts):
    """
    Ensure the total order meets the caterer's minimum for the number of
    distinct items. If not, merge least-popular items until it does.

    item_counts: dict of {item_id: count}
    Returns adjusted item_counts.
    """
    if not item_counts:
        return item_counts

    total_meals = sum(item_counts.values())
    num_items = len(item_counts)

    # Check from current distinct count down to 4
    for n in range(num_items, 3, -1):
        min_qty_field = f"Min Qty {n} Items"
        min_qty = caterer_fields.get(min_qty_field)

        if min_qty is not None and total_meals >= min_qty:
            # Current count of distinct items works at this level
            if n >= num_items:
                return item_counts
            # Need to reduce to n distinct items
            break
    else:
        # Even 4 items might not meet minimum — just proceed with what we have
        # The coordinator can review the draft
        return item_counts

    # Merge least-popular items into most-popular until we have n distinct items
    if len(item_counts) > n:
        sorted_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)
        merged = dict(sorted_items[:n])
        # Redistribute the merged items' quantities to the top item
        overflow = sum(count for _, count in sorted_items[n:])
        top_item_id = sorted_items[0][0]
        merged[top_item_id] += overflow

        s.log.info(
            f"Min qty enforcement: reduced from {len(item_counts)} to {n} distinct items "
            f"(total: {total_meals}, min for {n}: {min_qty})"
        )
        return merged

    return item_counts


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def determine_round():
    """Determine which round to compile based on today's day of week."""
    today = datetime.now().date()
    weekday = today.weekday()  # 0=Mon, 3=Thu, 5=Sat

    if weekday == 3:  # Thursday
        return 1
    elif weekday == 5:  # Saturday
        return 2
    else:
        s.log.info(f"Today is {today.strftime('%A')}. Defaulting to Round 1.")
        return 1


def generate_orders(dry_run=False, force_round=None):
    """Main order generation pipeline."""

    ordering_round = force_round or determine_round()
    round_label = "Round 1 (Mon–Wed)" if ordering_round == 1 else "Round 2 (Thu–Fri)"
    target_days = ROUND_1_DAYS if ordering_round == 1 else ROUND_2_DAYS

    next_monday = get_next_week_monday()
    week_label = get_week_label(next_monday)

    s.log.info(f"=== Generating orders for {week_label} — {round_label} ===")
    s.log.info(f"Target days: {', '.join(sorted(target_days))}")

    # Load all data
    data = load_all_data()
    lookups = build_lookups(data)

    # Find sessions for the target days
    # (Since sessions may not have future dates yet, we match by Day field)
    target_sessions = []
    for sess in data["sessions"]:
        day = sess["fields"].get("Day")
        if day in target_days:
            target_sessions.append(sess)

    s.log.info(f"Found {len(target_sessions)} sessions for {round_label}")

    if not target_sessions:
        s.log.warning("No sessions found for target days. Nothing to order.")
        return

    # --- Compile orders per caterer ---
    # Structure: caterer_id → { session_id → { item_id → count } }
    caterer_orders = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # Track assignment sources for reporting
    assignment_log = []

    for sess in target_sessions:
        sess_id = sess["id"]
        sess_fields = sess["fields"]
        sess_label = sess_fields.get("Session ID", sess_id)

        caterer_links = sess_fields.get("Caterer", [])
        if not caterer_links:
            s.log.warning(f"Session '{sess_label}' has no caterer assigned. Skipping.")
            continue
        caterer_id = caterer_links[0]

        # Get this caterer's menu
        caterer_menu = lookups["menu_items_by_caterer"].get(caterer_id, [])
        if not caterer_menu:
            s.log.warning(f"Caterer for session '{sess_label}' has no menu items. Skipping.")
            continue

        # Get enrolled students for this session
        enrolled = lookups["students_by_session"].get(sess_id, [])
        s.log.info(f"Session '{sess_label}': {len(enrolled)} enrolled students")

        for stu in enrolled:
            stu_id = stu["id"]
            stu_fields = stu["fields"]
            stu_name = stu_fields.get("Student Name", "?")

            # Check absence
            if (stu_id, sess_id) in lookups["absent_pairs"]:
                assignment_log.append((sess_label, stu_name, "absent", None))
                continue

            # Check exclusion
            if is_student_excluded(stu_fields, sess_fields, lookups):
                assignment_log.append((sess_label, stu_name, "excluded", None))
                continue

            # Resolve meal
            item_id, item_fields, source = resolve_student_meal(
                stu_id, stu_fields, sess_id, sess_fields, caterer_menu, lookups
            )

            if item_id:
                caterer_orders[caterer_id][sess_id][item_id] += 1
                item_name = item_fields.get("Menu Item Name", "?") if item_fields else "?"
                assignment_log.append((sess_label, stu_name, source, item_name))
            else:
                assignment_log.append((sess_label, stu_name, source, None))

    # --- Report assignments ---
    s.log.info("\n=== Meal Assignments ===")
    for sess_label, stu_name, source, item_name in assignment_log:
        if item_name:
            s.log.info(f"  {sess_label} | {stu_name:25s} | {source:15s} | {item_name}")
        else:
            s.log.info(f"  {sess_label} | {stu_name:25s} | {source:15s} | (no meal)")

    # --- Enforce min qty per caterer ---
    for caterer_id in caterer_orders:
        caterer_fields = lookups["caterer_by_id"].get(caterer_id, {})
        caterer_name = caterer_fields.get("Caterer Name", "?")

        # Aggregate across all sessions for this caterer
        total_by_item = defaultdict(int)
        for sess_id, items in caterer_orders[caterer_id].items():
            for item_id, count in items.items():
                total_by_item[item_id] += count

        total_meals = sum(total_by_item.values())
        num_distinct = len(total_by_item)
        s.log.info(
            f"\nCaterer '{caterer_name}': {total_meals} meals, {num_distinct} distinct items"
        )

        adjusted = enforce_min_qty(caterer_fields, dict(total_by_item))

        # If items were merged, we need to redistribute back to sessions
        if set(adjusted.keys()) != set(total_by_item.keys()):
            removed_items = set(total_by_item.keys()) - set(adjusted.keys())
            surviving_items = list(adjusted.keys())

            for sess_id in caterer_orders[caterer_id]:
                session_items = caterer_orders[caterer_id][sess_id]
                for removed_id in removed_items:
                    if removed_id in session_items:
                        # Move these counts to the first surviving item
                        session_items[surviving_items[0]] = (
                            session_items.get(surviving_items[0], 0)
                            + session_items.pop(removed_id)
                        )

    # --- Write to Airtable (or dry-run) ---
    if dry_run:
        s.log.info("\n=== DRY RUN — not writing to Airtable ===")
        _print_order_summary(caterer_orders, lookups, week_label, round_label)
        return

    s.log.info("\nWriting orders to Airtable...")
    _write_orders_to_airtable(caterer_orders, lookups, week_label, round_label, next_monday)

    s.log.info("Order generation complete!")


def _print_order_summary(caterer_orders, lookups, week_label, round_label):
    """Print a human-readable order summary."""
    for caterer_id, sessions in caterer_orders.items():
        caterer_fields = lookups["caterer_by_id"].get(caterer_id, {})
        caterer_name = caterer_fields.get("Caterer Name", "?")

        print(f"\n{'='*60}")
        print(f"  {caterer_name} — {week_label} {round_label}")
        print(f"{'='*60}")

        grand_total = 0
        for sess_id, items in sessions.items():
            sess_fields = lookups["session_by_id"].get(sess_id, {})
            sess_day = sess_fields.get("Day", "?")

            school_links = sess_fields.get("School", [])
            school_name = "?"
            if school_links:
                school_fields = lookups["school_by_id"].get(school_links[0], {})
                school_name = school_fields.get("School Name", "?")

            delivery_time = sess_fields.get("Dinner Time", "?")
            building = sess_fields.get("Building", "?")

            print(f"\n  {sess_day} — {school_name}")
            print(f"  Deliver by: {delivery_time} | Building: {building}")

            session_total = 0
            for item_id, count in sorted(items.items(), key=lambda x: -x[1]):
                item_fields = lookups["menu_item_by_id"].get(item_id, {})
                item_name = item_fields.get("Menu Item Name", "?")
                print(f"    {item_name:40s} ×{count}")
                session_total += count

            print(f"    {'─'*44}")
            print(f"    {'Subtotal':40s} ×{session_total}")
            grand_total += session_total

        print(f"\n  GRAND TOTAL: {grand_total} meals")


def _write_orders_to_airtable(caterer_orders, lookups, week_label, round_label,
                               week_start_date):
    """Write Weekly Orders and Order Line Items to Airtable."""
    round_tag = "R1" if "Mon" in round_label else "R2"

    for caterer_id, sessions in caterer_orders.items():
        caterer_fields = lookups["caterer_by_id"].get(caterer_id, {})
        caterer_name = caterer_fields.get("Caterer Name", "?")

        # Calculate totals
        grand_total = sum(
            count for items in sessions.values() for count in items.values()
        )

        # Estimate cost. Caterers charge a flat per-item price across their menu.
        price_per_item = caterer_fields.get("Price per Item", 0) or 0
        total_cost = 0.0
        for items in sessions.values():
            for count in items.values():
                total_cost += price_per_item * count

        # Add delivery fee
        delivery_fee = caterer_fields.get("Delivery Fee", 0) or 0
        fee_structure = caterer_fields.get("Delivery Fee Structure", "Per trip")
        if fee_structure == "Per school per trip":
            total_cost += delivery_fee * len(sessions)
        else:
            total_cost += delivery_fee

        order_id = f"{caterer_name} — {week_label}-{round_tag}"

        order_record = {
            "Order ID": order_id,
            "Caterer": [caterer_id],
            "Round": round_label,
            "Week Start": week_start_date.isoformat(),
            "Total Meals": grand_total,
            "Total Cost": total_cost,
            "Status": "Draft",
        }

        s.log.info(f"Creating Weekly Order: {order_id} ({grand_total} meals, ${total_cost:.2f})")
        created = s.airtable_post("Weekly Orders", [order_record])
        if not created:
            s.log.error(f"Failed to create order for {caterer_name}")
            continue

        weekly_order_id = created[0]["id"]

        # Create line items
        line_items = []
        for sess_id, items in sessions.items():
            for item_id, count in items.items():
                item_fields = lookups["menu_item_by_id"].get(item_id, {})
                item_name = item_fields.get("Menu Item Name", "?")

                sess_fields = lookups["session_by_id"].get(sess_id, {})
                sess_label = sess_fields.get("Session ID", sess_id)

                line_item_id = f"{order_id} — {sess_label} — {item_name}"

                line_items.append({
                    "Line Item ID": line_item_id,
                    "Weekly Order": [weekly_order_id],
                    "Menu Item": [item_id],
                    "Session": [sess_id],
                    "Quantity": count,
                })

        if line_items:
            s.log.info(f"  Creating {len(line_items)} line items...")
            s.airtable_post("Order Line Items", line_items)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate weekly meal orders")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview orders without writing to Airtable"
    )
    parser.add_argument(
        "--round", type=int, choices=[1, 2], default=None,
        help="Force ordering round (1=Mon-Wed, 2=Thu-Fri)"
    )
    args = parser.parse_args()

    generate_orders(dry_run=args.dry_run, force_round=args.round)
