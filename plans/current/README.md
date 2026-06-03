# plans/current — Project Brain

This folder is the source-of-truth for **how to think about** the Padea
catering codebase. It does **not** describe what every function does — that
is what [graphify](../../graphify-out/) is for. These docs exist for
context graphify cannot give you: design rules, invariants, the
human/business workflow, and the conventions an agent needs to make good
decisions.

## What to read, when

| You are about to… | Read |
|---|---|
| Make any non-trivial change | [`principles.md`](principles.md) |
| Touch the weekly order / feedback / catering switch flow | [`workflow.md`](workflow.md) |
| Navigate the repo / find code / decide where new code belongs | [`dev-guide.md`](dev-guide.md) |
| Answer a "what does X do?" question | Run `graphify query "<question>"` first; fall back to source. |

If you can't decide whether a question belongs to graphify or to these
docs, ask: *is this about behaviour I could derive from reading code, or
about a rule/intent that lives only in someone's head?* The latter belongs
here.

## When to update these docs

Update **as part of the same change** (not afterwards) whenever you:

- Add, remove, or rename a design principle, invariant, or workflow step.
- Cross a boundary that one of these docs explicitly draws
  (e.g. moving logic between Python and the webapp, changing where the
  source-of-truth for X lives, changing what `./run` exposes).
- Resolve a "known gap" flagged in `principles.md` (delete the bullet).
- Discover a new known gap — record it so the next agent doesn't trip on
  the same thing.

Code-level edits (renaming a function, splitting a module, adding tests)
don't need a doc update — graphify picks those up via `graphify update .`.

## Conventions in this folder

- **Imperative present tense** for rules ("Validate at boundaries", not
  "We should validate…").
- **Cite the file, not the function**, when pointing at code, so the doc
  stays valid across refactors (graphify can resolve the function).
- **One screenful per section**. If a section grows past that, it has
  probably accumulated specifics that belong in graphify, not here.
