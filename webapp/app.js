/**
 * Padea Meals — meal rating + next-week preference webapp.
 *
 * URL params:
 *   session  — Airtable Session record ID (required)
 *   student  — Airtable Student record ID (optional; from personalised QR)
 *
 * Data model (post-iteration-3):
 *   - Students.Dietary Requirements is a multipleRecordLinks → Dietary Restrictions.
 *   - Students.Meal Preference is a multipleRecordLinks → Menu Items (one item).
 *   - Menu Items.Dietary Tags is a multipleRecordLinks → Dietary Restrictions.
 *   - Dietary Restrictions has a 'Supersets' self-link describing the hierarchy
 *     (e.g. Vegetarian.Supersets = [No Red Meat]). An item is compatible with
 *     a constraint C iff one of its tags is in subset-closure(C).
 *   - Meal Selections is gone. Preference is upserted onto Students.Meal Preference.
 *
 * Loading strategy:
 *   - First paint is synchronous (picker or form skeleton) based on URL + localStorage.
 *   - Session, Dietary Restrictions and Menu Items load in parallel in the background.
 *   - The meal picker opens instantly once the menu has arrived.
 */

// ============================================================
// Constants
// ============================================================


// Short labels for badges. Anything not listed falls back to the full name.
const TAG_SHORT = {
  "Gluten Free": "GF",
  "Dairy Free": "DF",
  "Nut Free": "NF",
  "Vegetarian": "Veg",
  "Vegan": "Vegan",
  "Halal": "Halal",
  "Kosher": "Kosher",
  "Pescatarian": "Pesc",
};

// Name-keyword heuristic is loaded from /data/dietary_keywords.json at boot
// (see loadNegativeKeywords) so the order generator and the webapp share one
// source of truth. The resolved object is attached to dietMaps.negativeKeywords.

// Plain-language phrase for each constraint, used in reason labels.
const CONSTRAINT_PHRASE = {
  "Gluten Free": "gluten",
  "Dairy Free": "dairy",
  "Nut Free": "nuts",
  "Vegetarian": "meat",
  "Vegan": "animal products",
  "Pescatarian": "non-fish meat",
  "Halal": "non-halal ingredients",
  "Kosher": "non-kosher ingredients",
  "No Beef": "beef",
  "No Pork": "pork",
  "No Lamb": "lamb",
  "No Fish": "fish",
  "No Shellfish": "shellfish",
  "No Seafood": "seafood",
  "No Red Meat": "red meat",
};

// ============================================================
// API client
// ============================================================

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

// ============================================================
// Cache helpers
// ============================================================

// In-memory cache for API responses — lives only for the current page session.
// TTL and persistence are handled server-side; the client just avoids redundant
// requests within a single visit.
const _memCache = Object.create(null);

function cacheGet(key) {
  return Object.prototype.hasOwnProperty.call(_memCache, key) ? _memCache[key] : null;
}

function cacheSet(key, data) {
  _memCache[key] = data;
}

function cacheBust(key) {
  delete _memCache[key];
}

// localStorage is used only for the student-picker shortcut (persists across visits).
const ls = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { } },
  remove(k) { try { localStorage.removeItem(k); } catch { } },
};

function knownStudentKey(sessionId) { return `padea_known_student_${sessionId}`; }
function getKnownStudent(sessionId) { return ls.get(knownStudentKey(sessionId)); }
function setKnownStudent(sessionId, sid) { ls.set(knownStudentKey(sessionId), sid); }
function clearKnownStudent(sessionId) { ls.remove(knownStudentKey(sessionId)); }

// Device-side lockout — one submission per (session, device, day). Combined
// with the server-side roster filter (Last Submitted == today hides the
// student from the dropdown) this means a student who submits is locked out
// from re-using the form, either from their own device or someone else's.
function submittedKey(sessionId) {
  return `padea_submitted_${sessionId}_${new Date().toISOString().slice(0, 10)}`;
}
function getSubmittedFlag(sessionId) { return ls.get(submittedKey(sessionId)) === "1"; }
function setSubmittedFlag(sessionId) { ls.set(submittedKey(sessionId), "1"); }

// ============================================================
// Data loaders
// ============================================================

async function loadSession(sessionId) {
  const key = `padea_session_${sessionId}`;
  const cached = cacheGet(key);
  if (cached) {
    console.log(`[padea] session (cache hit): ${cached.fields["Session ID"]}`);
    return cached;
  }
  console.log(`[padea] fetching session ${sessionId}…`);
  const rec = await apiFetch(`/api/session/${sessionId}`);
  console.log(`[padea] session loaded: ${rec.fields["Session ID"]}`,
    "caterer:", rec.fields.Caterer,
    "incoming:", rec.fields["Incoming Caterer"] || []);
  cacheSet(key, rec);
  return rec;
}

// During a caterer-switch transition, Sessions.Incoming Caterer is set and the
// webapp should show the incoming caterer's menu for preferences. Ratings still
// belong to Sessions.Caterer (who cooked today's meal).
function menuCatererId(session) {
  if (!session) return null;
  const incoming = (session.fields["Incoming Caterer"] || [])[0];
  const current = (session.fields.Caterer || [])[0];
  return incoming || current || null;
}

function isInTransition(session) {
  return !!(session && (session.fields["Incoming Caterer"] || []).length);
}

