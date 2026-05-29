# Data Model

Single source of truth: `data/schema.py` (`TABLES_SCHEMA`).
`scripts/actions/update_schema.py` keeps the Airtable base in sync with it.

## Tables (14)

```
Schools ──< Sessions >── Caterers ──< Menu Items >── Dietary Restrictions
   │           │              │            │                  ↑
   │           ├──< On-Site Managers       │             (Supersets self-link)
   │           │       ↑                   │
   │           │       └─ Manager Substitutions (one-off override per date)
   │           │
   ├──< Students (Meal Preference → Menu Items)
   │       │
   │       ├──< Absences
   │       └──< Caterer Feedback (Caterer, Session)
   │
   └──< Exclusions

Weekly Orders ──< Orders >── Sessions, Menu Items, Students
Weekly Orders ──< Scheduled Emails >── Caterer Switch Proposals
                                              │
Sessions.Incoming Caterer ←───────────────────┘
```

### Schools
Six static records, seeded by `migrations/schools.py` (originally extracted from
`sessions.xlsx`).

- **School Name** (primary)
- **Region** (Redlands / South Brisbane / West Brisbane / Central Brisbane)

### On-Site Managers
Extracted from `sessions.xlsx`. Deduplicated by name.

- **Manager Name** (primary)
- **Mobile**
- **Email**

### Manager Substitutions
One record per one-off substitution. When a substitute covers a session on a
specific date, the coordinator creates a record here; scripts resolve the
*effective* manager by checking this table first before falling back to the
session's permanent On-Site Manager.

- **Substitution ID** (primary, format: `"<Session ID> - <YYYY-MM-DD>"`)
- **Session** → `Sessions`
- **Date** — the date of the one-off substitution
- **Substitute Manager** → `On-Site Managers`

`send_orders.py` calls `load_substitutions` + `resolve_manager_id` (in
`support/database.py`) to pick the right contact for each session's order
email. `evaluate_caterers.py` and `send_qr_emails.py` always use the
permanent manager (alerts are long-term; QR emails go out before substitutes
are known).

### Caterers
Four records. Pricing and contact fields populated in three passes:

- **Caterer Name** (primary)
- **Region**
- **Min Qty 4 Items**, **Min Qty 5 Items**, **Min Qty 6 Items** — when
  ordering N distinct items, each item must have ≥ this many portions.
- **Price per Item** (flat across menu, GST-inclusive; the migration
  multiplies by 1.10 at import time if the source quoted excl. GST so
  downstream callers can treat the stored number as final).
- **Contact Name / Email**, **Chef Name / Email**, **Chef Wants CC** (boolean —
  whether to CC the chef on order emails)
- **Delivery Fee**, **Delivery Fee Structure** (`Per trip` or `Per school per trip`)
- **Able to Serve Schools** → `Schools` — schools this caterer is *eligible*
  to serve (the *current* assignment is derived from `Sessions.Caterer`; no
  separate "Serves Schools" field exists).
- **Dietary Legend Tags** → `Dietary Restrictions` — the restrictions this
  caterer's menu explicitly tracks for every item (e.g. GF / DF / NF / VO).
  Absence of a tag for a legend-tracked restriction means the item
  *definitely* does not satisfy that restriction, converting an otherwise
  "maybe" into a "no" during compatibility checks. See `06-dietary-system.md`.
- **Notes**

### Menu Items
~40 records — one row per dish per caterer.

- **Menu Item Name** (primary)
- **Caterer** → `Caterers`
- **Dietary Tags** → `Dietary Restrictions` (multipleRecordLinks)
- **Is Variant** (checkbox). True for dietary-variant rows that should be
  hidden from the main meal list (the student sees the base item and picks
  the variant from a modal). Built during `caterer_menus.py` migration for
  every `VO` (vegetarian-option) flag encountered.
- **Variant Of** → `Menu Items` (self-link). Points the variant at its base
  item; the inverse back-link is renamed to `Variants`.
- **Notes**

> The "Halal" tag is auto-applied to any item whose name does **not** contain
> any of a small set of pork-indicating substrings ("pork", "bacon", "ham",
> "prosciutto", "pancetta", "lard", "salami", "chorizo"). This domain rule
> lives in `migrations/caterer_menus.py`.

