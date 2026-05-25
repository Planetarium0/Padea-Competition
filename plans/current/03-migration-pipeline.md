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
| `resources/caterers.xlsx` | Excel | Schools (seeded), Caterers |
| `resources/sessions.xlsx` | Excel | On-Site Managers, Sessions |
| `resources/students.xlsx` | Excel (multi-sheet) | Students |
| `resources/caterer-contacts.pdf` → `cache/caterer-contacts.txt` | PDF text | Caterers (contact fields) |
| `resources/caterer-menus.pdf` → `cache/caterer-menus.txt` | PDF text | Caterers (pricing) + Menu Items |
| `resources/absences.pdf` → `cache/absences.txt` | PDF text | Absences |
| `resources/exclusions.pdf` → `cache/exclusions.txt` | PDF text | Exclusions |

PDFs are pre-extracted to plain text by `scripts/actions/cache_pdf.py`
(uses `pypdf`).

## Migration order (load-bearing)

`./run migrate` runs every script in `scripts/migrations/`. The order is
alphabetical, but with `dietary_restrictions.py` forcibly bumped to first
(see the `./run` script). This satisfies all dependencies:

```
dietary_restrictions       # static hierarchy; needed by students + menus
caterers                   # also seeds Schools
caterer_contacts           # patches Caterers
caterer_menus              # needs Caterers + Dietary Restrictions
sessions                   # also creates On-Site Managers; needs Schools + Caterers
students                   # needs Sessions + Dietary Restrictions
absences                   # needs Students + Sessions
exclusions                 # needs Schools
```

## Schools are not their own migration

`Schools` is a static seeded list of six names + regions embedded inside
`migrations/caterers.py` (the `SCHOOLS_DATA` dict). Same list is duplicated as
`SCHOOLS_DATA` in `students.py` and `SCHOOLS_LIST` in `exclusions.py`.
(See `plans/problems/`.)

## LLM-extracted fields

Three migrations call `s.ask_llm()` with a JSON-mode prompt:

- `caterer_contacts.py` — extracts contact name/email/chef per caterer.
- `caterer_menus.py` — extracts menu items, prices, dietary codes.
- `exclusions.py` — extracts date + school + affected year levels + reason
  from free-text paragraphs.
- `students.py` — translates raw dietary strings to standardised tag arrays
  (cached in `cache/dietary_mappings.json` so reruns skip the call).

Each has a regex/keyword fallback for the no-key case. The Kenko Sushi House
"Big Mom (main point of contact and chef)" case is handled correctly by the
LLM but the heuristic fallback leaves `Contact Name` blank.

## Dietary mappings cache

`cache/dietary_mappings.json` maps every raw spreadsheet dietary string ever
seen (e.g. `"No Beef, No Pork"`) to a list of standard restriction names.
This is *append-only* across runs: missing entries are added by LLM (or
heuristic), existing entries are reused. Edit by hand to override.

The full taxonomy is in `scripts/data/dietary_data.py` —
`STANDARD_DIETARY_CHOICES` in `migrations/students.py` is a **subset** of
that, missing `Vegan`, `Kosher`, `Pescatarian`, `No Lamb`. (See problems.)

## Verification

```bash
./run script verify_migration   # (but see operational-commands — path bug)
python scripts/tests/verify_migration.py
```

The verifier counts records, asserts hard limits (6 schools, 4 caterers),
and walks linked-record fields looking for orphans. It logs `errors`
(structural problems) and `warnings` (data-quality issues) separately.

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
