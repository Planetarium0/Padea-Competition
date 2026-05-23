/**
 * Padea Meals — Instant-load meal rating and preference app.
 *
 * Requires config.env.js (defines window.CONFIG with BASE_ID and API_KEY).
 * URL: index.html?session=<Airtable session record ID>
 *
 * Loading strategy:
 *   - Rating section is interactive immediately (no data needed).
 *   - Session + menu load in the background; meal section shows a spinner.
 *   - Session fields cached 1 h, menu items cached 24 h.
 *   - Dietary filter and previous selections/ratings are stored locally.
 */

const AT_BASE = `https://api.airtable.com/v0/${CONFIG.BASE_ID}`;

const TAG_META = {
  "Gluten Free": { label: "GF",    css: "tag-gf"    },
  "Dairy Free":  { label: "DF",    css: "tag-df"    },
  "Nut Free":    { label: "NF",    css: "tag-nf"    },
  "Vegetarian":  { label: "Veg",   css: "tag-veg"   },
  "Halal":       { label: "Halal", css: "tag-halal" },
};

const NEGATIVE_MAP = {
  "No Beef":     ["beef", "bulgogi"],
  "No Pork":     ["pork", "bacon", "ham"],
  "No Seafood":  ["seafood", "shrimp", "prawn", "fish", "salmon", "tuna", "shellfish", "crab", "lobster"],
  "No Shellfish":["shellfish", "shrimp", "prawn", "crab", "lobster"],
  "No Fish":     ["fish", "salmon", "tuna"],
  "No Red Meat": ["beef", "lamb", "pork", "bulgogi"],
};

const DIETARY_OPTIONS = [
  "Gluten Free", "Dairy Free", "Nut Free", "Vegetarian", "Halal",
  "No Beef", "No Pork", "No Seafood", "No Fish", "No Red Meat",
];

// ============================================================
// Airtable API helpers
// ============================================================

function apiKey() {
  return new URLSearchParams(location.search).get("key") || CONFIG.API_KEY;
}

async function atFetch(table, params = {}) {
  const url = new URL(`${AT_BASE}/${encodeURIComponent(table)}`);
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(val => url.searchParams.append(k, val));
    else url.searchParams.set(k, v);
  }
  let records = [], offset = null;
  do {
    if (offset) url.searchParams.set("offset", offset);
    const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${apiKey()}` } });
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
    headers: { Authorization: `Bearer ${apiKey()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ records: [{ fields }] }),
  });
  if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
  return (await res.json()).records[0];
}

async function atGetRecord(table, recordId, fieldNames = []) {
  const url = new URL(`${AT_BASE}/${encodeURIComponent(table)}/${recordId}`);
  fieldNames.forEach(f => url.searchParams.append("fields[]", f));
  const res = await fetch(url.toString(), { headers: { Authorization: `Bearer ${apiKey()}` } });
  if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
  return res.json(); // returns { id, fields, createdTime }
}

async function atPatch(table, recordId, fields) {
  const res = await fetch(`${AT_BASE}/${encodeURIComponent(table)}/${recordId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${apiKey()}`, "Content-Type": "application/json" },
    body: JSON.stringify({ fields }),
  });
  if (!res.ok) throw new Error(`Airtable error ${res.status}: ${await res.text()}`);
  return res.json();
}

// ============================================================
// Dietary compatibility
// ============================================================

function isItemCompatible(itemFields, requirements) {
  if (!requirements || !requirements.length) return true;
  const itemTags = new Set(itemFields["Dietary Tags"] || []);
  const nameLower = (itemFields["Menu Item Name"] || "").toLowerCase();
  for (const req of requirements) {
    if (TAG_META[req] && !itemTags.has(req)) return false;
    const kws = NEGATIVE_MAP[req];
    if (kws && kws.some(kw => nameLower.includes(kw))) return false;
  }
  return true;
}

// ============================================================
// localStorage — TTL cache for Airtable data
// ============================================================

const CACHE_TTL = {
  session: 60 * 60 * 1000,      // 1 hour
  menu:    24 * 60 * 60 * 1000, // 24 hours
};

function cacheGet(key, type) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw);
    if (Date.now() - ts > CACHE_TTL[type]) { localStorage.removeItem(key); return null; }
    return data;
  } catch { return null; }
}

function cacheSet(key, data) {
  try { localStorage.setItem(key, JSON.stringify({ ts: Date.now(), data })); } catch {}
}

// ============================================================
// localStorage — app state (no TTL, session-scoped or global)
// ============================================================

const ls = {
  get: (k)    => { try { return localStorage.getItem(k); }          catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, String(v)); }      catch {} },
  getJson: (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } },
  setJson: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};