async function loadStudent(studentId) {
  const key = `padea_student_${studentId}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  const rec = await apiFetch(`/api/student/${studentId}`);
  cacheSet(key, rec);
  return rec;
}

async function loadStudentsForSession(sessionId) {
  const key = `padea_students_${sessionId}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  const result = await apiFetch(`/api/session/${sessionId}/students`);
  cacheSet(key, result);
  return result;
}

async function loadMenuItems(catererId) {
  const key = `padea_menu_${catererId}`;
  const cached = cacheGet(key);
  if (cached) {
    console.log(`[padea] menu (cache hit, ${cached.length} items)`);
    return cached;
  }
  const items = await apiFetch(`/api/caterer/${catererId}/menu`);
  console.log(`[padea] menu loaded: ${items.length} items`);
  cacheSet(key, items);
  return items;
}

async function loadDietaryRestrictions() {
  const key = "padea_diet_restrictions";
  const cached = cacheGet(key);
  if (cached) return cached;
  const data = await apiFetch("/api/dietary-restrictions");
  console.log(`[padea] dietary restrictions loaded: ${data.length}`);
  cacheSet(key, data);
  return data;
}

async function loadNegativeKeywords() {
  const key = "padea_neg_keywords";
  const cached = cacheGet(key);
  if (cached) return cached;
  const res = await fetch("data/dietary_keywords.json", { cache: "no-cache" });
  if (!res.ok) throw new Error(`keywords ${res.status}`);
  const data = (await res.json()).negative_keywords || {};
  console.log(`[padea] negative keywords loaded: ${Object.keys(data).length} entries`);
  cacheSet(key, data);
  return data;
}

async function loadCaterer(catererId) {
  const key = `padea_caterer_${catererId}`;
  const cached = cacheGet(key);
  if (cached) return cached;
  const data = await apiFetch(`/api/caterer/${catererId}`);
  cacheSet(key, data);
  return data;
}

async function loadExistingFeedback(studentId, catererId) {
  const key = `padea_fb_${studentId}_${catererId || ""}`;
  const cached = cacheGet(key);
  if (cached !== null) return cached;
  const fb = await apiFetch(`/api/feedback?student_id=${studentId}&caterer_id=${catererId || ""}`);
  cacheSet(key, fb);
  return fb;
}

async function loadStudentTicket(studentId, sessionId) {
  const key = `padea_ticket_${studentId}_${sessionId}`;
  const cached = cacheGet(key);
  if (cached !== null) return cached;
  const t = await apiFetch(`/api/student/${studentId}/ticket?session_id=${sessionId}`);
  cacheSet(key, t);
  return t;
}


// ============================================================
// Variant helpers
// ============================================================

function buildVariantMap(items) {
  const map = {};
  for (const item of items) {
    if (item.fields["Is Variant"]) {
      const parentId = (item.fields["Variant Of"] || [])[0];
      if (parentId) (map[parentId] ||= []).push(item);
    }
  }
  return map;
}

// Returns the best dietary severity across a parent item and its variants,
// so an item with an incompatible parent but a compatible variant isn't
// bucketed into the "doesn't match" section of the meal list.
function bestVariantSeverity(parentSeverity, variants, reqs, maps) {
  if (!maps || !reqs.length || !variants.length) return parentSeverity;
  let best = parentSeverity;
  for (const v of variants) {
    const { severity } = checkCompatibility(v, reqs, maps);
    if (severity === "ok") return "ok";
    if (severity === "maybe" && best === "no") best = "maybe";
  }
  return best;
}

// ============================================================
// Dietary hierarchy
// ============================================================

function buildHierarchyMaps(restrictions, negativeKeywords = {}) {
  const idToName = {};
  const nameToId = {};
  const idToRestr = {};
  const allergyIds = new Set();
  for (const r of restrictions) {
    idToName[r.id] = r.name;
    nameToId[r.name] = r.id;
    idToRestr[r.id] = r;
    if (r.isAllergy) allergyIds.add(r.id);
  }
  // Build child map (parentId → [subset childIds]) from each restriction's
  // Supersets list (a restriction lists its less-restrictive parents).
  const children = {};
  for (const r of restrictions) {
    for (const parentId of r.supersets) {
      (children[parentId] ||= []).push(r.id);
    }
  }
  // Transitive subset-closure: each restriction → itself + all more-restrictive descendants.
  function descendants(id, acc = new Set()) {
    if (acc.has(id)) return acc;
    acc.add(id);
    for (const c of children[id] || []) descendants(c, acc);
    return acc;
  }
  const subsetClosure = {};
  for (const r of restrictions) {
    subsetClosure[r.id] = descendants(r.id);
  }
  // Transitive superset-closure: each restriction → itself + all less-restrictive ancestors.
  // Used to detect definite incompatibility when an ancestor is a caterer legend tag.
  function ancestors(id, acc = new Set()) {
    if (acc.has(id)) return acc;
    acc.add(id);
    const r = idToRestr[id];
    if (r) for (const parentId of r.supersets) ancestors(parentId, acc);
    return acc;
  }
  const supersetClosure = {};
  for (const r of restrictions) {
    supersetClosure[r.id] = ancestors(r.id);
  }
  // legendTagIdSet is populated later once the caterer record is fetched.
  return {
    idToName, nameToId, subsetClosure, supersetClosure,
    negativeKeywords, allergyIds, legendTagIdSet: new Set(),
  };
}

