# 30 — `EmailStatus` literal advertises `Send Immediately` but the schema doesn't

**Severity:** Medium (will fail at runtime under the documented flag).
**Files:** `scripts/support/records.py`, `scripts/actions/send_orders.py`,
`data/schema.py`.

`scripts/support/records.py`:

```python
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
```

`scripts/actions/send_orders.py → schedule_email`:

```python
fields["Status"] = "Send Immediately" if immediate else "Queued"
```

But `data/schema.py → Scheduled Emails.Status`:

```python
"options": {
    "choices": [
        {"name": "Queued"},
        {"name": "Sent"},
        {"name": "Failed"},
    ]
},
```

The singleSelect doesn't accept `Send Immediately`. Any path that passes
`immediate=True` (e.g. `./run forms send parents --immediate`,
`./run caterer evaluate --immediate`,
`./run forms qr send --immediate`) will hit an Airtable
INVALID_SELECT_VALUE error on the write.

### Fix

Add `Send Immediately` to the `Scheduled Emails.Status` choices in
`data/schema.py` (and run `./run migrate schema` to push it), or drop
the literal from `EmailStatus` and have `--immediate` set some other
field (e.g. `Send Date = today`, or a new boolean `Send Immediately`).

The Airtable automation rules need to be updated either way so that
`Send Immediately` rows don't sit waiting for a cron tick.
