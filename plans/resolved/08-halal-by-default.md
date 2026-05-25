# 08 — "All non-pork meals are halal" is a brittle assumption

**Severity:** Medium (correctness depends on caterer practices).
**File:** `scripts/migrations/caterer_menus.py`.

The migration applies a global rule:

```python
# Apply "Assume all non-pork meals are halal" rule
if "pork" not in item_name.lower():
    dietary_choices.append("Halal")
```

This is a fine pragmatic approximation for the *current* roster of
caterers (the contractually-Halal caterer doesn't serve pork at all,
and the others' non-pork items are halal-enough in practice). It will
become wrong when:

- A non-pork item is cooked with alcohol or non-halal stock.
- A new caterer serves bacon (which is pork-adjacent but the substring
  "pork" doesn't appear).
- A non-pork meat dish is from a non-halal slaughter.

The `register_orders.py` `NEGATIVE_DIETARY_KEYWORDS["No Pork"]` does
include `"bacon"` and `"ham"`, which catches the second case for ordering
filters — but the **migration's `Halal` rule does not**, so an item
named "Bacon Stir-Fry" would be incorrectly tagged Halal in the
database.

### Fix

Make the rule explicit and configurable per caterer (e.g. a checkbox
"Caterer is Halal-certified" on the Caterers table; if set, default
non-pork items to Halal; if not, require explicit tags). Or maintain
a list of pork-related substrings (`pork`, `bacon`, `ham`, `prosciutto`,
…) and check all of them.
