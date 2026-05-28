# Problem: `MIN_SESSIONS = 0` disables the caterer-switch sanity floor

## Context
`scripts/actions/evaluate_caterers.py` exposes a `MIN_SESSIONS` constant —
the minimum number of distinct sessions with feedback required before
`get_rolling_stats` will return a result, which is the gate for proposing
a caterer switch.

The current value is `0`, with an inline comment:

```python
# disable MIN_SESSIONS for now
MIN_SESSIONS     = 0    # minimum distinct sessions with feedback to fire SWITCH
```

`MIN_RATERS = 4` still applies later in the pipeline, so a switch proposal
still requires at least 4 raters in the rolling window — but those raters
can all be from a **single session**.

## Problem Description
A single bad session can now mathematically trigger a switch proposal:

- One session with 4 unhappy students rating 1/5 (the minimum size for a
  small-group tutoring cohort) yields `avg=1.0, num_raters=4` — well below
  the `SWITCH_THRESHOLD` of 2.5.
- The pipeline finds replacement candidates, fires off a proposal email
  to the on-site manager, and writes a `Caterer Switch Proposals` record.

This is fragile because:

- One off night (driver was late, food arrived cold) shouldn't trigger a
  switch on its own — the rolling-window design was specifically intended
  to require multiple data points before acting.
- The `WATCH_THRESHOLD` warning email also fires on a single session,
  which means caterers may get warned-then-switched within two weeks of a
  single bad delivery.

The corresponding tests in `test_evaluate_caterers.py` were originally
written against `MIN_SESSIONS = 3` (still documented in the test bodies)
and have been updated to assert the current behaviour. The historical
intent was clearly "at least 3 distinct sessions" before acting.

## Proposed Solution
Pick the right threshold and restore it. Two reasonable options:

1. **Restore `MIN_SESSIONS = 3`** (the original design point). Combined
   with `MIN_RATERS = 4`, this requires ratings from at least three
   distinct sessions and four distinct students before a switch can be
   proposed.

2. **Set `MIN_SESSIONS = 2`** as a lower middle-ground if three is too
   conservative for the current data volume.

Either way: remove the `# disable MIN_SESSIONS for now` comment, and
update the two `TestGetRollingStats` tests (currently asserting `num_sessions=2`)
to assert the chosen threshold's behaviour.

Until then, manual review of every switch proposal is mandatory — the
coordinator should treat *every* proposal as "potentially based on a
single bad night" and check the underlying feedback before approving.
