# 07 — Compatibility logic duplicated between webapp and order generator

**Severity:** Medium.
**Files:** `webapp/app.js` (`checkCompatibility`, `NEGATIVE_KEYWORDS`,
`CONSTRAINT_PHRASE`), `scripts/actions/register_orders.py`
(`is_item_compatible`, `NEGATIVE_DIETARY_KEYWORDS`, `POSITIVE_DIETARY_TAGS`).

Two implementations of "is this menu item compatible with this student's
diet" run in different runtimes (JS in the browser, Python in the order
script). They have drifted:

| Aspect | webapp/app.js | register_orders.py |
|---|---|---|
| Uses dietary hierarchy (subset closure) | Yes | No (see #01) |
| Positive-tag check | Implicit via closure | Explicit dict of 5 entries |
| Includes `No Lamb` keywords | Yes | No |
| Includes `Vegan` / `Vegetarian` / `Pescatarian` keyword lists | Yes | No |
| Includes `Halal` keyword block | Yes (`pork, bacon, ham`) | No |
| Includes `Dairy Free` keyword block | Yes | No |
| `bulgogi` listed for No Beef / No Red Meat | Yes | Yes |

The two **must** agree, since:

- A meal the webapp lets a student pick must also be considered safe by
  the order generator (otherwise the explicit-preference override is the
  only thing keeping them from being swapped — see #01 for why this matters).
- A meal the order generator picks for a non-respondent must be one the
  student would have been able to pick themselves (no surprise dietary
  violation in the box on the day).

### Fix

Single source of truth. Options:

- Move keyword/closure data into a JSON file that both runtimes load.
- Generate `app.js` keyword constants from a Python source at build time.
- Push the compatibility logic into a tiny serverless function that
  both runtimes call (overkill for now).

Whichever route, having `register_orders.py` consult the live
`Dietary Restrictions` table (which it already loads) for the hierarchy
removes most of the drift surface in one step.
