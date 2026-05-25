# Dietary System

The most subtle part of the codebase. The webapp (JS) and the order
generator (Python) both have to agree on what counts as a "safe" meal
for a student. They share what they can:

- **Closure** is derived live from Airtable (`Dietary Restrictions.Supersets`).
- **Negative-keyword fallback** is held in `data/dietary_keywords.json` —
  the Python side reads it via `support.compatibility`, the webapp fetches
  it from `/data/dietary_keywords.json` (served by `host_webapp.py`).

## The taxonomy

Defined in `scripts/data/dietary_data.py`. Restrictions form a directed
graph where each node lists its **supersets** — its less-restrictive parents.

```
Vegan
├── Vegetarian
│   ├── Pescatarian
│   │   └── No Red Meat
│   │       ├── No Beef
│   │       ├── No Pork
│   │       └── No Lamb
│   └── No Seafood
│       ├── No Fish
│       └── No Shellfish
└── Dairy Free
Halal       → No Pork
Kosher      → No Pork, No Shellfish

Leaves (no supersets): Dairy Free, Gluten Free, Nut Free,
                       No Beef, No Pork, No Lamb,
                       No Fish, No Shellfish,
                       Opted out of Catering
```

Read `X.supersets = [Y]` as "any item that satisfies X also satisfies Y."

For example:
- A **Vegan** item satisfies Vegetarian, Pescatarian, No Red Meat, No Beef,
  No Pork, No Lamb, Dairy Free.
- A **Halal** item satisfies No Pork.

## Compatibility check (webapp implementation)

`webapp/app.js → buildHierarchyMaps + checkCompatibility`.

1. Build a `subsetClosure` map: for each restriction `R`, the set of all
   restrictions that imply `R` (i.e. anything in the closure of `R`'s
   subset-tree).
2. An item with tags `T` satisfies constraint `C` if `T ∩ closure(C) ≠ ∅`.
3. If no tag confirms it, fall back to name keywords (`NEGATIVE_KEYWORDS`):
   - Match → "Contains X" (definitely incompatible).
   - No match → "May contain X" (ambiguous).

Output is three buckets used by the picker: **ok**, **maybe**, **no**.

## Compatibility check (order generator)

`scripts/support/compatibility.py → is_item_compatible`, used by both
`register_orders.py` and `order_constraints.py`.

Same algorithm as the webapp:

1. Subset-closure satisfied → ok. (`build_hierarchy` over the live
   `Dietary Restrictions` records gives the same closure the webapp computes.)
2. Otherwise fall back to the shared `NEGATIVE_KEYWORDS` table loaded from
   `data/dietary_keywords.json` — keyword match means "definitely incompatible",
   no match means "may contain" (treated as compatible here to match the
   webapp's lenient `maybe` bucket).

## Tag application during migration

`scripts/migrations/caterer_menus.py` applies tags this way:

- Inline codes in the menu text (`GF`, `DF`, `NF`, `VO`) map to
  `Gluten Free`, `Dairy Free`, `Nut Free`, `Vegetarian`.
- A domain rule: any item whose **name** doesn't contain "pork" gets the
  `Halal` tag added automatically.
- No other tag is inferred. If the menu names a dish "Vegan Stir-Fry" but
  doesn't mark it `VO`, it stays untagged.

This means the item-tag set tends to be **sparse**. The shared subset-closure
logic compensates (a Vegetarian tag satisfies Pescatarian and No Red Meat)
for both the webapp and the order generator.

## Student-side: raw strings → tags

`migrations/students.py` collects every unique `Dietary` cell value from
the spreadsheets, batches them to the LLM for translation to standard
restriction names, and caches the result in `cache/dietary_mappings.json`.
The cache is the authoritative override — edit it to fix bad mappings.

Heuristic fallback (`map_dietary_heuristically`) matches keywords. The
heuristic uses `STANDARD_DIETARY_CHOICES` — a 12-item list that is a
**subset** of the 15-item taxonomy in `dietary_data.py`. Vegan, Kosher,
Pescatarian, and No Lamb are missing from the heuristic. Without an LLM
key, students with those raw strings will lose those tags.

## Edge cases worth knowing

### "Opted out of Catering"
A virtual restriction. It's not really a dietary requirement, but it's
modelled as one because students declare it the same way. The system
short-circuits in three places:

- Webapp: locks the whole form.
- `register_orders.py`: skips the student entirely (no order generated).
- `order_constraints.py`: subtracts from the expected eating count.

### Halal-by-default
Every non-pork menu item is tagged Halal automatically. This is correct
for the contracted caterers (the contractually-Halal caterer doesn't
serve pork at all, and the others' non-pork items are halal enough in
practice). It would be wrong in general — alcohol-cooked dishes,
non-halal-slaughtered meat, etc. Keep an eye on it as the caterer set
grows.

### "No Red Meat" includes "bulgogi"
A keyword in `data/dietary_keywords.json → "No Red Meat"` because "Korean
Beef Bulgogi Rice Bowl" was on a caterer's menu but the substring "beef"
wasn't enough. This is brittle — every dish-naming convention is a
landmine.

### Explicit override
A student's explicit `Meal Preference` is honoured *even if* it violates
their declared diet. The assumption is they know best — maybe the
declared diet was a typo, or a temporary preference, or a "I'll cheat
this once" thing. Both webapp and order generator preserve this rule.
