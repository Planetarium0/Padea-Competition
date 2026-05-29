# 31 — `send_orders.py` processes every Weekly Order with `Week Start >= TODAY()`

**Severity:** Low (rare in practice, painful when it bites).
**File:** `scripts/actions/send_orders.py`, `load_pending_orders`.

```python
def load_pending_orders(db: Database) -> list[Record[WeeklyOrderFields]]:
    orders = db.WeeklyOrders.all(formula="{Week Start} >= TODAY()")
    log.info(f"Found {len(orders)} Weekly Orders")
    return orders
```

The filter is `Week Start >= today`, not `Week Start == next_monday`.
That means:

- If `register_orders.py` is run twice in a row (e.g. once on Wednesday
  for next week, again on Friday for the *following* week), Thursday's
  `send_orders.py` will queue both weeks' emails.
- A stale Weekly Order created weeks ago and never sent will sit in the
  table forever and re-queue on every `./run orders send` run.

This compounds with [#29](29-email-queue-not-idempotent.md) — the same
two-week-ahead Weekly Order will be re-queued every Thursday until its
`Week Start` is in the past.

### Fix

Narrow the filter to "Monday of next week":

```python
next_monday = get_next_week_dates()["Monday"].isoformat()
orders = db.WeeklyOrders.all(
    formula=f"{{Week Start}} = '{next_monday}'",
)
```

Or, more conservatively, restrict to a single week window
`[next_monday, next_monday + 4]` so the script handles an order that
was generated a few days early without grabbing one generated a month
ahead.
