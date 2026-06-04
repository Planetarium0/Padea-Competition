# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## What this project does

Padea runs after-school tutoring sessions at partner high schools. Each
session includes a catered dinner. The program coordinator currently
guesses the weekly meal order by hand from each caterer's menu — students
dislike the picks, food quality drifts silently, and the workflow won't
scale.

**This repo solves the order-to-delivery loop**: students rate today's
caterer and pick next week's meal via a QR-code webapp; non-respondents
get smart fallbacks; the system generates the weekly order, enforces
dietary and minimum-quantity constraints, dispatches the caterer email,
and flags declining caterers so the coordinator only steps in for swaps.

This repo is **one of several Padea-bottleneck projects**; treat anything
not in scope here (e.g. enrolment, payments, tutor scheduling) as
delegated elsewhere.

## How to navigate this codebase

There are two complementary indices. Use them in this order:

1. **`plans/current/`** — design rules, weekly workflow, and the dev
   guide. **Read these first** for any non-trivial change; they hold the
   project's philosophy and invariants, which the code cannot tell you.

   | File | Read when |
   |---|---|
   | [`plans/current/README.md`](../plans/current/README.md) | Orienting; deciding which other doc to read |
   | [`plans/current/principles.md`](../plans/current/principles.md) | Before any non-trivial edit |
   | [`plans/current/workflow.md`](../plans/current/workflow.md) | Touching `scripts/actions/` or the weekly order/feedback/switch flow |
   | [`plans/current/dev-guide.md`](../plans/current/dev-guide.md) | Locating code, deciding where new code belongs, running tests |

2. **`graphify-out/`** — a knowledge graph with god nodes, communities,
   and cross-file relationships. Use it for *behavioural* questions
   (where is X defined? what calls Y? what does Z import?).

   - `graphify query "<question>"` — scoped subgraph, usually much
     smaller than `GRAPH_REPORT.md` or raw grep output.
   - `graphify path "<A>" "<B>"` — relationship between two symbols.
   - `graphify explain "<concept>"` — focused subgraph around one node.
   - `graphify-out/wiki/index.md` (if present) — broad navigation.
   - `graphify-out/GRAPH_REPORT.md` — only for broad architecture review.
   - After meaningful code edits run `graphify update .` (AST-only, no
     API cost) to keep the graph current.

> **Rule of thumb:** if the question is "how does this work / where is
> it?", ask graphify. If the question is "why is it this way / what
> should I do?", read `plans/current/`.

## When to update `plans/current/`

Update **in the same commit as the code change** when you:

- Add, remove, or rename a design principle or invariant
  (`principles.md`).
- Change the weekly workflow, decision points, or actor responsibilities
  (`workflow.md`).
- Change repo layout, `./run` verbs, the testing model, the
  self-healing loop, or where new code belongs (`dev-guide.md`).
- Resolve a "Known gap" — delete the bullet from `principles.md`.
- Discover a new known gap — record it as one line in `principles.md §6`.

Do **not** update `plans/current/` for pure code edits (renames, splits,
new tests, bugfixes that don't change a contract). graphify picks those
up via `graphify update .`.

When in doubt, ask: *will the next agent make a different choice if this
isn't written down?* If yes, write it down here.

## Python environment

All Python work uses the local `.venv/` at the project root (Python 3.13).
Always activate it or invoke it directly:

```bash
source .venv/bin/activate        # activate in shell
.venv/bin/python <script>        # or invoke directly
.venv/bin/pip install <pkg>      # install packages
```

Do not use the system `pip` or `python` — the system environment is
externally managed and packages installed there won't be visible to `.venv/`.
The agent harness (`scripts/tools/run_claude_agent.py`) already prefers
`.venv/` when present.

## Self-healing & agent-ready architecture

Spelled out in full in
[`plans/current/principles.md`](../plans/current/principles.md). Headline
rules:

1. **Validate at every database boundary.** All Supabase reads/writes go
   through `support.Database`, which runs Pydantic models from
   `scripts/support/schemas.py` on every payload. Don't fall back to
   bare TypedDict at runtime boundaries.
2. **Wrap operational entrypoints in `self_healing_error_handler`** with
   a `state_provider` that snapshots the relevant tables. Failures land
   in `cache/failures/failure_<ts>_<workflow>.json` and a
   `patch_prompt_<ts>_<workflow>.md` ready for an AI patcher.
3. **Regress every failure** in `scripts/tests/test_edge_cases.py` using
   `populate_mock_db` on the captured snapshot. Run `./run test` before
   marking work complete.
4. **The sandbox is the contract for agent edits**: file writes are
   restricted to `scripts/`, `supabase/`, `webapp/`, `plans/`; bash to
   a fixed allowlist (see `run_claude_agent.py`).

## Coding standards (enforced — not preferences)

- Type-hint every Python function signature crossing a module boundary.
- Anything that can fail has a unit test. Tests are pure-in-memory
  (`MockDatabase` in `scripts/tests/mock_db.py`); no real Supabase
  calls in the suite.
- One script = one operational goal (`scripts/actions/<domain>/<verb>.py`).
  Helpers used by more than one script move to `scripts/support/`.
- All operations are invoked via `./run` — no ad-hoc paths in docs,
  runbooks, or cron.
- Use `support.log` (and `log.verbose` at level 5); avoid `print`.

## Common operations

```bash
./run migrate                  # full destructive reseed
./run orders                   # generate next week + send caterer emails
./run orders generate --dry-run
./run caterer evaluate         # rolling-rating check + propose switches
./run forms qr [send]          # generate or email per-session QR codes
./run test                     # full suite (pure in-memory)
./run script <domain>/<name>   # ad-hoc: scripts/actions/<domain>/<name>.py
```

Self-healing harness:

```bash
.venv/bin/python scripts/tools/run_claude_agent.py --latest-error
.venv/bin/python scripts/tools/run_claude_agent.py --run-and-heal "./run orders"
```

See [`plans/current/dev-guide.md`](../plans/current/dev-guide.md) for the
full command surface, required env vars, and deployment notes.
