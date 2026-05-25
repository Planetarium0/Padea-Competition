"""
order_constraints.py — Verify that registered Orders for next week:
  1. Satisfy each caterer's Min Qty N Items constraint (per-caterer totals).
  2. Match the expected eating-student count per session (enrolled minus
     absent, excluded, opted-out).

Run after ./run orders generate.

Usage:
  python scripts/tests/order_constraints.py
"""

from collections import defaultdict
import support as s

from actions.register_orders import (
    get_next_week_dates,
    is_student_excluded,
    resolve_dietary_names,
    _find_min_qty,
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data():
    return {
        "sessions":             s.airtable_get("Sessions"),
        "students":             s.airtable_get("Students"),
        "caterers":             s.airtable_get("Caterers"),
        "menu_items":           s.airtable_get("Menu Items"),
        "dietary_restrictions": s.airtable_get("Dietary Restrictions"),
        "absences":             s.airtable_get("Absences"),
        "exclusions":           s.airtable_get("Exclusions"),
        "weekly_orders":        s.airtable_get("Weekly Orders"),
        "orders":               s.airtable_get("Orders"),
    }


def build_lookups(data):
    lk = {}
    lk["session_by_id"]   = {r["id"]: r["fields"] for r in data["sessions"]}
    lk["student_by_id"]   = {r["id"]: r["fields"] for r in data["students"]}
    lk["caterer_by_id"]   = {r["id"]: r["fields"] for r in data["caterers"]}
    lk["menu_item_by_id"] = {r["id"]: r["fields"] for r in data["menu_items"]}
    lk["dietary_name_by_id"] = {
        r["id"]: r["fields"].get("Restriction Name", "")
        for r in data["dietary_restrictions"]
    }
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
    return lk


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def expected_eating_count(sess_rec, session_date, lk):
    """Count enrolled students at this session who are not absent, excluded, or opted out."""
    sess_id     = sess_rec["id"]
    sess_fields = sess_rec["fields"]
    count = 0
    for stu in lk["students_by_session"].get(sess_id, []):
        stu_id     = stu["id"]
        stu_fields = stu["fields"]
        if (stu_id, sess_id) in lk["absent_pairs"]:
            continue
        if is_student_excluded(stu_fields, sess_fields, session_date, lk):
            continue
        dietary_names = resolve_dietary_names(
            stu_fields.get("Dietary Requirements"), lk["dietary_name_by_id"]
        )
        if "Opted out of Catering" in dietary_names:
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Check 1: Min-qty per caterer
# ---------------------------------------------------------------------------

def check_min_qty(data, lk, week_dates):
    s.log.info("\n--- Min-Qty Enforcement ---")
    next_monday = week_dates["Monday"].isoformat()
    week_date_strs = {d.isoformat() for d in week_dates.values()}

    # wo_id → item_id → total quantity (next week only)
    orders_by_wo = defaultdict(lambda: defaultdict(int))
    for order in data["orders"]:
        if order["fields"].get("Date") not in week_date_strs:
            continue
        item_id  = (order["fields"].get("Menu Item") or [None])[0]
        quantity = order["fields"].get("Quantity", 0)
        if not item_id:
            continue
        for wo_id in (order["fields"].get("Weekly Order") or []):
            orders_by_wo[wo_id][item_id] += quantity

    errors = 0
    checked = 0
    for wo in data["weekly_orders"]:
        if wo["fields"].get("Week Start") != next_monday:
            continue
        wo_label   = wo["fields"].get("Order ID", wo["id"])
        caterer_id = (wo["fields"].get("Caterer") or [None])[0]
        caterer_fields = lk["caterer_by_id"].get(caterer_id, {})

        item_totals = orders_by_wo.get(wo["id"], {})
        num_items   = len(item_totals)
        min_qty     = _find_min_qty(caterer_fields, num_items)

        if min_qty is None:
            s.log.info(f"  '{wo_label}': {num_items} item(s) — no min-qty constraint applies.")
            checked += 1
            continue

        violating = [(iid, cnt) for iid, cnt in item_totals.items() if cnt < min_qty]
        if not violating:
            s.log.info(f"✓ '{wo_label}': {num_items} items, all ≥ {min_qty} per item.")
            checked += 1
        else:
            for iid, cnt in violating:
                item_name = lk["menu_item_by_id"].get(iid, {}).get("Menu Item Name", "?")
                s.log.error(
                    f"✗ '{wo_label}': '{item_name}' has {cnt} (needs ≥ {min_qty} "
                    f"with {num_items} distinct items)."
                )
                errors += 1

    s.log.info(f"Checked {checked} Weekly Order(s); {errors} min-qty violation(s).")
    return errors


# ---------------------------------------------------------------------------
# Check 2: Session totals match eating-student counts
# ---------------------------------------------------------------------------

def check_session_totals(data, lk, week_dates):
    s.log.info("\n--- Session Order Totals ---")
    week_date_strs = {d.isoformat() for d in week_dates.values()}

    orders_by_session = defaultdict(int)
    for order in data["orders"]:
        if order["fields"].get("Date") not in week_date_strs:
            continue
        sess_id  = (order["fields"].get("Session") or [None])[0]
        quantity = order["fields"].get("Quantity", 0)
        if sess_id:
            orders_by_session[sess_id] += quantity

    errors = 0
    checked = 0
    for sess in data["sessions"]:
        day = sess["fields"].get("Day")
        if day not in week_dates:
            continue
        sess_id      = sess["id"]
        session_date = week_dates[day]
        sess_label   = sess["fields"].get("Session ID", sess_id)

        expected = expected_eating_count(sess, session_date, lk)
        actual   = orders_by_session.get(sess_id, 0)

        if expected == actual:
            s.log.info(f"✓ '{sess_label}' ({day}): {actual} meals (expected {expected}).")
            checked += 1
        else:
            s.log.error(
                f"✗ '{sess_label}' ({day}): {actual} meals, expected {expected} "
                f"(diff {actual - expected:+d})."
            )
            errors += 1

    s.log.info(f"Checked {checked + errors} session(s); {errors} mismatch(es).")
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    s.log.info("=== ORDER CONSTRAINTS TEST ===")
    week_dates = get_next_week_dates()
    s.log.info(f"Testing week of {week_dates['Monday'].isoformat()}")

    data = load_data()
    lk   = build_lookups(data)

    err_minqty  = check_min_qty(data, lk, week_dates)
    err_session = check_session_totals(data, lk, week_dates)

    total = err_minqty + err_session
    s.log.info("\n=== SUMMARY ===")
    s.log.info(f"Min-qty violations:       {err_minqty}")
    s.log.info(f"Session total mismatches: {err_session}")
    if total == 0:
        s.log.info("🎉 All order constraints passed!")
    else:
        s.log.error(f"❌ {total} issue(s) found.")
    return total


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() == 0 else 1)
