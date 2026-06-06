import { describe, test, expect } from 'vitest'
import {
  buildHierarchyMaps, checkCompatibility,
  buildVariantMap, bestVariantSeverity,
} from '../public/js/shared/diet.js'

// ── Fixture data ──────────────────────────────────────────────────────────────
//
// Hierarchy (superset_ids lists the less-restrictive parent):
//   No Red Meat  ←  Vegetarian  ←  Vegan
//   (root)           (child)        (grandchild)
//
// So subsetClosure('nrm')  = {nrm, veg, vegan}
//    subsetClosure('veg')  = {veg, vegan}
//    subsetClosure('vegan')= {vegan}
//    supersetClosure('vegan') = {vegan, veg, nrm}

const RESTRICTIONS = [
  { id: 'nrm',   name: 'No Red Meat',           superset_ids: [] },
  { id: 'veg',   name: 'Vegetarian',             superset_ids: ['nrm'] },
  { id: 'vegan', name: 'Vegan',                  superset_ids: ['veg'] },
  { id: 'gf',    name: 'Gluten Free',            superset_ids: [] },
  { id: 'opted', name: 'Opted out of Catering',  superset_ids: [] },
]

const maps = buildHierarchyMaps(RESTRICTIONS)

// ── buildHierarchyMaps ────────────────────────────────────────────────────────

describe('buildHierarchyMaps', () => {
  test('builds idToName and nameToId mappings', () => {
    expect(maps.idToName['veg']).toBe('Vegetarian')
    expect(maps.nameToId['Vegetarian']).toBe('veg')
    expect(maps.idToName['gf']).toBe('Gluten Free')
  })

  test('subset closure includes self and more-restrictive descendants', () => {
    // Vegetarian closure = {Vegetarian, Vegan}
    expect(maps.subsetClosure['veg'].has('veg')).toBe(true)
    expect(maps.subsetClosure['veg'].has('vegan')).toBe(true)
    expect(maps.subsetClosure['veg'].has('nrm')).toBe(false)
  })

  test('subset closure of root includes entire subtree', () => {
    expect(maps.subsetClosure['nrm'].has('nrm')).toBe(true)
    expect(maps.subsetClosure['nrm'].has('veg')).toBe(true)
    expect(maps.subsetClosure['nrm'].has('vegan')).toBe(true)
  })

  test('subset closure of leaf node is just itself', () => {
    expect([...maps.subsetClosure['vegan']]).toEqual(['vegan'])
  })

  test('superset closure includes self and less-restrictive ancestors', () => {
    // Vegan superset closure = {Vegan, Vegetarian, No Red Meat}
    expect(maps.supersetClosure['vegan'].has('vegan')).toBe(true)
    expect(maps.supersetClosure['vegan'].has('veg')).toBe(true)
    expect(maps.supersetClosure['vegan'].has('nrm')).toBe(true)
  })

  test('superset closure of root node is just itself', () => {
    expect([...maps.supersetClosure['nrm']]).toEqual(['nrm'])
  })

  test('legendTagIdSet is empty by default', () => {
    expect(maps.legendTagIdSet.size).toBe(0)
  })

  test('negativeKeywords are preserved from argument', () => {
    const kws = { Vegetarian: ['chicken', 'beef'] }
    const m = buildHierarchyMaps(RESTRICTIONS, kws)
    expect(m.negativeKeywords['Vegetarian']).toEqual(['chicken', 'beef'])
  })

  test('unrelated hierarchies are independent', () => {
    // GF has no relation to the meat hierarchy
    expect(maps.subsetClosure['gf'].has('veg')).toBe(false)
    expect(maps.supersetClosure['gf'].has('nrm')).toBe(false)
  })
})

// ── checkCompatibility — no requirements ──────────────────────────────────────

describe('checkCompatibility — no requirements', () => {
  test('always ok with empty requirements', () => {
    const item = { name: 'Beef burger', dietary_tag_ids: [] }
    const result = checkCompatibility(item, [], maps)
    expect(result.severity).toBe('ok')
    expect(result.compatible).toBe(true)
    expect(result.issues).toHaveLength(0)
  })
})

// ── checkCompatibility — tag matching ─────────────────────────────────────────

