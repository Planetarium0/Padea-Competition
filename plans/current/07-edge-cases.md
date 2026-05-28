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
- **GST.** Caterers quote either inclusive or exclusive of GST. The
  system stores the boolean but **does not convert** during order
  totalling — `Total Cost = Total Meals × Price per Item + Delivery`,
  using the raw `Price per Item` regardless of GST flag. (See
  `plans/gst.md` — the question of whether to normalise prices to a
  consistent basis is open.)
- **Min Qty 4/5/6 Items.** Per-item minimum, not total minimum. If you
  order 5 distinct items from a caterer with `Min Qty 5 Items = 3`,
  each of those 5 items needs ≥ 3 portions, i.e. ≥ 15 total. Many
  caterers have looser minimums for ordering fewer distinct items.

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
- **Explicit preferences are never swapped.** If the only violators
  are explicit, the constraint stays violated and a warning is logged.
- **Caterer with no menu items is skipped** with a warning.
- **Student with no compatible meal is skipped** (stats: `no_meal`).
  No fallback to "give them anything" — they get no order.
- **Existing Sent orders are preserved.** `clear_existing_orders` only
  drops `Draft` Weekly Orders for the target week — the audit trail
  is intact for re-runs.

## Webapp

- **Session ID required.** Without the `?session=` param, the page
  shows an error banner.
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
- **API key in URL.** `?key=` overrides `CONFIG.API_KEY`. Convenient
  for development; remove before printing QR codes.

## Email pipeline

- **Send happens outside Python.** The Airtable automation does the
  actual email send; `send_orders.py` only queues it. There's no
  retry logic in Python — that lives in the Airtable workflow.
- **`Sent` status is misleading.** `send_orders.py` flips Weekly
  Orders to `Sent` after queueing, not after delivery. A queued-but-
  -failed email leaves the Weekly Order marked `Sent` and the
  Scheduled Email marked `Failed`. Inspecting status requires looking
  at both tables.
- **Email body uses an Airtable-subset of Markdown** — no tables, no
  raw HTML. Format helper restricts to headings, bold, lists.
- **"Deliver by" = Dinner Time minus 10 minutes.** Hard-coded. If a
  caterer needs more buffer, the per-session dinner time has to be
  pushed earlier.

## Verification scripts

- `verify_migration.py` (post-migration) **does not check** the
  Dietary Restrictions, Weekly Orders, Orders, or Scheduled Emails
  tables. It still checks for a `Meal Feedback` table that no longer
  exists (the table is now `Caterer Feedback`).
- `order_constraints.py` re-implements `build_lookups` separately from
  `register_orders.py`. Drift between them would silently break tests.

## Operational

- **`./run script <name>`** runs `scripts/actions/<name>.py`. Test scripts
  under `scripts/tests/` must be run with `python` directly or via `./run test`.
- **`./run migrate`** delegates to `scripts/migrations/migrate.py`, which
  calls each migration in explicit dependency order — not alphabetically.
  That file is the authoritative source of run order.
- **PDFs need pre-extraction.** Each migration that reads a PDF expects
  the matching `.txt` in `cache/`. `cache_pdf.py` does the extraction —
  must run after a PDF changes, or the migration will use stale text.