// Returns { compatible, severity, issues, allergyBlocked } where:
//   compatible      — true if all constraints satisfied by tags
//   severity        — "ok" | "maybe" | "no"
//   issues          — array of { name, severity, label, isAllergy } per unmet constraint
//   allergyBlocked  — true if any issue is severity "no" against a registered allergy
function checkCompatibility(item, studentReqIds, maps) {
  if (!studentReqIds.length) return { compatible: true, severity: "ok", issues: [], allergyBlocked: false };

  const itemTagIds = item.fields["Dietary Tags"] || [];
  const itemNameLower = (item.fields["Menu Item Name"] || "").toLowerCase();
  const legendTagIdSet = maps.legendTagIdSet || new Set();
  const allergyIds = maps.allergyIds || new Set();

  const issues = [];
  for (const reqId of studentReqIds) {
    const reqName = maps.idToName[reqId];
    if (!reqName || reqName === "Opted out of Catering") continue;

    const closure = maps.subsetClosure[reqId] || new Set([reqId]);
    const tagMatch = itemTagIds.some(t => closure.has(t));
    if (tagMatch) continue; // satisfied by a tag in the subset closure

    const phrase = CONSTRAINT_PHRASE[reqName] || reqName.toLowerCase();
    const isAllergy = allergyIds.has(reqId);

    // Legend-based definite incompatibility: if a transitive superset of this
    // constraint is in the caterer's Dietary Legend and the item lacks any
    // satisfying tag for that superset, the item DEFINITELY fails this constraint
    // (the caterer would have tagged it otherwise). Converts "maybe" → "no" and
    // also propagates downward: absent VO → not Vegetarian → not Vegan either.
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
        issues.push({ name: reqName, severity: "no", label: `Contains ${phrase}`, isAllergy });
        continue;
      }
    }

    // No legend verdict. Fall back to name-keyword heuristic.
    const kws = maps.negativeKeywords?.[reqName];
    if (kws && kws.some(k => itemNameLower.includes(k))) {
      issues.push({ name: reqName, severity: "no", label: `Contains ${phrase}`, isAllergy });
    } else {
      issues.push({ name: reqName, severity: "maybe", label: `May contain ${phrase}`, isAllergy });
    }
  }

  if (!issues.length) return { compatible: true, severity: "ok", issues, allergyBlocked: false };
  const severity = issues.some(i => i.severity === "no") ? "no" : "maybe";
  const allergyBlocked = issues.some(i => i.severity === "no" && i.isAllergy);
  return { compatible: false, severity, issues, allergyBlocked };
}

function hasOptedOut(student, maps) {
  const reqs = student?.fields?.["Dietary Requirements"] || [];
  return reqs.some(id => maps.idToName[id] === "Opted out of Catering");
}

// ============================================================
// Wed 8pm cutoff
// ============================================================

function isPastOrderCutoff(now = new Date()) {
  const day = now.getDay();  // 0=Sun, ..., 6=Sat
  const hr = now.getHours();
  if (day === 3 && hr >= 20) return true;  // Wed >= 8pm
  return day === 4 || day === 5 || day === 6;  // Thu / Fri / Sat
}

// ============================================================
// State
// ============================================================

const state = {
  sessionId: null,
  studentId: null,
  firstSession: false,
  session: null,
  student: null,
  menuItems: null,
  menuPromise: null,
  catererPromise: null,
  dietRestrictions: null,
  dietPromise: null,
  dietMaps: null,

  initialRating: 0,
  initialComment: "",
  initialMealItemId: null,

  rating: 0,
  comment: "",
  mealItemId: null,
  variantMap: {},   // parentItemId → [variantItem, ...]

  feedbackRecordId: null,
  feedbackPromise: null,

  view: "loading",
};

const views = ["picker", "form", "meals", "done", "locked"];

function showView(name) {
  state.view = name;
  for (const v of views) {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== name);
  }
}

// ============================================================
// App actions
// ============================================================