### Dietary Restrictions
Static lookup table. Defines the dietary taxonomy and its hierarchy.

- **Restriction Name** (primary)
- **Supersets** → `Dietary Restrictions` (self-link). A restriction lists its
  *less-restrictive* parents. The inverse back-link is renamed to **Subsets**.

Read `Supersets` as "X is a subset of these" — every item that satisfies X
also satisfies any superset of X. Used by both the webapp and
`support/compatibility.py` to soft-filter the meal list.
See `06-dietary-system.md`.

> There is no `Is Allergy` column. Allergy treatment is driven by a hard-coded
> name list in the dietary code rather than a column; see `06-dietary-system.md`.

### Students
~320 records. One row per enrolled student.

- **Student Name** (primary)
- **Year Level** (6 – 12)
- **Subjects**
- **Dietary Requirements** → `Dietary Restrictions`
- **Student Email**, **Parent Name / Email / Mobile**
- **Sessions** → `Sessions` (a student is linked to every recurring weekly
  session they attend)
- **Meal Preference** → `Menu Items` (single item; the student's standing
  pick — updated by the webapp and persists until changed. Read each week by
  `register_orders.py`, which writes the result into `Orders`.)
- **Last Submitted** (date). Set by the webapp on every successful submit.
  The student-picker filters out students whose `Last Submitted == today`
  so a prankster can't impersonate them — see the one-way-roster lockout
  in `04-webapp.md`.

### Sessions
One record per recurring weekly session (~11). A session repeats every week of
the term on a given Day at a given School.

- **Session ID** (primary, format: `"<School Name> - <Day>"` e.g.
  `"Loreto College - Friday"`)
- **School** → `Schools`
- **Caterer** → `Caterers`
- **Date** — single date (one occurrence; the order generator uses Day, not this)
- **Day** (Monday – Friday)
- **On-Site Manager** → `On-Site Managers`
- **Start Time**, **End Time**, **Dinner Time**, **Year Levels**, **Building**
- **Incoming Caterer** → `Caterers`. Set when a Caterer Switch Proposal has
  been approved but not yet committed. The webapp uses this to show next
  week's menu (from the new caterer) for preference selection while the
  rating card still rates the current caterer. `register_orders.py`'s
  `flip_incoming_caterers` step commits the switch (`Caterer ←
  Incoming Caterer`) at the start of each order run.

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
- **Session Date** (date) — the actual date feedback was submitted. Used by
  `evaluate_caterers.py` for the rolling-window calculation; falls back to
  the session's `Date` field for legacy rows without an explicit date.

> Renamed from "Meal Feedback" — the rating is now of the *caterer's* output
> on a given day, not of a specific dish. The student rates whatever they
> were served, regardless of which item they picked.

### Weekly Orders
One per caterer per week. The aggregate parent of `Orders`.

- **Order ID** (primary, format: `"<Caterer Name> — <YYYY-Www>"`)
- **Caterer** → `Caterers`
- **Week Start** (Monday of the target week)
- **Total Meals**, **Total Cost**
- **Notes**

### Orders
One row per **(Session, Menu Item)** pair for a given week. All students
assigned that meal share the row via the `Student` linked field; `Quantity`
equals the length of that list. The Student link powers the webapp's
"digital ticket" lookup (`FIND` in `ARRAYJOIN({Student})`), and
`send_orders.py` sums `Quantity` for per-item totals.

- **Order ID** (primary, format: `"<Session ID> — <Item Name> — <YYYY-Www>"`)
- **Weekly Order** → `Weekly Orders`
- **Menu Item** → `Menu Items`
- **Session** → `Sessions`
- **Student** → `Students` (multipleRecordLinks; can hold many)
- **Date** (the actual date this session occurs, computed from Day)
- **Quantity** (= `len(Student)` for normal rows; manager overrides created
  via `/api/student/<id>/order-override` may use a different Order ID prefix
  like `OVR-…`)

