# 28 — `MIN_SESSIONS = 0` disables the caterer-switch sanity floor

**Severity:** Medium.
**File:** `scripts/actions/evaluate_caterers.py`, lines 56–60.

```python
SWITCH_THRESHOLD = 2.5
WATCH_THRESHOLD  = 3.0
# disable MIN_SESSIONS for now
MIN_SESSIONS     = 0    # minimum distinct sessions with feedback to fire SWITCH
MIN_RATERS       = 4
ROLLING_WINDOW   = 4
```

The intent of `MIN_SESSIONS` is to suppress a switch proposal until at
least N distinct session-dates' worth of feedback exists for a
(session, caterer) pair. Today it is set to `0`, so a single bad
session can already produce a switch proposal as long as it has
`MIN_RATERS = 4` raters. That makes the script very twitchy in the
opening weeks of a term.

`get_rolling_stats` still respects the value via
`if len(window) < MIN_SESSIONS`, so the floor would re-engage as soon
as the constant is set back to a non-zero value.

### Fix

Pick a real floor and put it back — e.g. `MIN_SESSIONS = 2` so a switch
proposal needs at least two bad sessions before firing. Reconsider in
combination with `ROLLING_WINDOW`; a 4-week window with a 2-session
minimum means "two of the last four sessions had bad ratings".
