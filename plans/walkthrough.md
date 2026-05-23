# Migration Walkthrough — Padea Data to Airtable

## Overview

This walkthrough documents the end-to-end process of migrating Padea's tutoring and catering data from flat Excel spreadsheets and unstructured PDFs into a fully relational Airtable database.

**Source files:**
| File | Format | Contents |
|---|---|---|
| `resources/caterers.xlsx` | Excel | Caterer names, regions, minimum order quantities |
| `resources/sessions.xlsx` | Excel | Weekly sessions per school, caterer assignments, on-site managers |
| `resources/students.xlsx` | Excel (multi-sheet) | Student enrolment list, one sheet per school/day |
| `resources/caterer-contacts.pdf` | PDF → `cache/caterer-contacts.txt` | Contact and chef details for each caterer |
| `resources/caterer-menus.pdf` | PDF → `cache/caterer-menus.txt` | Menu items, pricing, delivery fees |
| `resources/absences.pdf` | PDF → `cache/absences.txt` | Student absences grouped by session |
| `resources/exclusions.pdf` | PDF → `cache/exclusions.txt` | Cancelled sessions with free-text reasons |

PDFs were pre-extracted to plain text via `scripts/cache_pdf.py` and stored in `cache/`.

---

## Schema Design

The database was normalised into 10 tables rather than duplicating the flat spreadsheet structure. Key design decisions:

- **Schools** and **On-Site Managers** are independent tables. Both appeared as repeated text in the source data; extracting them as first-class entities lets Sessions link to them cleanly and avoids update anomalies.
- **Menu Items** are linked to Caterers (not embedded as text), allowing future Meal Feedback and Meal Selections tables to link to individual dishes.
- **Meal Feedback** and **Meal Selections** are included in the schema (currently empty) to support the planned student-ordering feature.
- Session IDs are natural keys in the format `"<School Name> - <YYYY-MM-DD>"`, matching the format used across Absences and Exclusions.

```
Schools ──< Sessions >── Caterers ──< Menu Items
  └──< Students >── Sessions ──< Absences
                              └──< Exclusions (via School)
```

To resolve circular `multipleRecordLinks` dependencies during schema creation, `update_schema.py` uses a two-pass approach: first create all tables with only their primary key field, then add all remaining fields once every table ID is known.

---

## Step-by-Step Migration

### 1. Schema initialisation (`./run schema update`)

`update_schema.py` runs idempotently — it fetches existing tables, creates any that are missing (primary key only), then adds all remaining fields. Relational fields (`multipleRecordLinks`) are resolved by injecting the live Airtable table ID at creation time.

**Result:** All 10 tables created with correct field types and relational links.

---

### 2. Caterers (`./run migrate caterers`)

**Source:** `resources/caterers.xlsx`, sheet `caterers`

Reads caterer names, regions, and minimum order quantities for 4-, 5-, and 6-item orders. The Schools table is seeded here first (6 hard-coded schools with their regions) since Caterers and Sessions both depend on it.

**Result:** 6 Schools, 4 Caterers inserted.

---

### 3. Caterer contacts (`./run migrate contacts`)

**Source:** `cache/caterer-contacts.txt`

Each paragraph in the text corresponds to one caterer, listing: contact person, email, chef (optional), chef CC preference, and the schools they serve vs. can serve. Parsed using Claude API (batched single prompt returning JSON) with a regex/keyword fallback.

Notable cases handled:
- **Kenko Sushi House:** "Big Mom" is both main contact and chef — the parser detects the phrase "main point of contact and chef" and sets both fields to the same person.
- **Terrific Noodles:** Two separate emails appear — first is assigned to the contact, second to the chef.

**Result:** 4 Caterers updated with contact info, school links (`Serves Schools`, `Able to Serve Schools`) populated.

> **Warning:** Kenko Sushi House's contact name field was not populated by the heuristic parser. The source text uses "Big Mom (main point of contact and chef)" which the LLM parser handles correctly but the fallback regex misses. This is the one data-quality warning flagged by `verify_migration.py`.

---

### 4. Caterer menus (`./run migrate menus`)

**Source:** `cache/caterer-menus.txt`

Each caterer's section has a header of the form:
```
<Name> Menu ($<price> including/excluding GST per item, $<delivery> delivery <structure>)
```
followed by item lines with inline dietary codes (`GF`, `DF`, `NF`, `VO`).

