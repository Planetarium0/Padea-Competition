# 19 — Missing `__init__.py` in script subdirectories

**Severity:** Low (works today via namespace packages; fragile).
**Directories:** `data/`, `scripts/migrations/`, `scripts/actions/`,
`scripts/tests/`. (Only `scripts/support/` has one.)

Imports like `from data.dietary_data import DIETARY_HIERARCHY`
(`scripts/migrations/dietary_restrictions.py`) work because Python 3.3+
treats packageless directories as **implicit namespace packages**, as
long as the parent is on `sys.path`. The `./run` script adds
`scripts/` to `PYTHONPATH`, so that condition is met.

But:

- Some IDEs / type-checkers refuse to follow implicit namespaces.
- Adding any `__init__.py` *anywhere* in the chain breaks the
  resolution path (the namespace package collapses to a regular package).
- The behaviour is surprising to anyone coming from older Python.

This interacts with #05: half the migrations use `from scripts import …`
which only works under different sys.path circumstances. Making the
package structure explicit makes both styles unambiguous.

### Fix

Add empty `__init__.py` files to `scripts/`, `data/`,
`scripts/migrations/`, `scripts/actions/`, `scripts/tests/`. Update all
imports to a single consistent form (see #05).
