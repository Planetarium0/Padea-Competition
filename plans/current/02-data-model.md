# Data Model

Single source of truth: `scripts/data/schema.py` (`TABLES_SCHEMA`).
`scripts/actions/update_schema.py` keeps the Airtable base in sync with it.

## Tables (13)

```
Schools ──< Sessions >── Caterers ──< Menu Items >── Dietary Restrictions
   │           │              │            │                  ↑
   │           ├──< On-Site Managers       │             (Supersets self-link)
   │           │                            │
   ├──< Students (Meal Preference → Menu Items)
   │       │                                │
   │       ├──< Absences                    │
   │       └──< Caterer Feedback (Caterer, Session)
   │
   └──< Exclusions

Weekly Orders ──< Orders >── Sessions, Menu Items
Weekly Orders ──< Scheduled Emails
```

### Schools
Six static records, seeded by `migrations/caterers.py`.

- **School Name** (primary)
- **Region** (Redlands / South Brisbane / West Brisbane / Central Brisbane)

### On-Site Managers
Extracted from `sessions.xlsx`. Deduplicated by name.

- **Manager Name** (primary)
- **Mobile**

### Caterers
Four records. Pricing and contact fields populated in three passes:

- **Caterer Name** (primary)
- **Region**
- **Min Qty 4 Items**, **Min Qty 5 Items**, **Min Qty 6 Items** — when
  ordering N distinct items, each item must have ≥ this many portions.
- **Price per Item** (flat across menu), **Price Includes GST**
- **Contact Name / Email**, **Chef Name / Email**, **Chef Wants CC** (boolean —
  whether to CC the chef on order emails)
- **Delivery Fee**, **Delivery Fee Structure** (`Per trip` or `Per school per trip`)
- **Serves Schools**, **Able to Serve Schools** — both link to `Schools`
- **Notes**

### Menu Items
~40 records — one row per dish per caterer.

- **Menu Item Name** (primary)
- **Caterer** → `Caterers`
- **Dietary Tags** → `Dietary Restrictions` (multipleRecordLinks)
- **Notes**

> The "Halal" tag is auto-applied to any item whose name does **not** contain
> "pork". This domain rule lives in `migrations/caterer_menus.py`.

### Dietary Restrictions
Static lookup table. Defines the dietary taxonomy and its hierarchy.

- **Restriction Name** (primary)
- **Supersets** → `Dietary Restrictions` (self-link). A restriction lists its
  *less-restrictive* parents. The inverse back-link is renamed to **Subsets**.

Read `Supersets` as "X is a subset of these" — every item that satisfies X
also satisfies any superset of X. Used by the webapp to soft-filter the meal
list. See `06-dietary-system.md`.

### Students
~320 records. One row per enrolled student.

- **Student Name** (primary)
- **Year Level** (6 – 12)
- **Subjects**
- **Dietary Requirements** → `Dietary Restrictions`
- **Student Email**, **Parent Name / Email / Mobile**
- **Sessions** → `Sessions` (a student is linked to every recurring weekly
  session they attend)
- **Meal Preference** → `Menu Items` (single item; current preference for
  next week — upserted by the webapp, snapshotted weekly by
  `register_orders.py`)

### Sessions
One record per recurring weekly session (~11). A session repeats every week of
the term on a given Day at a given School.

- **Session ID** (primary, format: `"<School Name> - <Day>"` e.g.
  `"Loreto College - Friday"`)
- **School** → `Schools`
- **Region** — denormalised from School
- **Caterer** → `Caterers`
- **Date** — single date (one occurrence; the order generator uses Day, not this)
- **Day** (Monday – Friday)
- **On-Site Manager** → `On-Site Managers`
- **Start Time**, **End Time**, **Dinner Time**, **Year Levels**, **Building**

### Absences
One record per known absence on a specific date.

- **Absence ID** (primary, format: `"<Student> - <School> - <YYYY-MM-DD>"`)
- **Student** → `Students`
- **Session** → `Sessions`
- **Date**, **Reason**

### Exclusions
One record per cancelled session (whole-school events).

- **Exclusion ID** (primary, format: `"<School> - <YYYY-MM-DD>"`)
- **School** → `Schools`
- **Date**
- **Affected Year Levels** (multipleSelects: `All`, `12`, `11`, …, `6`)
- **Reason**

### Caterer Feedback
Star rating + optional comment, written by the student via the webapp.

- **Feedback ID** (primary)
- **Student** → `Students`
- **Session** → `Sessions`
- **Caterer** → `Caterers`
- **Rating** (1 – 5 integer)
- **Comment**

> Renamed from "Meal Feedback" — the rating is now of the *caterer's* output
> on a given day, not of a specific dish. The student rates whatever they
> were served, regardless of which item they picked.

### Weekly Orders
One per caterer per week. The aggregate parent of `Orders`.

- **Order ID** (primary, format: `"<Caterer Name> — <YYYY-Www>"`)
- **Caterer** → `Caterers`
- **Week Start** (Monday of the target week)
- **Total Meals**, **Total Cost**
- **Status** (`Draft` / `Sent` / `Confirmed`)
- **Notes**

### Orders
One per (Session, Menu Item) pair per week — i.e. one row says "this many
of *that* dish for *that* session." Rolled up from individual student
preferences in `register_orders.py`.

- **Order ID** (primary, format: `"<Session ID> — <Item Name> — <YYYY-Www>"`)
- **Weekly Order** → `Weekly Orders`
- **Menu Item** → `Menu Items`
- **Session** → `Sessions`
- **Date** (the actual date this session occurs, computed from Day)
- **Quantity**

### Scheduled Emails
A queue table — `send_orders.py` inserts records, an Airtable automation
watches `Status='Queued'` and does the real send.

- **Email ID** (primary)
- **To**, **CC**, **Subject**, **Body**
- **Status** (`Queued` / `Sent` / `Failed`)
- **Weekly Order** → `Weekly Orders`
- **Send Date**

## Naming-key conventions

These string formats are not just labels — they're used as natural keys
during migration linking and verification. Changing them breaks the linkers.

| Table | Format | Notes |
|---|---|---|
| Sessions.Session ID | `<School> - <Day>` | Recurring; one record per weekly slot |
| Absences.Absence ID | `<Student> - <School> - <YYYY-MM-DD>` | Built from Session ID + Student |
| Exclusions.Exclusion ID | `<School> - <YYYY-MM-DD>` | Date-specific |
| Weekly Orders.Order ID | `<Caterer> — <YYYY-Www>` | em-dash, ISO week number |
| Orders.Order ID | `<Session ID> — <Item> — <YYYY-Www>` | em-dash |
| Scheduled Emails.Email ID | `EMAIL-<YYYY-MM-DD>-<wo_id[:8]>` | |

## Schema-sync behaviour (`update_schema.py`)

- Idempotent: missing tables are created with primary key first, then all
  fields are added in a second pass (resolves circular `multipleRecordLinks`).
- Anything in Airtable not in `TABLES_SCHEMA` is **renamed** with a
  `(deleted) ` prefix — the personal access token can rename but not delete,
  so a human deletes from the UI afterwards.
- Type mismatches are handled the same way: the existing field is renamed
  with the prefix, and a fresh field of the new type is created next to it.
- `inverse_name` on a `multipleRecordLinks` spec field renames Airtable's
  auto-created back-link (e.g. `Supersets` → `Subsets`).
