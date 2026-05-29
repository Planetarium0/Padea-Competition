# 18 — `diet` migration resource is undocumented

**Severity:** Low.
**Files:** `CLAUDE.md`, `./run` (help text).

The `./run` script accepts a `diet` resource that runs
`migrations/dietary_restrictions.py`:

```bash
declare -A RES_MAP=(
    [diet]="dietary_restrictions.py"
    ...
)
```

But:

- `CLAUDE.md` documents:
  `# Migrate a single resource (caterers, contacts, menus, sessions, students, absences, exclusions)`
  — `diet` is missing.
- The `./run help` `usage()` block lists no resources at all (just
  refers to the migration command).

This means an operator following the docs won't know they can migrate
the dietary restrictions table independently.

### Fix

- Add `diet` to the CLAUDE.md command list.
- Have `./run help` list the resources from `RES_MAP` programmatically
  rather than maintaining the list in two places.
