// UI utilities shared across meals.js, manage.js, and switch-proposal.js.

export function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

let _toastTimer = null;

export function toast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.add("hidden"), 2500);
}

export function showError(msg) {
  document.getElementById("error-text").textContent = msg;
  document.getElementById("error-banner").classList.remove("hidden");
}

// ── Confirm modal ─────────────────────────────────────────────────────────────
// Requires HTML: #confirm-modal, #confirm-title, #confirm-body, #confirm-yes.
// Optional: #confirm-no (used by hideCancel).

let _confirmCallback = null;

export function openConfirm({ title, body, confirmLabel, onConfirm, hideCancel = false }) {
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").textContent = body;
  document.getElementById("confirm-yes").textContent = confirmLabel || "OK";
  const noBtn = document.getElementById("confirm-no");
  if (noBtn) noBtn.classList.toggle("hidden", hideCancel);
  _confirmCallback = onConfirm;
  document.getElementById("confirm-modal").classList.remove("hidden");
}

export function closeConfirm() {
  document.getElementById("confirm-modal").classList.add("hidden");
  const noBtn = document.getElementById("confirm-no");
  if (noBtn) noBtn.classList.remove("hidden");
  _confirmCallback = null;
}

export function confirmModalYes() {
  const cb = _confirmCallback;
  closeConfirm();
  if (cb) cb();
}

export function confirmModalNo() {
  closeConfirm();
}