Parsed using Claude API (single batch prompt) with a regex fallback. Dietary tags are mapped: `GF → Gluten Free`, `DF → Dairy Free`, `NF → Nut Free`, `VO → Vegetarian`. A domain rule is applied: **all non-pork items are assumed halal** — any menu item whose name does not contain "pork" gets the `Halal` tag automatically.

Delivery pricing and GST status are written back to the **Caterers** table; individual items are inserted into **Menu Items** linked to their caterer.

**Result:** 40 Menu Items inserted; 38 of 40 tagged Halal (the 2 exceptions are "Grilled Pork Vermicelli Salad" and "Pulled pork burrito bowl").

---

### 5. Sessions (`./run migrate sessions`)

**Source:** `resources/sessions.xlsx`, sheet `sessions`

Reads one row per session (school, date, day, caterer, on-site manager, times, year levels, building). On-site managers are upserted first as a deduplicated list. Sessions are then inserted with links to Schools, Caterers, and On-Site Managers resolved by name. Session IDs follow the `"<School Name> - <YYYY-MM-DD>"` convention.

**Result:** 7 On-Site Managers, 11 Sessions inserted.

---

### 6. Students (`./run migrate students`)

**Source:** `resources/students.xlsx` (multi-sheet)

Each sheet is named for a school/day combination (e.g. `Moreton Bay Boys' College - Monday`). The first row is a header containing the school and day; actual data begins at row 3. The migration:

1. Scans all sheets to collect every unique raw dietary string (e.g. `"No Beef, No Pork"`).
2. Translates them to standard Airtable choices using Claude API in a single batch call, falling back to a keyword matcher. Results are cached in `cache/dietary_mappings.json` so reruns skip the LLM call for known strings.
3. Fetches all Sessions from Airtable and builds a `(school_name, day)` lookup so each student's `Sessions` link points to their correct recurring session(s).

**Result:** 320 Students inserted. 18 unique dietary strings resolved (see `cache/dietary_mappings.json`). All students linked to at least one session.

---

### 7. Absences (`./run migrate absences`)

**Source:** `cache/absences.txt`

Structured blocks of the form:
```
<School> - <DD/MM/YYYY> Absences
<Student Name>
...
```

Each absence record links to both the Student (by name) and the Session (by the `"<School> - <YYYY-MM-DD>"` ID). Unresolvable students or sessions are logged and skipped.

**Result:** 10 Absence records inserted across 6 sessions.

| Session | Absences |
|---|---|
| Moreton Bay Boys' College - 2026-05-02 | 1 |
| John Paul College - 2026-05-02 | 2 |
| MacGregor State High School - 2026-05-04 | 1 |
| Indooroopilly State High School - 2026-05-02 | 3 |
| Loreto College - 2026-05-01 | 2 |
| Cannon Hill Anglican College - 2026-05-03 | 1 |

---

### 8. Exclusions (`./run migrate exclusions`)

**Source:** `cache/exclusions.txt`

Free-text paragraphs describing cancelled sessions. Parsed using Claude API (single batch prompt returning structured JSON) with a regex/date fallback. Each exclusion links to a School record and captures the affected year levels and reason.

**Result:** 3 Exclusion records inserted.

| School | Date | Affected Year Levels | Reason |
|---|---|---|---|
| Indooroopilly State High School | 2026-05-04 | All | Open Day |
| Loreto College | 2026-05-02 | All | Parent Teacher Interviews |
| Cannon Hill Anglican College | 2026-05-03 | 12, 10 | School Camp |

---

## Verification Results

Run: `./run script verify_migration`

```
Schools:           6  ✓ (expected 6)
On-Site Managers:  7  ✓
Caterers:          4  ✓ (expected 4)
Menu Items:        40 ✓
Students:          320 ✓ (all linked to sessions)
Sessions:          11 ✓ (all linked to school, caterer, and manager)
Absences:          10 ✓ (all linked to student and session)
Exclusions:        3  ✓ (all linked to school and date)
Meal Feedback:     0  (empty — feature not yet launched)
Meal Selections:   0  (empty — feature not yet launched)

Errors:   0
Warnings: 1 — Kenko Sushi House missing Contact Name (source data ambiguity)
```

---

## Known Issues

- **Kenko Sushi House contact name:** The source PDF lists the contact as "Big Mom (main point of contact and chef)" without a clear first/last name — the heuristic parser does not extract a name from this pattern. The record has a contact email (`hellopadea@gmail.com`) and Chef Name set. The LLM parser handles this correctly; if re-running without an API key the field will remain blank.
- **Meal Feedback / Meal Selections:** Both tables exist in the schema and are linked correctly, but will remain empty until the student-facing feedback and ordering feature is built.
