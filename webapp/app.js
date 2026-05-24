/**
 * Padea Meals — meal rating + next-week preference webapp.
 *
 * URL params:
 *   session  — Airtable Session record ID (required)
 *   student  — Airtable Student record ID (optional; from personalised QR)
 *
 * Flow:
 *   1. Fetch session in background. Kick off menu fetch as soon as we know
 *      the caterer.
 *   2. If we have (or remember) a student ID, go straight to the form view
 *      and kick off existing-feedback/selection fetches.
 *   3. Otherwise show a picker, fetching the session's students. Once one is
 *      picked we remember it (localStorage) and continue.
 *
 * The menu is pre-fetched so the meal picker opens instantly.
 */

// ============================================================
// Constants
// ============================================================

const AT_BASE = `https://api.airtable.com/v0/${CONFIG.BASE_ID}`;

const POSITIVE_TAGS = new Set(["Gluten Free", "Dairy Free", "Nut Free", "Vegetarian", "Halal"]);

const TAG_LABEL = {
  "Gluten Free": "GF",
  "Dairy Free":  "DF",
  "Nut Free":    "NF",
  "Vegetarian":  "Veg",
  "Halal":       "Halal",
};

// Name-keyword fallback for negative dietary requirements that aren't
// expressed as Menu Item tags.
const NEGATIVE_KEYWORDS = {
  "No Beef":      ["beef", "bulgogi"],
  "No Pork":      ["pork", "bacon", "ham"],
  "No Seafood":   ["seafood", "shrimp", "prawn", "fish", "salmon", "tuna", "shellfish", "crab", "lobster"],
  "No Shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
  "No Fish":      ["fish", "salmon", "tuna"],
  "No Red Meat":  ["beef", "lamb", "pork", "bulgogi"],
};