const app = {

  async init() {
    const params = new URLSearchParams(location.search);
    state.sessionId = params.get("session");
    state.firstSession = !!params.get("first");

    if (!state.sessionId) {
      showError("Missing session ID. Please scan a valid QR code.");
      return;
    }

    // One-way device lockout — once this device has submitted for this
    // (session, day), refuse re-entry until the day rolls over.
    if (getSubmittedFlag(state.sessionId)) {
      renderCutoffFootnote();
      showSubmittedLock();
      return;
    }

    // Decide the view before any network so the first paint is correct.
    const urlStudent = params.get("student");
    const knownStudent = getKnownStudent(state.sessionId);
    const studentId = urlStudent || knownStudent;

    if (studentId) {
      if (urlStudent) setKnownStudent(state.sessionId, urlStudent);
      state.studentId = studentId;
      showFormSkeleton();
    } else {
      showPickerSkeleton();
    }

    // Show the cutoff footnote immediately based on local time.
    renderCutoffFootnote();

    // Fetch Dietary Restrictions + the shared NEGATIVE_KEYWORDS table in
    // parallel (both independent of session). Both feed dietMaps.
    state.dietPromise = Promise.all([
      loadDietaryRestrictions(),
      loadNegativeKeywords(),
    ])
      .then(([rs, kws]) => {
        state.dietRestrictions = rs;
        state.dietMaps = buildHierarchyMaps(rs, kws);
        return rs;
      })
      .catch(err => { console.error("[padea] diet load failed:", err); return []; });

    // Load session.
    let session;
    try {
      session = await loadSession(state.sessionId);
    } catch (err) {
      console.error(err);
      showError("Couldn't load this session. Please scan a valid QR code.");
      return;
    }
    state.session = session;
    document.getElementById("session-label").textContent =
      formatSessionLabel(session.fields);

    // Prefetch the menu — during a caterer switch transition, this is the
    // incoming caterer's menu; otherwise the current caterer's.
    const catererId = menuCatererId(session);
    if (catererId) {
      state.menuPromise = loadMenuItems(catererId)
        .then(items => {
          state.menuItems = items;
          state.variantMap = buildVariantMap(items);
          return items;
        })
        .catch(err => { console.error(err); return []; });

      // Fetch caterer legend tags and inject into dietMaps once both are ready.
      // catererPromise resolves after dietPromise so callers need only await this one.
      state.catererPromise = loadCaterer(catererId)
        .then(catererData => state.dietPromise.then(() => {
          if (state.dietMaps) {
            state.dietMaps.legendTagIdSet = new Set(catererData.legendTagIds || []);
            console.log(`[padea] caterer legend tags loaded: ${catererData.legendTagIds?.length || 0} tag(s)`);
          }
        }))
        .catch(err => console.error("[padea] caterer legend load failed:", err));
    }

    if (studentId) await loadFormData(studentId);
    else await loadPickerData();
  },

  async pickStudent(sid) {
    setKnownStudent(state.sessionId, sid);
    state.studentId = sid;
    showFormSkeleton();
    await loadFormData(sid);
  },

  async changeStudent() {
    clearKnownStudent(state.sessionId);
    resetFormState();
    showPickerSkeleton();
    if (state.session) await loadPickerData();
  },

  setRating(v) {
    state.rating = v;
    document.querySelectorAll("#stars .star").forEach(s => {
      s.classList.toggle("active", Number(s.dataset.v) <= v);
    });
    document.getElementById("comment-wrap").classList.toggle("hidden", v === 0 || v >= 4);
    updateSubmitState();
  },

  setComment(text) {
    state.comment = text;
    updateSubmitState();
  },

  openMealPicker() {
    if (!state.student) return;
    renderMealList();
    showView("meals");
  },

  closeMealPicker() {
    showView("form");
  },

  selectMeal(itemId) {
    state.mealItemId = itemId;
    updateMealTrigger();
    updateSubmitState();
    setTimeout(() => showView("form"), 140);
  },

  openVariantPicker(parentId) {
    const parent = state.menuItems.find(i => i.id === parentId);
    if (!parent) return;
    const variants = state.variantMap[parentId] || [];
    const allOptions = [parent, ...variants];
    const reqs = state.student?.fields["Dietary Requirements"] || [];
    const maps = state.dietMaps;

    // Determine the initial selection:
    // 1. Respect an existing choice within this group.
    // 2. Otherwise auto-select the single fully-compatible option.
    // 3. Fall back to the parent.
    let selectedId = parentId;
    if (allOptions.some(o => o.id === state.mealItemId)) {
      selectedId = state.mealItemId;
    } else if (maps && reqs.length) {
      const compatible = allOptions.filter(
        o => checkCompatibility(o, reqs, maps).severity === "ok"
      );
      if (compatible.length === 1) selectedId = compatible[0].id;
    }

    showVariantModal(allOptions, selectedId, maps, reqs);
  },

  attemptUnsafeSelect(itemId) {
    const item = state.menuItems.find(i => i.id === itemId);
    if (!item || !state.dietMaps) return;
    const reqs = state.student.fields["Dietary Requirements"] || [];
    const { severity, issues, allergyBlocked } = checkCompatibility(item, reqs, state.dietMaps);
    const name = item.fields["Menu Item Name"] || "this meal";

    // Allergy-grade hits are non-negotiable — show the lockout dialog
    // instead of the lifestyle override.
    if (allergyBlocked) {
      const allergyNames = issues
        .filter(i => i.severity === "no" && i.isAllergy)
        .map(i => i.name)
        .join(", ");
      openConfirm({
        title: "Option blocked",
        body: `"${name}" is not safe for your registered allergy (${allergyNames}). Talk to the on-site manager for manual overrides.`,
        confirmLabel: "OK",
        onConfirm: () => closeConfirm(),
        hideCancel: true,
      });
      return;
    }

    const phrases = issues
      .map(i => CONSTRAINT_PHRASE[i.name] || i.name.toLowerCase())
      .join(", ");
    const body = severity === "no"
      ? `"${name}" doesn't match your dietary requirements: ${issues.map(i => i.label).join(", ")}.`
      : `We don't know if "${name}" contains ${phrases}.`;
    openConfirm({
      title: "Are you sure?",
      body,
      confirmLabel: "Choose it anyway",
      onConfirm: () => {
        closeConfirm();
        app.selectMeal(itemId);
      },
    });
  },

  async submit() {
    const btn = document.getElementById("submit-btn");
    btn.disabled = true;
    btn.textContent = "Saving…";
    try {
      await persistChanges();
      // Mark this device + student as locked for today so the picker filters
      // them out and the form refuses to re-open on this device.
      setSubmittedFlag(state.sessionId);
      try {
        await apiFetch(`/api/student/${state.studentId}/mark-submitted`, { method: "POST" });
      } catch (err) {
        console.warn("[padea] mark-submitted failed", err);
      }
      showView("done");
      document.getElementById("done-msg").textContent = doneMessage();
    } catch (err) {
      console.error(err);
      toast("Couldn't save — please try again.");
      btn.disabled = false;
      btn.textContent = "Submit";
    }
  },

};

