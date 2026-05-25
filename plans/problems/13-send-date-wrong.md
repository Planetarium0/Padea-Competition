# 13 — `Send Date` on Scheduled Emails equals the meal week's Monday

**Severity:** Low (acknowledged TODO in source).
**File:** `scripts/actions/send_orders.py` (line 299).

```python
send_date = week_start  # Thursday send → Monday week start; adjust if needed
```

`Week Start` is the Monday of the *meal* week — the orders are *for*
that week. But the email should be sent ~Thursday of the **previous**
week, when `send_orders.py` itself runs.

So if the Airtable automation honours `Send Date` as a "don't send
before" gate, the email goes out late (on Monday of the meal week
itself) instead of the prior Thursday afternoon.

If the automation ignores `Send Date` and sends immediately on queue,
the field is just unused.

### Fix

Set `send_date` to "now" (or yesterday — whatever the automation
treats as "send ASAP") rather than the meal week's start. Or rename
the field to "Send Not Before" or "Meal Week" depending on intent.