describe('checkCompatibility — tag matching', () => {
  test('exact tag match → ok', () => {
    const item = { name: 'Veg salad', dietary_tag_ids: ['veg'] }
    expect(checkCompatibility(item, ['veg'], maps).severity).toBe('ok')
  })

  test('more-restrictive tag satisfies less-restrictive requirement', () => {
    // Vegan-tagged item satisfies a Vegetarian requirement
    const item = { name: 'Tofu bowl', dietary_tag_ids: ['vegan'] }
    expect(checkCompatibility(item, ['veg'], maps).severity).toBe('ok')
  })

  test('more-restrictive tag satisfies grandparent requirement', () => {
    // Vegan tag satisfies No Red Meat requirement (two levels up)
    const item = { name: 'Tofu bowl', dietary_tag_ids: ['vegan'] }
    expect(checkCompatibility(item, ['nrm'], maps).severity).toBe('ok')
  })

  test('less-restrictive tag does not satisfy more-restrictive requirement', () => {
    // Vegetarian-tagged item does NOT satisfy a Vegan requirement
    const item = { name: 'Cheese pizza', dietary_tag_ids: ['veg'] }
    const result = checkCompatibility(item, ['vegan'], maps)
    expect(result.severity).not.toBe('ok')
  })

  test('unrelated tag does not satisfy requirement', () => {
    const item = { name: 'GF beef patty', dietary_tag_ids: ['gf'] }
    expect(checkCompatibility(item, ['veg'], maps).severity).not.toBe('ok')
  })

  test('all requirements satisfied by tags → ok', () => {
    const item = { name: 'GF vegan bowl', dietary_tag_ids: ['vegan', 'gf'] }
    expect(checkCompatibility(item, ['veg', 'gf'], maps).severity).toBe('ok')
  })

  test('one unsatisfied requirement among many → not ok', () => {
    // GF is satisfied, Vegetarian is not
    const item = { name: 'GF chicken', dietary_tag_ids: ['gf'] }
    const result = checkCompatibility(item, ['veg', 'gf'], maps)
    expect(result.severity).not.toBe('ok')
    expect(result.issues).toHaveLength(1)
  })
})

// ── checkCompatibility — opted out ────────────────────────────────────────────

describe('checkCompatibility — Opted out of Catering', () => {
  test('opted-out requirement is skipped entirely', () => {
    const item = { name: 'Anything', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['opted'], maps).severity).toBe('ok')
  })

  test('opted-out alongside real requirement still checks the real one', () => {
    const item = { name: 'Beef stew', dietary_tag_ids: [] }
    const result = checkCompatibility(item, ['opted', 'veg'], maps)
    // Only the Vegetarian issue should appear
    expect(result.issues.every(i => i.name !== 'Opted out of Catering')).toBe(true)
    expect(result.issues.some(i => i.name === 'Vegetarian')).toBe(true)
  })
})

// ── checkCompatibility — keyword heuristic ────────────────────────────────────

describe('checkCompatibility — keyword heuristic (no legend)', () => {
  const kws = { Vegetarian: ['beef', 'chicken'] }
  const mapsKws = buildHierarchyMaps(RESTRICTIONS, kws)

  test('item name matches keyword → severity no', () => {
    const item = { name: 'Beef stew', dietary_tag_ids: [] }
    const result = checkCompatibility(item, ['veg'], mapsKws)
    expect(result.severity).toBe('no')
    expect(result.issues[0].label).toMatch(/Contains/)
  })

  test('keyword match is case-insensitive', () => {
    const item = { name: 'CHICKEN curry', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['veg'], mapsKws).severity).toBe('no')
  })

  test('keyword match on substring', () => {
    const item = { name: 'Beefburger', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['veg'], mapsKws).severity).toBe('no')
  })

  test('no keyword match and no legend → maybe', () => {
    const item = { name: 'Mystery soup', dietary_tag_ids: [] }
    const result = checkCompatibility(item, ['veg'], mapsKws)
    expect(result.severity).toBe('maybe')
    expect(result.issues[0].label).toMatch(/May contain/)
  })

  test('keyword for one requirement does not affect another', () => {
    // Only Vegetarian keywords defined; GF requirement should still be "maybe"
    const item = { name: 'Beef pasta', dietary_tag_ids: [] }
    const result = checkCompatibility(item, ['veg', 'gf'], mapsKws)
    const vegIssue = result.issues.find(i => i.name === 'Vegetarian')
    const gfIssue  = result.issues.find(i => i.name === 'Gluten Free')
    expect(vegIssue.severity).toBe('no')
    expect(gfIssue.severity).toBe('maybe')
  })
})

// ── checkCompatibility — legend-based definite no ─────────────────────────────

