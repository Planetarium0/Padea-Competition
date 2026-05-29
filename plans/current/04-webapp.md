# Webapp — Student Meal Form

Static frontend at `webapp/`. Plain HTML/CSS/JS, no framework, no build step.
All Airtable traffic is proxied through the Python server (`host_webapp.py`
+ `actions/api.py`) so the browser never sees the Airtable API key.

## Pages

| File | Role |
|---|---|
| `meals.html` + `app.js` | Student-facing form: rating + next-week meal preference (the QR-code target). |
| `manage.html` + `manage.js` | On-site-manager page: review students, update dietary requirements, override an individual order. |
| `switch-proposal.html` + `switch-proposal.js` | Coordinator-facing approve/reject screen for a Caterer Switch Proposal. |

There is no `index.html` — links and QR codes target `meals.html` directly.

## Goals (`meals.html`)

For every student, at every session:

1. **Collect a rating** (1–5 stars) of today's caterer, with an optional
   "what went wrong" comment if the rating is ≤ 3.
2. **Capture next week's meal preference** from the same caterer's menu,
   pre-filtered by the student's dietary requirements. If a Caterer Switch
   Proposal has been approved (`Sessions.Incoming Caterer` is set), the
   picker shows the *new* caterer's menu so students vote on what they'll
   actually eat next week.
3. **Show today's digital ticket** if an `Orders` row already exists for
   this student today.

That's it. No login, no signup, no account.

## URL contract

```
.../meals.html?session=<airtable_session_id>[&student=<student_id>][&first=1]
```

- **`session`** — required. The Airtable record ID of the session the form
  is being filled in for. Encoded in every QR code.
- **`student`** — optional. If the student kept a *personalised* QR (or
  follows a link from `send_meals_links.py`), this skips the student-picker.
  Without it, the user picks their name from a list. The choice is
  remembered in `localStorage` so subsequent visits from the same device
  skip the picker too.
