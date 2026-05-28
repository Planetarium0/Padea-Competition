# Ordering Pipeline

Two scripts, run roughly Wed evening and Thu afternoon. Both are currently
manual (`./run orders`); the long-term plan is a cron.

## `register_orders.py` — snapshot preferences into Orders

Run target: **Wednesday 8 PM**, for the *following* Mon–Fri week.

### Inputs

- `Sessions` for next week — matched by `Day` field (sessions recur weekly).
- `Students` linked to each Session — minus absent / excluded / opted-out.
- `Caterers` — for min-qty constraints, pricing, delivery fee structure.
- `Menu Items` — by caterer.
- `Absences`, `Exclusions` — for filtering.
- `Caterer Feedback` — for the average-rating side effect (loaded but not
  currently used by the assignment logic).

### Algorithm

```
1. Compute next week's Mon–Fri dates from today.
2. Clear any Orders + Weekly Orders dated in that range (idempotent).
3. Pre-scan to count eligible students and explicit preferences per caterer.
   - Pick fallback mode for each caterer:
       explicit_count >= 10  →  POPULARITY mode
       explicit_count <  10  →  VARIETY    mode (with item-cap)
4. For each Session next week:
     For each enrolled student:
       skip if absent / excluded / opted out
       if Meal Preference is set AND on this caterer's menu:
         use it (mark is_explicit=True) — honour even if it conflicts with diet
       else:
         fallback assign by mode
5. Enforce min-qty per caterer (proportional swap, see below).
6. Write Weekly Orders (one per caterer) and aggregated Orders rows.
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

`is_item_compatible` (in `register_orders.py`) checks:

- **Opted out**: never compatible.
- **Positive tag** (Gluten Free, Dairy Free, Nut Free, Vegetarian, Halal):
  item must have the exact tag.
- **Negative keyword** (No Beef, No Pork, …): item *name* must not contain
  any of a bunch of substrings (e.g. "No Beef" excludes anything with
  "beef" or "bulgogi" in the name).

> Note: this compatibility check uses a static `POSITIVE_DIETARY_TAGS`
> dict and does **not** consult the dietary hierarchy. The webapp does;
> these two compatibility implementations are out of sync. See problems.

### Explicit preference override

If a student's `Meal Preference` is set and the item is on the session's
caterer's menu, the script uses it — even if the item conflicts with a
**lifestyle** dietary restriction (Vegetarian, Halal, …). A warning is
logged; the student's choice is treated as an informed override.

**Allergies are not overridable.** If the explicit preference violates a
restriction flagged `Is Allergy = True` (Nut Free, Gluten Free, Dairy
Free by default), the script:

1. Refuses to honour the preference.
2. Logs a severe warning naming the offending allergy.
3. Falls through to the dietary-safe fallback as if no preference was set.

See `06-dietary-system.md → Medical allergies — hard block`.

Note: explicit preferences receive no special protection during min-qty
enforcement. If the preferred item falls below the per-item minimum, the
student is a dissolution candidate like any other. The only constraint on
the swap target is dietary compatibility.

### Idempotency

`clear_existing_orders` deletes all Orders and Weekly Orders whose Date /
Week Start falls in next week's window. Re-runs are safe.

### Outputs

- One `Weekly Orders` row per caterer per week.
- One `Orders` row per **student** per session — the per-student
  granularity powers the webapp's digital-ticket lookup. `Quantity` is
  always `1`; callers that want per-item totals (e.g. `send_orders.py`,
  `order_constraints.py`) sum `Quantity` across rows.

## `send_orders.py` — format and queue caterer emails

Run target: **Thursday 3 PM**, the day after `register_orders.py`.

### Behaviour

1. Reads every `Weekly Orders` row with `Week Start >= today`.
2. For each: fetches the caterer, the linked Sessions (with school +
   on-site manager details), and aggregates the Orders rows.
3. Formats a Markdown email body, one section per delivery (sorted by
   Session ID alphabetically — which roughly orders Mon→Fri because
   Session IDs start with school names).
4. Writes a record to `Scheduled Emails` with `Status='Queued'`.

### What gets *actually* sent

The Python script **does not call any SMTP/HTTP email API**. Send is
deferred to an **Airtable automation** that watches the `Scheduled
Emails` table for `Status='Queued'` records, sends the actual mail
via Airtable's email integration, and updates the row's status.

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

### CC behaviour

If `Caterer.Chef Wants CC` is true, the chef's email is added to the
record's `CC` field. Otherwise no CC.

### Send Date

Set to `Week Start` (Monday of the target week) — flagged as a TODO in
the source. Should probably be earlier (e.g. Thursday of the prior week).

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

Returns non-zero on any failure.
