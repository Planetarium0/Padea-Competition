# Action Script Tests

Unit and integration tests for the four action scripts. Tests run
entirely in memory — no Airtable connection required.

## Running tests

```bash
# Run the full suite
./run test

# Run a single test module
./run test test_register_orders
./run test test_send_orders
./run test test_evaluate_caterers
./run test test_execute_caterer_switch
```

Or directly with Python from the project root:

```bash
PYTHONPATH=$PWD:$PWD/scripts python scripts/tests/run_all.py
```

## File layout

```
scripts/tests/
  mock_db.py                 — MockTable / MockDatabase (in-memory Airtable)
  fixtures.py                — Record factory helpers and stable ID constants
  test_register_orders.py    — 30 tests
  test_send_orders.py        — 12 tests
  test_evaluate_caterers.py  — 24 tests
  test_execute_caterer_switch.py — 9 tests
  run_all.py                 — test runner (discovers all four modules)
  order_constraints.py       — post-migration integration check (needs live DB)
```

## What is tested

### `register_orders.py`
| Test class | Scenarios |
|---|---|
| `TestIsStudentExcluded` | No exclusions; all year levels; matching year; wrong year; wrong date |
| `TestAssignFallbackMeal` | No restrictions; vegetarian blocked from meat items; no compatible meal returns `None`; popularity weighting |
| `TestAssignVarietyMeal` | Picks least-ordered item; `max_items` cap prevents new items; dietary exception overrides cap |
| `TestComputeMaxVariety` | Enough students for 4-item constraint; fallback when insufficient; divide-by-3 fallback; higher `n` preferred |
| `TestEnforceMinQty` | No violations; below-threshold non-explicit swapped; explicit preference never swapped |
| `TestFlipIncomingCaterers` | Session with pending switch gets flipped; dry-run makes no writes; no pending switches |
| `TestRegisterOrdersPipeline` | 2 students → 2 meals; opted-out skipped; absent skipped; explicit preference respected; vegetarian never gets meat; dry-run writes nothing |

### `send_orders.py`
| Test class | Scenarios |
|---|---|
| `TestSubtractMinutes` | 12h format; 24h format; compact format; crossing the hour; invalid string; `None`; custom offset |
| `TestFormatEmailBody` | Per-trip fee; per-school-per-trip (2 deliveries × fee); manager contact included; building included; deliver-by 10 min before dinner |
| `TestScheduleEmail` | Weekly order link + Queued status; switch proposal link + Send Immediately + CC |

### `evaluate_caterers.py`
| Test class | Scenarios |
|---|---|
| `TestGetRollingStats` | Below `MIN_SESSIONS` → `None`; enough data returns correct average; rolling window excludes oldest sessions; unique student counts |
| `TestCatererCoversAllStudents` | All covered; vegan blocked by meat-only menu; opted-out skipped; no menu items; vegan tag satisfies vegetarian |
| `TestScoreCandidate` | Blended school+overall score; overall-only when no school history; defaults to 3.0 with no history |
| `TestHasActiveProposal` | Pending/Approved/Executed block; Rejected does not; different school does not |
| `TestWasRejectedThisTerm` | Rejected after term start; rejected on start day; rejected before term start (not suppressed); Pending not treated as rejected; different caterer not matched |
| `TestGetTermStart` | During T1; exactly on start; during T2; before all terms |

### `execute_caterer_switch.py`
| Test class | Scenarios |
|---|---|
| `TestExecuteCatererSwitch` | Sets Incoming Caterer on all school sessions; updates Serves Schools; updates Able to Serve; clears student Meal Preference; marks proposal Executed; non-Approved → `SystemExit(1)`; missing proposal → `SystemExit(1)`; dry-run writes nothing; sessions at other schools untouched |

## Test infrastructure

**`MockTable`** — in-memory table that records every mutation:
- `created_fields: list[dict]` — fields passed to `.create()`
- `updates: list[tuple[id, fields]]` — each `.update()` call
- `batch_update_calls: list[list[dict]]` — each `.batch_update()` call
- `deleted_ids: list[str]` — IDs passed to `.delete()` / `.batch_delete()`

**`MockDatabase`** — instantiates a fresh `MockTable` for each of the 14 Airtable tables.

**`fixtures.py`** — canonical test IDs and factory functions for Records.
All dietary, caterer, menu, session, and student records are available as
`fixtures.dietary_records()`, `fixtures.caterer_a()`, etc. Stable string IDs
(e.g. `CATERER_A_ID = "cAlpha001"`) are re-exported so test assertions stay readable.

## Adding tests

1. Add a new `test_*` method to an existing class, or a new `class Test*`
   in the relevant module.
2. Use `fixtures.py` factories for Record construction; add new fixtures there
   if needed.
3. Use `MockDatabase` for anything that calls Airtable; use
   `_make_index()` / `types.SimpleNamespace` for pure-function tests that
   only need a partial index.
4. Re-run `./run test` to confirm everything still passes.
