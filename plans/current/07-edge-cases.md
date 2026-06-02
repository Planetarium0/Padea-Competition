# Edge Cases

Non-obvious behaviour and corner cases the system explicitly handles
(or fails to handle). Cross-reference this with the corresponding source
when modifying behaviour.

## Sessions

- **Sessions recur weekly.** Each `Sessions` record represents one
  weekly slot at one school. The `Date` field holds a single occurrence
  (currently used as a representative date during migration); the order
  generator ignores `Date` and uses `Day` to find next week's date.
- **Session ID format**: `<School Name> - <Day>` (e.g. `"Loreto College -
  Friday"`). Originally documented as including a date, but date was
  dropped when sessions became recurring. Absence records still use the
  date form: `"<Student> - <School> - <YYYY-MM-DD>"`.
- **A session with no caterer** is skipped by the order generator with
  a warning. Likewise a session whose caterer has no menu items.
- **Pending caterer switch.** If a session's `Incoming Caterer` is set,
  `register_orders.py` flips `Caterer ← Incoming Caterer` at the start of
  the run, clears `Incoming Caterer`, and marks the matching Caterer
  Switch Proposal `Executed`. From that point on the order is built
  against the new caterer's menu.

## Students

- **Multi-session students.** A student can be linked to multiple
  Sessions (e.g. attends Monday at School A and Wednesday at School B).
  `register_orders.py` iterates by session, so the student appears in
  both. Each gets its own meal allocation.
- **Mid-term enrolment.** Not supported by the migration scripts (they
  clear and re-import). Add new students directly in Airtable.
- **Year level matters for exclusions.** An `Exclusions.Affected Year
  Levels` of `["All"]` cancels everyone; a specific list cancels only
  those year levels. Year level is stored as a number, year-level
  exclusion choices are strings — comparison converts via `str(int(yr))`.
- **`Last Submitted` is the day-locked roster gate.** Once a student
  has submitted once today, they vanish from the picker for the rest of
  the day. Manager workflow: clear `Last Submitted` (or wait until
  tomorrow) to let the student submit again.

## Absences

- **Absences are date-specific**, not session-specific in the recurring
  sense. A student absent on `2026-05-04` is filtered out only for that
  date's occurrence of their session, not future weeks.
- **Linking by name + date.** The migration looks up the (student, session)
  pair by name + session ID. Orphan rows (student not in DB, or session
  ID not matching) are logged and skipped — not fatal.

## Exclusions

