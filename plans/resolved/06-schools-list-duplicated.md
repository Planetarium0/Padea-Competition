# 06 — Schools list duplicated in three places

**Severity:** Medium (correctness depends on three independent edits staying in sync).
**Files:** `scripts/migrations/caterers.py`, `scripts/migrations/students.py`,
`scripts/migrations/exclusions.py`.

The six-school roster appears as a hard-coded constant in three places:

- `caterers.py → SCHOOLS_DATA` (name → region map; seeds the Schools table).
- `students.py → SCHOOLS_DATA` (name list; used to resolve sheet header
  names to canonical school names).
- `exclusions.py → SCHOOLS_LIST` (name list; used to match free-text school
  mentions during heuristic parsing).

Adding or renaming a school requires editing all three. Forgetting one
means students at the new school will silently fail to migrate, or
exclusions will fail to attach.

Same applies to `caterer_contacts.py → SCHOOL_MAP`, which has a similar
keyword-to-canonical-name lookup with extra aliases (`"Moreton Bay Boys
College"` without apostrophe, etc.).

### Resolution

Removed all hardcoded lists. `schools.py` (new) seeds the Schools table by
reading unique school names and regions directly from `resources/sessions.xlsx`.
All other migrations (`students.py`, `exclusions.py`, `caterer_contacts.py`)
now fetch canonical school names from the already-migrated Schools table via
`s.airtable_get("Schools")`. Fuzzy matching (apostrophe-strip + bidirectional
substring) is done locally in each script's `_resolve_school` helper.

Every migration script was also wrapped in a `run()` function and a
`migrate.py` orchestrator was created to call them in explicit dependency order.
