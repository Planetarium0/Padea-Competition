# 20 — `register_orders.py` has unused imports and dead code

**Severity:** Low (cleanliness).
**File:** `scripts/actions/register_orders.py`.

Spotted while reading:

- `import sys` — never used.
- `from pathlib import Path` — never used.
- The script loads `Caterer Feedback` and computes an average rating per
  caterer (`lk["caterer_avg_rating"]`) but the result is never consulted
  during assignment or min-qty enforcement. (See also #21.)
- Comment-banner section "Idempotency" sits in the middle of the
  module body unattached to a function — minor structural noise.

Also worth noting (not strictly dead, but suspicious):

- `assign_fallback_meal` weights the score `0.8 × order_share + 0.2 ×
  random.uniform(0, 1)`. With `order_share` capped at 1.0 and `random`
  in [0,1], they're on roughly the same scale. The first-picked item
  for an otherwise-empty caterer will be near-random; once an item has
  any orders, the system locks onto it. This may be intentional but
  warrants a comment.

### Fix

Remove unused imports. Either delete the unused
`caterer_avg_rating` block or wire it into assignment scoring (see #21).
