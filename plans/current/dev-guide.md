# Dev Guide

How to find your way around the repo, where to put new code, and how to
keep the docs and the graph honest. Read this when you're about to write
code, not before.

---

## First moves on any task

1. **Ask graphify before grepping.** For "where is X?" / "what depends
   on Y?" / "what does Z call?", `graphify query "<question>"` returns
   a scoped subgraph, far smaller than raw search output. Fall through
   to `graphify path "A" "B"` or `graphify explain "X"` for sharper
   focus, and only read `graphify-out/GRAPH_REPORT.md` for broad
   architecture review.
2. **Read [`principles.md`](principles.md) before any non-trivial
   edit.** It is the difference between "compiles" and "won't surprise
   a future agent".
3. **Read [`workflow.md`](workflow.md) before touching any action
   script.** Those scripts encode the weekly rhythm; the file is the
   only place that map is drawn end-to-end.
4. **Search captured failures.** `ls cache/failures/` — if there's a
   recent `patch_prompt_*.md` related to what you're working on,
   reproduce its test in `test_edge_cases.py` first.

## Repo layout

```
.
├── run                       Bash dispatcher. Every operation is `./run <verb>`.
├── supabase/
│   ├── config.toml           Local Supabase project config.
│   └── migrations/           Canonical schema. SQL only. Append, don't edit.
├── webapp/                   Static SPA (HTML/CSS/JS). No framework, no build.
│   ├── meals.html / app.js          Student form (rating + preference).
│   ├── manage.html / manage.js      On-site-manager page.
│   ├── switch-proposal.html / .js   Coordinator approve/reject screen.
│   └── supabase_client.js           Publishable-anon-key Supabase client.
├── data/
│   ├── dietary_data.py       The dietary taxonomy (used by migrations).
│   └── dietary_keywords.json Negative-keyword fallback shared with the webapp.
├── scripts/
│   ├── support/              Shared modules. Cross-cutting concerns live here.
│   │   ├── database.py            Typed Supabase wrapper (Table, Record, Database).
│   │   ├── schemas.py             Pydantic models. Validate on every I/O.
│   │   ├── records.py             TypedDicts mirroring view shapes.
│   │   ├── compatibility.py       Dietary verdict (mirrored in webapp/app.js).
│   │   ├── email.py               schedule_email — audit-log + SendGrid dispatch.
│   │   ├── inbound.py             InboundMailbox protocol + SupabaseInboundInbox adapter.
│   │   ├── error_handler.py       self_healing_error_handler context manager.
│   │   ├── llm_tools.py           Tool schemas + executor factory for the support-email LLM loop.
│   │   ├── mcp_server.py          Minimal JSON-RPC 2.0 MCP server (stdio) for support tools.
│   │   └── support.py             log, ask_llm, env bootstrap.
│   ├── tools/                Dev/ops tools (not imported as library modules).
│   │   └── run_claude_agent.py    Sandboxed agent harness.
│   ├── actions/              One file per operational goal, grouped by domain.
│   │   ├── dietary/               clarify_dietary, escalate_dietary, parse_dietary_reply, poll_dietary_inbox
│   │   ├── emails/                retry_failed_emails
│   │   ├── orders/                register_orders, send_orders
│   │   ├── caterers/              evaluate_caterers, execute_caterer_switch, cache_pdf
│   │   ├── forms/                 generate_qr, send_qr_emails, send_meals_links
│   │   ├── inbox/                 poll_support_inbox, handle_support_email
│   │   ├── system/                register_edge_case, implement_plan
│   │   └── clear_database.py
│   ├── migrations/           Destructive seed scripts (PDFs/Excel → DB).
│   └── tests/                Pure-in-memory tests (MockDatabase).
├── cache/
│   ├── failures/             Auto-generated failure snapshots + patch prompts.
│   ├── plans/                Edge-case plan JSON files (pending/approved/implemented/failed).
│   ├── resolved/             Moved-here artifacts once a failure is patched by the harness.
│   ├── *.txt                 PDF text extractions for migrations.
│   └── dietary_mappings.json LLM-mapped raw dietary strings → standard names.
├── graphify-out/             Knowledge graph (use `graphify query …`).
├── plans/
│   ├── current/              ← you are here
│   ├── problems/             Open bug tickets / inefficiencies.
│   └── old/                  Historical plans. Reference, may be stale.
└── .old/                     Archive of retired code & docs (e.g. pre-Supabase).
```

