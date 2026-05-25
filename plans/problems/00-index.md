# Problems Found

Catalogue of bugs, inefficiencies, inconsistencies and unresolved questions
found while writing the `plans/current/` summary. Severity is my own
assessment — operator should triage.

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
| 10 | `exclusions.py` always calls LLM (`if key or True:`) | Medium |
| 11 | API key exposed in webapp bundle | High |
| 12 | "Sent" Weekly Order status is misleading | Low |
| 13 | ~~`send_orders.py` `Send Date` is wrong~~ | ~~Low~~ |
| 14 | Region denormalised on Sessions and Caterers | Low |
| 15 | No mid-term enrolment / incremental migration path | Medium |
| 16 | Last-week-fallback never implemented | Low |
| 17 | `gst.md` open question unresolved | Medium |
| 18 | `diet` resource missing from CLAUDE.md docs | Low |
| 19 | No `__init__.py` in `data`, `migrations`, etc. | Low |
| 20 | `register_orders` has unused / dead imports + dead code | Low |
| 21 | Order-generator caterer-feedback rating loaded but unused | Low |
| 22 | Heuristic contact parser still misses Kenko Sushi House | Low |
| 23 | `order_constraints.py` re-implements `build_lookups` | Low |
| 24 | `host_webapp.py` uses `os.chdir` (process-wide side effect) | Low |

See individual files for detail and suggested fixes.
