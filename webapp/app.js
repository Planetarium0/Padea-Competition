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

const AT_BASE = `https://api.airtable.com/v0/${CONFIG.BASE_ID}`;

const CACHE_TTL = {
  session: 60 * 60 * 1000,         // 1h
  student: 24 * 60 * 60 * 1000,    // 24h
  students: 60 * 60 * 1000,         // 1h
  menu: 24 * 60 * 60 * 1000,    // 24h
  diet: 24 * 60 * 60 * 1000,    // 24h
  feedback: 5 * 60 * 1000,          // 5m
};

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

// Name-keyword heuristic. If a menu item's NAME contains any of these
// substrings, we treat that as definite evidence it violates the listed
// constraint — i.e. "Contains beef" rather than the softer "May contain beef".
const NEGATIVE_KEYWORDS = {
  "No Beef": ["beef", "bulgogi"],
  "No Pork": ["pork", "bacon", "ham"],
  "No Lamb": ["lamb"],
  "No Seafood": ["seafood", "shrimp", "prawn", "fish", "salmon", "tuna", "shellfish", "crab", "lobster"],
  "No Shellfish": ["shellfish", "shrimp", "shrimps", "prawn", "crab", "lobster"],
  "No Fish": ["fish", "salmon", "tuna"],
  "No Red Meat": ["beef", "lamb", "pork", "bulgogi"],
  "Vegetarian": ["beef", "pork", "lamb", "chicken", "fish", "shrimp", "prawn", "salmon", "tuna", "seafood", "shellfish", "crab", "lobster", "bulgogi", "bacon", "ham"],
  "Vegan": ["beef", "pork", "lamb", "chicken", "fish", "shrimp", "prawn", "salmon", "tuna", "seafood", "shellfish", "crab", "lobster", "bulgogi", "bacon", "ham", "cheese", "milk", "butter", "cream", "yogurt"],
  "Pescatarian": ["beef", "pork", "lamb", "chicken", "bulgogi", "bacon", "ham"],
  "Dairy Free": ["cheese", "milk", "butter", "cream", "yogurt"],
  "Halal": ["pork", "bacon", "ham"],
  "Kosher": ["pork", "bacon", "ham", "shellfish", "shrimp", "prawn", "crab", "lobster"],
};

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
// Airtable client
// ============================================================

function apiKey() {
  return new URLSearchParams(location.search).get("key") || CONFIG.API_KEY;
}

async function atFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${apiKey()}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`Airtable ${res.status}: ${await res.text()}`);
  return res.json();
}

async function atList(table, params = {}) {
  const url = new URL(`${AT_BASE}/${encodeURIComponent(table)}`);
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(val => url.searchParams.append(k, val));
    else url.searchParams.set(k, v);
  }
  let records = [], offset = null;
  do {
    if (offset) url.searchParams.set("offset", offset);
    else url.searchParams.delete("offset");
    const data = await atFetch(url.toString());
    records = records.concat(data.records || []);
    offset = data.offset;
  } while (offset);
  return records;
}

async function atGet(table, id) {
  return atFetch(`${AT_BASE}/${encodeURIComponent(table)}/${id}`);
}

async function atCreate(table, fields) {
  const data = await atFetch(`${AT_BASE}/${encodeURIComponent(table)}`, {
    method: "POST",
    body: JSON.stringify({ records: [{ fields }] }),
  });
  return data.records[0];
}