function getDietaryFilter()   { return ls.getJson("padea_dietary_filter") || []; }
function setDietaryFilter(v)  { ls.setJson("padea_dietary_filter", v); }

function getSavedRating(sid)  { const v = parseInt(ls.get(`padea_fb_rating_${sid}`), 10); return isNaN(v) ? 0 : v; }

// ============================================================
// State
// ============================================================

const state = {
  sessionId:    null,
  sessionFields: null,
  catererItems: [],
  dietaryFilter: [],
  currentRating: 0,
};

// ============================================================
// App
// ============================================================

const app = {
  async init() {
    state.sessionId = new URLSearchParams(location.search).get("session");
    if (!state.sessionId) {
      showError("No session ID in URL. Please scan the correct QR code.");
      showMealsError();
      return;
    }

    // Restore local state — no network needed, page is already interactive
    state.dietaryFilter = getDietaryFilter();
    renderDietaryFilter();

    const savedRating = getSavedRating(state.sessionId);
    if (savedRating) {
      state.currentRating = savedRating;
      document.querySelectorAll(".star").forEach((s, i) =>
        s.classList.toggle("active", i < savedRating)
      );
      // Stars pre-filled but button stays disabled until user taps to change
    }

    // Background load — doesn't block the UI
    loadSessionData().catch(err => {
      showError(err.message);
      showMealsError();
    });
  },

  setRating(value) {
    state.currentRating = value;
    document.querySelectorAll(".star").forEach((s, i) =>
      s.classList.toggle("active", i < value)
    );
    document.getElementById("btn-submit-rating").disabled = false;
    document.getElementById("rating-saved-msg").classList.add("hidden");
  },

  async submitRating() {
    if (!state.currentRating) return;

    const btn = document.getElementById("btn-submit-rating");
    btn.textContent = "Saving…";
    btn.disabled = true;

    const comment  = document.getElementById("rate-comment").value.trim();
    const existingId = ls.get(`padea_fb_rec_${state.sessionId}`);

    try {
      const fields = {
        ...(!existingId && { "Feedback ID": `FB-${state.sessionId.slice(-6)}-${Date.now()}` }),
        "Session": [state.sessionId],
        "Rating": state.currentRating,
        ...(comment ? { "Comment": comment } : {}),
      };

      if (existingId) {
        await atPatch("Meal Feedback", existingId, fields);
      } else {
        const created = await atPost("Meal Feedback", fields);
        ls.set(`padea_fb_rec_${state.sessionId}`, created.id);
      }

      ls.set(`padea_fb_rating_${state.sessionId}`, state.currentRating);
      btn.textContent = "Save Rating";
      showSavedMsg();
    } catch (err) {
      console.error(err);
      alert("Failed to save rating. Please try again.");
      btn.textContent = "Save Rating";
      btn.disabled = false;
    }
  },

  toggleDietaryFilter(chip, option) {
    chip.classList.toggle("active");
    if (chip.classList.contains("active")) {
      if (!state.dietaryFilter.includes(option)) state.dietaryFilter.push(option);
    } else {
      state.dietaryFilter = state.dietaryFilter.filter(d => d !== option);
    }
    setDietaryFilter(state.dietaryFilter);
    renderMenuList();
  },

  async selectMeal(itemId) {
    const item = state.catererItems.find(i => i.id === itemId);
    if (!item) return;

    // Immediate visual feedback
    document.querySelectorAll(".menu-item-card").forEach(c => {
      c.classList.remove("selected");
      c.querySelector(".menu-item-check").textContent = "";
      c.querySelector(".prev-note")?.remove();
    });
    const card = document.getElementById(`item-${itemId}`);
    if (card) {
      card.classList.add("selected");
      card.querySelector(".menu-item-check").textContent = "✓";
      const note = document.createElement("div");
      note.className = "prev-note";
      note.textContent = "✓ Your selection";
      card.querySelector(".menu-item-info").appendChild(note);
    }

    try {
      const existingId = ls.get(`padea_sel_rec_${state.sessionId}`);
      const fields = {
        ...(!existingId && { "Selection ID": `SEL-${state.sessionId.slice(-6)}-${Date.now()}` }),
        "Session": [state.sessionId],
        "Menu Item": [itemId],
        "Selection Date": new Date().toISOString().slice(0, 10),
      };

      if (existingId) {
        await atPatch("Meal Selections", existingId, fields);
      } else {
        const created = await atPost("Meal Selections", fields);
        ls.set(`padea_sel_rec_${state.sessionId}`, created.id);
      }
      ls.set(`padea_sel_item_${state.sessionId}`, itemId);
    } catch (err) {
      console.error(err);
      alert("Failed to save selection. Please try again.");
      document.querySelectorAll(".menu-item-card").forEach(c => {
        c.classList.remove("selected");
        c.querySelector(".menu-item-check").textContent = "";
        c.querySelector(".prev-note")?.remove();
      });
    }
  },
};

