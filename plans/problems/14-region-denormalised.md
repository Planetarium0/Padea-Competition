# 14 — `Region` denormalised across three tables

**Severity:** Low (data redundancy; not currently causing bugs).
**File:** `data/schema.py`.

The same `Region` `singleSelect` choices (Redlands, South Brisbane, West
Brisbane, Central Brisbane) appear three times:

- `Schools.Region`
- `Caterers.Region`
- `Sessions.Region`

The Schools value is the source of truth; the other two are
denormalised copies. The migration scripts set them independently —
nothing currently enforces they stay in sync (e.g. if Loreto College's
region is corrected in `Schools`, the corresponding `Sessions` and any
caterer `Region` won't auto-update).

The `Sessions.Region` migration also reads directly from `sessions.xlsx`
rather than from the linked school, so a typo in the spreadsheet
diverges silently from the Schools record.

### Fix

In Airtable, replace `Sessions.Region` and `Caterers.Region` with a
*lookup* field (`Region from School` / `Region from Serves Schools`).
That removes the singleSelect choices and the migration write step.

If keeping the explicit field for filtering convenience, add a
validation step in `verify_migration.py` that walks Sessions and
Caterers and warns when the value diverges from the linked school.
