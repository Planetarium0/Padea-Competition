# Principles

The rules an agent should apply by default. If a change conflicts with
one of these, that is a signal to stop and discuss — not a signal to
silently break the rule.

---

## 1. The database is the source of truth

Supabase (Postgres) is canonical. Python and the webapp are clients.

- **Schema lives in `supabase/migrations/*.sql`.** Don't introduce a
  parallel schema description in Python or JS. The Pydantic models in
  `scripts/support/schemas.py` mirror Postgres column types; they do not
  define them.
- **Aggregated read shapes live in Postgres views** (`*_view`).
  Many-to-many fields are surfaced as UUID arrays via views; writes go
  to the underlying junction tables (see `_JUNCTION_MAP` in
  `scripts/support/database.py`). Python and JS both read through the
  views so they see identical shapes.
- **Webapp talks to Supabase directly** (`webapp/supabase_client.js`).
  There is no Python proxy server. Logic that must be enforced server-side
  belongs in the database (constraints, RLS, views, RPCs) — not in JS.
- **Live data edits happen in Supabase Studio**, not via scripts.
  Migration scripts (`scripts/migrations/`) are *destructive seed* tools:
  they `clear()` their target tables before re-inserting. They are not
  safe for incremental updates.
- **Schema changes are migrations.** `./run migrate schema` is disabled
  on purpose — write a new `supabase/migrations/<timestamp>_*.sql` file
  and apply it via the Supabase CLI/MCP.

> Known gap: **RLS is not yet configured.** The webapp uses the
> publishable anon key and reads/writes are unrestricted. Treat anon-key
> access as "every authenticated school+session+student can see
> everything" — fine for a closed pilot, not fine for public launch.
> Add policies before opening the URL beyond LAN/QR distribution.

## 2. Self-healing and agent-ready

The system is designed to be debugged and patched by AI agents with
minimal human intervention.

- **Validate at every database boundary.** Any read from / write to
  Supabase goes through `support.Database` → `support.schemas` Pydantic
  models. `model_validate()` runs on every fetched row and every payload
  before insert/update. If a record can't be modelled, the contract is
  wrong; either fix the data or fix the schema.
- **Wrap operational entrypoints in `self_healing_error_handler`.** All
  active recurring workflows (`register_orders.py`, `send_orders.py`,
  `evaluate_caterers.py`, `execute_caterer_switch.py`) must enter the
  handler with a `state_provider` that snapshots the relevant tables.
  On failure it writes `cache/failures/failure_<ts>_<workflow>.json`
  and a sibling `patch_prompt_<ts>_<workflow>.md` ready to feed to an
  AI patcher.
- **Regress every failure.** When you patch a captured failure, add a
  test in `scripts/tests/test_edge_cases.py` that loads the snapshot
  via `populate_mock_db` and reproduces the bug. `./run test` must pass
  before the patch is shipped.
- **The sandbox is the contract for agent edits.** `scripts/support/run_claude_agent.py`
  restricts agent file writes to `scripts/`, `supabase/`, `webapp/`,
  `plans/` and bash commands to a fixed allowlist. If you want an agent
  to touch something outside those paths, that is a deliberate change to
  the harness, not an exception to make in passing.

## 3. One dispatcher, one entrypoint per goal

- **All operations go through `./run`.** No scripts are run directly in
  documentation, runbooks, or cron — if a workflow needs a new
  entrypoint, add a `./run <verb>` for it.
- **One script = one goal.** A file under `scripts/actions/` exists to
  accomplish exactly one operational outcome (generate orders, send
  emails, evaluate caterers, execute a switch).
- **Cross-cutting helpers go in their own module.** When a helper
  function is imported by more than one action script, it has outgrown
  its current home and should move into `scripts/support/`. *Example:*
  `schedule_email` lives in `send_orders.py` today but is imported by
  `send_qr_emails.py`, `send_meals_links.py`, and `evaluate_caterers.py`
  — it belongs in a dedicated email module (`scripts/support/email.py`
  or similar). This kind of cleanup is part of touching the affected
  code, not a separate refactor.
- **Tests mirror actions, one file per script.** `test_<script>.py`
  for every `actions/<script>.py`; `test_edge_cases.py` for
  failure-replay regressions.

## 4. Webapp = static, thin, and shared with Python by construction

- **No framework, no build step.** `webapp/` is hand-written
  HTML/CSS/JS deployed as static files to GitHub Pages
  (`.github/workflows/deploy.yml`). Adding a bundler is a real
  architectural choice — discuss before introducing one.
- **JS and Python share verdict logic by construction**, not by
  copy-paste:
  - **Dietary hierarchy** comes from the live `dietary_restrictions`
    table — both sides build the same subset closure.
  - **Negative-keyword fallback** comes from `data/dietary_keywords.json`
    — the Python side reads it via `support.compatibility`, the
    webapp fetches it from the same file at boot.
  - **Compatibility algorithm** is the same three-step ladder
    (closure → caterer legend hard block → keyword fallback). Any
    change to one side must apply to the other.
- **Cache for performance, not for correctness.** Client-side caches
  are scoped to a single page visit; long-lived freshness comes from
  the database. Cache invalidation that depends on TTLs is a smell —
  if correctness depends on freshness, read live.

## 5. Coding standards

These aren't preferences; they're invariants for an agent-friendly
codebase.

- **Type hints on every Python function signature** that crosses a
  module boundary. Use `Literal`/`TypedDict`/Pydantic at I/O edges so
  errors surface at the boundary, not three function calls deep.
- **Anything that can fail has a unit test.** "Can fail" includes:
  network calls (mock them), date arithmetic, ID generation, dietary
  fallbacks, min-qty dissolution, manager substitution resolution,
  email recipient computation. A new branch without a corresponding
  test is incomplete work.
- **Tests are pure-in-memory.** `scripts/tests/mock_db.py` mirrors the
  real `Database`/`Table` interface; tests use `MockDatabase` and the
  factories in `fixtures.py`. No real Supabase calls in the suite.
- **Logging beats `print`.** `support.log` (and `log.verbose` at
  level 5) is the only sanctioned channel. Adjust `LOG_LEVEL` in `.env`
  rather than reaching for `print`.
- **Defensive at boundaries, trusting inside.** Validate user input,
  network responses, and Postgres reads. Don't re-validate values
  already minted by trusted code; that adds noise without safety.

## 6. Known gaps (treat as planned, not yet built)

These exist so an agent doesn't mistake absence-of-implementation for
intentional design. Resolve a bullet, delete it.

- **RLS / auth.** See principle 1. No real authentication; publishable
  key only.
- **Scheduling.** `register_orders.py`, `send_orders.py`,
  `evaluate_caterers.py` are all wall-clock-sensitive (Wed 8 PM /
  Thu 3 PM cadence) but nothing in the repo schedules them. Today
  they run manually.
- **Email send semantics.** `scheduled_emails` is an *audit log*, not
  a queue: `schedule_email` writes the row **and** dispatches via
  Resend in the same call. The earlier Airtable-automation queue model
  is gone. Don't reintroduce queue semantics by accident (e.g.
  watching for `Status='Queued'` rows expecting something else to
  send them).
- **`schedule_email` lives in the wrong place.** See principle 3 —
  extract it before adding another caller.

If you add a new known gap, give it a one-line description and a
pointer to the affected file(s). Don't write a roadmap here.