const CACHE_TTL = {
  session:   60 * 60 * 1000,         // 1h
  student:   24 * 60 * 60 * 1000,    // 24h
  students:  60 * 60 * 1000,         // 1h
  menu:      24 * 60 * 60 * 1000,    // 24h
  selection: 5 * 60 * 1000,          // 5m  — may change as user submits
  feedback:  5 * 60 * 1000,
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
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Airtable ${res.status}: ${text}`);
  }
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
// Local storage helpers
// ============================================================

const ls = {
  get(k)        { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v)     { try { localStorage.setItem(k, v); } catch {} },
  remove(k)     { try { localStorage.removeItem(k); } catch {} },
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
function getKnownStudent(sessionId)  { return ls.get(knownStudentKey(sessionId)); }
function setKnownStudent(sessionId, sid) { ls.set(knownStudentKey(sessionId), sid); }
function clearKnownStudent(sessionId)    { ls.remove(knownStudentKey(sessionId)); }

// ============================================================
// Data loaders (cache-first, returns the cached value if fresh)
// ============================================================

async function loadSession(sessionId) {
  const key = `padea_session_${sessionId}`;
  const cached = cacheGet(key, "session");
  if (cached) return cached;
  const rec = await atGet("Sessions", sessionId);
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
    "fields[]": ["Student Name", "Dietary Requirements"],
  });
  const result = recs.map(r => ({
    id: r.id,
    name: r.fields["Student Name"] || "(no name)",
    dietary: r.fields["Dietary Requirements"] || [],
  })).sort((a, b) => a.name.localeCompare(b.name));
  cacheSet(key, result);
  return result;
}

async function loadMenuItems(catererId) {
  const key = `padea_menu_${catererId}`;
  const cached = cacheGet(key, "menu");
  if (cached) return cached;
  const items = await atList("Menu Items", {
    filterByFormula: `FIND('${catererId}', ARRAYJOIN({Caterer}))`,
    "fields[]": ["Menu Item Name", "Dietary Tags"],
  });
  cacheSet(key, items);
  return items;
}

async function loadExistingSelection(studentId, sessionId) {
  const key = `padea_sel_${studentId}_${sessionId}`;
  const cached = cacheGet(key, "selection");
  if (cached !== null) return cached;
  const formula = `AND(FIND('${studentId}', ARRAYJOIN({Student})), FIND('${sessionId}', ARRAYJOIN({Session})))`;
  const recs = await atList("Meal Selections", {
    filterByFormula: formula,
    "fields[]": ["Menu Item", "Selection Date"],
  });
  recs.sort((a, b) => (b.fields["Selection Date"] || "").localeCompare(a.fields["Selection Date"] || ""));
  const sel = recs[0]
    ? { recordId: recs[0].id, itemId: (recs[0].fields["Menu Item"] || [])[0] || null }
    : { recordId: null, itemId: null };
  cacheSet(key, sel);
  return sel;
}

async function loadExistingFeedback(studentId, sessionId) {
  const key = `padea_fb_${studentId}_${sessionId}`;
  const cached = cacheGet(key, "feedback");
  if (cached !== null) return cached;
  const formula = `AND(FIND('${studentId}', ARRAYJOIN({Student})), FIND('${sessionId}', ARRAYJOIN({Session})))`;
  const recs = await atList("Meal Feedback", {
    filterByFormula: formula,
    "fields[]": ["Rating", "Comment", "Menu Item"],
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
// Dietary compatibility
// ============================================================

function isCompatible(itemFields, requirements) {
  if (!requirements || !requirements.length) return true;
  const tags = new Set(itemFields["Dietary Tags"] || []);
  const name = (itemFields["Menu Item Name"] || "").toLowerCase();
  for (const req of requirements) {
    if (req === "Opted out of Catering") continue;
    if (POSITIVE_TAGS.has(req) && !tags.has(req)) return false;
    const kws = NEGATIVE_KEYWORDS[req];
    if (kws && kws.some(k => name.includes(k))) return false;
  }
  return true;
}

// ============================================================
// State
// ============================================================

const state = {
  sessionId: null,
  studentId: null,

  session: null,        // raw Airtable record
  student: null,        // raw Airtable record
  menuItems: null,      // raw Airtable records
  menuPromise: null,    // in-flight menu fetch (for instant picker open)

  // Initial (loaded) values
  initialRating: 0,
  initialComment: "",
  initialMealItemId: null,

  // Pending (user-edited) values
  rating: 0,
  comment: "",
  mealItemId: null,

  // Existing record IDs for upsert
  feedbackRecordId: null,
  selectionRecordId: null,

  view: "loading",
};

// ============================================================
// View routing
// ============================================================

const views = ["picker", "form", "meals", "done"];

function showView(name) {
  state.view = name;
  for (const v of views) {
    document.getElementById(`view-${v}`).classList.toggle("hidden", v !== name);
  }
}

// ============================================================
// Init
// ============================================================

const app = {

  async init() {
    const params = new URLSearchParams(location.search);
    state.sessionId = params.get("session");

    if (!state.sessionId) {
      showError("Missing session ID. Please scan a valid QR code.");
      return;
    }

    // 1. Decide the view *before* any network so the first paint is correct.
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

    // 2. Load session (cached if fresh).
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

    // 3. As soon as we know the caterer, prefetch the menu.
    const catererId = (session.fields.Caterer || [])[0];
    if (catererId) {
      state.menuPromise = loadMenuItems(catererId)
        .then(items => { state.menuItems = items; return items; })
        .catch(err => { console.error(err); return []; });
    }

    // 4. Drive the chosen view.
    if (studentId) await loadFormData(studentId);
    else           await loadPickerData();
  },

  // -------------- Picker --------------
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

  // -------------- Rating --------------
  setRating(v) {
    state.rating = v;
    document.querySelectorAll("#stars .star").forEach(s => {
      s.classList.toggle("active", Number(s.dataset.v) <= v);
    });
    document.getElementById("comment-wrap").classList.toggle("hidden", v >= 4 || v === 0);
    updateSubmitState();
  },

  setComment(text) {
    state.comment = text;
    updateSubmitState();
  },

  // -------------- Meal picker --------------
  openMealPicker() {
    if (!state.student) return; // dietary reqs not loaded yet — shouldn't be reachable
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
    // small delay so the user sees the selection animate
    setTimeout(() => showView("form"), 140);
  },

  // -------------- Submit --------------
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

  // -------------- Done -> back to form --------------
  reset() {
    // values are already in state; just go back to the form view.
    refreshFormFromState();
    showView("form");
  },
};

// ============================================================
// View skeletons (sync — paint immediately) + data loaders
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
  // Keep prefetched menuItems / menuPromise — they're per-caterer, not per-student.
  state.student = null;
  state.initialRating = 0;
  state.initialComment = "";
  state.initialMealItemId = null;
  state.rating = 0;
  state.comment = "";
  state.mealItemId = null;
  state.feedbackRecordId = null;
  state.selectionRecordId = null;
}

async function loadFormData(studentId) {
  // 1. Student record — needed to render name and to know dietary reqs.
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

  // 2. Existing selection & feedback — both background, don't block UI.
  loadExistingSelection(studentId, state.sessionId)
    .then(sel => {
      state.selectionRecordId = sel.recordId;
      state.initialMealItemId = sel.itemId;
      if (state.mealItemId === null) state.mealItemId = sel.itemId;
      updateMealTrigger();
      updateSubmitState();
    })
    .catch(err => console.error(err));

  loadExistingFeedback(studentId, state.sessionId)
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

  // 3. When menu arrives (if not already), refresh meal trigger.
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

  const reqs = state.student?.fields["Dietary Requirements"] || [];
  sub.textContent = reqs.length
    ? `Filtered for: ${reqs.join(", ")}`
    : "All available meals from your caterer.";

  // If menu hasn't arrived yet, show spinner.
  if (!state.menuItems) {
    loading.classList.remove("hidden");
    if (state.menuPromise) {
      state.menuPromise.then(() => {
        if (state.view === "meals") renderMealList();
      });
    }
    return;
  }
  loading.classList.add("hidden");

  const compatible = state.menuItems.filter(i =>
    isCompatible(i.fields, reqs)
  );

  if (!compatible.length) {
    empty.classList.remove("hidden");
    empty.textContent = state.menuItems.length
      ? "No meals match your dietary requirements. Speak to your on-site manager."
      : "No menu items found for this caterer.";
    return;
  }

  ul.classList.remove("hidden");
  ul.innerHTML = compatible.map(item => {
    const name = item.fields["Menu Item Name"] || "—";
    const tags = item.fields["Dietary Tags"] || [];
    const selected = item.id === state.mealItemId;
    const tagsHtml = tags
      .map(t => `<span class="tag">${TAG_LABEL[t] || t}</span>`).join("");
    return `
      <li class="meal-item${selected ? " selected" : ""}"
          onclick="app.selectMeal('${item.id}')">
        <div class="meal-radio"></div>
        <div class="meal-content">
          <div class="meal-name">${escapeHtml(name)}</div>
          <div class="meal-tags">${tagsHtml}</div>
        </div>
      </li>`;
  }).join("");
}

function updateMealTrigger() {
  const trig = document.getElementById("meal-trigger");
  const label = document.getElementById("meal-trigger-label");
  const nameEl = document.getElementById("meal-trigger-name");

  // Session has no caterer assigned — nothing to choose from.
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

// ============================================================
// Persistence
// ============================================================

async function persistChanges() {
  const today = new Date().toISOString().slice(0, 10);

  const ratingChanged = state.rating > 0 &&
    (state.rating !== state.initialRating || state.comment !== state.initialComment);
  const mealChanged = state.mealItemId && state.mealItemId !== state.initialMealItemId;

  const ops = [];

  // Meal Feedback
  if (ratingChanged) {
    const fields = {
      "Student": [state.studentId],
      "Session": [state.sessionId],
      "Rating": state.rating,
      // Always include Comment so clearing it actually clears the field.
      "Comment": state.comment.trim(),
      // Link feedback to the meal they had (their current selection, if any)
      ...(state.initialMealItemId ? { "Menu Item": [state.initialMealItemId] } : {}),
    };
    if (state.feedbackRecordId) {
      ops.push(atUpdate("Meal Feedback", state.feedbackRecordId, fields));
    } else {
      fields["Feedback ID"] = makeId("FB", state.studentId, state.sessionId);
      ops.push(
        atCreate("Meal Feedback", fields).then(rec => {
          state.feedbackRecordId = rec.id;
        })
      );
    }
  }

  // Meal Selection
  if (mealChanged) {
    const fields = {
      "Student": [state.studentId],
      "Session": [state.sessionId],
      "Menu Item": [state.mealItemId],
      "Selection Date": today,
    };
    if (state.selectionRecordId) {
      ops.push(atUpdate("Meal Selections", state.selectionRecordId, fields));
    } else {
      fields["Selection ID"] = makeId("SEL", state.studentId, state.sessionId);
      ops.push(
        atCreate("Meal Selections", fields).then(rec => {
          state.selectionRecordId = rec.id;
        })
      );
    }
  }

  await Promise.all(ops);

  // Update initial values so a re-submit without further edits is a no-op.
  if (ratingChanged) {
    state.initialRating = state.rating;
    state.initialComment = state.comment;
  }
  if (mealChanged) {
    state.initialMealItemId = state.mealItemId;
  }

  // Bust cached selection/feedback so a future visit sees fresh data.
  ls.remove(`padea_sel_${state.studentId}_${state.sessionId}`);
  ls.remove(`padea_fb_${state.studentId}_${state.sessionId}`);
}

function doneMessage() {
  const parts = [];
  if (state.rating > 0) parts.push("Rating saved");
  if (state.mealItemId) parts.push("preference saved");
  return parts.length ? parts.join(" — ") + "." : "Your response has been saved.";
}

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
  const date = fields["Date"] || "";
  return [id, date].filter(Boolean).join(" · ");
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
