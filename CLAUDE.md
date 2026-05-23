# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

This project is part of a larger set of projects aimed at fixing bottlenecks in a tutoring business (Padea).
Schools partner with Padea to run weekly, small-group tutoring sessions on their campus after hours. Families enrol at the start of each term, so largely the same students attend every session that term (ignoring absences and rare mid-term enrolments). Each session includes a restaurant-catered dinner break in the middle.
Padea contracts external caterers to cook and deliver individually boxed meals (one per student) to each session. The order should arrive 5–10 minutes before the dinner break so the on-site manager can set up the meals with the delivery driver’s help.
The on-site manager may collect feedback and share it with us. The on-site manager is usually the same on a given day at a given school each week (e.g. Mondays at ACME School), though this can change on one-off occasions. The caterer may contact the on-site manager’s mobile to confirm arrival, report being late, or ask for help finding the
session location (building and room).
Each Thursday, our program coordinator emails each caterer an order for the following week’s meals, picking a few items off the caterer’s menu and making an educated guess at the best meals and quantities of each meal.
Students often tell us the selected meals don’t match their taste preferences. Food quality also tends to decline over time with each caterer. Ordering meals is tedious for the program coordinator – and will become a bottleneck for the business.
The planned fix for this bottleneck is for students to be able to record feedback on their meals (1-5 star rating) and also choose the meals for next week.

This project is aimed at fixing this bottleneck - solving the problem from order to delivery.

## Commands

```bash
# Migrate all resources
./run migrate

# Migrate a single resource (caterers, contacts, menus, sessions, students, absences, exclusions)
./run migrate caterers

# Initialize / sync Airtable schema (idempotent — run before first migration)
./run schema update

# Verify post-migration record counts and relational integrity
./run script verify_migration
```

## Environment setup

`.env` (not committed) must contain:
```
AIRTABLE_API_KEY=...
AIRTABLE_ID=...
# Optional — enables LLM-based extraction; falls back to heuristics if absent
CLAUDE_CODE_API_KEY=...
# or ANTHROPIC_API_KEY=...
```

## Architecture

### Data flow

```
resources/*.xlsx + resources/*.pdf
        ↓ (cache_pdf.py extracts PDF → txt)
cache/*.txt  +  cache/dietary_mappings.json
        ↓ (migrations/*.py)
Airtable (10 tables, fully relational)
```

### Core modules

**`scripts/support.py`** — imported as `s` by every migration script. Provides:
- `s.log` — standard logger
- `s.get_table(name)`, `s.airtable_get(name, formula)`, `s.airtable_post(name, records)`, `s.clear_table(name)`
- `s.ask_llm(prompt)` — calls Claude API if key present, else opens Tkinter GUI (`prompt_user.py`) for manual entry

**`scripts/schema.py`** — single source of truth: `TABLES_SCHEMA` dict describes all 10 Airtable tables (fields, types, relational links).

**`scripts/update_schema.py`** — idempotent schema sync: creates missing tables with only the primary key first, then adds all other fields (including `multipleRecordLinks`). This two-pass approach resolves circular link dependencies.

### Migration pattern

Each `migrations/*.py` script follows the same pattern:
1. `s.clear_table(...)` — wipe the target table(s) for a clean, repeatable run
2. Parse source data from `resources/` or `cache/`
3. LLM extraction via `s.ask_llm()` (JSON output expected) with a local heuristic fallback
4. Lookup already-migrated records by name to get Airtable record IDs for `multipleRecordLinks` fields
5. `s.airtable_post(...)` — batch-insert in groups of 10

### Migration order matters

Dependencies flow in this order — run `caterers` before `contacts`/`menus`, `sessions` before `students`/`absences`/`exclusions`:

```
caterers → caterer_contacts → caterer_menus
sessions → students → absences → exclusions
```

`./run migrate` runs all scripts via glob (`migrations/*.py`) — alphabetical order currently satisfies these dependencies.

### LLM fallback behaviour

- With `CLAUDE_CODE_API_KEY` / `ANTHROPIC_API_KEY`: uses `claude-3-5-sonnet-latest` for structured JSON extraction
- Without a key: heuristic regex parsers handle most cases; `prompt_user.py` pops a Tkinter window for unresolvable cases
- `cache/dietary_mappings.json` caches per-student dietary string translations to avoid repeated LLM calls

### Airtable record linking

Migrations that create records with relational fields must first fetch the already-inserted target table and build a `{name: id}` dict. Record IDs (not names) go into `multipleRecordLinks` fields as arrays, e.g. `"Caterer": [caterer_id]`.
