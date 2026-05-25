# Operational Commands

Everything goes through `./run` at the project root. The script lives in
`./run` and is just a thin bash dispatcher.

## Setup once

```bash
# .env at project root (not committed):
AIRTABLE_API_KEY=<personal-access-token>
AIRTABLE_ID=<base-id>
# Optional — enables LLM extraction during migration
CLAUDE_CODE_API_KEY=<...>   # or ANTHROPIC_API_KEY=<...>

# Install deps
pip install pyairtable python-dotenv pandas openpyxl anthropic pypdf qrcode pillow
```

## Schema

```bash
./run schema update          # idempotent — diffs schema.py against Airtable
                             # creates missing tables/fields, renames orphans
                             # to '(deleted) X' for human deletion
```

Safe to run any time — never destroys data.

## Migration

```bash
./run migrate                # full clean-slate import (all 8 migrations)
./run migrate caterers       # single resource
./run migrate diet           # dietary restrictions (lookup table)
./run migrate contacts       # caterer_contacts.py
./run migrate menus          # caterer_menus.py
./run migrate sessions
./run migrate students
./run migrate absences
./run migrate exclusions
./run migrate all            # explicit form of the no-arg version
```

Migration **clears its target table(s) first** — destructive by design.
See `03-migration-pipeline.md`.

```bash
# PDF extraction (run if a resources/*.pdf changes)
python scripts/actions/cache_pdf.py
```

## Orders

```bash
./run orders                       # generate then queue emails
./run orders generate              # write Orders + Draft Weekly Orders
./run orders generate --dry-run    # print summary, don't write to Airtable
./run orders preview               # log emails without queueing
./run orders send                  # queue emails (writes Scheduled Emails)
```

The dry run prints a per-session summary grouped by caterer. Useful
before letting it commit to Airtable.

## Verification

```bash
# Post-migration sanity check (currently has stale table names — see problems)
python scripts/tests/verify_migration.py

# Post-order constraints (min-qty + session totals)
python scripts/tests/order_constraints.py
```

> Note: `./run script verify_migration` is documented in `CLAUDE.md` but
> doesn't actually work — `./run script` looks in `scripts/actions/`, not
> `scripts/tests/`. Run the test scripts with `python` directly.

## Webapp

```bash
./run host                       # serve webapp/ on 0.0.0.0:8000 (default)
./run host --port 9000           # alternate port
```

Prints both `http://localhost:<port>/index.html` and a LAN URL. The LAN
URL is what the QR codes need to encode.

## QR codes

```bash
# Phone-scannable codes (needed for actual on-site use)
./run qr --origin http://192.168.1.5:8000

# Public URL (for a future live deploy)
./run qr --base-url https://meals.padea.com.au

# Local-only (default; only useful on the host machine)
./run qr

# Just one session
./run qr --origin http://... --session "Loreto College - Friday"
```

Output goes to `output/qrcodes/<sanitised-session-id>.png`.

## Where things live

| Action | File |
|---|---|
| Help | `./run help` |
| Run any actions/ script | `./run script <name>` (e.g. `./run script generate_qr`) |
| Single migration | `./run migrate <resource>` |
| Manual REPL | `python -i -c "import sys; sys.path.insert(0,'scripts'); import support as s"` |

## Cron targets (planned, not yet automated)

The intent — *not currently implemented* — is to schedule:

| When | What |
|---|---|
| Wed 8 PM | `register_orders.py` |
| Thu 3 PM | `send_orders.py` |

The Airtable automation watching `Scheduled Emails` runs continuously
on Airtable's side once the email row appears.
