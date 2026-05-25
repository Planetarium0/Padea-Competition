# 15 — No path for incremental data updates

**Severity:** Medium (will hurt as soon as the term changes).
**Files:** every script in `scripts/migrations/`.

Each migration starts with `s.clear_table(...)` for its target tables.
There is no codepath that does:

- "Add this one new student" → keep the existing 320, append one.
- "End-of-term reset" → keep `Caterers`, `Menu Items`, `Schools`,
  `Dietary Restrictions`; wipe `Students`, `Sessions`, `Absences`,
  `Exclusions`, all order tables.
- "This caterer changed their menu" → diff against current Menu Items
  rather than clear-and-reinsert (re-inserting breaks every existing
  `Meal Preference` link).

Today, the operator workflow when something changes is **edit Airtable
directly in the UI**. Migrations can never be re-run after the first
day of business.

For some tables this matters more than others. The most painful one is
`Menu Items`: clearing and re-inserting breaks every student's saved
`Meal Preference` because the linked record IDs change.

### Fix

Make migrations idempotent by *upsert* rather than *clear-then-insert*:

- Look up the existing record by natural key (e.g. Menu Item Name +
  Caterer).
- Patch the existing record if found; create otherwise.
- Optionally, mark missing-from-source records with a flag so the
  operator can review for deletion.

Lower effort: at minimum, add a flag (`--clear`) that the operator
*opts into*, and have the default behaviour refuse to run if any of
the target tables already has records.
