"""
Shared dietary-compatibility logic.

Used by:
  - scripts/actions/register_orders.py  (meal assignment + min-qty swaps)
  - scripts/tests/order_constraints.py  (opted-out / eligibility check)

The webapp implements the same algorithm in JS at
``webapp/app.js -> buildHierarchyMaps + checkCompatibility``. The two
implementations must agree, since:
  - A meal the webapp lets a student pick must also pass the order
    generator's check (otherwise the explicit-preference override is the
    only thing protecting it from a fallback swap).
  - A meal the order generator assigns to a non-respondent must be one the
    student could legitimately have picked themselves.

Both runtimes read the keyword fallback from ``data/dietary_keywords.json``
so there is exactly one source of truth. Closure rules come from the live
``Dietary Restrictions`` table (its self-link ``Supersets``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .database import Record
from .records import DietaryRestrictionFields, MenuItemFields

_KEYWORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "dietary_keywords.json"

# Name-keyword fallback. If a menu item's *name* contains any of these
# substrings, treat that as definite evidence it violates the constraint.
# Loaded from the shared JSON file at import time.
with open(_KEYWORDS_PATH, encoding="utf-8") as _f:
    NEGATIVE_KEYWORDS: dict[str, list[str]] = json.load(_f)["negative_keywords"]

OPTED_OUT = "Opted out of Catering"


@dataclass(frozen=True)
class DietaryHierarchy:
    """Pre-computed lookup tables built from the Dietary Restrictions table.

    A restriction lists its less-restrictive parents; for compatibility we
    want the inverse — the set of restrictions whose tags would satisfy a
    given constraint (the subset closure).
    """

    id_to_name: dict[str, str] = field(default_factory=dict)
    name_to_id: dict[str, str] = field(default_factory=dict)
    subset_closure: dict[str, set[str]] = field(default_factory=dict)
    # superset_closure[X] = X ∪ all transitive supersets (less-restrictive ancestors).
    # Used to detect definite incompatibility when a caterer's Dietary Legend
    # explicitly tracks an ancestor restriction and the item is missing it.
    superset_closure: dict[str, set[str]] = field(default_factory=dict)


def build_hierarchy(
    dietary_restrictions: Iterable[Record[DietaryRestrictionFields]],
) -> DietaryHierarchy:
    """Build a :class:`DietaryHierarchy` from a list of restriction records."""
    restrictions = list(dietary_restrictions)
    id_to_name: dict[str, str] = {}
    name_to_id: dict[str, str] = {}
    children: dict[str, list[str]] = {}  # parent_id -> [subset child ids]
    parents: dict[str, list[str]] = {}   # rid -> [parent/superset ids]

    for r in restrictions:
        rid = r.id
        name = r.fields.get("Restriction Name", "")
        id_to_name[rid] = name
        if name:
            name_to_id[name] = rid
        supersets = list(r.fields.get("Supersets") or [])
        parents[rid] = supersets
        for parent_id in supersets:
            children.setdefault(parent_id, []).append(rid)

    def descendants(rid: str, acc: set[str]) -> set[str]:
        if rid in acc:
            return acc
        acc.add(rid)
        for c in children.get(rid, []):
            descendants(c, acc)
        return acc

    def ancestors(rid: str, acc: set[str]) -> set[str]:
        if rid in acc:
            return acc
        acc.add(rid)
        for p in parents.get(rid, []):
            ancestors(p, acc)
        return acc

    subset_closure = {r.id: descendants(r.id, set()) for r in restrictions}
    superset_closure = {r.id: ancestors(r.id, set()) for r in restrictions}
    return DietaryHierarchy(
        id_to_name=id_to_name,
        name_to_id=name_to_id,
        subset_closure=subset_closure,
        superset_closure=superset_closure,
    )


def resolve_dietary_names(
    dietary_ids: Iterable[str] | None,
    hierarchy: DietaryHierarchy,
) -> list[str]:
    """Convert dietary record IDs to their restriction-name strings."""
    return [hierarchy.id_to_name.get(did, did) for did in (dietary_ids or [])]


def has_opted_out(
    dietary_ids: Iterable[str] | None,
    hierarchy: DietaryHierarchy,
) -> bool:
    """True if any of the student's dietary IDs is the 'Opted out of Catering' tag."""
    return OPTED_OUT in resolve_dietary_names(dietary_ids, hierarchy)


def is_item_compatible(
    item_fields: MenuItemFields,
    student_dietary_ids: Iterable[str] | None,
    hierarchy: DietaryHierarchy,
    caterer_legend_tag_ids: Iterable[str] | None = None,
) -> bool:
    """Check that a menu item can be assigned to a student with the given
    Dietary Requirement IDs. Algorithm (matches the webapp):

      1. Opted out short-circuits to False.
      2. For each constraint, satisfied if any of the item's Dietary Tags
         is in the constraint's subset-closure (e.g. a Vegan-tagged item
         satisfies Vegetarian, Pescatarian, No Red Meat, ...).
      3. If the caterer's Dietary Legend explicitly tracks a transitive
         superset of the constraint (e.g. VO → Vegetarian covers Vegan too)
         and the item lacks any satisfying tag for that superset, the item
         is DEFINITELY incompatible — not merely "may contain". This
         converts "maybe" to "no" for legend-tracked restrictions.
      4. Otherwise fall back to NEGATIVE_KEYWORDS against the item *name*.
         A keyword match means "definitely contains" -> False. No keyword
         match means "may contain" — treated as compatible here for the
         same lenient behaviour the webapp groups under the "maybe" badge.
    """
    dietary_ids = list(student_dietary_ids or [])
    if not dietary_ids:
        return True

    item_tag_ids = set(item_fields.get("Dietary Tags") or [])
    item_name_lower = item_fields.get("Menu Item Name", "").lower()
    legend_ids = set(caterer_legend_tag_ids or [])

    for req_id in dietary_ids:
        req_name = hierarchy.id_to_name.get(req_id, "")
        if req_name == OPTED_OUT:
            return False
        closure = hierarchy.subset_closure.get(req_id, {req_id})
        if item_tag_ids & closure:
            continue

        if legend_ids:
            for ancestor_id in hierarchy.superset_closure.get(req_id, {req_id}):
                if ancestor_id not in legend_ids:
                    continue
                ancestor_closure = hierarchy.subset_closure.get(ancestor_id, {ancestor_id})
                if not (item_tag_ids & ancestor_closure):
                    return False

        for kw in NEGATIVE_KEYWORDS.get(req_name, ()):
            if kw in item_name_lower:
                return False
    return True
