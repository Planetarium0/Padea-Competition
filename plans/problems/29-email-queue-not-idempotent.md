# 29 — Outbound email queueing is not idempotent

**Severity:** Medium.
**Files:** `scripts/actions/send_orders.py`,
`scripts/actions/send_meals_links.py`, `scripts/actions/send_qr_emails.py`,
`scripts/actions/evaluate_caterers.py`.

Every "queue an email" script does the same shape of thing:

```python
schedule_email(
    db,
    to_email=...,
    subject=...,
    body=...,
    email_id=f"EMAIL-{week_start}-{wo_record.id[:8]}",   # or similar
    ...
)
```

`schedule_email` always *creates* a new `Scheduled Emails` row — it never
checks whether a row with the same `Email ID` (or pointing at the same
Weekly Order / Proposal / Student) already exists. So:

- `./run orders send` twice in a row queues two of every order email.
- `./run caterer evaluate` re-running creates a second proposal +
  alert email per session-caterer pair (the proposal de-dup catches
  the proposal, but only on the second run — the *first* run after a
  reset would queue both).
- `./run forms send parents` always re-queues for everyone.

The Airtable automation then sends every queued row, so duplicates land
in real inboxes.

### Fix

Before inserting, query `Scheduled Emails` for the deterministic
`Email ID` (or for `Weekly Order` / `Caterer Switch Proposal` link +
`Status='Queued'`):

```python
existing = db.ScheduledEmails.all(formula=f"{{Email ID}}='{email_id}'")
if existing:
    log.info(f"Already queued: {email_id} — skipping")
    return
```

The Order-side IDs (`EMAIL-<date>-<wo_id[:8]>`,
`SWITCH-PROP-...`, `WATCH-...`, `NOCAND-...`) are already
deterministic per Weekly Order / proposal / day; the parent / student
links append `int(time.time())` and need to drop that suffix to make
the check work.