describe('checkCompatibility — legend (caterer declares what they label)', () => {
  // Caterer's legend includes Vegetarian — meaning they tag all vegetarian items.
  // An untagged item therefore definitely contains meat.
  const mapsLegend = buildHierarchyMaps(RESTRICTIONS)
  mapsLegend.legendTagIdSet = new Set(['veg'])

  test('untagged item, requirement ancestor in legend → no', () => {
    const item = { name: 'Unknown dish', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['vegan'], mapsLegend).severity).toBe('no')
  })

  test('same requirement, exact tag present → ok', () => {
    const item = { name: 'Tofu bowl', dietary_tag_ids: ['vegan'] }
    expect(checkCompatibility(item, ['vegan'], mapsLegend).severity).toBe('ok')
  })

  test('legend ancestor not relevant to the requirement → falls back to maybe', () => {
    // GF requirement, legend only covers Vegetarian — unrelated
    const item = { name: 'Wheat pasta', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['gf'], mapsLegend).severity).toBe('maybe')
  })

  test('legend only applies when the legend tag is an ancestor of the requirement', () => {
    // Legend has Vegetarian (veg). No Red Meat (nrm) is a root — its superset closure
    // is just {nrm}. Since veg is a descendant of nrm (not an ancestor), the legend
    // check does not fire, and we fall back to maybe.
    const item = { name: 'Unknown dish', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['nrm'], mapsLegend).severity).toBe('maybe')
  })

  test('tagged item is ok even when other items would be blocked by legend', () => {
    const item = { name: 'Veggie burger', dietary_tag_ids: ['veg'] }
    expect(checkCompatibility(item, ['nrm'], mapsLegend).severity).toBe('ok')
  })
})

// ── checkCompatibility — issues shape ─────────────────────────────────────────

describe('checkCompatibility — issues shape', () => {
  test('one issue per unmet requirement', () => {
    const item = { name: 'Pasta', dietary_tag_ids: [] }
    const result = checkCompatibility(item, ['veg', 'gf'], maps)
    expect(result.issues).toHaveLength(2)
  })

  test('issue has name, severity, and label fields', () => {
    const item = { name: 'Pasta', dietary_tag_ids: [] }
    const { issues } = checkCompatibility(item, ['veg'], maps)
    expect(issues[0]).toHaveProperty('name')
    expect(issues[0]).toHaveProperty('severity')
    expect(issues[0]).toHaveProperty('label')
  })

  test('overall severity is "no" when any issue is "no"', () => {
    const kws = { Vegetarian: ['beef'] }
    const m = buildHierarchyMaps(RESTRICTIONS, kws)
    const item = { name: 'Beef pasta', dietary_tag_ids: [] }
    // Veg → no (keyword), GF → maybe (no keyword)
    expect(checkCompatibility(item, ['veg', 'gf'], m).severity).toBe('no')
  })

  test('overall severity is "maybe" when all issues are "maybe"', () => {
    const item = { name: 'Mystery pasta', dietary_tag_ids: [] }
    expect(checkCompatibility(item, ['veg', 'gf'], maps).severity).toBe('maybe')
  })

  test('compatible is true iff severity is ok', () => {
    const ok   = checkCompatibility({ name: 'Tofu', dietary_tag_ids: ['vegan'] }, ['veg'], maps)
    const notOk = checkCompatibility({ name: 'Pasta', dietary_tag_ids: [] }, ['veg'], maps)
    expect(ok.compatible).toBe(true)
    expect(notOk.compatible).toBe(false)
  })
})

// ── buildVariantMap ───────────────────────────────────────────────────────────

describe('buildVariantMap', () => {
  const items = [
    { id: 'burger',     name: 'Burger',          is_variant: false, variant_of_id: null },
    { id: 'burger-gf',  name: 'Burger (GF)',      is_variant: true,  variant_of_id: 'burger' },
    { id: 'burger-veg', name: 'Burger (Veg)',     is_variant: true,  variant_of_id: 'burger' },
    { id: 'salad',      name: 'Salad',            is_variant: false, variant_of_id: null },
  ]
  const vm = buildVariantMap(items)

  test('groups both variants under their parent id', () => {
    expect(vm['burger']).toHaveLength(2)
    expect(vm['burger'].map(i => i.id)).toContain('burger-gf')
    expect(vm['burger'].map(i => i.id)).toContain('burger-veg')
  })

  test('non-variant parents are not keys', () => {
    expect(vm['salad']).toBeUndefined()
  })

  test('variant with no variant_of_id is silently ignored', () => {
    const orphan = [{ id: 'x', is_variant: true, variant_of_id: null }]
    expect(buildVariantMap(orphan)).toEqual({})
  })

  test('empty item list → empty map', () => {
    expect(buildVariantMap([])).toEqual({})
  })
})

// ── bestVariantSeverity ───────────────────────────────────────────────────────

