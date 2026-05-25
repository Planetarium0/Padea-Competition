# 03 — `verify_migration.py` checks tables that no longer exist

**Severity:** High (verification is silently passing).
**File:** `scripts/tests/verify_migration.py`.

The verifier's table list still says:

```python
tables_to_check = [
    "Schools", "On-Site Managers", "Caterers", "Menu Items",
    "Dietary Restrictions", "Students", "Sessions", "Absences",
    "Exclusions", "Meal Feedback",   # <-- table no longer exists
    "Orders",
]
```

The `Meal Feedback` table was renamed to `Caterer Feedback` in commit
`25d2900` ("Changed the star rating to rate the caterer instead of the
meal, renaming the schema table…"). The verifier still asks for the old
name — Airtable will return `[]`, the log will record "Table 'Meal
Feedback': 0 records" without raising, and the count is never checked.

Several other current tables are completely absent from the check:

- `Caterer Feedback` (replacement for Meal Feedback)
- `Weekly Orders`
- `Scheduled Emails`

The `Dietary Restrictions` table is in the list but isn't audited — no
check that the 15 expected records are present, no check that the
`Supersets` self-link is populated.

### Fix

- Drop `Meal Feedback` from `tables_to_check`; add `Caterer Feedback`,
  `Weekly Orders`, `Scheduled Emails`.
- Add an audit step that confirms `Dietary Restrictions` has every name
  in `all_restriction_names()` and that the `Supersets` links match
  `DIETARY_HIERARCHY`.