// ============================================================
// Skeletons + data drivers
// ============================================================

function showPickerSkeleton() {
  showView("picker");
  document.getElementById("student-list").classList.add("hidden");
  document.getElementById("picker-empty").classList.add("hidden");
  document.getElementById("picker-loading").classList.remove("hidden");
  document.getElementById("student-search").value = "";
}

function showSubmittedLock() {
  showView("locked");
}

function renderTicket(ticket, student) {
  const el = document.getElementById("meal-ticket");
  if (!el) return;
  if (!ticket || !ticket.meal) {
    el.classList.add("hidden");
    return;
  }
  document.getElementById("ticket-meal-name").textContent = ticket.meal.name;

  const maps = state.dietMaps;
  const tagsEl = document.getElementById("ticket-meal-tags");
  const tagIds = ticket.meal.tags || [];
  tagsEl.innerHTML = tagIds.map(tid => {
    const name = maps?.idToName[tid];
    if (!name) return "";
    return `<span class="tag">${escapeHtml(TAG_SHORT[name] || name)}</span>`;
  }).join("");

  // Highlight any allergy restrictions registered on the student — the
  // on-site manager uses this to prioritise hand-off of allergy-safe boxes.
  const allergyBanner = document.getElementById("ticket-allergy-banner");
  const reqs = student?.fields["Dietary Requirements"] || [];
  const allergyNames = maps
    ? reqs.filter(rid => maps.allergyIds?.has(rid)).map(rid => maps.idToName[rid]).filter(Boolean)
    : [];
  if (allergyNames.length) {
    allergyBanner.textContent = `⚠️ ${allergyNames.join(", ").toUpperCase()} TICKET`;
    allergyBanner.classList.remove("hidden");
  } else {
    allergyBanner.classList.add("hidden");
  }
  el.classList.remove("hidden");
}

async function loadPickerData() {
  let students;
  try {
    students = await loadStudentsForSession(state.sessionId);
  } catch (err) {
    console.error(err);
    showError("Couldn't load the student list. Please try again.");
    document.getElementById("picker-loading").classList.add("hidden");
    return;
  }
  document.getElementById("picker-loading").classList.add("hidden");
  renderStudentList(students, "");
  document.getElementById("student-search").oninput = (e) =>
    renderStudentList(students, e.target.value);
}

function showFormSkeleton() {
  showView("form");
  resetFormState();
  clearOptedOutLock();
  document.getElementById("rating-card").classList.toggle("hidden", state.firstSession);
  document.getElementById("transition-banner").classList.add("hidden");
  document.getElementById("student-name").textContent = "…";
  document.querySelectorAll("#stars .star").forEach(s => s.classList.remove("active"));
  document.getElementById("comment-wrap").classList.add("hidden");
  document.getElementById("comment").value = "";
  const trig = document.getElementById("meal-trigger");
  trig.disabled = true;
  document.getElementById("meal-trigger-label").textContent = "Loading menu…";
  document.getElementById("meal-trigger-name").textContent = "";
  document.getElementById("submit-btn").disabled = true;
}

function resetFormState() {
  state.student = null;
  state.initialRating = 0;
  state.initialComment = "";
  state.initialMealItemId = null;
  state.rating = 0;
  state.comment = "";
  state.mealItemId = null;
  state.feedbackRecordId = null;
  state.feedbackPromise = null;
}

async function loadFormData(studentId) {
  let student;
  try {
    student = await loadStudent(studentId);
  } catch (err) {
    console.error(err);
    showError("Couldn't load your record. Try scanning the QR again.");
    return;
  }
  state.student = student;
  document.getElementById("student-name").textContent =
    student.fields["Student Name"] || "—";

  // During a caterer-switch transition the student's preference was cleared by
  // execute_caterer_switch.py — treat the form as unselected regardless of any
  // stale cached value so the trigger shows "Tap to choose a meal".
  const transition = isInTransition(state.session);
  state.initialMealItemId = transition
    ? null
    : ((student.fields["Meal Preference"] || [])[0] || null);
  state.mealItemId = state.initialMealItemId;
  document.getElementById("transition-banner").classList.toggle("hidden", !transition);

  console.log(`[padea] student loaded: ${student.fields["Student Name"]}`,
    "diet ids:", student.fields["Dietary Requirements"] || [],
    "preference:", state.initialMealItemId);

  // Apply opted-out lock if applicable. Needs dietary maps first.
  await state.dietPromise;
  if (state.dietMaps && hasOptedOut(student, state.dietMaps)) {
    applyOptedOutLock();
    return;
  }

  // Fetch today's finalized meal ticket. Rendered above the form if a
  // matching Order exists for today.
  loadStudentTicket(studentId, state.sessionId)
    .then(ticket => renderTicket(ticket, student))
    .catch(err => console.warn("[padea] ticket load failed", err));

  // Load existing feedback in the background. persistChanges awaits this
  // promise before deciding create vs update, preventing duplicate records
  // if the user submits before this resolves.
  const catererId = (state.session?.fields?.Caterer || [])[0];
  state.feedbackPromise = loadExistingFeedback(studentId, catererId)
    .then(fb => {
      state.feedbackRecordId = fb.recordId;
      state.initialRating = fb.rating;
      state.initialComment = fb.comment;
      if (state.rating === 0 && fb.rating > 0) {
        state.rating = fb.rating;
        document.querySelectorAll("#stars .star").forEach(s => {
          s.classList.toggle("active", Number(s.dataset.v) <= fb.rating);
        });
        document.getElementById("comment-wrap").classList.toggle("hidden", fb.rating >= 4);
      }
      if (state.comment === "" && fb.comment) {
        state.comment = fb.comment;
        document.getElementById("comment").value = fb.comment;
      }
      updateSubmitState();
    })
    .catch(err => console.error(err));

  if (state.menuPromise) {
    state.menuPromise.then(() => updateMealTrigger());
  } else {
    updateMealTrigger();
  }
}

