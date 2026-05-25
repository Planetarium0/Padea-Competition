# 01 — Dietary hierarchy is ignored by `register_orders.py`

**Severity:** High.
**Files:** `scripts/actions/register_orders.py`, `scripts/data/dietary_data.py`.

The webapp builds a subset-closure from the `Dietary Restrictions` table
and uses it for compatibility checks (`webapp/app.js → buildHierarchyMaps`
and `checkCompatibility`). A Vegan-tagged item correctly satisfies any
Vegetarian / Pescatarian / No Red Meat student.

`register_orders.py → is_item_compatible` doesn't do this. It has a
static `POSITIVE_DIETARY_TAGS` dict with only five keys:

```python
POSITIVE_DIETARY_TAGS = {
    "Gluten Free": "Gluten Free",
    "Dairy Free":  "Dairy Free",
    "Nut Free":    "Nut Free",
    "Vegetarian":  "Vegetarian",
    "Halal":       "Halal",
}
```

So:

- A **Vegan** student gets no positive-tag check (because "Vegan" isn't
  in the dict). They can be assigned any non-keyword-blocked item, even
  one with no Vegan/Vegetarian/Dairy Free tag.
- A **Vegetarian** student is only matched against items literally
  tagged "Vegetarian". A "Vegan Stir-Fry" tagged only `Vegan` is
  considered incompatible.
- A **No Red Meat** student is only filtered by name keywords (no
  positive tag side). The hierarchy says a Vegetarian item satisfies
  No Red Meat — this code doesn't.

### Fix

Have `register_orders.py` load the Dietary Restrictions table (which it
already does), build the same subset-closure as the webapp, and replace
`is_item_compatible` with an equivalent hierarchy-aware check.

Centralising the dietary logic in a Python module that both `register_orders`
and `order_constraints` import would also fix the duplication noted in #07.