describe('bestVariantSeverity', () => {
  const veganItem = { name: 'Burger (Vegan)', dietary_tag_ids: ['vegan'] }
  const gfItem    = { name: 'Burger (GF)',    dietary_tag_ids: ['gf'] }
  const plainItem = { name: 'Burger',         dietary_tag_ids: [] }

  const kws = { Vegetarian: ['beef'], 'Gluten Free': ['wheat'] }
  const mapsKws = buildHierarchyMaps(RESTRICTIONS, kws)

  test('no variants → parent severity unchanged', () => {
    expect(bestVariantSeverity('no', [], ['veg'], maps)).toBe('no')
    expect(bestVariantSeverity('maybe', [], ['veg'], maps)).toBe('maybe')
    expect(bestVariantSeverity('ok', [], ['veg'], maps)).toBe('ok')
  })

  test('no requirements → parent severity unchanged', () => {
    expect(bestVariantSeverity('no', [veganItem], [], maps)).toBe('no')
  })

  test('null maps → parent severity unchanged', () => {
    expect(bestVariantSeverity('no', [veganItem], ['veg'], null)).toBe('no')
  })

  test('one compatible variant → ok regardless of parent severity', () => {
    // Vegan variant satisfies Vegetarian requirement
    expect(bestVariantSeverity('no', [veganItem], ['veg'], maps)).toBe('ok')
  })

  test('ok variant short-circuits: stops after first ok found', () => {
    expect(bestVariantSeverity('no', [veganItem, plainItem], ['veg'], maps)).toBe('ok')
  })

  test('maybe variant upgrades no → maybe', () => {
    // Plain item has no tags and no keywords → maybe (not no)
    expect(bestVariantSeverity('no', [plainItem], ['veg'], maps)).toBe('maybe')
  })

  test('no variant leaves no unchanged', () => {
    // wheatItem name matches 'wheat' keyword for Gluten Free → no
    const wheatItem = { name: 'Wheat bun', dietary_tag_ids: [] }
    expect(bestVariantSeverity('no', [wheatItem], ['gf'], mapsKws)).toBe('no')
  })

  test('multiple variants: best result wins', () => {
    // beef variant → no, plain → maybe; best is maybe
    const beefItem = { name: 'Beef burger', dietary_tag_ids: [] }
    expect(bestVariantSeverity('no', [beefItem, plainItem], ['veg'], mapsKws)).toBe('maybe')
  })
})

// ── buildHierarchyMaps — DB-driven display fields ─────────────────────────────

describe('buildHierarchyMaps — tag_short and constraint_phrase from DB', () => {
  const RESTRICTIONS_WITH_DISPLAY = [
    { id: 'gf',  name: 'Gluten Free', superset_ids: [], tag_short: 'GF',    constraint_phrase: 'gluten' },
    { id: 'veg', name: 'Vegetarian',  superset_ids: [], tag_short: 'Veg',   constraint_phrase: 'meat' },
    { id: 'sf',  name: 'Soy Free',    superset_ids: [], tag_short: 'SF',    constraint_phrase: 'soy' },
    { id: 'new', name: 'No Almonds',  superset_ids: [], tag_short: null,    constraint_phrase: null },
  ]
  const m = buildHierarchyMaps(RESTRICTIONS_WITH_DISPLAY)

  test('tagShortByName uses tag_short from DB', () => {
    expect(m.tagShortByName['Gluten Free']).toBe('GF')
    expect(m.tagShortByName['Soy Free']).toBe('SF')
  })

  test('tagShortByName falls back to restriction name when tag_short is null', () => {
    expect(m.tagShortByName['No Almonds']).toBe('No Almonds')
  })

  test('constraintPhraseByName uses constraint_phrase from DB', () => {
    expect(m.constraintPhraseByName['Gluten Free']).toBe('gluten')
    expect(m.constraintPhraseByName['Soy Free']).toBe('soy')
  })

  test('constraintPhraseByName falls back to lowercased name when constraint_phrase is null', () => {
    expect(m.constraintPhraseByName['No Almonds']).toBe('no almonds')
  })

  test('checkCompatibility label uses constraint_phrase from maps', () => {
    const item = { name: 'Bread', dietary_tag_ids: [] }
    const { issues } = checkCompatibility(item, ['gf'], m)
    expect(issues[0].label).toBe('May contain gluten')
    expect(issues[0].phrase).toBe('gluten')
  })

  test('checkCompatibility label falls back gracefully for null constraint_phrase', () => {
    const item = { name: 'Mixed nuts', dietary_tag_ids: [] }
    const { issues } = checkCompatibility(item, ['new'], m)
    expect(issues[0].label).toBe('May contain no almonds')
  })
})
