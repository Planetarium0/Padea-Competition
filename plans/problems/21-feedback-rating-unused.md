# 21 — Caterer feedback ratings are computed but never used

**Severity:** Low.
**File:** `scripts/actions/register_orders.py`.

```python
# Average feedback rating per caterer
caterer_ratings = defaultdict(list)
for fb in data["feedback"]:
    rating     = fb["fields"].get("Rating")
    caterer_id = (fb["fields"].get("Caterer") or [None])[0]
    if rating is not None and caterer_id:
        caterer_ratings[caterer_id].append(rating)
lk["caterer_avg_rating"] = {
    cid: sum(rs) / len(rs) for cid, rs in caterer_ratings.items()
}
```

The script reads `Caterer Feedback`, computes the average rating per
caterer, stores it in `lk["caterer_avg_rating"]`, and **then never
references it again**. There is no caterer-rating-based logic in
assignment or min-qty enforcement.

This means the feedback loop the project promises (declining caterers
get flagged) is data-collected but not yet data-acted-on. Two
adjacent problems:

- The order generator could use the rating in the fallback scoring
  (boost compatible items from highly-rated caterers; today they're
  all equal).
- A separate quality dashboard / alert was in the original plan
  (`plans/old/emailing/implementation_plan.md` Phase 4) but never built.

### Fix

Either delete the dead lookup, or:

- Decide whether the score should drive a swap recommendation, an alert
  email, or an Airtable formula field that the coordinator monitors.
- For per-item ratings (vs per-caterer), `Caterer Feedback` only links
  to the caterer, not the menu item. Item-level popularity has to come
  from past `Orders` quantities, not from feedback rows.
