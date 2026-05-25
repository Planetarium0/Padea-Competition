# Padea Catering Automation — Project Overview

This folder is the current source of truth for what the project does, why, and how
the pieces fit together. Files are intended to be read in order, but each is
self-contained.

| # | File | Topic |
|---|---|---|
| 00 | overview.md | This file — high-level map of the project |
| 01 | business-context.md | Padea the business and the specific bottleneck being fixed |
| 02 | data-model.md | The Airtable schema (13 tables) and key relationships |
| 03 | migration-pipeline.md | One-shot import of spreadsheets and PDFs → Airtable |
| 04 | webapp.md | Student-facing QR-code form: rating + next-week meal preference |
| 05 | ordering-pipeline.md | Weekly cron: turn preferences into caterer orders + emails |
| 06 | dietary-system.md | Dietary hierarchy, compatibility checks, edge cases |
| 07 | edge-cases.md | Non-obvious behaviour the system handles (and the ones it doesn't) |
| 08 | operational-commands.md | Reference for the `./run` script and the routine ops |
| 09 | unfinished-work.md | What was designed but not built, and what is planned next |

## At a glance

Padea runs weekly after-school tutoring sessions at six partner high schools
around Brisbane. Each session includes a catered dinner. Up to now the program
coordinator has guessed every Thursday at what to order from each caterer for
the following week — students often hate the choices, food quality silently
declines, and the manual workflow doesn't scale.

This project replaces the manual order with a closed loop:

```
Tuesday session     →   QR code → mobile webapp
                        Students rate today's caterer + pick next week's meal
                        ↓
                       (Airtable: Students.Meal Preference, Caterer Feedback)
                        ↓
Wednesday 8 PM      →   register_orders.py   (cron, eventually)
                        Snapshot preferences into Orders; fill gaps; enforce min-qty
                        ↓
                       (Airtable: Weekly Orders, Orders)
                        ↓
Thursday afternoon  →   send_orders.py       (cron, eventually)
                        Format markdown email per caterer → Scheduled Emails
                        ↓
                       (Airtable automation sends actual email)
                        ↓
                        Caterer cooks and delivers, on-site manager receives
```

Today the cron pieces are run manually via `./run orders`. The webapp is hosted
locally (`./run host`) and reached via QR codes (`./run qr`).

## Tech stack

- **Storage**: a single Airtable base (`appTaP4DLPhZJICMH`). All ground-truth
  data lives here; the Python code is just a client.
- **Backend**: Python 3, `pyairtable`, optional Anthropic SDK for LLM-based
  data extraction during migration.
- **Frontend**: hand-written static SPA in `webapp/` (no framework, no build).
  Talks directly to the Airtable REST API with a personal access token.
- **Glue**: a bash script `./run` exposes every common operation.

## Repository layout

```
.
├── run                       # bash entry-point for every operation
├── CLAUDE.md                 # project-level instructions for Claude Code
├── resources/                # source spreadsheets + PDFs (input to migration)
├── cache/                    # PDF→txt extractions + dietary mapping cache
├── output/qrcodes/           # generated QR PNGs (one per session)
├── webapp/                   # static SPA (HTML/CSS/JS + config)
├── scripts/
│   ├── support/              # shared helpers (Airtable client, LLM wrapper)
│   ├── data/                 # static reference data: schema + dietary hierarchy
│   ├── migrations/           # one-per-table importers
│   ├── actions/              # operational scripts (orders, schema, QR, host)
│   └── tests/                # post-migration and post-order verification
├── plans/
│   ├── current/              # this folder
│   ├── problems/             # known bugs and inefficiencies
│   └── old/                  # historical plans, may be out of date
└── graphify-out/             # knowledge-graph index (auto-generated)
```