## Where new code belongs

Decide first what kind of code it is.

| Kind of change | Where it goes |
|---|---|
| New operational goal (runs from `./run`) | `scripts/actions/<domain>/<verb>.py` + a new case in `./run` |
| Helper used by one script | Stay in that script |
| Helper used by two+ scripts | Move to `scripts/support/<topic>.py` |
| New table / column / constraint | `supabase/migrations/<timestamp>_<desc>.sql` + Pydantic in `schemas.py` + TypedDict in `records.py` + view if many-to-many |
| New dietary-restriction logic | `scripts/support/compatibility.py` *and* `webapp/app.js` (mirror) |
| New webapp page | `webapp/<name>.html` + `<name>.js`; talks to Supabase via `supabase_client.js`. No Python proxy. |
| New test | Mirror the action: `scripts/tests/test_<verb>.py` (flat, no subdirs). Regression for a captured failure: `test_edge_cases.py`. Pipeline/integration tests for the edge-case system: `test_edge_case_pipeline.py`. |
| Anything one-off / exploratory | Don't add it under `scripts/`. Run it from a notebook or a REPL. |

If you're tempted to put a helper "temporarily" in an `actions/` file
because it'll only have one caller for now — don't. Either it belongs in
that file forever, or it belongs in `support/` from day one.

## Working with the database

The contract:

- **Reads** go through `db.<Table>.all(filter=…)` / `.get(id)`. The
  underlying view (e.g. `students_view`) gives you aggregated fields;
  Pydantic validates every row.
- **Writes** go through `.create()` / `.update()` / `.batch_update()` /
  `.delete()` / `.clear()`. The wrapper splits view-only fields from
  the underlying table and writes junction-table rows for you.
- **Filters** are callables: `lambda q: q.gte("date", start).lte("date",
  end)` (replaces Airtable formula strings).
- **Don't bypass the wrapper.** If you need to call the raw Supabase
  client, write the wrapper method first.

The webapp uses `@supabase/supabase-js` directly. There is no Python
proxy — anything the webapp needs must be readable with the
publishable anon key (today: everything; eventually: gated by RLS).

## Running, testing, and deploying

```bash
./run migrate                     # full destructive reseed (dependency order)
./run migrate <resource>          # one table (diet|schools|caterers|contacts|menus|sessions|students|absences|exclusions)
./run orders                      # generate next week's orders, then send
./run orders generate [--dry-run] # generate only
./run orders preview              # log email bodies, don't send
./run caterer evaluate            # rolling-rating check + propose switches
./run caterer switch <id>         # execute an Approved switch
./run forms qr [send]             # generate or email per-session QR codes
./run forms send {parents|students}  # email preference links direct to people
./run dietary clarify              # sweep all caterers for MAYBE items; also runs escalation
./run dietary clarify <caterer>    # same sweep, one named caterer only
./run dietary clarify <caterer> --restriction <name>  # single restriction only
./run dietary escalate            # mark overdue Open/Clarifying requests Escalated + notify coordinator
./run dietary poll [--dry-run]    # drain dietary_inbound_messages, parse replies, run escalation
./run emails retry [--dry-run] [--limit N]  # re-send scheduled_emails rows with status=Failed
./run support poll [--dry-run]    # drain support_inbound_messages, run AI handler for parent emails
./run procedure start-of-term [--dry-run]  # forms send parents --first, then forms qr send
./run procedure weekly [--dry-run]         # orders (generate + send), then caterer evaluate
./run procedure polling [--dry-run]        # support poll, dietary poll, escalate, clarify, emails retry, fix
./run fix [--latest-error|--run-and-heal CMD|...]  # self-healing agent harness
./run edge-case "<description>" [--source manual|email|failure] [--dry-run]  # register a new edge case
./run edge-case --from-failure [--dry-run]  # register latest captured failure as an edge case
./run test [name]                 # full suite or a single test_*.py module
./run script <domain>/<name>      # ad-hoc: scripts/actions/<domain>/<name>.py
```

