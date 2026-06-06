"""
Hard-coded dietary-restriction hierarchy.

Each restriction lists its *direct* SUPERSETS — i.e. the less-restrictive parents
that this restriction satisfies by being more strict. The Subsets back-link is
auto-created by Airtable.

How to read the relation:
    X.supersets = [Y, ...]   means   X is a subset of Y
                              means   "every item that's X also satisfies Y"

Concretely:
- Vegan is a subset of Vegetarian and Dairy Free  →  any Vegan item satisfies
  a "Vegetarian" or "Dairy Free" constraint.
- Vegetarian is a subset of Pescatarian          →  any Vegetarian item
  satisfies a "Pescatarian" constraint.
- Pescatarian is a subset of No Red Meat         →  any Pescatarian item
  satisfies a "No Red Meat" constraint.

So Vegan transitively satisfies Vegetarian, Pescatarian, No Red Meat, No Beef,
No Pork, No Lamb, and Dairy Free.

For Halal and Kosher we encode their religious meat constraints. A full
treatment of Kosher rules (e.g. no meat+dairy together) is out of scope.
"""

DIETARY_HIERARCHY: list[tuple[str, list[str]]] = [
    # name, direct supersets (less-restrictive parents)
    ("Vegan",         ["Vegetarian", "Dairy Free"]),
    # Pescatarians eat fish, so Vegetarian must reach No Fish / No Shellfish
    # via No Seafood rather than via Pescatarian.
    ("Vegetarian",    ["Pescatarian", "No Seafood"]),
    ("Pescatarian",   ["No Red Meat"]),
    ("No Red Meat",   ["No Beef", "No Pork", "No Lamb"]),
    ("Halal",         ["No Pork"]),
    ("Kosher",        ["No Pork", "No Shellfish"]),
    ("No Seafood",    ["No Fish", "No Shellfish"]),
    # leaves
    ("Dairy Free",    []),
    ("Gluten Free",   []),
    ("Nut Free",      []),
    ("No Beef",       []),
    ("No Pork",       []),
    ("No Lamb",       []),
    ("No Fish",       []),
    ("No Shellfish",  []),
    ("Opted out of Catering", []),
]

# Short display labels shown on meal tags.
TAG_SHORT: dict[str, str] = {
    "Gluten Free":  "GF",
    "Dairy Free":   "DF",
    "Nut Free":     "NF",
    "Vegetarian":   "Veg",
    "Vegan":        "Vegan",
    "Halal":        "Halal",
    "Kosher":       "Kosher",
    "Pescatarian":  "Pesc",
}

# Plain-language phrase for each constraint, used in "Contains X" / "May contain X" labels.
CONSTRAINT_PHRASE: dict[str, str] = {
    "Gluten Free":   "gluten",
    "Dairy Free":    "dairy",
    "Nut Free":      "nuts",
    "Vegetarian":    "meat",
    "Vegan":         "animal products",
    "Pescatarian":   "non-fish meat",
    "Halal":         "non-halal ingredients",
    "Kosher":        "non-kosher ingredients",
    "No Beef":       "beef",
    "No Pork":       "pork",
    "No Lamb":       "lamb",
    "No Fish":       "fish",
    "No Shellfish":  "shellfish",
    "No Seafood":    "seafood",
    "No Red Meat":   "red meat",
}


def all_restriction_names() -> list[str]:
    """Flat list of all restriction names, including those only referenced
    as supersets — so the migration can create every record before linking."""
    names = {name for name, _ in DIETARY_HIERARCHY}
    for _, supers in DIETARY_HIERARCHY:
        names.update(supers)
    return sorted(names)
