# Webapp — Student Meal Form

Single-page mobile-first app at `webapp/`. Plain HTML/CSS/JS, no framework,
no build step. Talks directly to the Airtable REST API.

## Goals

For every student, at every session:

1. **Collect a rating** (1–5 stars) of today's caterer, with an optional
   "what went wrong" comment if the rating is ≤ 3.
2. **Capture next week's meal preference** from the same caterer's menu,
   pre-filtered by the student's dietary requirements.

That's it. No login, no signup, no account.

## URL contract

```
.../webapp/index.html?session=<airtable_session_id>[&student=<student_id>][&key=<api_key>]
```

- **`session`** — required. The Airtable record ID of the session the form
  is being filled in for. Encoded in every QR code.
- **`student`** — optional. If the student kept a *personalised* QR, this
  skips the student-picker. Without it, the user picks their name from a
  list. The choice is remembered in `localStorage` so subsequent visits
  from the same device skip the picker too.
- **`key`** — optional. Overrides the hard-coded `CONFIG.API_KEY` (handy
  for development).

## Screens

### 1. Picker — "Who are you?"
Shown when no student is identified. Lazy-loads the session's student list
in the background (the session record already carries a `Students` backlink
of IDs). Search box filters by name on every keystroke. Tap to proceed.

The picker endpoint **filters out students whose `Last Submitted == today`**
— part of the one-way roster lockout (see below). Already-submitted
students simply don't appear in the dropdown.

### 2. Form
Single scrollable page with three sections:

- **Meal ticket banner** (if an `Orders` record exists for this student
  today). Shows the student's finalized assigned meal for today's session,
  plus an allergy tag in red if they have a registered allergy. Acts as
  the on-site manager's "line pass" — the student opens the webapp, picks
  their name, and shows the screen at the catering box pickup.
- **Rating card**: 1–5 stars. If ≤ 3, an optional textarea slides in.
- **Meal preference card**: a button labelled "Tap to choose a meal" (or
  showing the current selection). Tapping opens the meal picker overlay.

A footnote explains the purpose. A second footnote appears past the
**Wednesday 8 PM cutoff** explaining that any change now affects the
week *after* next, not next week (because the Wednesday cron has already
registered orders using the current preferences).

The Submit button is disabled until at least one of {rating, comment,
meal preference} has actually changed from its initial value.

### 3. Meal picker
A full-screen overlay listing the caterer's menu, **bucketed** by dietary
compatibility:

1. **Compatible** items first.
2. **Possibly compatible** items (no negative-keyword match in the name,
   but no positive tag confirming compatibility either) — shown with a
   "May contain X" subtitle. Tapping prompts a confirmation modal.
3. **Doesn't match** items last, greyed out — shown with a "Contains X"
   subtitle. Tapping prompts a stronger confirmation modal.

The student can override lifestyle restrictions; the system honours their
explicit pick even if it conflicts with a declared lifestyle preference.

**Allergy-blocked items** (an item that definitely violates a restriction
flagged `Is Allergy = True`) get separate treatment: red strike-through
styling, a ⊘ radio, and tapping shows a non-overridable lockout dialog
pointing to the on-site manager. Variants follow the same rule. See
`06-dietary-system.md` → *Medical allergies — hard block*.

### 4. Done
A confirmation screen. No "edit response" path — once submitted, the
device is locked out for the rest of the day (see one-way lockout below).
The copy directs the student to the on-site manager for changes.

### 5. Locked
Shown on subsequent visits from a device that has already submitted today
(or `Last Submitted == today` was already populated). Mirrors the Done
copy: *"Already submitted — see the on-site manager for changes."*

## Caching strategy

Two-tier: server-side in-memory cache (primary) + client-side in-memory
cache (secondary, within a single page visit).

### Server-side cache (`api.py` — `_ServerCache`)

All Airtable traffic goes through the Python server. The server caches
responses in a thread-safe in-memory dict. Stale entries are evicted by
TTL; write handlers additionally bust relevant entries immediately.

| Resource | Cache key | TTL | Busted on |
|---|---|---|---|
| Dietary Restrictions | `"diet"` | 24 h | — |
| Caterer menu | `"menu:{caterer_id}"` | 24 h | — |
| Session record | `"session:{session_id}"` | 1 h | — |
| Student record | `"student:{student_id}"` | ∞ | meal-preference PATCH, mark-submitted |
| Caterer Feedback table | `"feedback_table"` | 60 s | feedback POST |

The picker endpoint (`/api/session/<id>/students`) is **not** cached — it
filters by `Last Submitted == today`, which changes throughout the night.