### Scheduled Emails
A queue table — `send_orders.py`, `evaluate_caterers.py`,
`send_meals_links.py`, and `send_qr_emails.py` all insert records here. An
Airtable automation watches `Status='Queued'` (or `Send Immediately`) and
does the real send.

- **Email ID** (primary)
- **To**, **CC**, **Subject**, **Body**
- **Status** (`Queued` / `Sent` / `Failed`). The TypedDict in
  `support/records.py` also includes `Send Immediately` as a recognised
  status; if used, the matching choice must be added to the Airtable
  singleSelect schema first.
- **Weekly Order** → `Weekly Orders` (optional — set on order emails)
- **Caterer Switch Proposal** → `Caterer Switch Proposals` (optional — set
  on switch-proposal emails). Airtable doesn't support polymorphic links,
  so both live as separate optional fields on this table.
- **Send Date** (date) — left null at queue time; the Airtable automation
  fills it in when the message actually goes out.

### Caterer Switch Proposals
One row per automated proposal generated by `evaluate_caterers.py`.
Coordinators review in Airtable or via the webapp page
`switch-proposal.html?id=<rec>` (see `04-webapp.md`).

- **Proposal ID** (primary)
- **Session** → `Sessions`
- **Outgoing Caterer**, **Incoming Caterer** → `Caterers`
- **Avg Rating** (number, 2dp) — the rolling-window average that triggered
  the proposal. Blank for proposals created via `--force`.
- **Sessions Sampled**, **Unique Raters** — supporting stats. Blank for forced.
- **Proposed On** (date)
- **Effective Week** (date) — the Monday the switch should first apply.
- **Status** (`Pending` / `Approved` / `Rejected` / `Executed`)
- **Notes**

Lifecycle: `evaluate_caterers.py` creates rows as `Pending`. The coordinator
approves (`Pending`→`Approved`), which triggers `execute_caterer_switch.py`
to set `Sessions.Incoming Caterer` and clear every affected student's
`Meal Preference`. The next `register_orders.py` run flips the caterer and
marks the proposal `Executed`.

## Naming-key conventions

These string formats are not just labels — they're used as natural keys
during migration linking and verification. Changing them breaks the linkers.

| Table | Format | Notes |
|---|---|---|
| Sessions.Session ID | `<School> - <Day>` | Recurring; one record per weekly slot |
| Absences.Absence ID | `<Student> - <School> - <YYYY-MM-DD>` | Built from Session ID + Student |
| Exclusions.Exclusion ID | `<School> - <YYYY-MM-DD>` | Date-specific |
| Manager Substitutions.Substitution ID | `<Session ID> - <YYYY-MM-DD>` | |
| Weekly Orders.Order ID | `<Caterer> — <YYYY-Www>` | em-dash, ISO week number |
| Orders.Order ID | `<Session ID> — <Item> — <YYYY-Www>` | em-dash; one row per (session, item) per week |
| Scheduled Emails.Email ID | `EMAIL-<YYYY-MM-DD>-<wo_id[:8]>` (orders) <br> `SWITCH-<proposal_id>` (switch alerts) <br> `WATCH-…` / `NOCAND-…` (watch alerts) <br> `MEALS-<PAR\|STU>-…` (preference links) <br> `MEALS-QR-…` (QR emails) | |
| Caterer Switch Proposals.Proposal ID | `PROP-<SESSION_PREFIX>-<YYYY-MM-DD>` | First 10 chars of Session ID (uppercase, no spaces) |

## Schema-sync behaviour (`update_schema.py`)

- Idempotent: missing tables are created with primary key first, then all
  fields are added in a second pass (resolves circular `multipleRecordLinks`).
- Anything in Airtable not in `TABLES_SCHEMA` is **renamed** with a
  `(deleted) ` prefix — the personal access token can rename but not delete,
  so a human deletes from the UI afterwards.
- Type mismatches are handled the same way: the existing field is renamed
  with the prefix, and a fresh field of the new type is created next to it.
- `inverse_name` on a `multipleRecordLinks` spec field renames Airtable's
  auto-created back-link (e.g. `Supersets` → `Subsets`, `Variant Of` →
  `Variants`).
