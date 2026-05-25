"""
Shared dietary-compatibility logic.

Used by:
  - scripts/actions/register_orders.py  (meal assignment + min-qty swaps)
  - scripts/tests/order_constraints.py  (opted-out / eligibility check)

The webapp implements the same algorithm in JS at
`webapp/app.js -> buildHierarchyMaps + checkCompatibility`. The two
implementations must agree, since:
  - A meal the webapp lets a student pick must also pass the order
    generator's check (otherwise the explicit-preference override is the
    only thing protecting it from a fallback swap).
  - A meal the order generator assigns to a non-respondent must be one the
    student could legitimately have picked themselves.

Both runtimes read the keyword fallback from `data/dietary_keywords.json`
so there is exactly one source of truth. Closure rules come from the live
`Dietary Restrictions` table (its self-link `Supersets`).
"""

import json
from pathlib import Path

_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "dietary_keywords.json"

# Name-keyword fallback. If a menu item's *name* contains any of these
# substrings, treat that as definite evidence it violates the constraint.
# Loaded from the shared JSON file at import time.
with open(_KEYWORDS_PATH, encoding="utf-8") as _f:
    NEGATIVE_KEYWORDS = json.load(_f)["negative_keywords"]

OPTED_OUT = "Opted out of Catering"


def build_hierarchy(dietary_restrictions):
    """Pre-compute lookups from a list of Dietary Restriction records.

    Each record looks like {"id": ..., "fields": {"Restriction Name": ...,
    "Supersets": [parent_ids]}}. A restriction lists its less-restrictive
    parents; for compatibility we want the inverse — the set of restrictions
    whose tags would satisfy a given constraint (the subset closure).

    Returns:
        {
          "id_to_name":     {record_id: name},
          "name_to_id":     {name: record_id},
          "subset_closure": {record_id: set(record_ids)},  # includes itself
        }
    """
    id_to_name = {}
    name_to_id = {}
    children   = {}  # parent_id -> [subset child ids]
    for r in dietary_restrictions:
        rid  = r["id"]
        name = r["fields"].get("Restriction Name", "")
        id_to_name[rid] = name
        if name:
            name_to_id[name] = rid
        for parent_id in (r["fields"].get("Supersets") or []):
            children.setdefault(parent_id, []).append(rid)

    def descendants(rid, acc):
        if rid in acc:
            return acc
        acc.add(rid)
        for c in children.get(rid, []):
            descendants(c, acc)
        return acc

    subset_closure = {r["id"]: descendants(r["id"], set()) for r in dietary_restrictions}
    return {
        "id_to_name":     id_to_name,
        "name_to_id":     name_to_id,
        "subset_closure": subset_closure,
    }


def resolve_dietary_names(dietary_ids, hierarchy):
    """Convert dietary record IDs to their restriction-name strings."""
    id_to_name = hierarchy["id_to_name"]
    return [id_to_name.get(did, did) for did in (dietary_ids or [])]


def has_opted_out(dietary_ids, hierarchy):
    """True if any of the student's dietary IDs is the 'Opted out of Catering' tag."""
    return OPTED_OUT in resolve_dietary_names(dietary_ids, hierarchy)


def is_item_compatible(item_fields, student_dietary_ids, hierarchy):
    """Check that a menu item can be assigned to a student with the given
    Dietary Requirement IDs. Algorithm (matches the webapp):

      1. Opted out short-circuits to False.
      2. For each constraint, satisfied if any of the item's Dietary Tags
         is in the constraint's subset-closure (e.g. a Vegan-tagged item
         satisfies Vegetarian, Pescatarian, No Red Meat, ...).
      3. Otherwise fall back to NEGATIVE_KEYWORDS against the item *name*.
         A keyword match means "definitely contains" -> False. No keyword
         match means "may contain" — treated as compatible here for the
         same lenient behaviour the webapp groups under the "maybe" badge.
    """
    if not student_dietary_ids:
        return True

    id_to_name     = hierarchy["id_to_name"]
    subset_closure = hierarchy["subset_closure"]

    item_tag_ids    = set(item_fields.get("Dietary Tags") or [])
    item_name_lower = item_fields.get("Menu Item Name", "").lower()

    for req_id in student_dietary_ids:
        req_name = id_to_name.get(req_id, "")
        if req_name == OPTED_OUT:
            return False
        closure = subset_closure.get(req_id, {req_id})
        if item_tag_ids & closure:
            continue
        for kw in NEGATIVE_KEYWORDS.get(req_name, ()):
            if kw in item_name_lower:
                return False
    return True
