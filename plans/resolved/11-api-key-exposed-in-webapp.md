# 11 — Airtable API key exposed in the webapp bundle ✓ RESOLVED

**Severity:** High (read-and-write to the entire base).
**File:** `webapp/config.env.js`.

```js
const CONFIG = {
  BASE_ID: "appTaP4DLPhZJICMH",
  API_KEY: "patw30iXXZrJ71F8B.5a3838fed9...",
};
```

Notes:

- `*.env.*` is in `.gitignore`, so this file isn't in git history.
  (Confirmed via `git ls-files`.) That mitigates one risk vector.
- However the file is **served to every browser that hits the webapp**.
  Anyone who scans a QR code (or guesses the URL) can read the token
  from `view-source:` or DevTools.
- The token is a personal access token. The scopes are whatever the
  owner attached — if it includes write to every table in the base,
  any visitor can rewrite the base.

This is fine for purely local testing (`./run host` on a closed LAN
with trusted users), but cannot be the long-term hosting story.

### Fix applied

The webapp no longer calls Airtable directly. All Airtable traffic is
proxied through the Python server:

- `webapp/app.js` — `AT_BASE` changed to `/api/airtable`; `Authorization`
  header removed from `atFetch`; `apiKey()` helper removed.
- `webapp/config.env.js` — `API_KEY` and `BASE_ID` stripped; `CONFIG`
  is now an empty object (file kept so `meals.html`'s script tag doesn't 404).
- `host_webapp.py` — new `_proxy_airtable()` method forwards GET/POST/PATCH
  requests to `https://api.airtable.com/v0/{BASE_ID}/…` using
  `AIRTABLE_API_KEY` from `.env` (server-side only). Route: `/api/airtable/*`.

**Latency impact:** negligible. The extra hop (browser → Python server) is
~0–1 ms on LAN. The dominant cost (Python → Airtable over the internet,
~100–300 ms per call) is unchanged.

**Remaining for production:** rotate the current key (it was in plaintext
while the problem existed). For a cloud deployment replace `host_webapp.py`
with a proper server (e.g. Cloudflare Worker, Lambda) that keeps the key
in env vars — the webapp side requires no further changes.
