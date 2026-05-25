# 14 — `Region` denormalised across three tables

**Severity:** Low  
**Resolved:** 2026-05-25

`Sessions.Region` removed from `data/schema.py` and from the `sessions.py` migration.
`Schools.Region` is the source of truth; `Caterers.Region` is intentionally separate (a caterer serves a region, which may differ from any one school's region).

Any code needing a session's region should follow the `Session → School → Region` link.
