# 11 — Airtable API key exposed in the webapp bundle

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

### Fix

For the eventual live deployment:

- Use a token scoped to the *minimum* set of tables / operations the
  webapp actually needs:
  - Read: Sessions, Students, Menu Items, Caterers, Dietary Restrictions,
    Caterer Feedback.
  - Write: Caterer Feedback (POST/PATCH), Students.Meal Preference (PATCH).
- Better: stop trusting the browser. Put a tiny proxy in front of
  Airtable that takes a session/student token and forwards only the
  allowed writes. Even a Cloudflare Worker / Lambda / serverless
  function with the Airtable PAT in env vars would work.
- In any case, rotate the current key before going live — it's been
  visible in plaintext to every developer who has touched the project.
