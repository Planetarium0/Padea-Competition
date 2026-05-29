# Ordering Pipeline

Two scripts, run roughly Wed evening and Thu afternoon. Both are currently
manual (`./run orders`); the long-term plan is a cron.

## `register_orders.py` — snapshot preferences into Orders

Run target: **Wednesday 8 PM**, for the *following* Mon–Fri week.

### Inputs

- `Sessions` for next week — matched by `Day` field (sessions recur weekly).
- `Students` linked to each Session — minus absent / excluded / opted-out.
- `Caterers` — for min-qty constraints, pricing, delivery fee structure,
  and `Dietary Legend Tags`.
- `Menu Items` — by caterer.
- `Absences`, `Exclusions` — for filtering.
- `Caterer Feedback` — loaded but currently unused inside
  `register_orders.py`. The rating loop lives in `evaluate_caterers.py`.

### Algorithm

```
1. Flip any pending caterer switches: for every Session with
   Incoming Caterer set, Caterer ← Incoming Caterer, then clear Incoming
   Caterer. Mark the matching Approved Caterer Switch Proposal as Executed.
2. Compute next week's Mon–Fri dates from today.
3. Clear any Orders + Weekly Orders dated in that range (idempotent).
4. Pre-scan to count eligible students and explicit preferences per caterer.
   - Pick fallback mode for each caterer:
       explicit_count >= 10  →  POPULARITY mode
       explicit_count <  10  →  VARIETY    mode (with item-cap)
5. For each Session next week:
     For each enrolled student:
       skip if absent / excluded / opted out
       if Meal Preference is set AND on this caterer's menu:
         if it's *definitely* incompatible → refuse, fallback (warn)
         else                                 → honour (mark is_explicit=True)
       else:
         fallback assign by mode
6. Enforce min-qty per caterer (proportional dissolve, see below).
7. Group assignments by (session, item); write one Weekly Order per
   caterer and one Order row per (session, item) with the student list.
```

### Two fallback modes

- **POPULARITY** (10+ explicit preferences): scores compatible items by
  `0.8 × order_share + 0.2 × random` and picks the highest. This makes
  non-respondents drift toward what the explicit students chose.
- **VARIETY** (under 10 explicit preferences): picks the *least-ordered*
  compatible item. Spreads orders across the menu so the dataset has
  enough breadth to learn from in future weeks.

In variety mode, once the order has reached the caterer's "max variety"
distinct items (computed so the min-qty for N items is still
satisfiable), new students are constrained to existing items unless a
dietary exception forces a new one.

### Min-qty enforcement

`Min Qty N Items` says: "if you're ordering N distinct items from me,
each item must have at least this many portions."

After all assignments, the script:

1. Finds the constraint for the current number of distinct items.
2. Identifies violating items (count < min_qty).
3. For each violating item, checks whether **every** student on it has at
   least one dietarily compatible target among the non-violating items.
   If any student on the item is blocked, the **entire item** is left
   in place — partially dissolving it would swap students off their meals
   while still leaving the same violation behind.
4. Dissolves each item that passed the check: proportionally reassigns its
   students to non-violating compatible items (weighted by current
   popularity). Item counts are updated as each student is moved, so later
   students within the same dissolution benefit from up-to-date weights.
5. Repeats up to 30 iterations.

### Per-meal dietary checks during fallback

`is_item_compatible` (in `support/compatibility.py`, shared with the webapp):

- **Opted out**: never compatible.
- **Subset closure**: an item satisfies a constraint if any of its
  `Dietary Tags` is in the constraint's subset closure (e.g. Vegan
  satisfies Vegetarian, No Red Meat, No Beef, …).
- **Dietary legend hard block**: if the caterer's `Dietary Legend Tags`
  includes a transitive superset of the constraint, the item *must* carry
  a satisfying tag for that superset — otherwise it's a definite "no".
- **Negative keyword fallback**: item *name* must not contain any of the
  registered substrings for the constraint (e.g. "No Beef" excludes
  anything with "beef" or "bulgogi" in the name).

> Webapp and order generator now share `support/compatibility.py` (the
> Python side) and `data/dietary_keywords.json` (the keyword fallback).
> They also share the live `Dietary Restrictions` table for the closure
> calculation — both sides agree by construction.