The student's "digital ticket" (`/api/student/<id>/ticket`) is **not**
cached either — it reads `Orders` for today, which is small and rarely
hit per student.

The feedback table is cached as a whole (not per-student) so every student
on the same session night benefits from the same Airtable scan.

### Client-side cache (`app.js` — `_memCache`)

A plain JS object. No TTLs — the server owns freshness. Prevents redundant
API calls within a single page visit (e.g. navigating between views).
Busted in `persistChanges` after a submit so that the next `loadStudent`
or feedback lookup within the same visit gets current data.

`localStorage` is used **only** for `padea_known_student_{sessionId}` —
the student-picker shortcut that persists across visits.

Loads happen in parallel where possible:

- Dietary Restrictions fetch starts immediately on `app.init`.
- The session fetch resolves the caterer ID; the menu fetch piggy-backs
  on that promise and runs while the user is still picking a name.

By the time the user opens the meal picker, the menu is usually already
in memory.

## Persistence

On Submit:

- **Rating changed** → upserts a `Caterer Feedback` record for (Student,
  Session, Caterer). A background lookup runs while the form is open to
  determine whether to PATCH an existing record or POST a new one — the
  Submit handler awaits that promise before deciding, so a fast submit
  can't create duplicates.
- **Meal preference changed** → PATCHes the `Students.Meal Preference`
  field directly with a single Menu Item link.
- **Always** → POSTs `/api/student/<id>/mark-submitted`, setting
  `Students.Last Submitted = today`. This is the server-side half of
  the one-way lockout (see below).

After saving, the per-student cache key is busted so the next visit reads
the new preference.

## One-way roster lockout

Goal: prevent a prankster from impersonating a classmate by picking their
name from the dropdown. Two layers, independent:

1. **Device lock** (`localStorage`). On successful submit, the webapp sets
   `padea_submitted_<sessionId>_<YYYY-MM-DD>=1`. On subsequent loads on the
   same device that key triggers the *Locked* view immediately — no
   network round-trip.
2. **Roster filter** (server-side). `Students.Last Submitted` is updated
   to today on every successful submit. The picker endpoint refuses to
   return students whose `Last Submitted == today`, so they vanish from
   the dropdown for everyone scanning the QR after that point.

Together: a friend who submits *first* disappears from the dropdown; a
friend who hasn't submitted yet and finds their name missing is the
canary that alerts the on-site manager that someone tried to pose as
them. Manual overrides go through the on-site manager.

The picker endpoint is *not cached* server-side — caching would let
already-submitted students reappear in the dropdown until the TTL expired.

## Opted-out lock

If a student's dietary requirements include `Opted out of Catering`, the
form is read-only. A banner explains "No rating or preference needed —
enjoy your own dinner!" Star buttons, comment field, and meal trigger
are all disabled.

## Dietary compatibility

The webapp builds an in-memory subset-closure map from the Dietary
Restrictions table on every load (see `06-dietary-system.md`):

- An item is **OK** for a constraint if any of its tags is in the
  constraint's subset closure (e.g. Vegan-tagged item satisfies
  Vegetarian, Pescatarian, No Red Meat, No Beef, No Pork, No Lamb,
  Dairy Free).
- Failing that, the item's *name* is searched for known-bad keywords
  (`NEGATIVE_KEYWORDS`). Match → **No**. No match → **Maybe**.

The same logic powers the bucketing in the meal picker and the
confirmation-modal messages.

## Wednesday 8 PM cutoff

Hard-coded in `isPastOrderCutoff()` — the form will still accept
submissions after Wed 8 PM, but the cutoff footnote warns that the
change will only affect the *following* week's order. This is purely
informational; the order pipeline does its own filtering.

## Configuration

`webapp/config.env.js`:
```js
const CONFIG = {
  BASE_ID: "appTaP4DLPhZJICMH",
  API_KEY: "patw30iX...",     // committed in repo — see problems
};
```

The API key has scoped write access to a small set of tables. Replace it
before launching to production.

## Hosting

Currently local-only:

```bash
./run host                                        # serves webapp/ on 0.0.0.0:8000
./run forms qr --origin http://<lan-ip>:8000      # makes phone-scannable QR codes
```

The default `./run forms qr` (no `--origin`) emits `file://` QR codes that
only work on the host machine. For a phone, `--origin` is required.

## Brand

- Primary colour: `#A51C30` (red)
- Light scheme, Inter font, rounded corners, premium-feeling
- Mobile-first viewport with theme-color meta for iOS Safari
