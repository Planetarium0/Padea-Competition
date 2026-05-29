# 21 — Caterer feedback loaded by `register_orders.py` but never used

**Severity:** Low.
**File:** `scripts/actions/register_orders.py`.

```python
@dataclass(frozen=True)
class OrderingData:
    ...
    feedback: list[Record[CatererFeedbackFields]]

    @classmethod
    def load(cls, db: Database) -> "OrderingData":
        ...
        feedback=db.CatererFeedback.all(),
```

`OrderingData.load()` fetches the entire `Caterer Feedback` table on every
order run, but nothing inside `register_orders.py` reads
`data.feedback` after that — no scoring boost, no warning, no rollup. The
declining-caterer loop is now closed elsewhere (`evaluate_caterers.py`),
so this load is just dead I/O.

### Fix

- Drop `feedback` from `OrderingData` (and from the `.load()` body /
  `OrderingIndex.build` callers).
- Or, if you want fallback assignment to bias toward higher-rated
  caterers, wire `data.feedback` into the popularity scoring (today it's
  pure `order_share * 0.8 + random * 0.2`).
