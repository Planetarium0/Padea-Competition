# Webapp Changes for Caterer Switching

When a caterer switch is approved and executed (`execute_caterer_switch.py`
runs), the session enters a **transition period**: `Sessions.Caterer` still
points to the outgoing caterer (for attribution of today's rating), but
`Sessions.Incoming Caterer` now points to the incoming caterer (for preference
selection). `register_orders.py` commits the full flip on Wednesday 8 PM.

The webapp needs to handle this split state.

---

## New session field to load

`Sessions.Incoming Caterer` — a `multipleRecordLinks` field added in the
schema update. The webapp should load it alongside the existing `Sessions`
fetch. It will be `null` / empty array during normal operation, and populated
only during the transition period.

---

## Meal preference card

**Before transition** (`Incoming Caterer` is empty):
Behaviour unchanged — menu shown is from `session.fields.Caterer[0]`.

**During transition** (`Incoming Caterer` is set):
- Show the **incoming caterer's** menu items instead.
- Reset any pre-selected meal to "Tap to choose a meal" (the student's
  `Meal Preference` was cleared by `execute_caterer_switch.py`).
- Show a brief banner: "**Next week's caterer has changed.** Please choose
  from the new menu below."

Implementation: wherever the app resolves the caterer ID for menu loading,
use:
```js
const catererId = (session.fields["Incoming Caterer"] || [])[0]
               ?? (session.fields["Caterer"]          || [])[0];
```

---

## Rating card

The rating is **always** for the caterer who cooked today's meal — that is,
`session.fields.Caterer[0]`, regardless of `Incoming Caterer`.

No change to the rating card logic or the record written to `Caterer Feedback`.
The `Caterer` field on the feedback record must be set from `session.fields.Caterer`,
not from `Incoming Caterer`.

---

## Session Date on feedback submission

`Caterer Feedback` now has a `Session Date` (date) field. The webapp must set
it to today's ISO date when submitting a rating. `evaluate_caterers.py` uses
it to order feedback by actual occurrence date for the rolling-window
calculation. Without it, the script falls back to the session's representative
migration date, which is less accurate.

Add to the PATCH/POST body when writing a `Caterer Feedback` record:
```js
"Session Date": new Date().toISOString().slice(0, 10)
```

---

## Caching

`Sessions` are cached for 1 hour. The `Incoming Caterer` field is part of the
session record, so it will be picked up naturally on the next cache miss.
No new cache key is needed.

If a switch executes mid-session-day (unlikely but possible), a manual cache
bust is the coordinator's responsibility (e.g., clear site data in browser
settings, or wait for the 1-hour TTL to expire).

---

## Summary of changes

| Location | Change |
|---|---|
| Session fetch | Load `Incoming Caterer` field |
| Meal preference card | Use `Incoming Caterer` caterer ID if set; show banner |
| Rating card | No change — always use `Caterer` |
| Feedback submission | Add `"Session Date": today` to written fields |
| Caterer feedback PATCH/POST | `Caterer` field stays as `session.Caterer`, not `Incoming Caterer` |
