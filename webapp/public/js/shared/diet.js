// Dietary logic shared across meals.js and manage.js.
// Hierarchy computation and meal compatibility checking.

export function buildHierarchyMaps(restrictions, negativeKeywords = {}) {
  const idToName = {};
  const nameToId = {};
  const idToRestr = {};
  for (const r of restrictions) {
    idToName[r.id] = r.name;
    nameToId[r.name] = r.id;
    idToRestr[r.id] = r;
  }
  // Build child map (parentId → [subset childIds]) from each restriction's
  // superset_ids list (a restriction lists its less-restrictive parents).
  const children = {};
  for (const r of restrictions)
    for (const parentId of r.superset_ids) (children[parentId] ||= []).push(r.id);

  // Transitive subset-closure: each restriction → itself + all more-restrictive descendants.
  function descendants(id, acc = new Set()) {
    if (acc.has(id)) return acc;
    acc.add(id);
    for (const c of children[id] || []) descendants(c, acc);
    return acc;
  }
  // Transitive superset-closure: each restriction → itself + all less-restrictive ancestors.
  function ancestors(id, acc = new Set()) {
    if (acc.has(id)) return acc;
    acc.add(id);
    const r = idToRestr[id];
    if (r) for (const parentId of r.superset_ids) ancestors(parentId, acc);
    return acc;
  }
  const subsetClosure = {};
  const supersetClosure = {};
  for (const r of restrictions) {
    subsetClosure[r.id] = descendants(r.id);
    supersetClosure[r.id] = ancestors(r.id);
  }

  // Build display maps from DB fields, falling back to the hardcoded constants.
  const tagShortByName = {};
  const constraintPhraseByName = {};
  for (const r of restrictions) {
    tagShortByName[r.name] = r.tag_short || r.name;
    constraintPhraseByName[r.name] = r.constraint_phrase || r.name.toLowerCase();
  }

  // legendTagIdSet is populated later once the caterer record is fetched.
  return {
    idToName, nameToId, subsetClosure, supersetClosure,
    negativeKeywords, legendTagIdSet: new Set(),
    tagShortByName, constraintPhraseByName,
  };
}

// Returns { compatible, severity, issues } where:
//   compatible  — true if all constraints satisfied by tags
//   severity    — "ok" | "maybe" | "no"
//   issues      — array of { name, severity, label } per unmet constraint
export function checkCompatibility(item, studentReqIds, maps) {
  if (!studentReqIds.length) return { compatible: true, severity: "ok", issues: [] };

  const itemTagIds = item.dietary_tag_ids || [];
  const itemNameLower = (item.name || "").toLowerCase();
  const legendTagIdSet = maps.legendTagIdSet || new Set();

  const issues = [];

  for (const reqId of studentReqIds) {
    const reqName = maps.idToName[reqId];
    if (!reqName || reqName === "Opted out of Catering") continue;

    const closure = maps.subsetClosure[reqId] || new Set([reqId]);
    if (itemTagIds.some(t => closure.has(t))) continue;

    const phrase = maps.constraintPhraseByName?.[reqName] || reqName.toLowerCase();

    // Legend-based definite incompatibility: if a transitive superset of this
    // constraint is in the caterer's Dietary Legend and the item lacks any
    // satisfying tag for that superset, the item DEFINITELY fails this constraint.
    if (legendTagIdSet.size) {
      const ancestorIds = maps.supersetClosure[reqId] || new Set([reqId]);
      let definitelyNo = false;
      for (const ancestorId of ancestorIds) {
        if (!legendTagIdSet.has(ancestorId)) continue;
        const ancestorClosure = maps.subsetClosure[ancestorId] || new Set([ancestorId]);
        if (!itemTagIds.some(t => ancestorClosure.has(t))) {
          definitelyNo = true;
          break;
        }
      }
      if (definitelyNo) {
        issues.push({ name: reqName, severity: "no", label: `Contains ${phrase}`, phrase });
        continue;
      }
    }

    // No legend verdict — fall back to name-keyword heuristic.
    const kws = maps.negativeKeywords?.[reqName];
    if (kws && kws.some(k => itemNameLower.includes(k)))
      issues.push({ name: reqName, severity: "no", label: `Contains ${phrase}`, phrase });
    else
      issues.push({ name: reqName, severity: "maybe", label: `May contain ${phrase}`, phrase });
  }

  if (!issues.length) return { compatible: true, severity: "ok", issues };
  const severity = issues.some(i => i.severity === "no") ? "no" : "maybe";
  return { compatible: false, severity, issues };
}

export function buildVariantMap(items) {
  const map = {};
  for (const item of items)
    if (item.is_variant) {
      const parentId = item.variant_of_id;
      if (parentId) (map[parentId] ||= []).push(item);
    }
  return map;
}

// Returns the best dietary severity across a parent item and its variants,
// so an item with an incompatible parent but a compatible variant isn't
// bucketed into the "doesn't match" section of the meal list.
export function bestVariantSeverity(parentSeverity, variants, reqs, maps) {
  if (!maps || !reqs.length || !variants.length) return parentSeverity;
  let best = parentSeverity;
  for (const v of variants) {
    const { severity } = checkCompatibility(v, reqs, maps);
    if (severity === "ok") return "ok";
    if (severity === "maybe" && best === "no") best = "maybe";
  }
  return best;
}
