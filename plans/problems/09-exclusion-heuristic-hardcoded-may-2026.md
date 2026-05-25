# 09 — Exclusion heuristic parser hard-codes May 2026

**Severity:** Medium.
**File:** `scripts/migrations/exclusions.py`, `parse_exclusions_heuristic`.

```python
day_match = re.search(r"(\d+)(?:st|nd|rd|th)?\s+of\s+May", blk, re.IGNORECASE)
if day_match:
    day = int(day_match.group(1))
    date_iso = f"2026-05-{day:02d}"
```

If the source PDF mentions a date in any other month, or a different
year, the heuristic fallback either misses the date entirely or
constructs the wrong one. The LLM path is robust to this; the fallback
is not.

### Fix

Parse month and year from the text, or accept an explicit current-term
context (e.g. `--term-month=May --term-year=2026` as a CLI flag) instead
of hard-coding.

Related: the heuristic only recognises year levels via the pattern
`years? [\d\s,and]+`, which silently fails for "year 12" and similar
singular forms.
