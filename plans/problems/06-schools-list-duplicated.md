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

### Fix

Move the canonical list (and region mapping) into
`scripts/data/schools_data.py` or similar. Have every migration import
it. For the keyword aliases, a single shared `resolve_school(raw_str)`
helper avoids further drift.