// ============================================================
// Data loading
// ============================================================

async function loadSessionData() {
  // Session fields — cached 1 h
  const sessKey = `padea_sess_${state.sessionId}`;
  let sessionFields = cacheGet(sessKey, "session");
  if (!sessionFields) {
    const rec = await atGetRecord("Sessions", state.sessionId, ["Session ID", "Caterer"]);
    if (!rec.fields) throw new Error("Session not found. Please scan the correct QR code.");
    sessionFields = rec.fields;
    cacheSet(sessKey, sessionFields);
  }
  state.sessionFields = sessionFields;
  document.getElementById("session-info").textContent =
    sessionFields["Session ID"] || state.sessionId;

  // Menu items — cached 24 h per caterer
  const [catId] = sessionFields["Caterer"] || [];
  if (!catId) { showMealsError("No caterer assigned to this session."); return; }

  const menuKey = `padea_menu_${catId}`;
  let menuItems = cacheGet(menuKey, "menu");
  if (!menuItems) {
    menuItems = await atFetch("Menu Items", {
      filterByFormula: `FIND('${catId}', ARRAYJOIN({Caterer}))`,
      "fields[]": ["Menu Item Name", "Caterer", "Price", "Dietary Tags"],
    });
    cacheSet(menuKey, menuItems);
  }
  state.catererItems = menuItems;

  document.getElementById("meals-loading").classList.add("hidden");
  document.getElementById("menu-items-list").classList.remove("hidden");
  renderMenuList();
}

// ============================================================
// Rendering
// ============================================================

function renderDietaryFilter() {
  document.getElementById("filter-chips").innerHTML = DIETARY_OPTIONS.map(opt => `
    <button class="filter-chip${state.dietaryFilter.includes(opt) ? " active" : ""}"
            onclick="app.toggleDietaryFilter(this, '${opt}')">${opt}</button>
  `).join("");
}

function renderMenuList() {
  const container = document.getElementById("menu-items-list");
  if (container.classList.contains("hidden")) return; // still loading

  const selectedItemId = ls.get(`padea_sel_item_${state.sessionId}`);
  const compatible = state.catererItems.filter(i =>
    isItemCompatible(i.fields, state.dietaryFilter)
  );

  if (!compatible.length) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🚫</div>
        <p>${state.catererItems.length
          ? "No items match your dietary requirements.<br><small>Try deselecting some filters.</small>"
          : "No menu items found for this session."
        }</p>
      </div>`;
    return;
  }

  container.innerHTML = compatible.map(item => {
    const f = item.fields;
    const name  = f["Menu Item Name"] || "?";
    const price = f["Price"] != null ? `$${Number(f["Price"]).toFixed(2)}` : "";
    const tags  = f["Dietary Tags"] || [];
    const isSelected = item.id === selectedItemId;

    const tagsHtml = tags.map(t => {
      const m = TAG_META[t];
      return m ? `<span class="menu-item-tag ${m.css}">${m.label}</span>` : "";
    }).join("");

    return `
      <div id="item-${item.id}" class="menu-item-card${isSelected ? " selected" : ""}"
           onclick="app.selectMeal('${item.id}')">
        <div class="menu-item-info">
          <div class="menu-item-name">${name}</div>
          <div class="menu-item-meta">
            ${price ? `<span class="menu-item-price">${price}</span>` : ""}
            ${tagsHtml}
          </div>
          ${isSelected ? '<div class="prev-note">✓ Your selection</div>' : ""}
        </div>
        <div class="menu-item-check">${isSelected ? "✓" : ""}</div>
      </div>`;
  }).join("");
}

// ============================================================
// Utility
// ============================================================

function showError(msg) {
  document.getElementById("error-text").textContent = msg;
  document.getElementById("error-banner").classList.remove("hidden");
}

function showMealsError(msg = "Could not load the menu.") {
  document.getElementById("meals-loading").classList.add("hidden");
  const list = document.getElementById("menu-items-list");
  list.innerHTML = `<div class="empty-state"><p>${msg}</p></div>`;
  list.classList.remove("hidden");
}

function showSavedMsg() {
  const el = document.getElementById("rating-saved-msg");
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3000);
}

// ============================================================
// Bootstrap
// ============================================================
document.addEventListener("DOMContentLoaded", () => app.init());
