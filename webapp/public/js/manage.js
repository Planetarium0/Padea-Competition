/**
 * manage.js — Student dietary & meal management.
 *
 * URL modes:
 *   ?manager=<id>  — on-site manager: sees all their sessions, can update
 *                    dietary requirements, meal preference, and today's order.
 *   ?student=<id>  — parent / guardian: can update dietary requirements only.
 *
 * No login or submission lockout — this page is access-controlled by the
 * obscurity of the link (manager ID or student ID embedded in the URL).
 */

"use strict";

import { supabase } from './shared/supabase_client.js'
import { TAG_SHORT, CONSTRAINT_PHRASE, buildHierarchyMaps, checkCompatibility, buildVariantMap, bestVariantSeverity } from './shared/diet.js'
import { escapeHtml, toast, showError, openConfirm, closeConfirm, confirmModalYes, confirmModalNo } from './shared/ui.js'

// ── URL params ────────────────────────────────────────────────────────────────
const _p = new URLSearchParams(location.search);
const MANAGER_ID = _p.get("manager");
const STUDENT_ID = _p.get("student");
const IS_MANAGER = !!MANAGER_ID;

// Display order for the dietary checkboxes.
const DIET_DISPLAY_ORDER = [
  "Gluten Free", "Dairy Free", "Nut Free",
  "Vegan", "Vegetarian", "Pescatarian",
  "Halal", "Kosher",
  "No Red Meat", "No Beef", "No Pork", "No Lamb",
  "No Seafood", "No Fish", "No Shellfish",
  "Opted out of Catering",
];

const OPTED_OUT_NAME = "Opted out of Catering";
const ALL_VIEWS = ["session-picker", "student-picker", "edit", "meals", "done", "error"];

// ── State ─────────────────────────────────────────────────────────────────────
let sessions        = [];           // [{id, label, day, catererIds, incomingCatererIds}]
let selectedSession = null;
let studentList     = [];           // [{id, name}] for current session
let filteredStudents = [];

let studentId   = STUDENT_ID || null;
let studentName = "";
let allRestrictions = [];           // [{id, name, superset_ids}]
let initialDietIds  = new Set();
let checkedDietIds  = new Set();

let menuItems   = [];               // [{id, name, dietary_tag_ids, is_variant, variant_of_id, ...}]
let variantMap  = {};               // parentId → [variantItem, ...]
let legendTagIds = [];
let dietMaps    = null;             // built once restrictions + neg-keywords are loaded

let mealPickerTarget     = null;    // "preference" | "override"
let initialPrefItemId    = null;
let selectedPrefItemId   = null;
let todayOrderItemId     = null;    // current assigned meal for today
let selectedOverrideItemId = null;
let hasExistingOrder     = false;

let variantModalSelected = null;

// ── In-memory cache (per page load) ──────────────────────────────────────────
const _cache = Object.create(null);
const cacheGet = k => Object.prototype.hasOwnProperty.call(_cache, k) ? _cache[k] : null;
const cacheSet = (k, v) => { _cache[k] = v; };

// ── Utility ───────────────────────────────────────────────────────────────────

function eqSets(a, b) {
  if (a.size !== b.size) return false;
  for (const v of a) if (!b.has(v)) return false;
  return true;
}

// ── Views ─────────────────────────────────────────────────────────────────────
function showView(name) {
  for (const v of ALL_VIEWS) {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== name);
  }
}


// ── Data loaders ──────────────────────────────────────────────────────────────
let _restrictionsP = null;
let _negKwP        = null;

function loadRestrictions() {
  if (_restrictionsP) return _restrictionsP;
  _restrictionsP = supabase.from('dietary_restrictions_view').select('*').then(({ data }) => {
    allRestrictions = data || [];
    return allRestrictions;
  });
  return _restrictionsP;
}

function loadNegativeKeywords() {
  if (_negKwP) return _negKwP;
  _negKwP = fetch('./data/dietary_keywords.json', { cache: 'no-cache' })
    .then(r => r.json())
    .then(d => d.negative_keywords || {})
    .catch(() => ({}));
  return _negKwP;
}

