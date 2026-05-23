/**
 * Padea Meals — Student meal selection and feedback app.
 *
 * Requires config.env.js to be loaded first (defines window.CONFIG with
 * BASE_ID and API_KEY). That file is gitignored — never commit it.
 *
 * URL parameters:
 *   ?session=recXXXXXXXXXXXXXX   — Airtable record ID of the session
 *   ?key=AIRTABLE_PAT            — overrides CONFIG.API_KEY (dev shortcut)
 */

// ============================================================

const AT_BASE = `https://api.airtable.com/v0/${CONFIG.BASE_ID}`;

// Dietary tag display helpers
const TAG_META = {
  "Gluten Free": { label: "GF", css: "tag-gf" },
  "Dairy Free": { label: "DF", css: "tag-df" },
  "Nut Free": { label: "NF", css: "tag-nf" },
  "Vegetarian": { label: "Veg", css: "tag-veg" },
  "Halal": { label: "Halal", css: "tag-halal" },
};

// Negative dietary requirements — used to filter out incompatible menu items
const NEGATIVE_MAP = {
  "No Beef": ["beef", "bulgogi"],
  "No Pork": ["pork", "bacon", "ham"],
  "No Seafood": ["seafood", "shrimp", "prawn", "fish", "salmon", "tuna", "shellfish", "crab", "lobster"],
  "No Shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster"],
  "No Fish": ["fish", "salmon", "tuna"],
  "No Red Meat": ["beef", "lamb", "pork", "bulgogi"],
};

// ============================================================
// Airtable API helpers
// ============================================================

function apiKey() {
  const params = new URLSearchParams(location.search);
  return params.get("key") || CONFIG.API_KEY;
}

async function atFetch(table, params = {}) {
  const url = new URL(`${AT_BASE}/${encodeURIComponent(table)}`);
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(val => url.searchParams.append(k, val));
    else url.searchParams.set(k, v);
  }

  let records = [];
  let offset = null;

  do {
    if (offset) url.searchParams.set("offset", offset);
    const res = await fetch(url.toString(), {
      headers: { Authorization: `Bearer ${apiKey()}` },
    });
    if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
    const json = await res.json();
    records = records.concat(json.records || []);
    offset = json.offset;
  } while (offset);

  return records;
}

async function atPost(table, fields) {
  const res = await fetch(`${AT_BASE}/${encodeURIComponent(table)}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ records: [{ fields }] }),
  });
  if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
  return (await res.json()).records[0];
}

async function atPatch(table, recordId, fields) {
  const res = await fetch(`${AT_BASE}/${encodeURIComponent(table)}/${recordId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${apiKey()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ fields }),
  });
  if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
  return (await res.json());
}

// ============================================================
// Dietary compatibility
// ============================================================

function isItemCompatible(itemFields, studentDietary) {
  if (!studentDietary || studentDietary.length === 0) return true;
  if (studentDietary.includes("Opted out of Catering")) return false;

  const itemTags = new Set(itemFields["Dietary Tags"] || []);
  const itemNameLower = (itemFields["Menu Item Name"] || "").toLowerCase();

  for (const req of studentDietary) {
    // Positive requirements: item must have the tag
    if (TAG_META[req] && !itemTags.has(req)) return false;

    // Negative requirements: item name must not contain keywords
    const keywords = NEGATIVE_MAP[req];
    if (keywords && keywords.some(kw => itemNameLower.includes(kw))) return false;
  }
  return true;
}

// ============================================================
// App state & navigation
// ============================================================

const state = {
  sessionId: null,
  sessionFields: null,
  catererItems: [],       // menu items for this session's caterer
  students: [],           // students enrolled in this session
  selectedStudent: null,
  selectedMenuItemForRating: null,
  currentRating: 0,

  // Existing selection for this student+session (for upsert)
  existingSelectionId: null,
  // All selections for upsert check
  allSelections: [],
  // All feedback for this session
  allFeedback: [],
};