- **Cancel the whole school's session that day** when `Affected Year
  Levels = All`. Targeted exclusions (e.g. School Camp for years 10 and
  12) only filter the matching students.
- **Heuristic parser is May-2026 hard-coded.** The fallback in
  `migrations/exclusions.py` builds dates as `2026-05-{day:02d}`. Will
  not work for other months/years without code changes.

## Caterers

- **Delivery fee structure** is either flat per trip (one charge no
  matter how many schools) or per-school-per-trip (multiplied by the
  number of delivery destinations that week).
- **Big Mom = contact + chef.** Kenko Sushi House's single staff member.
  Heuristic parser misses the contact name (LLM gets it right).
- **GST.** `Price per Item` is stored as a final, GST-inclusive number.
  The migration multiplies the raw quote by 1.10 at import time if the
  source said "excluding GST", so downstream callers don't need a flag.
- **Min Qty 4/5/6 Items.** Per-item minimum, not total minimum. If you
  order 5 distinct items from a caterer with `Min Qty 5 Items = 3`,
  each of those 5 items needs ≥ 3 portions, i.e. ≥ 15 total. Many
  caterers have looser minimums for ordering fewer distinct items.
- **Dietary Legend Tags.** When a caterer's menu has a published legend
  (GF / DF / NF / VO), the matching restriction IDs are linked here.
  Absence of a tag for a legend-tracked restriction is treated as
  definitive — see `06-dietary-system.md`.

## Order generation

- **Variety vs popularity.** Threshold = 10 explicit preferences per
  caterer. Below: variety mode (least-ordered first), capped at the
  max distinct items the order can support without violating min-qty.
  At or above: popularity mode (most-ordered first, weighted).
- **Random seed isn't set.** Both modes use `random.uniform(0, 1)` for
  tie-breaking. Reruns won't produce identical orders.
- **Min-qty swap is proportional.** When dissolving a violating item,
  the swap-target distribution mirrors current popularity — so a 10/5/3
  caterer order tends to drift toward 10s.
- **Explicit preferences are not protected from min-qty swaps.** A
  preferred-but-violating item is dissolved like any other; the student
  is just moved to a dietarily compatible target.
- **Caterer with no menu items is skipped** with a warning.
- **Student with no compatible meal is skipped** (stats: `no_meal`).
  No fallback to "give them anything" — they get no order.
- **Idempotency.** `clear_existing_orders` drops *all* Orders and Weekly
  Orders dated in the target week before rebuilding — there is no
  per-row Status field, so re-runs always wipe the slate clean.

## Webapp

- **Session ID required.** Without the `?session=` param, the page
  shows an error banner.
- **Entry point is `meals.html`** (not `index.html`). The same
  `host_webapp.py` server also serves `manage.html` and
  `switch-proposal.html`.
- **localStorage student persistence is per-session.** Key is
  `padea_known_student_<sessionId>` — switching sessions on the same
  device shows the picker again.
- **Wednesday 8 PM cutoff** is *advisory only*. The form still saves
  preferences after the cutoff; a footnote warns the user that next
  week's order has already been placed. The check uses *local time*
  on the device, not Australia/Brisbane — relevant for travellers.
- **Explicit override via confirmation modal.** Tapping an
  incompatible meal triggers a confirm modal. After confirming, the
  pick is treated identically to a compatible one downstream.
- **No API key in the browser.** All Airtable traffic goes through
  `/api/...` on the Python server. The old `?key=` URL override is gone.

## Email pipeline

- **Send happens outside Python.** The Airtable automation does the
  actual email send; `send_orders.py` (and the other senders) only
  queue rows in `Scheduled Emails`. There's no retry logic in Python
  — that lives in the Airtable workflow.
- **No queueing idempotency.** Running `./run orders send` (or
  `evaluate_caterers.py` etc.) twice in a row will queue duplicate
  emails. Status / send-tracking is currently a manual concern.
- **CC includes more than the chef.** `send_orders.py` CCs the chef
  (if `Chef Wants CC`), then every on-site manager email across the
  sessions in that order, de-duplicated.
- **Email body uses an Airtable-subset of Markdown** — no tables, no
  raw HTML. Format helper restricts to headings, bold, lists. The QR
  emails are an exception: `send_qr_emails.py` embeds inline `<img>`
  tags pointing to `api.qrserver.com`.
- **"Deliver by" = Dinner Time minus 10 minutes.** Hard-coded. If a
  caterer needs more buffer, the per-session dinner time has to be
  pushed earlier.

## Verification scripts

- The old `verify_migration.py` has been retired (it lives under `old/`
  and isn't wired up anywhere). Post-migration sanity is now mostly
  covered by the unit-test suite under `scripts/tests/` — see
  `testing.md`.
- `order_constraints.py` reuses `register_orders.py`'s data loaders
  (`OrderingData`, `OrderingIndex`, `_find_min_qty`,
  `get_next_week_dates`, `is_student_excluded`), so drift is unlikely.

## Operational

- **`./run script <name>`** runs `scripts/actions/<name>.py`. Test scripts
  under `scripts/tests/` are not action scripts; run them with `./run test`.
- **`./run migrate`** delegates to `scripts/migrations/migrate.py`, which
  calls each migration in explicit dependency order — not alphabetically.
  That file is the authoritative source of run order.
- **PDFs need pre-extraction.** Each migration that reads a PDF expects
  the matching `.txt` in `cache/`. `cache_pdf.py` does the extraction —
  must run after a PDF changes, or the migration will use stale text.

## Self-Healing & Validation Architecture

To ensure high reliability and enable automated agent-ready debugging, the active operational workflows implement a self-healing loop:

### 1. Pydantic Runtime Validation
- **Location**: `scripts/support/schemas.py`
- **Execution**: Database read and write operations (in `scripts/support/database.py`) actively validate fetched data against Pydantic models. Any malformed Airtable fields (e.g. type mismatches, missing required links, or invalid enums) immediately trigger a Pydantic `ValidationError`.
- **Active Schema Mappings**:
  - `MODEL_MAP` maps active table names to their validation models (e.g., `Students` -> `Student`, `Caterers` -> `Caterer`, `Sessions` -> `Session`).

### 2. State-Capture Exception Serialization
- **Handler**: `support.self_healing_error_handler` context manager.
- **Coverage**: Wraps the entry points for all primary actions:
  - Order Generation (`scripts/actions/register_orders.py`)
  - Email Pipeline (`scripts/actions/send_orders.py`)
  - Caterer Evaluation (`scripts/actions/evaluate_caterers.py`)
  - Proposal Execution (`scripts/actions/execute_caterer_switch.py`)
  - API Dispatch Router (`scripts/actions/api.py` / `host_webapp.py`)
- **Behavior**: Upon intercepting a validation or runtime exception (e.g., `IndexError`, `KeyError`, `ValidationError`):
  1. Serializes the active command, traceback, and inputs.
  2. Queries the live database context to capture a complete snapshot of all active tables.
  3. Writes a machine-readable state representation to `cache/failures/failure_<timestamp>_<workflow>.json`.
  4. Auto-generates a pre-formatted markdown instruction prompt `cache/failures/patch_prompt_<timestamp>_<workflow>.md` outlining the error and exact debug instructions.

### 3. Test-Driven Regression & Healing Loop
- **Test Harness**: `scripts/tests/test_edge_cases.py`
- **Verification Workflow**:
  1. The automated agent reads `failure_*.json`.
  2. The agent initializes a new test inside `test_edge_cases.py`, using `populate_mock_db` to load the database snapshot directly into `MockDatabase`.
  3. The agent replicates the error in memory, implements the code patch, and runs `./run test` to verify the fix before deploying to production.