async function ensureDietMaps() {
  if (dietMaps) return dietMaps;
  const [rs, kws] = await Promise.all([loadRestrictions(), loadNegativeKeywords()]);
  dietMaps = buildHierarchyMaps(rs, kws);
  return dietMaps;
}

async function loadManagerSessions(managerId) {
  const { data } = await supabase
    .from('sessions_view')
    .select('*, schools(name)')
    .eq('on_site_manager_id', managerId);
  const DAY_ORDER = { Monday: 0, Tuesday: 1, Wednesday: 2, Thursday: 3, Friday: 4 };
  return (data || [])
    .map(sess => ({
      id: sess.id,
      label: `${sess.day} — ${sess.schools?.name || '?'}`,
      day: sess.day,
      catererIds: sess.caterer_id ? [sess.caterer_id] : [],
      incomingCatererIds: sess.incoming_caterer_id ? [sess.incoming_caterer_id] : [],
    }))
    .sort((a, b) => (DAY_ORDER[a.day] ?? 99) - (DAY_ORDER[b.day] ?? 99));
}

async function loadSessionStudentsAll(sessionId) {
  const { data } = await supabase
    .from('students')
    .select('id, name, student_sessions!inner(session_id)')
    .eq('student_sessions.session_id', sessionId);
  return (data || [])
    .map(s => ({ id: s.id, name: s.name || '(no name)' }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// ── Initialisation ────────────────────────────────────────────────────────────
async function init() {
  if (!MANAGER_ID && !STUDENT_ID) { showView("error"); return; }

  // Start loading restrictions immediately — needed in both modes.
  loadRestrictions();

  if (IS_MANAGER) {
    document.getElementById("topbar-label").textContent = "Manager";
    showView("session-picker");
    await _loadManagerSessions();
  } else {
    await loadEditForm(STUDENT_ID, false);
  }
}

// ── Manager: session list ─────────────────────────────────────────────────────
async function _loadManagerSessions() {
  try {
    sessions = await loadManagerSessions(MANAGER_ID);
  } catch {
    showError("Could not load your sessions. Check your link or try again.");
    return;
  }
  const loading = document.getElementById("session-loading");
  const list    = document.getElementById("session-list");
  const empty   = document.getElementById("session-empty");
  loading.classList.add("hidden");
  if (!sessions.length) { empty.classList.remove("hidden"); return; }
  list.innerHTML = sessions.map(s =>
    `<li onclick="mgr.selectSession(${JSON.stringify(s.id)})">${escapeHtml(s.label)}</li>`
  ).join("");
  list.classList.remove("hidden");
}

async function selectSession(sessId) {
  selectedSession = sessions.find(s => s.id === sessId);
  document.getElementById("session-picker-title").textContent =
    selectedSession ? selectedSession.label : "Students";
  document.getElementById("student-search").value = "";
  showView("student-picker");

  const loading = document.getElementById("student-loading");
  const list    = document.getElementById("student-list");
  const empty   = document.getElementById("student-empty");
  loading.classList.remove("hidden");
  list.classList.add("hidden");
  empty.classList.add("hidden");

  try {
    studentList = await loadSessionStudentsAll(sessId);
  } catch {
    showError("Could not load students for this session.");
    loading.classList.add("hidden");
    return;
  }
  loading.classList.add("hidden");
  filteredStudents = studentList;
  renderStudentList();
}

function backToSessions() { showView("session-picker"); }

function filterStudents(query) {
  const q = query.trim().toLowerCase();
  filteredStudents = q ? studentList.filter(s => s.name.toLowerCase().includes(q)) : studentList;
  renderStudentList();
}

function renderStudentList() {
  const list  = document.getElementById("student-list");
  const empty = document.getElementById("student-empty");
  if (!filteredStudents.length) {
    list.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = studentList.length ? "No matching student." : "No students in this session.";
    return;
  }
  empty.classList.add("hidden");
  list.innerHTML = filteredStudents.map(s =>
    `<li onclick="mgr.selectStudent(${JSON.stringify(s.id)}, ${JSON.stringify(s.name)})">${escapeHtml(s.name)}</li>`
  ).join("");
  list.classList.remove("hidden");
}

async function selectStudent(sId, name) {
  studentId   = sId;
  studentName = name;
  await loadEditForm(sId, true);
}

function changeStudent() {
  studentId              = null;
  selectedPrefItemId     = null;
  selectedOverrideItemId = null;
  hasExistingOrder       = false;
  todayOrderItemId       = null;
  document.getElementById("student-search").value = "";
  filteredStudents = studentList;
  renderStudentList();
  showView("student-picker");
}

// ── Edit form ─────────────────────────────────────────────────────────────────
async function loadEditForm(sId, isManager) {
  showView("edit");

  // Reset per-student state.
  initialDietIds         = new Set();
  checkedDietIds         = new Set();
  initialPrefItemId      = null;
  selectedPrefItemId     = null;
  todayOrderItemId       = null;
  selectedOverrideItemId = null;
  hasExistingOrder       = false;

  document.getElementById("diet-loading").classList.remove("hidden");
  document.getElementById("diet-list").classList.add("hidden");
  document.getElementById("pref-card").classList.add("hidden");
  document.getElementById("order-card").classList.add("hidden");
  document.getElementById("save-btn").disabled = true;

  if (isManager) {
    document.getElementById("identity-row").classList.remove("hidden");
    document.getElementById("edit-student-name").textContent = studentName || sId;
  } else {
    document.getElementById("identity-row").classList.add("hidden");
  }

  try {
    const [{ data: studentData }, _restrictions] = await Promise.all([
      supabase.from('students_view').select('*').eq('id', sId).single(),
      loadRestrictions(),
    ]);

    if (!studentData) throw new Error('Student not found');

    studentName = studentData.name || sId;
    if (isManager) {
      document.getElementById("edit-student-name").textContent = studentName;
    } else {
      document.getElementById("topbar-label").textContent = studentName;
    }

    const dietIds = studentData.dietary_requirement_ids || [];
    initialDietIds = new Set(dietIds);
    checkedDietIds = new Set(dietIds);
    renderDietList();

    if (isManager) {
      initialPrefItemId  = studentData.meal_preference_id || null;
      selectedPrefItemId = initialPrefItemId;

      const catId = (selectedSession.incomingCatererIds[0] || selectedSession.catererIds[0]) || null;
      if (catId) {
        document.getElementById("pref-card").classList.remove("hidden");
        loadMenu(catId);     // async — updates trigger label when done
      }
      loadTodayOrder(sId, selectedSession.id);   // async — shows card when order exists
    }
  } catch (e) {
    showError(`Could not load student data: ${e.message}`);
  }
}

// ── Dietary checkboxes ────────────────────────────────────────────────────────
function renderDietList() {
  document.getElementById("diet-loading").classList.add("hidden");
  const container = document.getElementById("diet-list");
  container.classList.remove("hidden");

  const sorted = [...allRestrictions].sort((a, b) => {
    const ai = DIET_DISPLAY_ORDER.indexOf(a.name);
    const bi = DIET_DISPLAY_ORDER.indexOf(b.name);
    if (ai === -1 && bi === -1) return a.name.localeCompare(b.name);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });

  container.innerHTML = sorted.map(r => {
    const checked   = checkedDietIds.has(r.id) ? "checked" : "";
    const optedOut  = r.name === OPTED_OUT_NAME ? " diet-item--opted-out" : "";
    return `<label class="diet-item${optedOut}">
      <input type="checkbox" class="diet-checkbox"
             data-id="${escapeHtml(r.id)}" data-name="${escapeHtml(r.name)}"
             ${checked} onchange="mgr.toggleDiet(this)" />
      <span class="diet-name">${escapeHtml(r.name)}</span>
    </label>`;
  }).join("");
}

function toggleDiet(checkbox) {
  const id   = checkbox.dataset.id;
  const name = checkbox.dataset.name;
  if (checkbox.checked) checkedDietIds.add(id);
  else                  checkedDietIds.delete(id);

  if (name === OPTED_OUT_NAME && IS_MANAGER) {
    const optedOut = checkbox.checked;
    document.getElementById("pref-card").classList.toggle(
      "hidden", optedOut || !selectedSession || !(selectedSession.incomingCatererIds[0] || selectedSession.catererIds[0])
    );
    document.getElementById("order-card").classList.toggle("hidden", optedOut || !hasExistingOrder);
  }
  updateSaveBtn();
}

// ── Menu loading ──────────────────────────────────────────────────────────────
async function loadMenu(catId) {
  setPrefTrigger("Loading menu…", "");
  document.getElementById("pref-trigger").disabled = true;
  try {
    const cached = cacheGet(`menu:${catId}`);
    let items, catData;
    if (cached) {
      ({ items, catData } = cached);
    } else {
      const [menuResult, legendResult] = await Promise.all([
        supabase.from('menu_items_view').select('*').eq('caterer_id', catId),
        supabase.from('caterer_legend_tags').select('restriction_id').eq('caterer_id', catId),
      ]);
      items   = menuResult.data || [];
      catData = { legendTagIds: (legendResult.data || []).map(r => r.restriction_id) };
      cacheSet(`menu:${catId}`, { items, catData });
    }
    menuItems    = items;
    variantMap   = buildVariantMap(items);
    legendTagIds = catData.legendTagIds || [];

    const maps = await ensureDietMaps();
    maps.legendTagIdSet = new Set(legendTagIds);

    document.getElementById("pref-trigger").disabled = false;
    updatePrefTrigger();
  } catch {
    setPrefTrigger("Could not load menu", "");
  }
}

function setPrefTrigger(label, name) {
  document.getElementById("pref-trigger-label").textContent = label;
  document.getElementById("pref-trigger-name").textContent  = name;
}

function updatePrefTrigger() {
  if (!selectedPrefItemId) { setPrefTrigger("Tap to choose a meal", ""); return; }
  const item = menuItems.find(m => m.id === selectedPrefItemId);
  item
    ? setPrefTrigger("Currently selected", item.name || "—")
    : setPrefTrigger("Tap to choose a meal", "");
}

function setOrderTrigger(label, name) {
  document.getElementById("order-trigger-label").textContent = label;
  document.getElementById("order-trigger-name").textContent  = name;
}

function updateOrderTrigger() {
  if (!selectedOverrideItemId) { setOrderTrigger("Choose a different meal…", ""); return; }
  const item = menuItems.find(m => m.id === selectedOverrideItemId);
  setOrderTrigger("Override to", item ? item.name || "—" : "—");
}

// ── Today's order ─────────────────────────────────────────────────────────────
async function loadTodayOrder(sId, sessId) {
  try {
    const today = new Date().toISOString().slice(0, 10);
    const { data } = await supabase
      .from('order_students')
      .select('orders!inner(id, date, session_id, menu_item_id, menu_items(id, name, menu_item_dietary_tags(restriction_id)))')
      .eq('student_id', sId)
      .eq('orders.session_id', sessId)
      .eq('orders.date', today)
      .maybeSingle();

    if (!data?.orders) return;
    const order = data.orders;
    hasExistingOrder = true;
    todayOrderItemId = order.menu_item_id;

    const isOptedOut = [...checkedDietIds].some(id => {
      const r = allRestrictions.find(r => r.id === id);
      return r && r.name === OPTED_OUT_NAME;
    });
    if (isOptedOut) return;

    const mealName = order.menu_items?.name || '(unnamed)';
    const mealTags = (order.menu_items?.menu_item_dietary_tags || []).map(t => t.restriction_id);

    document.getElementById("order-meal-name").textContent = mealName;
    document.getElementById("order-meal-tags").innerHTML = mealTags.map(tid => {
      const name = allRestrictions.find(r => r.id === tid)?.name;
      return name ? `<span class="tag">${escapeHtml(TAG_SHORT[name] || name)}</span>` : "";
    }).join("");
    document.getElementById("order-card").classList.remove("hidden");
  } catch {
    // No order today — keep card hidden.
  }
}

// ── Meal picker ───────────────────────────────────────────────────────────────
function openMealPicker(target) {
  mealPickerTarget = target;
  document.getElementById("meals-sub").textContent = target === "override"
    ? "Select a different meal for today's session."
    : "Select next week's meal preference.";
  showView("meals");
  renderMealList();
}

function closeMealPicker() { showView("edit"); }

function renderMealList() {
  const ul      = document.getElementById("meals-list");
  const loading = document.getElementById("meals-loading");
  const empty   = document.getElementById("meals-empty");

  if (!menuItems.length || !dietMaps) {
    loading.classList.remove("hidden");
    ul.classList.add("hidden");
    empty.classList.add("hidden");
    // Retry once data arrives.
    Promise.all([_restrictionsP, _negKwP].filter(Boolean)).then(
      () => { if (document.getElementById("view-meals").classList.contains("hidden")) return; renderMealList(); }
    );
    return;
  }
  loading.classList.add("hidden");

  const activeDietIds = [...checkedDietIds].filter(id => {
    const r = allRestrictions.find(r => r.id === id);
    return r && r.name !== OPTED_OUT_NAME;
  });

  const currentId = mealPickerTarget === "override"
    ? (selectedOverrideItemId || todayOrderItemId)
    : selectedPrefItemId;

  const displayItems = menuItems.filter(i => !i.is_variant);
  const compat = [], maybe = [], incompat = [];

  for (const item of displayItems) {
    const r       = checkCompatibility(item, activeDietIds, dietMaps);
    const variants = variantMap[item.id] || [];
    const eff     = bestVariantSeverity(r.severity, variants, activeDietIds, dietMaps);
    if      (eff === "ok")    compat.push({ item, result: r });
    else if (eff === "maybe") maybe.push({ item, result: r });
    else                      incompat.push({ item, result: r });
  }

  function renderRow({ item, result }) {
    const name     = item.name || "—";
    const tagIds   = item.dietary_tag_ids || [];
    const tagsHtml = tagIds.map(tid => {
      const tName = dietMaps.idToName[tid];
      return tName ? `<span class="tag">${escapeHtml(TAG_SHORT[tName] || tName)}</span>` : "";
    }).join("");

    const variants    = variantMap[item.id] || [];
    const hasVariants = variants.length > 0;
    const selected    = item.id === currentId || variants.some(v => v.id === currentId);
    const blocked     = (hasVariants ? [item, ...variants] : [item]).every(
      o => checkCompatibility(o, activeDietIds, dietMaps).severity === "no"
    );
    const sev = result.severity;
    const eff = hasVariants ? bestVariantSeverity(sev, variants, activeDietIds, dietMaps) : sev;

    const reasonText = (blocked || (!hasVariants && result.issues.length))
      ? result.issues.map(i => i.label).join(" · ") : "";
    const reasonHtml = reasonText
      ? `<div class="meal-reason meal-reason-${blocked ? "blocked" : sev}">${escapeHtml(reasonText)}</div>` : "";
    const variantNote = hasVariants && !blocked
      ? (sev !== "ok" && eff !== "no" ? "Dietary variant available" : "Options available") : "";
    const variantNoteHtml = variantNote
      ? `<div class="meal-variant-note">${variantNote}</div>` : "";

    // Managers can pick anything, but get a confirmation modal for conflicts.
    const onclick = hasVariants
      ? `mgr.openVariantPicker(${JSON.stringify(item.id)})`
      : `mgr.selectMeal(${JSON.stringify(item.id)}, ${JSON.stringify(sev)})`;

    const klass = ["meal-item",
      selected  ? "selected"     : "",
      blocked   ? "blocked"      : "",
      eff === "no"    ? "incompatible" : "",
      eff === "maybe" ? "maybe"        : "",
    ].filter(Boolean).join(" ");

    return `<li class="${klass}" onclick="${onclick}">
      <div class="meal-radio"></div>
      <div class="meal-content">
        <div class="meal-name">${escapeHtml(name)}</div>
        ${reasonHtml}${variantNoteHtml}
        <div class="meal-tags">${tagsHtml}</div>
      </div>
    </li>`;
  }

  let html = compat.map(renderRow).join("");
  if (maybe.length)   html += `<li class="meal-divider">Possibly compatible</li>` + maybe.map(renderRow).join("");
  if (incompat.length) html += `<li class="meal-divider">Doesn't match student's requirements</li>` + incompat.map(renderRow).join("");

  if (!html) {
    ul.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = "No meals found for this caterer.";
    return;
  }
  ul.innerHTML = html;
  ul.classList.remove("hidden");
  empty.classList.add("hidden");
}

function selectMeal(itemId, severity) {
  if (severity === "no") {
    openConfirm({
      title: "Override dietary restriction?",
      body: "This meal doesn't match the student's requirements. Assign it anyway?",
      confirmLabel: "Assign anyway",
      onConfirm: () => { closeConfirm(); commitMealSelection(itemId); },
    });
    return;
  }
  if (severity === "maybe") {
    openConfirm({
      title: "Possible conflict",
      body: "This meal may not match the student's requirements. Assign it anyway?",
      confirmLabel: "Assign anyway",
      onConfirm: () => { closeConfirm(); commitMealSelection(itemId); },
    });
    return;
  }
  commitMealSelection(itemId);
}

function commitMealSelection(itemId) {
  if (mealPickerTarget === "preference") {
    selectedPrefItemId = itemId;
    updatePrefTrigger();
  } else {
    selectedOverrideItemId = itemId;
    updateOrderTrigger();
  }
  updateSaveBtn();
  showView("edit");
}

// ── Variant picker ────────────────────────────────────────────────────────────
function openVariantPicker(parentId) {
  const parent   = menuItems.find(i => i.id === parentId);
  if (!parent) return;
  const variants    = variantMap[parentId] || [];
  const allOptions  = [parent, ...variants];
  const activeDietIds = [...checkedDietIds].filter(id => {
    const r = allRestrictions.find(r => r.id === id);
    return r && r.name !== OPTED_OUT_NAME;
  });
  const currentId = mealPickerTarget === "override"
    ? (selectedOverrideItemId || todayOrderItemId) : selectedPrefItemId;

  let selectedId = allOptions.some(o => o.id === currentId) ? currentId : parentId;
  if (dietMaps && activeDietIds.length && !allOptions.some(o => o.id === currentId)) {
    const compatible = allOptions.filter(
      o => checkCompatibility(o, activeDietIds, dietMaps).severity === "ok"
    );
    if (compatible.length === 1) selectedId = compatible[0].id;
  }
  variantModalSelected = selectedId;

  document.getElementById("variant-options").innerHTML = allOptions.map(item => {
    const { severity, issues } = dietMaps
      ? checkCompatibility(item, activeDietIds, dietMaps)
      : { severity: "ok", issues: [] };
    const name     = item.name || "—";
    const tagIds   = item.dietary_tag_ids || [];
    const tagsHtml = tagIds.map(tid => {
      const tName = dietMaps?.idToName[tid];
      return tName ? `<span class="tag">${escapeHtml(TAG_SHORT[tName] || tName)}</span>` : "";
    }).join("");
    const reasonHtml = issues.length
      ? `<div class="meal-reason meal-reason-${severity}">${escapeHtml(issues.map(i => i.label).join(" · "))}</div>` : "";
    const isSelected = item.id === selectedId;
    const klass = ["variant-option",
      isSelected        ? "selected"     : "",
      severity === "no" ? "incompatible" : severity === "maybe" ? "maybe" : "",
    ].filter(Boolean).join(" ");
    return `<div class="${klass}" data-item-id="${item.id}"
                 onclick="mgr.selectVariantOption(${JSON.stringify(item.id)})">
      <div class="meal-radio"></div>
      <div class="meal-content">
        <div class="meal-name">${escapeHtml(name)}</div>
        ${reasonHtml}
        <div class="meal-tags">${tagsHtml}</div>
      </div>
    </div>`;
  }).join("");

  document.getElementById("variant-modal").classList.remove("hidden");
}

function selectVariantOption(itemId) {
  variantModalSelected = itemId;
  document.querySelectorAll(".variant-option").forEach(el => {
    el.classList.toggle("selected", el.dataset.itemId === itemId);
  });
}

function closeVariantModal() {
  document.getElementById("variant-modal").classList.add("hidden");
  variantModalSelected = null;
}

function confirmVariantModal() {
  const id = variantModalSelected;
  closeVariantModal();
  if (!id) return;
  const item = menuItems.find(i => i.id === id);
  const activeDietIds = [...checkedDietIds].filter(idv => {
    const r = allRestrictions.find(r => r.id === idv);
    return r && r.name !== OPTED_OUT_NAME;
  });
  if (item && dietMaps && activeDietIds.length) {
    const { severity } = checkCompatibility(item, activeDietIds, dietMaps);
    if (severity !== "ok") { selectMeal(id, severity); return; }
  }
  commitMealSelection(id);
}

// ── Dirty check & save button ─────────────────────────────────────────────────
function isDirty() {
  if (!eqSets(initialDietIds, checkedDietIds)) return true;
  if (IS_MANAGER) {
    if (selectedPrefItemId !== initialPrefItemId) return true;
    if (selectedOverrideItemId && selectedOverrideItemId !== todayOrderItemId) return true;
  }
  return false;
}

function updateSaveBtn() {
  document.getElementById("save-btn").disabled = !isDirty();
}

// ── Save ──────────────────────────────────────────────────────────────────────
async function save() {
  const btn = document.getElementById("save-btn");
  btn.disabled = true;
  btn.textContent = "Saving…";

  const ops = [];

  if (!eqSets(initialDietIds, checkedDietIds)) {
    ops.push(saveDietaryRequirements(studentId, [...checkedDietIds]));
  }

  if (IS_MANAGER && selectedPrefItemId !== initialPrefItemId && selectedPrefItemId) {
    ops.push(
      supabase.from('students').update({ meal_preference_id: selectedPrefItemId }).eq('id', studentId)
    );
  }

  if (IS_MANAGER && selectedOverrideItemId && selectedOverrideItemId !== todayOrderItemId) {
    ops.push(overrideOrder(studentId, selectedSession.id, selectedOverrideItemId));
  }

  try {
    await Promise.all(ops);
    initialDietIds     = new Set(checkedDietIds);
    initialPrefItemId  = selectedPrefItemId;
    if (selectedOverrideItemId) {
      todayOrderItemId       = selectedOverrideItemId;
      selectedOverrideItemId = null;
    }
    document.getElementById("done-msg").textContent = "Changes saved successfully.";
    document.getElementById("edit-another-btn").classList.toggle("hidden", !IS_MANAGER);
    showView("done");
  } catch (e) {
    showError(`Save failed: ${e.message}`);
    btn.disabled = false;
    btn.textContent = "Save changes";
  }
}

async function saveDietaryRequirements(sId, restrictionIds) {
  await supabase.from('student_dietary_restrictions').delete().eq('student_id', sId);
  if (restrictionIds.length > 0) {
    await supabase.from('student_dietary_restrictions').insert(
      restrictionIds.map(rid => ({ student_id: sId, restriction_id: rid }))
    );
  }
}

async function overrideOrder(sId, sessId, newMenuItemId) {
  const today = new Date().toISOString().slice(0, 10);
  const { data, error } = await supabase.rpc('override_order', {
    p_student_id: sId,
    p_session_id: sessId,
    p_new_menu_item_id: newMenuItemId,
    p_date: today,
  });
  if (error) throw new Error(error.message);
  return data;
}

function editAnother() {
  studentId              = null;
  selectedPrefItemId     = null;
  selectedOverrideItemId = null;
  hasExistingOrder       = false;
  todayOrderItemId       = null;
  document.getElementById("student-search").value = "";
  filteredStudents = studentList;
  renderStudentList();
  showView("student-picker");
}

// ── Public interface (called from onclick attributes) ─────────────────────────
const mgr = {
  selectSession, backToSessions, filterStudents, selectStudent, changeStudent,
  openMealPicker, closeMealPicker, selectMeal, commitMealSelection,
  openVariantPicker, selectVariantOption, closeVariantModal, confirmVariantModal,
  toggleDiet, save, editAnother,
};

// Expose globals so onclick attributes in HTML work with module scripts.
window.mgr = mgr;
window.confirmModalYes = confirmModalYes;
window.confirmModalNo = confirmModalNo;

init();