function refreshFormFromState() {
  document.getElementById("student-name").textContent =
    state.student?.fields["Student Name"] || "—";
  document.querySelectorAll("#stars .star").forEach(s => {
    s.classList.toggle("active", Number(s.dataset.v) <= state.rating);
  });
  document.getElementById("comment").value = state.comment;
  document.getElementById("comment-wrap").classList.toggle(
    "hidden",
    state.rating === 0 || state.rating >= 4,
  );
  updateMealTrigger();
  updateSubmitState();
}

// ============================================================
// Rendering
// ============================================================

function renderStudentList(students, query) {
  const q = query.trim().toLowerCase();
  const filtered = q
    ? students.filter(s => s.name.toLowerCase().includes(q))
    : students;
  const list = document.getElementById("student-list");
  const empty = document.getElementById("picker-empty");

  if (!filtered.length) {
    list.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = students.length
      ? "No matching student."
      : "No students assigned to this session yet.";
    return;
  }

  empty.classList.add("hidden");
  list.classList.remove("hidden");
  list.innerHTML = filtered.map(s =>
    `<li onclick="app.pickStudent('${s.id}')">${escapeHtml(s.name)}</li>`
  ).join("");
}

function renderMealList() {
  const ul = document.getElementById("meals-list");
  const loading = document.getElementById("meals-loading");
  const empty = document.getElementById("meals-empty");
  const sub = document.getElementById("meals-sub");

  ul.classList.add("hidden");
  empty.classList.add("hidden");

  const allReqs = state.student?.fields["Dietary Requirements"] || [];
  const maps = state.dietMaps;
  const reqs = maps
    ? allReqs.filter(id => maps.idToName[id] !== "Opted out of Catering")
    : [];
  const reqNames = reqs.map(id => maps?.idToName[id]).filter(Boolean);
  sub.textContent = reqNames.length
    ? `Filtered for: ${reqNames.join(", ")}`
    : "All available meals from your caterer.";

  // Wait on menu, dietary maps, and caterer legend tags before rendering.
  // catererPromise chains on dietPromise, so awaiting it covers both.
  if (!state.menuItems || !maps) {
    loading.classList.remove("hidden");
    const legendOrDiet = state.catererPromise || state.dietPromise;
    Promise.all([state.menuPromise, legendOrDiet].filter(Boolean))
      .then(() => { if (state.view === "meals") renderMealList(); });
    return;
  }
  loading.classList.add("hidden");

  if (!state.menuItems.length) {
    empty.classList.remove("hidden");
    empty.textContent = "No menu items found for this caterer.";
    return;
  }

  // Exclude variants from the main list — they appear only inside the variant picker.
  const displayItems = state.menuItems.filter(i => !i.fields["Is Variant"]);

  // Bucket items: compatible / possibly-compatible / definitely-incompatible.
  // For items with variants, use the best severity across all options.
  const compat = [], maybe = [], incompat = [];
  for (const item of displayItems) {
    const r = checkCompatibility(item, reqs, maps);
    const variants = state.variantMap[item.id] || [];
    const effectiveSev = bestVariantSeverity(r.severity, variants, reqs, maps);
    if (effectiveSev === "ok") compat.push({ item, result: r });
    else if (effectiveSev === "maybe") maybe.push({ item, result: r });
    else incompat.push({ item, result: r });
  }

  const renderRow = ({ item, result }) => {
    const name = item.fields["Menu Item Name"] || "—";
    const tagIds = item.fields["Dietary Tags"] || [];
    const tagsHtml = tagIds.map(tid => {
      const tName = maps.idToName[tid];
      if (!tName) return "";
      const short = TAG_SHORT[tName] || tName;
      return `<span class="tag">${escapeHtml(short)}</span>`;
    }).join("");

    const variants = state.variantMap[item.id] || [];
    const hasVariants = variants.length > 0;

    // An item counts as selected if it or one of its variants is chosen.
    const selected = item.id === state.mealItemId ||
      variants.some(v => v.id === state.mealItemId);

    const sev = result.severity;
    // If any option (parent or a variant) is allergy-safe, the row isn't blocked.
    const allergySafeOption = (hasVariants ? [item, ...variants] : [item]).some(o => {
      const r = checkCompatibility(o, reqs, maps);
      return !r.allergyBlocked;
    });
    const blocked = !allergySafeOption;

    // Items with variants always open the picker, never select directly.
    const onclick = hasVariants
      ? `app.openVariantPicker('${item.id}')`
      : sev === "ok"
        ? `app.selectMeal('${item.id}')`
        : `app.attemptUnsafeSelect('${item.id}')`;

    // Show the parent's incompatibility reason only when no variant rescues it.
    const effectiveSev = hasVariants
      ? bestVariantSeverity(sev, variants, reqs, maps)
      : sev;
    const reasonText = blocked
      ? result.issues
          .filter(i => i.severity === "no" && i.isAllergy)
          .map(i => `Not safe — registered allergy: ${i.name}`)
          .join(" · ")
        || result.issues.map(i => i.label).join(" · ")
      : (!hasVariants || effectiveSev === "no") && result.issues.length
        ? result.issues.map(i => i.label).join(" · ")
        : "";
    const reasonHtml = reasonText
      ? `<div class="meal-reason meal-reason-${blocked ? "blocked" : sev}">${escapeHtml(reasonText)}</div>`
      : "";

    // Show a note when there are variant options.
    const variantNoteText = hasVariants && !blocked
      ? (sev !== "ok" && effectiveSev !== "no" ? "Dietary variant available" : "Options available")
      : "";
    const variantNoteHtml = variantNoteText
      ? `<div class="meal-variant-note">${variantNoteText}</div>`
      : "";

    const klass = [
      "meal-item",
      selected ? "selected" : "",
      blocked ? "blocked" : "",
      effectiveSev === "no" ? "incompatible" : "",
      effectiveSev === "maybe" ? "maybe" : "",
    ].filter(Boolean).join(" ");

    return `
      <li class="${klass}" onclick="${onclick}">
        <div class="meal-radio"></div>
        <div class="meal-content">
          <div class="meal-name">${escapeHtml(name)}</div>
          ${reasonHtml}
          ${variantNoteHtml}
          <div class="meal-tags">${tagsHtml}</div>
        </div>
      </li>`;
  };

  let html = compat.map(renderRow).join("");
  if (maybe.length) {
    html += `<li class="meal-divider">Possibly compatible</li>`;
    html += maybe.map(renderRow).join("");
  }
  if (incompat.length) {
    html += `<li class="meal-divider">Doesn't match your preferences</li>`;
    html += incompat.map(renderRow).join("");
  }
  ul.classList.remove("hidden");
  ul.innerHTML = html;
}