- **`first=1`** — optional. Hides the rating card (start-of-term mode, when
  there isn't a previous session to rate). Set by `send_meals_links.py
  --first` and `generate_qr.py --first`.

The legacy `?key=` API-key override was removed when the Airtable token
left the browser.

## Screens (`meals.html`)

### 1. Picker — "Who are you?"
Shown when no student is identified. The picker endpoint
(`/api/session/<id>/students`) returns only students enrolled in the
session whose `Last Submitted ≠ today`. Search box filters by name on
every keystroke. Tap to proceed.

The endpoint **filters out students whose `Last Submitted == today`**
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
  Hidden when `?first=1` is set.
- **Meal preference card**: a button labelled "Tap to choose a meal" (or
  showing the current selection). A transition banner appears if next
  week's caterer differs from today's (i.e. `Incoming Caterer` is set).
  Tapping opens the meal picker overlay.

A footnote explains the purpose. A second footnote appears past the
**Wednesday 8 PM cutoff** explaining that any change now affects the
week *after* next, not next week (because the Wednesday cron has already
registered orders using the current preferences).

The Submit button is disabled until at least one of {rating, comment,
meal preference} has actually changed from its initial value.

### 3. Meal picker
A full-screen overlay listing the caterer's menu (the *incoming* caterer
if a switch is pending), **bucketed** by dietary compatibility:

1. **Compatible** items first.
2. **Possibly compatible** items (no negative-keyword match in the name,
   but no positive tag confirming compatibility either) — shown with a
   "May contain X" subtitle. Tapping prompts a confirmation modal.
3. **Doesn't match** items last, greyed out — shown with a "Contains X"
   subtitle. Tapping prompts a stronger confirmation modal.

The student can override lifestyle restrictions; the system honours their
explicit pick even if it conflicts with a declared lifestyle preference.

**Allergy-blocked items** (an item that definitely violates an
allergy-grade restriction — Nut Free / Gluten Free / Dairy Free) get
separate treatment: red strike-through styling, a ⊘ radio, and tapping
shows a non-overridable lockout dialog pointing to the on-site manager.
Variants follow the same rule. See
`06-dietary-system.md → Medical allergies — hard block`.

If an item has `Variant Of` siblings (e.g. a vegetarian version), tapping
the base item opens a small "Choose your option" modal listing the
compatible variants — the picked variant is what gets saved as the
preference.

### 4. Done
A confirmation screen. No "edit response" path — once submitted, the
device is locked out for the rest of the day (see one-way lockout below).
The copy directs the student to the on-site manager for changes.

### 5. Locked
Shown on subsequent visits from a device that has already submitted today
(or `Last Submitted == today` was already populated). Mirrors the Done
copy: *"Already submitted — see the on-site manager for changes."*

## API endpoints

All endpoints are registered in `scripts/actions/api.py` via `@route(...)`
and dispatched by `host_webapp.py`. URLs are relative to the server origin.

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/session/<id>` | Session record (Caterer + Incoming Caterer). Cached 1h. |
| GET | `/api/session/<id>/students` | Picker list, filtered by `Last Submitted ≠ today`. **Not cached.** |
| GET | `/api/session/<id>/students-all` | Same list without the lockout filter — used by `manage.html`. |
| GET | `/api/student/<id>` | Student fields the webapp needs (name, dietary IDs, preference, last submitted). Cached until busted. |
| GET | `/api/student/<id>/ticket?session_id=<sid>` | Today's digital-ticket meal. Not cached. |
| PATCH | `/api/student/<id>/meal-preference` | Upsert `Students.Meal Preference`. |
| PATCH | `/api/student/<id>/dietary-requirements` | Replace `Students.Dietary Requirements`. Manager-side. |
| PATCH | `/api/student/<id>/order-override` | Move a student to a different meal in today's order (manager-side). Updates an existing row's student list or creates an `OVR-…` row. |
| POST | `/api/student/<id>/mark-submitted` | Set `Students.Last Submitted = today` (server-side half of the lockout). |
| GET | `/api/caterer/<id>` | Caterer's `Dietary Legend Tags`. Cached 24h. |
| GET | `/api/caterer/<id>/menu` | Menu items including `Is Variant` / `Variant Of`. Cached 24h. |
| GET | `/api/dietary-restrictions` | Restrictions + Supersets. Cached 24h. |
| GET | `/api/feedback?student_id=&caterer_id=` | Existing feedback for upsert. Backed by a 60s table-wide cache. |
| POST | `/api/feedback` | Upsert a `Caterer Feedback` row. Busts the feedback-table cache. |
| GET | `/api/manager/<id>/sessions` | All sessions a manager runs. Used by `manage.html`. |
| GET | `/api/proposal/<id>` | Caterer Switch Proposal details. Used by `switch-proposal.html`. |
| POST | `/api/proposal/<id>/approve` | Run `execute_caterer_switch.execute`. |
| POST | `/api/proposal/<id>/reject` | Mark proposal `Rejected` + notes. |

## Caching strategy

Two-tier: server-side in-memory cache (primary) + client-side in-memory
cache (secondary, within a single page visit).

### Server-side cache (`api.py` — `_ServerCache`)

Thread-safe in-memory dict in the Python process. TTL eviction; write
handlers bust relevant entries immediately.

| Resource | Cache key | TTL | Busted on |
|---|---|---|---|
| Dietary Restrictions | `"diet"` | 24 h | — |
| Caterer record (legend tags) | `"caterer:{caterer_id}"` | 24 h | — |
| Caterer menu | `"menu:{caterer_id}"` | 24 h | — |
| Session record | `"session:{session_id}"` | 1 h | — |
| Student record | `"student:{student_id}"` | ∞ | meal-preference PATCH, dietary PATCH, mark-submitted |
| Caterer Feedback (whole table) | `"feedback_table"` | 60 s | feedback POST |

The picker endpoint (`/api/session/<id>/students`) is **not** cached — it
filters by `Last Submitted == today`, which changes throughout the night.
The digital ticket (`/api/student/<id>/ticket`) is also not cached — it
reads `Orders` for today, which is small and rarely hit per student.

### Client-side cache (`app.js` — `_memCache`)

A plain JS object. No TTLs — the server owns freshness. Prevents redundant
API calls within a single page visit. Busted in `persistChanges` after a
submit so that the next `loadStudent` or feedback lookup within the same
visit gets current data.

`localStorage` is used **only** for `padea_known_student_{sessionId}` —
the student-picker shortcut that persists across visits — and
`padea_submitted_<sessionId>_<YYYY-MM-DD>` for the device-side lock.

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
  can't create duplicates. The record also stores `Session Date = today`
  so `evaluate_caterers.py` has an explicit date to window over.
- **Meal preference changed** → PATCHes the `Students.Meal Preference`
  field directly with a single Menu Item link (the chosen variant if one
  was selected, otherwise the base item).
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
them. Manual overrides go through the on-site manager (via `manage.html`).

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
- If a caterer's `Dietary Legend Tags` includes a transitive superset of
  the constraint, the absence of a satisfying tag is treated as
  definitive (legend-tracked restrictions never produce "maybe").
- Failing both checks, the item's *name* is searched for known-bad
  keywords (`NEGATIVE_KEYWORDS`, fetched from `/data/dietary_keywords.json`):
  match → **No**, no match → **Maybe**.

The same logic powers the bucketing in the meal picker and the
confirmation-modal messages. It is implemented in JS but mirrors
`support/compatibility.py` so the order generator and the webapp produce
identical verdicts.

## Wednesday 8 PM cutoff

Hard-coded in `isPastOrderCutoff()` — the form will still accept
submissions after Wed 8 PM, but the cutoff footnote warns that the
change will only affect the *following* week's order. This is purely
informational; the order pipeline does its own filtering. The check uses
*local device time*, not Australia/Brisbane — relevant for travellers.

## `manage.html` — on-site-manager page

URL: `/manage.html?manager=<manager_id>` (linked from QR-code emails) or
`/manage.html?student=<student_id>` (linked from meal-preference emails).

- Manager mode: pick a session, then a student, then update dietary
  requirements or override today's meal assignment.
- Student mode: jumps straight to the dietary editor for that student.

Talks to the same `/api/...` endpoints as `meals.html`, plus the
manager-specific `/api/manager/<id>/sessions`,
`/api/session/<id>/students-all`, and `/api/student/<id>/order-override`.

## `switch-proposal.html` — coordinator approve/reject page

URL: `/switch-proposal.html?id=<proposal_record_id>` (linked from the
switch alert emails generated by `evaluate_caterers.py`).

GET `/api/proposal/<id>` populates the page; approve / reject buttons
POST to `/api/proposal/<id>/approve` (which calls
`execute_caterer_switch.execute(..., approve=True)`) or `/.../reject`.

## Hosting

Currently local-only:

```bash
./run host                                            # serves on 0.0.0.0:8000
./run forms qr --origin http://<lan-ip>:8000          # makes phone-scannable QR codes
```

The default `./run forms qr` (no `--origin`) emits `file://` QR codes that
only work on the host machine. For a phone, `--origin` is required.

## Brand

- Primary colour: `#A51C30` (red)
- Light scheme, Inter font, rounded corners, premium-feeling
- Mobile-first viewport with theme-color meta for iOS Safari