const app = {
  // ---- Screen navigation ----
  goTo(screenName) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById(`screen-${screenName}`).classList.add("active");
  },

  // ---- Entry point ----
  async init() {
    const params = new URLSearchParams(location.search);
    state.sessionId = params.get("session");

    if (!state.sessionId) {
      showError("No session ID in URL. Please scan the correct QR code.");
      return;
    }

    try {
      await loadSessionData();
      renderStudentList();
      app.goTo("students");
    } catch (err) {
      console.error(err);
      showError(err.message || "Failed to load session data.");
    }
  },

  // ---- Student picker ----
  selectStudent(studentId) {
    state.selectedStudent = state.students.find(s => s.id === studentId);
    if (!state.selectedStudent) return;

    document.getElementById("student-name-display").textContent =
      state.selectedStudent.fields["Student Name"];

    // Disable rating if student opted out of catering
    const dietary = state.selectedStudent.fields["Dietary Requirements"] || [];
    const optedOut = dietary.includes("Opted out of Catering");
    const btnSelect = document.getElementById("btn-select");
    const btnRate = document.getElementById("btn-rate");

    if (optedOut) {
      btnSelect.classList.add("disabled");
      btnRate.classList.add("disabled");
      btnSelect.querySelector(".action-desc").textContent = "Not enrolled in catering";
      btnRate.querySelector(".action-desc").textContent = "Not enrolled in catering";
    } else {
      btnSelect.classList.remove("disabled");
      btnRate.classList.remove("disabled");
      btnSelect.querySelector(".action-desc").textContent = "Choose what you want to eat";
      btnRate.querySelector(".action-desc").textContent = "Tell us what you thought";
    }

    app.goTo("actions");
  },

  // ---- Rating flow ----
  startRating() {
    const stu = state.selectedStudent;
    document.getElementById("rate-student-badge").textContent = stu.fields["Student Name"];
    document.getElementById("rate-form").classList.add("hidden");
    state.selectedMenuItemForRating = null;
    state.currentRating = 0;
    resetStars();
    renderRateItemList();
    app.goTo("rate");
  },

  selectItemForRating(itemId) {
    const item = state.catererItems.find(i => i.id === itemId);
    if (!item) return;
    state.selectedMenuItemForRating = item;
    document.getElementById("rate-item-name").textContent = item.fields["Menu Item Name"];
    document.getElementById("rate-comment").value = "";
    state.currentRating = 0;
    resetStars();
    document.getElementById("rate-form").classList.remove("hidden");
    document.getElementById("rate-form").scrollIntoView({ behavior: "smooth" });
  },

  setRating(value) {
    state.currentRating = value;
    document.querySelectorAll(".star").forEach((s, i) => {
      s.classList.toggle("active", i < value);
    });
  },

  async submitRating() {
    if (!state.currentRating) {
      alert("Please tap a star to give a rating.");
      return;
    }
    const stu = state.selectedStudent;
    const item = state.selectedMenuItemForRating;
    const comment = document.getElementById("rate-comment").value.trim();

    const btn = document.getElementById("btn-submit-rating");
    btn.textContent = "Saving…";
    btn.disabled = true;

    try {
      // Check for existing feedback for this student+session+item
      const existing = state.allFeedback.find(fb => {
        const fstu = (fb.fields["Student"] || [])[0];
        const fsess = (fb.fields["Session"] || [])[0];
        const fitem = (fb.fields["Menu Item"] || [])[0];
        return fstu === stu.id && fsess === state.sessionId && fitem === item.id;
      });

      const feedbackId = `FB-${stu.id.slice(-6)}-${item.id.slice(-6)}-${state.sessionId.slice(-6)}`;
      const fields = {
        "Feedback ID": feedbackId,
        "Student": [stu.id],
        "Session": [state.sessionId],
        "Menu Item": [item.id],
        "Rating": state.currentRating,
        ...(comment ? { "Comment": comment } : {}),
      };

      if (existing) {
        await atPatch("Meal Feedback", existing.id, fields);
      } else {
        await atPost("Meal Feedback", fields);
      }

      showConfirmation("Rating saved!", `You gave "${item.fields["Menu Item Name"]}" ${state.currentRating} star${state.currentRating !== 1 ? "s" : ""}.`, "⭐");
    } catch (err) {
      console.error(err);
      alert("Failed to save rating. Please try again.");
    } finally {
      btn.textContent = "Submit Rating";
      btn.disabled = false;
    }
  },

  // ---- Meal selection flow ----
  startSelection() {
    const stu = state.selectedStudent;
    document.getElementById("select-student-badge").textContent = stu.fields["Student Name"];

    // Find the NEXT session for this school+day for displaying context
    // (selections are for next week — we link to THIS session record as a placeholder;
    //  generate_orders.py will look up the actual next session when compiling orders)
    state.existingSelectionId = null;
    const existingSel = state.allSelections.find(sel => {
      return (sel.fields["Student"] || [])[0] === stu.id &&
        (sel.fields["Session"] || [])[0] === state.sessionId;
    });
    if (existingSel) state.existingSelectionId = existingSel.id;

    renderMenuList(existingSel);
    app.goTo("select");
  },

  async selectMeal(itemId) {
    const stu = state.selectedStudent;
    const item = state.catererItems.find(i => i.id === itemId);
    if (!item) return;

    // Highlight the card immediately for responsiveness
    document.querySelectorAll(".menu-item-card").forEach(c => c.classList.remove("selected"));
    document.getElementById(`item-${itemId}`)?.classList.add("selected");

    try {
      const selectionId = `SEL-${stu.id.slice(-6)}-${state.sessionId.slice(-6)}`;
      const today = new Date().toISOString().slice(0, 10);
      const fields = {
        "Selection ID": selectionId,
        "Student": [stu.id],
        "Session": [state.sessionId],
        "Menu Item": [item.id],
        "Selection Date": today,
      };

      if (state.existingSelectionId) {
        await atPatch("Meal Selections", state.existingSelectionId, fields);
      } else {
        const created = await atPost("Meal Selections", fields);
        state.existingSelectionId = created.id;
        // Update local state
        state.allSelections.push(created);
      }

      showConfirmation(
        "Meal selected!",
        `You chose "${item.fields["Menu Item Name"]}" for next week.`,
        "🍽️"
      );
    } catch (err) {
      console.error(err);
      alert("Failed to save your selection. Please try again.");
      // Revert highlight
      document.querySelectorAll(".menu-item-card").forEach(c => c.classList.remove("selected"));
    }
  },
};

