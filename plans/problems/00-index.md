# Problems Found

Catalogue of bugs, inefficiencies, inconsistencies and unresolved questions
in the current codebase. Severity is my own assessment — operator should
triage. Strike-through entries are resolved; their notes are kept under
`plans/resolved/` for reference.

| # | Problem | Severity |
|---|---|---|
| 01 | ~~Dietary hierarchy ignored by `register_orders.py`~~ | ~~High~~ |
| 02 | ~~`STANDARD_DIETARY_CHOICES` ≠ full taxonomy~~ | ~~High~~ |
| 03 | ~~`verify_migration.py` checks stale `Meal Feedback` table~~ | ~~High~~ |
| 04 | ~~`./run script verify_migration` doesn't work~~ | ~~Medium~~ |
| 05 | ~~Inconsistent imports in migration scripts~~ | ~~Medium~~ |
| 06 | ~~Schools list duplicated across three files~~ | ~~Medium~~ |
| 07 | ~~Compatibility logic duplicated webapp ↔ register_orders~~ | ~~Medium~~ |
| 08 | ~~Halal-by-default tag rule is brittle~~ | ~~Medium~~ |
| 09 | ~~Exclusion heuristic hard-codes May 2026~~ | ~~Medium~~ |
| 10 | ~~`exclusions.py` always calls LLM (`if key or True:`)~~ | ~~Medium~~ |
| 11 | ~~API key exposed in webapp bundle~~ (now proxied) | ~~High~~ |
| 12 | ~~"Sent" Weekly Order status is misleading~~ | ~~Low~~ |
| 13 | ~~`send_orders.py` `Send Date` is wrong~~ | ~~Low~~ |
| 14 | ~~Region denormalised on Sessions and Caterers~~ | ~~Low~~ |
| 15 | No mid-term enrolment / incremental migration path | Medium |
| 16 | ~~Last-week-fallback never implemented~~ | ~~Low~~ |
| 17 | ~~`gst.md` open question unresolved~~ (price now stored GST-inclusive) | ~~Medium~~ |
| 18 | ~~`diet` resource missing from CLAUDE.md docs~~ | ~~Low~~ |
| 19 | `__init__.py` still missing under `scripts/migrations`, `scripts/actions`, `scripts/tests` | Low |
| 20 | ~~`register_orders` has unused / dead imports + dead code~~ | ~~Low~~ |
| 21 | `Caterer Feedback` loaded by `register_orders.py` but never used inside it | Low |
| 22 | Heuristic contact parser still misses Kenko Sushi House | Low |
| 23 | ~~`order_constraints.py` re-implements `build_lookups`~~ (now imports from register_orders) | ~~Low~~ |
| 24 | ~~`host_webapp.py` uses `os.chdir`~~ (switched to `translate_path`) | ~~Low~~ |
| 25 | ~~Explicit override of medical allergies is a legal/health hazard~~ | ~~High~~ |
| 26 | ~~Shared student picker dropdown allows pranks~~ | ~~Medium~~ |
| 27 | ~~Swapped orders cause lunch line confusion and waste~~ | ~~Medium~~ |
| 28 | `MIN_SESSIONS = 0` disables caterer-switch sanity floor | Medium |
| 29 | No idempotency on outbound email queueing — re-runs duplicate emails | Medium |
| 30 | `EmailStatus` literal includes `Send Immediately` but Airtable schema doesn't | Medium |
| 31 | `send_orders.py` processes every Weekly Order with `Week Start >= TODAY()` | Low |
| 32 | `host_webapp.py` startup hint and `qr` URL helper point at `./run qr` (correct cmd is `./run forms qr`) | Low |

See individual files for detail and suggested fixes.
