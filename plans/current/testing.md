# Action Script Tests

Unit and integration tests for the action scripts. Tests run entirely in
memory — no Airtable connection required.

## Running tests

```bash
# Run the full suite
./run test

# Run a single test module
./run test test_register_orders
./run test test_send_orders
./run test test_evaluate_caterers
./run test test_execute_caterer_switch
./run test test_api
./run test test_manage_api
./run test test_substitutions
```

Or directly with Python from the project root:

```bash
PYTHONPATH=$PWD:$PWD/scripts python scripts/tests/run_all.py
```

## File layout

```
scripts/tests/
  mock_db.py                       — MockTable / MockDatabase (in-memory Airtable)
  fixtures.py                      — Record factory helpers and stable ID constants
  test_register_orders.py          — register_orders.py pipeline
  test_send_orders.py              — send_orders.py formatting + queueing
  test_evaluate_caterers.py        — rolling stats, candidate scoring, dedup
  test_execute_caterer_switch.py   — switch execution + dry-run safety
  test_api.py                      — webapp API endpoints (meals form)
  test_manage_api.py               — manage-page endpoints + order overrides
  test_substitutions.py            — Manager Substitutions resolution
  run_all.py                       — test runner (discovers all modules)
  order_constraints.py             — post-migration integration check (needs live DB)
```

## What is tested

### `register_orders.py`
Covers `is_student_excluded`, fallback assignment (popularity + variety),
`compute_max_variety`, `enforce_min_qty`, the caterer-switch flip, and
the end-to-end pipeline including absences, exclusions, opt-outs,
explicit preferences, and dry-run safety.

### `send_orders.py`
Covers the time helpers (`subtract_minutes`), email-body formatting per
fee structure / building / manager, and `schedule_email` for both
order emails and switch-proposal emails.

### `evaluate_caterers.py`
Covers `get_rolling_stats` (window size, unique counts),
`caterer_covers_all_students` (dietary coverage hard filter),
`score_candidate` (school + overall blend), and the term/proposal
dedup helpers (`has_active_proposal`, `was_rejected_this_term`,
`get_term_start`).

### `execute_caterer_switch.py`
Covers proposal status gating (only `Approved` / `Pending` w/ `--approve`),
`Sessions.Incoming Caterer` being set, `Students.Meal Preference` being
cleared, the proposal being marked `Approved` (the order run then promotes
it to `Executed`), and dry-run safety.

### `test_api.py`
Endpoint behaviour for the meals form: session/student lookups,
dietary-restriction fetch, feedback upsert (PATCH vs POST), meal-preference
PATCH, mark-submitted, the picker's `Last Submitted` filter, the digital
ticket endpoint, and cache busting.

### `test_manage_api.py`
Endpoints used by `manage.html`: `/api/manager/<id>/sessions`,
`/api/session/<id>/students-all`, the dietary-requirements PATCH, and the
order-override flow (current row update vs delete vs new `OVR-` row).

### `test_substitutions.py`
`load_substitutions` and `resolve_manager_id` — including week-window
range queries, substitution-vs-permanent precedence, and the
`manager_is_sub` flag that surfaces in the order email.

## Test infrastructure

**`MockTable`** — in-memory table that records every mutation:
- `created_fields: list[dict]` — fields passed to `.create()`
- `updates: list[tuple[id, fields]]` — each `.update()` call
- `batch_update_calls: list[list[dict]]` — each `.batch_update()` call
- `deleted_ids: list[str]` — IDs passed to `.delete()` / `.batch_delete()`

**`MockDatabase`** — instantiates a fresh `MockTable` for each of the 14
Airtable tables in `data/schema.py`.

**`fixtures.py`** — canonical test IDs and factory functions for Records.
All dietary, caterer, menu, session, and student records are available as
`fixtures.dietary_records()`, `fixtures.caterer_a()`, etc. Stable string IDs
(e.g. `CATERER_A_ID = "cAlpha001"`) are re-exported so test assertions stay
readable.

## Adding tests

1. Add a new `test_*` method to an existing class, or a new `class Test*`
   in the relevant module.
2. Use `fixtures.py` factories for Record construction; add new fixtures
   there if needed.
3. Use `MockDatabase` for anything that calls Airtable; use
   `_make_index()` / `types.SimpleNamespace` for pure-function tests that
   only need a partial index.
4. Re-run `./run test` to confirm everything still passes.