// ============================================================
// Data loading
// ============================================================

async function loadSessionData() {
  // Load session
  const sessions = await atFetch("Sessions", {
    filterByFormula: `RECORD_ID()='${state.sessionId}'`,
  });
  if (!sessions.length) throw new Error("Session not found. Please scan the correct QR code.");
  state.sessionFields = sessions[0].fields;

  const sessionLabel = state.sessionFields["Session ID"] || state.sessionId;
  document.getElementById("session-info").textContent = sessionLabel;

  // Load caterer's menu items
  const catererLinks = state.sessionFields["Caterer"] || [];
  if (catererLinks.length) {
    const catId = catererLinks[0];
    state.catererItems = await atFetch("Menu Items", {
      filterByFormula: `FIND('${catId}', ARRAYJOIN({Caterer}))`,
    });
  }

  // Load enrolled students via the Students table (filter by session link)
  // We have to fetch all students and filter client-side since Airtable
  // doesn't support filtering on linked-record arrays cleanly.
  const allStudents = await atFetch("Students");
  state.students = allStudents.filter(stu => {
    const sessLinks = stu.fields["Sessions"] || [];
    return sessLinks.includes(state.sessionId);
  }).sort((a, b) => {
    const na = a.fields["Student Name"] || "";
    const nb = b.fields["Student Name"] || "";
    return na.localeCompare(nb);
  });

  // Load existing selections for this session
  state.allSelections = await atFetch("Meal Selections", {
    filterByFormula: `FIND('${state.sessionId}', ARRAYJOIN({Session}))`,
  });

  // Load feedback for this session
  state.allFeedback = await atFetch("Meal Feedback", {
    filterByFormula: `FIND('${state.sessionId}', ARRAYJOIN({Session}))`,
  });
}

// ============================================================
// Rendering
// ============================================================