function updateMealTrigger() {
  const trig = document.getElementById("meal-trigger");
  const label = document.getElementById("meal-trigger-label");
  const nameEl = document.getElementById("meal-trigger-name");

  if (state.session && !menuCatererId(state.session)) {
    label.textContent = "No caterer assigned to this session.";
    nameEl.textContent = "";
    trig.disabled = true;
    return;
  }
  if (!state.menuItems) {
    label.textContent = "Loading menu…";
    nameEl.textContent = "";
    trig.disabled = true;
    return;
  }
  trig.disabled = false;
  if (state.mealItemId) {
    const item = state.menuItems.find(i => i.id === state.mealItemId);
    if (item) {
      label.textContent = "Currently selected";
      nameEl.textContent = item.fields["Menu Item Name"] || "—";
      return;
    }
  }
  label.textContent = "Tap to choose a meal";
  nameEl.textContent = "";
}

function updateSubmitState() {
  const ratingChanged = state.rating > 0 && state.rating !== state.initialRating;
  const commentChanged = state.rating > 0 && state.comment !== state.initialComment;
  const mealChanged = state.mealItemId && state.mealItemId !== state.initialMealItemId;
  const btn = document.getElementById("submit-btn");
  btn.disabled = !(ratingChanged || commentChanged || mealChanged);
  btn.textContent = "Submit";
}

function renderCutoffFootnote() {
  const note = document.getElementById("cutoff-note");
  if (!note) return;
  if (isPastOrderCutoff()) {
    note.classList.remove("hidden");
  } else {
    note.classList.add("hidden");
  }
}

// ============================================================
// Persistence
// ============================================================

async function persistChanges() {
  const ratingChanged = state.rating > 0 &&
    (state.rating !== state.initialRating || state.comment !== state.initialComment);
  const mealChanged = state.mealItemId && state.mealItemId !== state.initialMealItemId;

  const ops = [];

  if (ratingChanged) {
    // Wait for the background lookup to resolve so we never create a duplicate
    // when the user submits faster than the server responds.
    if (state.feedbackPromise) await state.feedbackPromise;
    // Always attribute to session.Caterer (who cooked today), not Incoming Caterer.
    const catererId = (state.session?.fields?.Caterer || [])[0] || "";
    ops.push(
      apiFetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          student_id: state.studentId,
          session_id: state.sessionId,
          caterer_id: catererId,
          rating: state.rating,
          comment: state.comment.trim(),
          feedback_record_id: state.feedbackRecordId || null,
        }),
      }).then(data => { state.feedbackRecordId = data.recordId; })
    );
  }

  if (mealChanged) {
    ops.push(
      apiFetch(`/api/student/${state.studentId}/meal-preference`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meal_item_id: state.mealItemId }),
      }).then(() => {
        cacheBust(`padea_student_${state.studentId}`);
      })
    );
  }

  await Promise.all(ops);

  if (ratingChanged) {
    state.initialRating = state.rating;
    state.initialComment = state.comment;
  }
  if (mealChanged) {
    state.initialMealItemId = state.mealItemId;
  }

  const _catererId = (state.session?.fields?.Caterer || [])[0] || "";
  cacheBust(`padea_fb_${state.studentId}_${_catererId}`);
}