**Required env in `.env`:**

```
SUPABASE_URL=…
SUPABASE_SERVICE_KEY=…       # service key bypasses RLS for backend scripts
SENDGRID_API_KEY=…           # SendGrid API key for outbound email dispatch
DEV_NOTIFICATION_EMAIL=…     # where escalate_to_dev sends "agent stuck" alerts
COORDINATOR_EMAIL=…          # where notify_coordinator sends dietary escalations
                             # (falls back to DEV_NOTIFICATION_EMAIL if unset)
URL_ORIGIN=https://…         # used in QR codes + preference links
ANTHROPIC_API_KEY=…          # optional, only for LLM-assisted workflows
SENDGRID_INBOUND_VERIFICATION_KEY=… # ECDSA P-256 public key for inbound Edge Functions
APP_DOMAIN=…                 # e.g. padea.com.au; used to construct reply-to addresses
SUPPORT_EMAIL=support@help.<APP_DOMAIN>  # inbound support address; used to validate To: and send replies from
LOG_LEVEL=info               # verbose|info|warning|error
```

**Webapp** auto-deploys to GitHub Pages on push to `main` that changes
`webapp/**` (see `.github/workflows/deploy.yml`).

## Self-healing loop (when something breaks)

1. The script fails (either an exception escaped *or* one or more
   `log.failure(...)` calls fired inside the wrapped block — both
   trigger the same capture). The `self_healing_error_handler` context
   manager wrote `cache/failures/failure_<ts>_<workflow>.json` (state
   snapshot + `logged_failures` list) and
   `patch_prompt_<ts>_<workflow>.md` (preformatted instructions).
2. Reproduce: load the snapshot into `MockDatabase` via
   `populate_mock_db` in `scripts/tests/test_edge_cases.py`. Confirm
   you see the same exception, or the same `log.failure` messages.
3. Patch in the offending module.
4. Run `./run test test_edge_cases` (or the full suite). Must pass.
5. If the patch changes a principle or invariant in `principles.md` /
   `workflow.md`, update those files in the same commit.
6. **Or, if the failure is environmental and you've ruled out a
   logical fix (see `principles.md §2`), escalate**:
   `python scripts/tools/run_claude_agent.py --escalate "<reason>"
   [--suggested-action "<text>"]`. This writes
   `cache/failures/escalation_<id>.md` and best-effort notifies
   `DEV_NOTIFICATION_EMAIL`. Dedupes by failure_id.

The harness `scripts/tools/run_claude_agent.py` automates steps 1–4
under a sandbox (PATH allowlist + edit-path guard + post-edit
revert-on-unauthorized). Invoke it via `./run fix --latest-error` or
`./run fix --run-and-heal "<command>"`.

`./run procedure polling` runs the harness automatically after every
polling cycle. If the harness cannot fix the failure, polling
automatically falls through to `./run edge-case --from-failure
--source failure`, which registers the failure as a human-gated
implementation plan (see *Implementation manager* in `workflow.md`).

## Keeping graphify and docs in sync

- After meaningful code edits, run `graphify update .` (AST-only, no
  API cost) so subsequent agents see the new structure.
- After edits that change a principle, invariant, or workflow step,
  update the relevant file in `plans/current/` *in the same commit*.
  Reviewers should be able to verify "the doc still matches the code"
  from the diff alone.
- Don't write new docs **about** code — write code with good names and
  let graphify expose it. These three files exist for what graphify
  can't see.