function renderStudentList() {
  const container = document.getElementById("student-list");
  if (!state.students.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🤔</div>
        <p>No students found for this session.</p>
      </div>`;
    return;
  }

  container.innerHTML = state.students.map(stu => {
    const name = stu.fields["Student Name"] || "Unknown";
    const initials = name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const dietary = stu.fields["Dietary Requirements"] || [];
    const dietTags = dietary.filter(d => TAG_META[d]);

    const tagsHtml = dietTags.map(d =>
      `<span class="dietary-tag">${TAG_META[d].label}</span>`
    ).join("");

    return `
      <button class="student-btn" onclick="app.selectStudent('${stu.id}')">
        <div class="student-avatar">${initials}</div>
        <div>
          <div>${name}</div>
          ${tagsHtml ? `<div class="dietary-tags">${tagsHtml}</div>` : ""}
        </div>
      </button>`;
  }).join("");
}

function renderMenuList(existingSel) {
  const container = document.getElementById("menu-items-list");
  const stu = state.selectedStudent;
  const dietary = stu.fields["Dietary Requirements"] || [];

  const existingItemId = existingSel ? (existingSel.fields["Menu Item"] || [])[0] : null;

  const compatible = state.catererItems.filter(item =>
    isItemCompatible(item.fields, dietary)
  );

  if (!compatible.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🚫</div>
        <p>No menu items match your dietary requirements for this caterer.</p>
        <p style="margin-top:8px;font-size:.85rem;">Please speak to your on-site manager.</p>
      </div>`;
    return;
  }

  container.innerHTML = compatible.map(item => {
    const f = item.fields;
    const name = f["Menu Item Name"] || "?";
    const price = f["Price"] != null ? `$${Number(f["Price"]).toFixed(2)}` : "";
    const tags = (f["Dietary Tags"] || []);
    const isSelected = item.id === existingItemId;

    const tagsHtml = tags.map(t => {
      const m = TAG_META[t];
      return m ? `<span class="menu-item-tag ${m.css}">${m.label}</span>` : "";
    }).join("");

    const prevNote = isSelected
      ? `<div class="prev-note">✓ Your current selection</div>`
      : "";

    return `
      <div id="item-${item.id}" class="menu-item-card ${isSelected ? "selected" : ""}"
           onclick="app.selectMeal('${item.id}')">
        <div class="menu-item-info">
          <div class="menu-item-name">${name}</div>
          <div class="menu-item-meta">
            ${price ? `<span class="menu-item-price">${price}</span>` : ""}
            ${tagsHtml}
          </div>
          ${prevNote}
        </div>
        <div class="menu-item-check">${isSelected ? "✓" : ""}</div>
      </div>`;
  }).join("");
}

function renderRateItemList() {
  const container = document.getElementById("rate-items-list");

  if (!state.catererItems.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🍽️</div>
        <p>No menu items found for this session's caterer.</p>
      </div>`;
    return;
  }

  const stu = state.selectedStudent;
  const dietary = stu.fields["Dietary Requirements"] || [];

  // Show all compatible items (they might have eaten any of them)
  const visible = state.catererItems.filter(item =>
    isItemCompatible(item.fields, dietary)
  );

  container.innerHTML = visible.map(item => {
    const f = item.fields;
    const name = f["Menu Item Name"] || "?";
    const tags = (f["Dietary Tags"] || []);

    const tagsHtml = tags.map(t => {
      const m = TAG_META[t];
      return m ? `<span class="menu-item-tag ${m.css}">${m.label}</span>` : "";
    }).join("");

    return `
      <div class="menu-item-card" onclick="app.selectItemForRating('${item.id}')">
        <div class="menu-item-info">
          <div class="menu-item-name">${name}</div>
          <div class="menu-item-meta">${tagsHtml}</div>
        </div>
        <div class="menu-item-check">›</div>
      </div>`;
  }).join("");
}

// ============================================================
// Utility
// ============================================================

function showError(msg) {
  document.getElementById("error-message").textContent = msg;
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById("screen-error").classList.add("active");
}

function showConfirmation(title, message, icon = "✅") {
  document.getElementById("confirm-icon").textContent = icon;
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-message").textContent = message;
  app.goTo("confirm");
}

function resetStars() {
  document.querySelectorAll(".star").forEach(s => s.classList.remove("active"));
}

// ============================================================
// Bootstrap
// ============================================================
document.addEventListener("DOMContentLoaded", () => app.init());
