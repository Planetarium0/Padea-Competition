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

## Migrate

All data setup goes through `migrate`. `schema` syncs the Airtable schema
against `data/schema.py`; the resource subcommands import source data.

```bash
./run migrate schema         # idempotent — diffs schema.py against Airtable
                             # creates missing tables/fields, renames orphans
                             # to '(deleted) X' for human deletion
```

Safe to run any time — never destroys data. Run once before the first migration,
and again whenever `data/schema.py` changes.

```bash
./run migrate                # full clean-slate import (all migrations, dependency order)
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

## Forms

`forms` covers everything to do with getting the meal preference form into
students' and parents' hands — QR codes and direct email links.

```bash
# Generate QR code PNGs (one per session) in output/qrcodes/
./run forms qr                                   # file:// codes (host machine only)
./run forms qr --origin http://192.168.1.5:8000  # phone-scannable (LAN)
./run forms qr --base-url https://meals.padea.com.au  # public URL
./run forms qr --session "Loreto College - Friday"    # single session

# Email QR codes to on-site managers
./run forms qr send
./run forms qr send --dry-run

# Email meal preference links directly to parents or students
./run forms send parents
./run forms send students
./run forms send parents --immediate   # send now rather than queuing
./run forms send parents --dry-run
```

## Caterer management

```bash
./run caterer evaluate              # assess rolling ratings, generate switch proposals
./run caterer evaluate --dry-run    # print proposals without writing to Airtable

./run caterer switch <proposal_id>  # execute an approved switch proposal
./run caterer switch <proposal_id> --dry-run
```

## Webapp

```bash
./run host                       # serve webapp/ on 0.0.0.0:8000 (default)
./run host --port 9000           # alternate port
```

Prints both `http://localhost:<port>/index.html` and a LAN URL. The LAN
URL is what the QR codes need to encode.

## Verification

```bash
# Post-migration sanity check
python scripts/tests/verify_migration.py

# Post-order constraints (min-qty + session totals)
python scripts/tests/order_constraints.py

# Full test suite
./run test
./run test test_register_orders
```

## Quick reference

| Action | Command |
|---|---|
| Help | `./run help` |
| Sync schema | `./run migrate schema` |
| Full migration | `./run migrate` |
| Weekly orders | `./run orders` |
| Host webapp | `./run host` |
| Generate QR codes | `./run forms qr --origin <url>` |
| Run any actions/ script | `./run script <name>` |
| Manual REPL | `python -i -c "import sys; sys.path.insert(0,'scripts'); import support as s"` |

## Cron targets (planned, not yet automated)

The intent — *not currently implemented* — is to schedule:

| When | What |
|---|---|
| Wed 8 PM | `register_orders.py` |
| Thu 3 PM | `send_orders.py` |

The Airtable automation watching `Scheduled Emails` runs continuously
on Airtable's side once the email row appears.
