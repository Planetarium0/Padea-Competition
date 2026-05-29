# Migration Pipeline

One-shot import of business data from spreadsheets and PDFs into a clean
Airtable base. Every migration script:

1. **Clears** its target table(s) (`s.clear_table(...)`).
2. Parses source data from `resources/` or `cache/`.
3. Tries an **LLM extraction** via `s.ask_llm(...)`; falls back to a
   regex/heuristic parser if no API key.
4. **Resolves linked-record IDs** by name from any already-migrated parent tables.
5. **Inserts** in batches of 10 (Airtable's per-call cap).

## Source files

| File | Format | Migrates into |
|---|---|---|
| `resources/sessions.xlsx` | Excel | Schools, On-Site Managers, Sessions |
| `resources/caterers.xlsx` | Excel | Caterers |
| `resources/students.xlsx` | Excel (multi-sheet) | Students |
| `resources/caterer-contacts.pdf` → `cache/caterer-contacts.txt` | PDF text | Caterers (contact fields) |
| `resources/caterer-menus.pdf` → `cache/caterer-menus.txt` | PDF text | Caterers (pricing) + Menu Items |
| `resources/absences.pdf` → `cache/absences.txt` | PDF text | Absences |
| `resources/exclusions.pdf` → `cache/exclusions.txt` | PDF text | Exclusions |

PDFs are pre-extracted to plain text by `scripts/actions/cache_pdf.py`
(uses `pypdf`).

## Migration order (load-bearing)

`./run migrate` delegates to `scripts/migrations/migrate.py`, which calls each
script's `run()` function in explicit dependency order:

```
dietary_restrictions       # (no deps) — full restriction hierarchy
schools                    # (no deps) — seeded from sessions.xlsx
caterers                   # (no deps)
caterer_contacts           # ← caterers, schools
caterer_menus              # ← caterers, dietary_restrictions
sessions                   # ← schools, caterers; also seeds On-Site Managers
students                   # ← sessions, schools, dietary_restrictions
absences                   # ← students, sessions
exclusions                 # ← schools
```

Individual scripts can still be run standalone for targeted reruns.

## LLM-extracted fields

Three migrations call `s.ask_llm()` with a JSON-mode prompt:

- `caterer_contacts.py` — extracts contact name/email/chef per caterer.
- `caterer_menus.py` — extracts menu items, prices, dietary codes.
- `exclusions.py` — extracts date + school + affected year levels + reason
  from free-text paragraphs.

Each has a regex/keyword fallback for the no-key case. `students.py` uses a
comma-split + case-insensitive exact-match heuristic; unrecognised parts are
logged as errors (no LLM call).

## Verification

The standalone `verify_migration.py` (record counts + orphan walker) has
been retired and now lives under `old/`. Post-migration sanity is mostly
covered by the unit-test suite (`./run test`) plus the live integration
check `python scripts/tests/order_constraints.py` for order rounds.
A fresh row-count audit would be a small, useful add-back — but the
current code doesn't ship one.

## Re-running migrations

Every migration is idempotent in the sense that it **clears its tables
first**. Re-running `./run migrate students` will delete and recreate all
~320 student records, breaking any links that other tables held to them.

This is fine for fresh-import workflows but means **migrations cannot be
used to incrementally add a new student mid-term** — that would require
either a different code path or just direct Airtable edits in the UI.

The same applies to `Sessions`, `Absences`, `Exclusions`, `Caterers` and
`Menu Items`. The post-launch workflow assumes operators edit data in
Airtable directly.
