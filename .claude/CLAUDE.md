# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

This project is part of a larger set of projects aimed at fixing bottlenecks in a tutoring business (Padea).
Schools partner with Padea to run weekly, small-group tutoring sessions on their campus after hours. Families enrol at the start of each term, so largely the same students attend every session that term (ignoring absences and rare mid-term enrolments). Each session includes a restaurant-catered dinner break in the middle.
Padea contracts external caterers to cook and deliver individually boxed meals (one per student) to each session. The order should arrive 5–10 minutes before the dinner break so the on-site manager can set up the meals with the delivery driver’s help.
The on-site manager may collect feedback and share it with us. The on-site manager is usually the same on a given day at a given school each week (e.g. Mondays at ACME School), though this can change on one-off occasions. The caterer may contact the on-site manager’s mobile to confirm arrival, report being late, or ask for help finding the
session location (building and room).
Each Thursday, our program coordinator emails each caterer an order for the following week’s meals, picking a few items off the caterer’s menu and making an educated guess at the best meals and quantities of each meal.
Students often tell us the selected meals don’t match their taste preferences. Food quality also tends to decline over time with each caterer. Ordering meals is tedious for the program coordinator – and will become a bottleneck for the business.

This project is aimed at fixing this bottleneck - solving the problem from order to delivery.

## Python scripting

You are building on an arch linux system with an externally managed environment. If installing packages with pip you must use the system package manager or install locally with `pip install --user --break-system-packages [package]`

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Self-Healing & Agent-Ready Architecture Standards

1. **Strict Data Validation (Pydantic Layer)**:
   - All runtime Airtable data reads and writes must pass through the validation models defined in `scripts/support/schemas.py`.
   - Never rely solely on static Typings/TypedDict for data loaded at active runtime boundaries.

2. **Automated State Capture & AI Prompting**:
   - Wrap entrypoints of all active, recurring workflows in the `self_healing_error_handler` context manager (from `support` module).
   - This handler serializes the localized database context and stack traces to `cache/failures/failure_<timestamp>.json`, and auto-generates a pre-formatted self-healing instruction prompt `cache/failures/patch_prompt_<timestamp>.md`.
   - If you encounter a new failure JSON and prompt, load the state snapshot directly using the regression suite.

3. **Regression Testing**:
   - Write edge-case regression tests in `scripts/tests/test_edge_cases.py`.
   - Before pushing or marking a task complete, **you MUST run the full test suite** using `./run test` and ensure all tests pass.

4. **Documentation Guidelines**:
   - After modifying core logic, you **MUST** review and update the documentation under `plans/current/` (e.g. reflecting updated constraints, abstractions, or workflows). Single-use localized edge cases do not need separate plan documentation unless they alter system-wide contracts.

5. **Good Coding Practices**:
   - Implement descriptive log levels, robust error assertions, type-safe fallback assignments, and defense-in-depth bounds checking.

