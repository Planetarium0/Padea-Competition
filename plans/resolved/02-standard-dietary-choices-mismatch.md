# 02 — `STANDARD_DIETARY_CHOICES` is missing taxonomy members

**Severity:** High (silent data loss without LLM).
**File:** `scripts/migrations/students.py`.

`students.py` defines:

```python
STANDARD_DIETARY_CHOICES = [
    "Dairy Free", "Gluten Free", "Nut Free", "Vegetarian", "Halal",
    "No Beef", "No Pork", "No Seafood", "No Shellfish", "No Fish",
    "No Red Meat", "Opted out of Catering"
]
```

But `data/dietary_data.py` lists 15 restrictions, including:

- `Vegan`
- `Kosher`
- `Pescatarian`
- `No Lamb`

These four are **missing** from `STANDARD_DIETARY_CHOICES`. The heuristic
fallback `map_dietary_heuristically` never produces them.

So without an LLM key, every Vegan, Kosher, Pescatarian or No-Lamb
student loses their dietary tag silently.

The LLM prompt similarly only lists `STANDARD_DIETARY_CHOICES` as the
allowed targets — so even *with* the key, the LLM will refuse to map a
"Vegan" cell to "Vegan" (because "Vegan" isn't in the schema it's been
told).

### Fix

Either:
- Source `STANDARD_DIETARY_CHOICES` from `all_restriction_names()` in
  `dietary_data.py` so the two stay in sync, or
- Make the migration query the Dietary Restrictions table for the
  current list at runtime.