function doneMessage() {
  const parts = [];
  if (state.rating > 0) parts.push("Rating saved");
  if (state.mealItemId) parts.push("Preference saved");
  return parts.length ? parts.join(" — ") + "." : "Your response has been saved.";
}

// ============================================================
// Opted-out lock
// ============================================================

function applyOptedOutLock() {
  document.getElementById("opted-out-banner").classList.remove("hidden");
  document.getElementById("transition-banner").classList.add("hidden");
  document.querySelectorAll("#stars .star").forEach(s => s.disabled = true);
  document.getElementById("comment").disabled = true;
  document.getElementById("meal-trigger").disabled = true;
  document.getElementById("meal-trigger-label").textContent = "Catering opted out";
  document.getElementById("meal-trigger-name").textContent = "";
  document.getElementById("submit-btn").disabled = true;
}

function clearOptedOutLock() {
  document.getElementById("opted-out-banner").classList.add("hidden");
  document.querySelectorAll("#stars .star").forEach(s => s.disabled = false);
  document.getElementById("comment").disabled = false;
}

// ============================================================
// Confirm modal
// ============================================================

let confirmCallback = null;

function openConfirm({ title, body, confirmLabel, onConfirm, hideCancel }) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").textContent = body;
  document.getElementById("confirm-yes").textContent = confirmLabel || "OK";
  document.getElementById("confirm-no").classList.toggle("hidden", !!hideCancel);
  confirmCallback = onConfirm;
  document.getElementById("confirm-modal").classList.remove("hidden");
}

function closeConfirm() {
  document.getElementById("confirm-modal").classList.add("hidden");
  document.getElementById("confirm-no").classList.remove("hidden");
  confirmCallback = null;
}

window.confirmModalYes = () => { if (confirmCallback) confirmCallback(); };
window.confirmModalNo = () => closeConfirm();

// ============================================================
// Utility
// ============================================================

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatSessionLabel(fields) {
  const id = fields["Session ID"] || "";
  // ID is sufficient
  // const date = fields["Date"] || "";
  return id; //, date].filter(Boolean).join(" · ");
}

function showError(msg) {
  document.getElementById("error-text").textContent = msg;
  document.getElementById("error-banner").classList.remove("hidden");
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2400);
}

// ============================================================
// Variant picker modal
// ============================================================

let variantModalSelected = null;

function showVariantModal(options, selectedId, maps, reqs) {
  variantModalSelected = selectedId;

  const optionsEl = document.getElementById("variant-options");
  optionsEl.innerHTML = options.map(item => {
    const { severity, issues, allergyBlocked } = maps
      ? checkCompatibility(item, reqs, maps)
      : { severity: "ok", issues: [], allergyBlocked: false };
    const name = item.fields["Menu Item Name"] || "—";
    const tagIds = item.fields["Dietary Tags"] || [];
    const tagsHtml = tagIds.map(tid => {
      const tName = maps?.idToName[tid];
      if (!tName) return "";
      return `<span class="tag">${escapeHtml(TAG_SHORT[tName] || tName)}</span>`;
    }).join("");
    const reasonText = allergyBlocked
      ? issues
          .filter(i => i.severity === "no" && i.isAllergy)
          .map(i => `Not safe — registered allergy: ${i.name}`)
          .join(" · ")
      : issues.map(i => i.label).join(" · ");
    const reasonHtml = reasonText
      ? `<div class="meal-reason meal-reason-${allergyBlocked ? "blocked" : severity}">${escapeHtml(reasonText)}</div>`
      : "";
    const isSelected = item.id === selectedId;
    const klass = [
      "variant-option",
      isSelected ? "selected" : "",
      allergyBlocked ? "blocked" : "",
      severity === "no" ? "incompatible" : severity === "maybe" ? "maybe" : "",
    ].filter(Boolean).join(" ");
    return `
      <div class="${klass}" data-item-id="${item.id}" data-blocked="${allergyBlocked ? '1' : ''}" onclick="selectVariantOption('${item.id}')">
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

window.selectVariantOption = function (itemId) {
  const el = document.querySelector(`.variant-option[data-item-id="${itemId}"]`);
  if (el && el.dataset.blocked === "1") {
    toast("Option blocked — registered allergy. Talk to the on-site manager.");
    return;
  }
  variantModalSelected = itemId;
  document.querySelectorAll(".variant-option").forEach(el => {
    el.classList.toggle("selected", el.dataset.itemId === itemId);
  });
};

window.closeVariantModal = function () {
  document.getElementById("variant-modal").classList.add("hidden");
  variantModalSelected = null;
};

window.confirmVariantModal = function () {
  const id = variantModalSelected;
  closeVariantModal();
  if (!id) return;

  // If the chosen option is dietarily problematic, route through the
  // existing unsafe-select confirmation flow.
  const item = state.menuItems.find(i => i.id === id);
  const reqs = state.student?.fields["Dietary Requirements"] || [];
  if (item && state.dietMaps && reqs.length) {
    const { severity } = checkCompatibility(item, reqs, state.dietMaps);
    if (severity !== "ok") {
      app.attemptUnsafeSelect(id);
      return;
    }
  }
  app.selectMeal(id);
};

// ============================================================
// Bootstrap
// ============================================================

document.addEventListener("DOMContentLoaded", () => app.init());