async function atUpdate(table, id, fields) {
  return atFetch(`${AT_BASE}/${encodeURIComponent(table)}/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ fields }),
  });
}

// ============================================================
// localStorage helpers
// ============================================================

const ls = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { } },
  remove(k) { try { localStorage.removeItem(k); } catch { } },
};

function cacheGet(key, type) {
  const raw = ls.get(key);
  if (!raw) return null;
  try {
    const { ts, data } = JSON.parse(raw);
    if (Date.now() - ts > CACHE_TTL[type]) { ls.remove(key); return null; }
    return data;
  } catch { return null; }
}

function cacheSet(key, data) {
  ls.set(key, JSON.stringify({ ts: Date.now(), data }));
}

function knownStudentKey(sessionId) { return `padea_known_student_${sessionId}`; }
function getKnownStudent(sessionId) { return ls.get(knownStudentKey(sessionId)); }
function setKnownStudent(sessionId, sid) { ls.set(knownStudentKey(sessionId), sid); }
function clearKnownStudent(sessionId) { ls.remove(knownStudentKey(sessionId)); }

// ============================================================
// Data loaders
// ============================================================

async function loadSession(sessionId) {
  const key = `padea_session_${sessionId}`;
  const cached = cacheGet(key, "session");
  if (cached) {
    console.log(`[padea] session (cache hit): ${cached.fields["Session ID"]}`);
    return cached;
  }
  console.log(`[padea] fetching session ${sessionId}…`);
  const rec = await atGet("Sessions", sessionId);
  console.log(`[padea] session loaded: ${rec.fields["Session ID"]}`,
    "caterer:", rec.fields.Caterer, "students:", (rec.fields.Students || []).length);
  cacheSet(key, rec);
  return rec;
}

async function loadStudent(studentId) {
  const key = `padea_student_${studentId}`;
  const cached = cacheGet(key, "student");
  if (cached) return cached;
  const rec = await atGet("Students", studentId);
  cacheSet(key, rec);
  return rec;
}

async function loadStudentsForSession(sessionId, studentIds) {
  const key = `padea_students_${sessionId}`;
  const cached = cacheGet(key, "students");
  if (cached) return cached;
  if (!studentIds || !studentIds.length) return [];
  const formula = `OR(${studentIds.map(id => `RECORD_ID()='${id}'`).join(",")})`;
  const recs = await atList("Students", {
    filterByFormula: formula,
    "fields[]": ["Student Name"],
  });
  const result = recs.map(r => ({
    id: r.id,
    name: r.fields["Student Name"] || "(no name)",
  })).sort((a, b) => a.name.localeCompare(b.name));
  cacheSet(key, result);
  return result;
}

async function loadMenuItems(catererId) {
  const key = `padea_menu_${catererId}`;
  const cached = cacheGet(key, "menu");
  if (cached) {
    console.log(`[padea] menu (cache hit, ${cached.length} items)`);
    return cached;
  }
  // Fetch caterer to get its Menu Items back-link IDs, then fetch the items.
  // We can't filter Menu Items by Caterer record ID because Airtable formulas
  // render linked-record fields as the primary field (name), not the ID.
  console.log(`[padea] fetching caterer ${catererId}…`);
  const caterer = await atGet("Caterers", catererId);
  const menuIds = caterer.fields["Menu Items"] || [];
  console.log(
    `[padea] caterer "${caterer.fields["Caterer Name"]}" has ${menuIds.length} menu items`,
  );
  if (!menuIds.length) {
    cacheSet(key, []);
    return [];
  }
  const formula = `OR(${menuIds.map(id => `RECORD_ID()='${id}'`).join(",")})`;
  const items = await atList("Menu Items", {
    filterByFormula: formula,
    "fields[]": ["Menu Item Name", "Dietary Tags"],
  });
  console.log(`[padea] menu loaded: ${items.length} items`);
  cacheSet(key, items);
  return items;
}

async function loadDietaryRestrictions() {
  const key = "padea_diet_restrictions";
  const cached = cacheGet(key, "diet");
  if (cached) return cached;
  const recs = await atList("Dietary Restrictions", {
    "fields[]": ["Restriction Name", "Supersets"],
  });
  const data = recs.map(r => ({
    id: r.id,
    name: r.fields["Restriction Name"],
    supersets: r.fields["Supersets"] || [],
  }));
  console.log(`[padea] dietary restrictions loaded: ${data.length}`);
  cacheSet(key, data);
  return data;
}

async function loadExistingFeedback(studentId, sessionId, catererId) {
  console.log("Loading Existing Feedback");
  const key = `padea_fb_${studentId}_${sessionId}_${catererId || ""}`;
  const cached = cacheGet(key, "feedback");
  if (cached !== null) return cached;
  const catererClause = catererId ? `, FIND('${catererId}', ARRAYJOIN({Caterer}))` : "";
  const formula = `AND(FIND('${studentId}', ARRAYJOIN({Student})), FIND('${sessionId}', ARRAYJOIN({Session}))${catererClause})`;
  const recs = await atList("Caterer Feedback", {
    filterByFormula: formula,
    "fields[]": ["Rating", "Comment"],
  });
  const fb = recs[0]
    ? {
      recordId: recs[0].id,
      rating: recs[0].fields.Rating || 0,
      comment: recs[0].fields.Comment || "",
    }
    : { recordId: null, rating: 0, comment: "" };
  cacheSet(key, fb);
  return fb;
}


// ============================================================
// Dietary hierarchy
// ============================================================

function buildHierarchyMaps(restrictions) {
  const idToName = {};
  const nameToId = {};
  for (const r of restrictions) {
    idToName[r.id] = r.name;
    nameToId[r.name] = r.id;
  }
  // Build child map (parentId → [subset childIds]) from each restriction's
  // Supersets list (a restriction lists its less-restrictive parents).
  const children = {};
  for (const r of restrictions) {
    for (const parentId of r.supersets) {
      (children[parentId] ||= []).push(r.id);
    }
  }
  // Transitive subset-closure for each restriction (including itself).
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
  return { idToName, nameToId, subsetClosure };
}

// Returns { compatible, severity, issues } where:
//   compatible — true if all constraints satisfied by tags
//   severity   — "ok" | "maybe" | "no"
//   issues     — array of { name, severity, label } describing each unmet constraint
function checkCompatibility(item, studentReqIds, maps) {
  if (!studentReqIds.length) return { compatible: true, severity: "ok", issues: [] };

  const itemTagIds = item.fields["Dietary Tags"] || [];
  const itemTagIdSet = new Set(itemTagIds);
  const itemNameLower = (item.fields["Menu Item Name"] || "").toLowerCase();

  const issues = [];
  for (const reqId of studentReqIds) {
    const reqName = maps.idToName[reqId];
    if (!reqName || reqName === "Opted out of Catering") continue;

    const closure = maps.subsetClosure[reqId] || new Set([reqId]);
    const tagMatch = itemTagIds.some(t => closure.has(t));
    if (tagMatch) continue; // satisfied by a tag in the subset closure

    // No tag confirms it. Use the name-keyword heuristic to distinguish
    // definitely-incompatible vs ambiguous-may-contain.
    const phrase = CONSTRAINT_PHRASE[reqName] || reqName.toLowerCase();
    const kws = NEGATIVE_KEYWORDS[reqName];
    if (kws && kws.some(k => itemNameLower.includes(k))) {
      issues.push({ name: reqName, severity: "no", label: `Contains ${phrase}` });
    } else {
      issues.push({ name: reqName, severity: "maybe", label: `May contain ${phrase}` });
    }
  }

  if (!issues.length) return { compatible: true, severity: "ok", issues };
  const severity = issues.some(i => i.severity === "no") ? "no" : "maybe";
  return { compatible: false, severity, issues };
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
  session: null,
  student: null,
  menuItems: null,
  menuPromise: null,
  dietRestrictions: null,
  dietPromise: null,
  dietMaps: null,

  initialRating: 0,
  initialComment: "",
  initialMealItemId: null,

  rating: 0,
  comment: "",
  mealItemId: null,

  feedbackRecordId: null,
  feedbackPromise: null,

  view: "loading",
};

const views = ["picker", "form", "meals", "done"];

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

    if (!state.sessionId) {
      showError("Missing session ID. Please scan a valid QR code.");
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

    // Start Dietary Restrictions fetch in parallel (independent of session).
    state.dietPromise = loadDietaryRestrictions()
      .then(rs => {
        state.dietRestrictions = rs;
        state.dietMaps = buildHierarchyMaps(rs);
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

    // Prefetch the caterer's menu.
    const catererId = (session.fields.Caterer || [])[0];
    if (catererId) {
      state.menuPromise = loadMenuItems(catererId)
        .then(items => { state.menuItems = items; return items; })
        .catch(err => { console.error(err); return []; });
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

  attemptUnsafeSelect(itemId) {
    const item = state.menuItems.find(i => i.id === itemId);
    if (!item || !state.dietMaps) return;
    const reqs = state.student.fields["Dietary Requirements"] || [];
    const { severity, issues } = checkCompatibility(item, reqs, state.dietMaps);
    const name = item.fields["Menu Item Name"] || "this meal";
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
      showView("done");
      document.getElementById("done-msg").textContent = doneMessage();
    } catch (err) {
      console.error(err);
      toast("Couldn't save — please try again.");
      btn.disabled = false;
      btn.textContent = "Submit";
    }
  },

  reset() {
    refreshFormFromState();
    showView("form");
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

async function loadPickerData() {
  let students;
  try {
    students = await loadStudentsForSession(
      state.sessionId,
      (state.session.fields.Students || []),
    );
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

  // Read the current preference straight off the student record.
  state.initialMealItemId = (student.fields["Meal Preference"] || [])[0] || null;
  state.mealItemId = state.initialMealItemId;

  console.log(`[padea] student loaded: ${student.fields["Student Name"]}`,
    "diet ids:", student.fields["Dietary Requirements"] || [],
    "preference:", state.initialMealItemId);

  // Apply opted-out lock if applicable. Needs dietary maps first.
  await state.dietPromise;
  if (state.dietMaps && hasOptedOut(student, state.dietMaps)) {
    applyOptedOutLock();
    return;
  }

  // Load existing feedback in the background. persistChanges awaits this
  // promise before deciding create vs update, preventing duplicate records
  // if the user submits before this resolves.
  const catererId = (state.session?.fields?.Caterer || [])[0];
  state.feedbackPromise = loadExistingFeedback(studentId, state.sessionId, catererId)
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

  // Wait on both menu and dietary maps before rendering meaningfully.
  if (!state.menuItems || !maps) {
    loading.classList.remove("hidden");
    Promise.all([state.menuPromise, state.dietPromise].filter(Boolean))
      .then(() => { if (state.view === "meals") renderMealList(); });
    return;
  }
  loading.classList.add("hidden");

  if (!state.menuItems.length) {
    empty.classList.remove("hidden");
    empty.textContent = "No menu items found for this caterer.";
    return;
  }

  // Bucket items: compatible / possibly-compatible / definitely-incompatible.
  const compat = [], maybe = [], incompat = [];
  for (const item of state.menuItems) {
    const r = checkCompatibility(item, reqs, maps);
    if (r.severity === "ok") compat.push({ item, result: r });
    else if (r.severity === "maybe") maybe.push({ item, result: r });
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
    const selected = item.id === state.mealItemId;
    const sev = result.severity;
    const reasonHtml = result.issues.length
      ? `<div class="meal-reason meal-reason-${sev}">${escapeHtml(result.issues.map(i => i.label).join(" · "))
      }</div>`
      : "";
    // Both "no" and "maybe" rows require confirmation; only fully-compatible
    // rows are picked directly.
    const onclick = sev === "ok"
      ? `app.selectMeal('${item.id}')`
      : `app.attemptUnsafeSelect('${item.id}')`;
    const klass = [
      "meal-item",
      selected ? "selected" : "",
      sev === "no" ? "incompatible" : "",
      sev === "maybe" ? "maybe" : "",
    ].filter(Boolean).join(" ");
    return `
      <li class="${klass}" onclick="${onclick}">
        <div class="meal-radio"></div>
        <div class="meal-content">
          <div class="meal-name">${escapeHtml(name)}</div>
          ${reasonHtml}
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

  if (state.session && !(state.session.fields.Caterer || []).length) {
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

  // Caterer Feedback (Student, Session, Caterer, Rating, Comment)
  if (ratingChanged) {
    // Wait for the background lookup to resolve so we never create a duplicate
    // when the user submits faster than Airtable responds.
    if (state.feedbackPromise) await state.feedbackPromise;
    const catererId = (state.session?.fields?.Caterer || [])[0];
    const fields = {
      "Student": [state.studentId],
      "Session": [state.sessionId],
      "Rating": state.rating,
      "Comment": state.comment.trim(),
      ...(catererId ? { "Caterer": [catererId] } : {}),
    };
    if (state.feedbackRecordId) {
      ops.push(atUpdate("Caterer Feedback", state.feedbackRecordId, fields));
    } else {
      fields["Feedback ID"] = makeId("FB", state.studentId, state.sessionId);
      ops.push(atCreate("Caterer Feedback", fields).then(rec => {
        state.feedbackRecordId = rec.id;
      }));
    }
  }

  // Meal Preference — patch the Student record directly.
  if (mealChanged) {
    ops.push(atUpdate("Students", state.studentId, {
      "Meal Preference": [state.mealItemId],
    }).then(() => {
      // Bust the per-student cache so a fresh visit reads the new preference.
      ls.remove(`padea_student_${state.studentId}`);
    }));
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
  ls.remove(`padea_fb_${state.studentId}_${state.sessionId}_${_catererId}`);
}

function doneMessage() {
  const parts = [];
  if (state.rating > 0) parts.push("Rating saved");
  if (state.mealItemId) parts.push("preference saved");
  return parts.length ? parts.join(" — ") + "." : "Your response has been saved.";
}

// ============================================================
// Opted-out lock
// ============================================================

function applyOptedOutLock() {
  document.getElementById("opted-out-banner").classList.remove("hidden");
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

function openConfirm({ title, body, confirmLabel, onConfirm }) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").textContent = body;
  document.getElementById("confirm-yes").textContent = confirmLabel || "OK";
  confirmCallback = onConfirm;
  document.getElementById("confirm-modal").classList.remove("hidden");
}

function closeConfirm() {
  document.getElementById("confirm-modal").classList.add("hidden");
  confirmCallback = null;
}

window.confirmModalYes = () => { if (confirmCallback) confirmCallback(); };
window.confirmModalNo = () => closeConfirm();

// ============================================================
// Utility
// ============================================================

function makeId(prefix, studentId, sessionId) {
  return `${prefix}-${studentId.slice(-6)}-${sessionId.slice(-6)}-${Date.now()}`;
}

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
// Bootstrap
// ============================================================

document.addEventListener("DOMContentLoaded", () => app.init());
