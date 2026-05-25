# 23 — `order_constraints.py` re-implements `build_lookups`

**Severity:** Low (maintenance burden).
**Files:** `scripts/actions/register_orders.py`,
`scripts/tests/order_constraints.py`.

`order_constraints.py` imports `is_student_excluded`,
`resolve_dietary_names`, `_find_min_qty`, and `get_next_week_dates`
from `register_orders.py` — good. But it then defines its own
`build_lookups` separately, populating only the subset of keys it
needs.

The two implementations have to agree on:

- How absences are keyed (`(student_id, session_id)` tuple).
- How `Dietary Requirements` IDs are resolved to names.
- Which restriction names short-circuit (only `Opted out of Catering`).

When `register_orders.py`'s lookup adds a new key, `order_constraints.py`
silently won't have it. The test passes against a buggy register because
both halves drift in tandem.

### Fix

Export `build_lookups` from `register_orders.py` (or pull both into a
shared module under `scripts/data/`) and import from one source.
Alternatively, have `order_constraints.py` call
`register_orders.build_lookups` directly even though it loads more data
than the constraints check needs — the cost is small.
