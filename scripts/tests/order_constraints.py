"""
order_constraints.py — Verify that registered Orders for next week:
  1. Satisfy each caterer's Min Qty N Items constraint (per-caterer totals).
  2. Match the expected eating-student count per session (enrolled minus
     absent, excluded, opted-out).

Run after ./run orders generate.

Usage:
  python scripts/tests/order_constraints.py
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from actions.orders.register_orders import (
    OrderingData,
    OrderingIndex,
    _find_min_qty,
    get_next_week_dates,
    is_student_excluded,
)
from support import (
    Database,
    OrderFields,
    Record,
    SessionFields,
    WeeklyOrderFields,
    log,
)
from support.compatibility import has_opted_out


# ---------------------------------------------------------------------------
# Snapshot bundle — extends the runtime OrderingData with the Weekly Orders
# and Orders tables we're checking.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConstraintsData:
    base:          OrderingData
    weekly_orders: list[Record[WeeklyOrderFields]]
    orders:        list[Record[OrderFields]]

    @classmethod
    def load(cls, db: Database) -> "ConstraintsData":
        return cls(
            base=          OrderingData.load(db),
            weekly_orders= db.WeeklyOrders.all(),
            orders=        db.Orders.all(),
        )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

def expected_eating_count(
    sess_rec:     Record[SessionFields],
    session_date: date,
    index:        OrderingIndex,
) -> int:
    """Count enrolled students at this session who are not absent, excluded, or opted out."""
    count = 0
    for stu in index.students_by_session.get(sess_rec.id, []):
        if (stu.id, sess_rec.id) in index.absent_pairs:
            continue
        if is_student_excluded(stu.fields, sess_rec.fields, session_date, index):
            continue
        if has_opted_out(stu.fields.get("dietary_requirement_ids"), index.dietary_hierarchy):
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Check 1: Min-qty per caterer
# ---------------------------------------------------------------------------

def check_min_qty(
    data:       ConstraintsData,
    index:      OrderingIndex,
    week_dates: dict[str, date],
) -> int:
    log.info("\n--- Min-Qty Enforcement ---")
    next_monday = week_dates["Monday"].isoformat()
    week_date_strs = {d.isoformat() for d in week_dates.values()}

    # wo_id → item_id → total quantity (next week only)
    orders_by_wo: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for order in data.orders:
        if order.fields.get("date") not in week_date_strs:
            continue
        item_id  = order.fields.get("menu_item_id")
        quantity = order.fields.get("quantity", 0)
        if not item_id:
            continue
        wo_id = order.fields.get("weekly_order_id")
        if wo_id:
            orders_by_wo[wo_id][item_id] += quantity

    errors  = 0
    checked = 0
    for wo in data.weekly_orders:
        if wo.fields.get("week_start") != next_monday:
            continue
        wo_label   = wo.fields.get("order_code", wo.id)
        caterer_id = wo.fields.get("caterer_id")
        caterer_fields = index.caterer_by_id.get(caterer_id, {}) if caterer_id else {}

        item_totals = orders_by_wo.get(wo.id, {})
        num_items   = len(item_totals)
        min_qty     = _find_min_qty(caterer_fields, num_items)

        if min_qty is None:
            log.info(f"  '{wo_label}': {num_items} item(s) — no min-qty constraint applies.")
            checked += 1
            continue

        violating = [(iid, cnt) for iid, cnt in item_totals.items() if cnt < min_qty]
        if not violating:
            log.info(f"✓ '{wo_label}': {num_items} items, all ≥ {min_qty} per item.")
            checked += 1
        else:
            for iid, cnt in violating:
                item_name = index.menu_item_by_id.get(iid, {}).get("name", "?")
                log.error(
                    f"✗ '{wo_label}': '{item_name}' has {cnt} (needs ≥ {min_qty} "
                    f"with {num_items} distinct items)."
                )
                errors += 1

    log.info(f"Checked {checked} Weekly Order(s); {errors} min-qty violation(s).")
    return errors


# ---------------------------------------------------------------------------
# Check 2: Session totals match eating-student counts
# ---------------------------------------------------------------------------

def check_session_totals(
    data:       ConstraintsData,
    index:      OrderingIndex,
    week_dates: dict[str, date],
) -> int:
    log.info("\n--- Session Order Totals ---")
    week_date_strs = {d.isoformat() for d in week_dates.values()}

    orders_by_session: dict[str, int] = defaultdict(int)
    for order in data.orders:
        if order.fields.get("date") not in week_date_strs:
            continue
        sess_id  = order.fields.get("session_id")
        quantity = order.fields.get("quantity", 0)
        if sess_id:
            orders_by_session[sess_id] += quantity

    errors  = 0
    checked = 0
    for sess in data.base.sessions:
        day = sess.fields.get("day")
        if day not in week_dates:
            continue
        session_date = week_dates[day]
        sess_label   = sess.fields.get("session_code", sess.id)

        expected = expected_eating_count(sess, session_date, index)
        actual   = orders_by_session.get(sess.id, 0)

        if expected == actual:
            log.info(f"✓ '{sess_label}' ({day}): {actual} meals (expected {expected}).")
            checked += 1
        else:
            log.error(
                f"✗ '{sess_label}' ({day}): {actual} meals, expected {expected} "
                f"(diff {actual - expected:+d})."
            )
            errors += 1

    log.info(f"Checked {checked + errors} session(s); {errors} mismatch(es).")
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(db: Database | None = None) -> int:
    db = db or Database.from_env()
    log.info("=== ORDER CONSTRAINTS TEST ===")
    week_dates = get_next_week_dates()
    log.info(f"Testing week of {week_dates['Monday'].isoformat()}")

    data  = ConstraintsData.load(db)
    index = OrderingIndex.build(data.base)

    err_minqty  = check_min_qty(data, index, week_dates)
    err_session = check_session_totals(data, index, week_dates)

    total = err_minqty + err_session
    log.info("\n=== SUMMARY ===")
    log.info(f"Min-qty violations:       {err_minqty}")
    log.info(f"Session total mismatches: {err_session}")
    if total == 0:
        log.info("All order constraints passed!")
    else:
        log.error(f"{total} issue(s) found.")
    return total


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() == 0 else 1)
