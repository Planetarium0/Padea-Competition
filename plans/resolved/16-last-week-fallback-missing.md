# 16 — "Reuse last week's preference" fallback was never implemented

**Severity:** Low (feature gap rather than bug).
**File:** `scripts/actions/register_orders.py`.

`plans/old/emailing/implementation_plan_revised.md` and
`plans/old/webapp/webapp.md` both spec a tiered fallback for
non-respondents:

```
1. Explicit Meal Preference for this session → use it
2. Otherwise reuse the student's pick from a previous equivalent
   session (same school + day) → use it
3. Otherwise → AI assignment
```

Step 2 was never built. `register_orders.py` only checks the current
`Meal Preference` (which is a single value, overwritten on every change).
The Orders table holds historical picks, but nothing reads them as
a fallback.

This is the difference between a student who set a preference once and
expects it to "stick" vs. having to re-tap every week.

### Fix

In `register_orders.py`, for a student with no current `Meal Preference`,
query `Orders` for their most recent past pick at any session with the
same caterer, and use it if the menu item is still on the menu and
still dietary-compatible.
