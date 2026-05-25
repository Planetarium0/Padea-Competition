# 12 — "Sent" Weekly Order status is misleading

**Severity:** Low.
**File:** `scripts/actions/send_orders.py` (lines 309–311).

```python
s.get_table("Weekly Orders").update(wo_record["id"], {"Status": "Sent"})
s.log.info(f"Marked '{wo_id_label}' as Sent.")
```

`send_orders.py` flips a Weekly Order to `Status='Sent'` as soon as it
has queued the corresponding row in `Scheduled Emails`. The actual
send is done later by an Airtable automation watching the
`Scheduled Emails.Status='Queued'` rows.

So:

- Queueing succeeded, the email send later failed → Scheduled Email is
  `Failed`, but the Weekly Order is still `Sent`.
- Operator looking at Weekly Orders thinks the caterer received the
  email when they didn't.

### Fix

Either:

- Use `Queued` (and `Failed` / `Sent`) as the Weekly Order statuses too,
  mirroring the Scheduled Email's status (e.g. via an Airtable formula
  that rolls up the latest Scheduled Email's status onto the parent).
- Add `Queued` as a Weekly Orders.Status choice, set it after queueing,
  let the Airtable automation flip Weekly Orders to `Sent` after a
  successful send.