### Explicit preference override

If a student's `Meal Preference` is set and the item is on the session's
caterer's menu, the script consults `is_item_compatible`:

- **Compatible** (including "maybe") → use it; the student's own judgement
  is trusted.
- **Definitely incompatible** (closure missed, legend missed, or keyword
  match) → refuse, log a warning naming the offending restrictions, and
  fall through to the dietary-safe fallback as if no preference was set.

Note: explicit preferences receive no special protection during min-qty
enforcement. If the preferred item falls below the per-item minimum, the
student is a dissolution candidate like any other. The only constraint on
the swap target is dietary compatibility.

### Idempotency

`clear_existing_orders` deletes all Orders **and** all Weekly Orders whose
Date / Week Start falls in next week's window. There is no `Status` field
on Weekly Orders — re-runs always wipe and rebuild.

### Outputs

- One `Weekly Orders` row per caterer per week.
- One `Orders` row per **(Session, Menu Item)** pair, with all students
  assigned that meal linked in the `Student` field. `Quantity =
  len(Student)`. `send_orders.py` sums `Quantity` to get per-item totals;
  the webapp's digital-ticket lookup uses `FIND` in `ARRAYJOIN({Student})`
  to find the row belonging to a given student.

## `send_orders.py` — format and queue caterer emails

Run target: **Thursday 3 PM**, the day after `register_orders.py`.

### Behaviour

1. Reads every `Weekly Orders` row with `Week Start >= today`.
2. For each: fetches the caterer, the linked Sessions (with school +
   on-site manager details, applying `Manager Substitutions` for the
   exact date), and aggregates the Orders rows.
3. Formats a Markdown email body, one section per delivery (sorted by
   Session ID alphabetically — which roughly orders Mon→Fri because
   Session IDs start with school names).
4. Writes a record to `Scheduled Emails` with `Status='Queued'` and
   `Send Date=None`.

> There is currently no idempotency guard: re-running queues another
> copy of every email for every Weekly Order in the date window.

### What gets *actually* sent

The Python script **does not call any SMTP/HTTP email API**. Send is
deferred to an **Airtable automation** that watches the `Scheduled
Emails` table for `Status='Queued'` records, sends the actual mail
via Airtable's email integration, and updates the row's status + Send
Date.

This split keeps email credentials out of the codebase.

### Email format

Markdown, using only the formatting Airtable's email send supports
(headings, bold, lists; no tables). Example structure:

```
Hi <First name>,

Here is the meal order for **<Caterer>** for the week of **<date>**:

## Monday — <School>
**Deliver by:** <Dinner Time minus 10 min>
**Building:** <Building>
**On-site manager:** <Name> (<Mobile>)
   ↑ labelled "(substitute)" when Manager Substitutions matched

- <Item A> ×4
- <Item B> ×3

**Subtotal: 7 meals**

## Wednesday — <School>
...

---
**Grand total: <total> meals**
**Delivery fee:** $<amount> (<num> deliveries × $<fee> | $<fee> per trip)

Thanks,
Padea
```

### Recipients

- **To**: `Caterer.Contact Email`.
- **CC**: starts empty, then adds `Caterer.Chef Email` if `Chef Wants CC`
  is true (unless it equals the contact email), then adds every on-site
  manager email that appears across the order's sessions, de-duplicated.
  This is wider than just "the chef" — it copies every manager whose
  session is in the order.

### Send Date

Set to `None` at queue time. The Airtable automation fills it in when
the message actually goes out, so the field doubles as a "did this send"
audit trail.

## Constraint verification

After running orders:

```bash
python scripts/tests/order_constraints.py
```

Checks two invariants:

1. **Min-qty respected per Weekly Order** — every item in a caterer's
   weekly order has ≥ the per-item minimum.
2. **Session totals match eligible-student counts** — the sum of
   `Quantity` across a session equals enrolled minus absent minus
   excluded minus opted-out.

Returns non-zero on any failure. It imports `OrderingData`, `OrderingIndex`,
`_find_min_qty`, `get_next_week_dates`, and `is_student_excluded` straight
from `register_orders.py`, so the two halves stay in lock-step.
