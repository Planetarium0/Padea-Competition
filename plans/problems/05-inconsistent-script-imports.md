# 05 — Inconsistent imports in migration scripts

**Severity:** Medium (fragile; relies on implicit sys.path behaviour).
**Files:** `scripts/migrations/caterers.py`, `scripts/migrations/caterer_menus.py`
(use one style); all other migrations use the other style.

Two `support` import styles are used in parallel:

```python
# caterers.py, caterer_menus.py
from scripts import support as s

# absences.py, caterer_contacts.py, dietary_restrictions.py,
# exclusions.py, sessions.py, students.py
import support as s
```

The `./run` script sets `PYTHONPATH=…:./scripts`, which means:

- `import support as s` works because `scripts/` is on the path and
  `support/` is a package within it.
- `from scripts import support` works *only* because the cwd
  (project root) is also implicitly on `sys.path` when running
  `python scripts/migrations/foo.py` from the project root — Python
  picks up `scripts/` as an implicit namespace package.

This is real implementation-defined behaviour and breaks under any of:

- Running from a different cwd.
- Running through a tool that doesn't add cwd (e.g. some launchers).
- Adding `scripts/__init__.py` (would shadow the namespace package).
- Renaming `scripts/`.

### Fix

Pick one style and apply it everywhere. The simpler choice is
`import support as s`, since the `./run` script already arranges for
`scripts/` to be on the path. Then drop the cwd-implicit dependency.

While in there, normalise the `from pathlib import Path` and unused
`import os` lines — several migrations import them and don't use them.
