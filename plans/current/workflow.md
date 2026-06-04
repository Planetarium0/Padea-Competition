# Workflow

The business problem and the weekly rhythm the code is shaped around.
Read this before you touch any of the action scripts in
`scripts/actions/`.

---

## Why this project exists

Padea runs after-school tutoring at partner high schools. Each session
includes a catered dinner that an external caterer cooks and delivers in
individually-boxed meals. Today's bottleneck:

> Every Thursday the program coordinator guesses meal picks and
> quantities from each caterer's menu and emails the order. Students
> often dislike the picks, food quality silently drifts, and the
> workflow doesn't scale with new schools.

What "fixed" looks like:

1. **Students pick their own meals** via QR-code form. Non-respondents
   get smart fallbacks.
2. **Quality is measured** — every session-day the form collects a 1–5
   rating of today's caterer.
3. **Switching caterers is closed-loop** — a declining caterer is
   automatically flagged, a switch proposal is generated, the
   coordinator approves it in the webapp, and the next order is built
   from the new caterer's menu.

The system optimizes for **freeing the coordinator from per-week
decisions**, not for cost. If a rule would force the coordinator into
the loop more often, it's the wrong rule.

## Actors

| Actor | What they do | How they interact |
|---|---|---|
| **Student** | Rates today's caterer; picks next week's meal. | `meals.html` via QR code at session. |
| **On-site manager** | Receives delivery, hands out meals, handles overrides for absent/late students. | `manage.html` (linked from QR emails). One per school per weekday, usually stable across a term. |
| **Caterer (contact)** | Receives the weekly order email, cooks, delivers. | Inbound email; phone call to on-site manager on delivery day. |
| **Caterer (chef)** | May be CC'd on order emails if `caterers.chef_wants_cc` is true. | Same email thread. |
| **Program coordinator** | Approves/rejects caterer switch proposals, edits enrolment in Supabase Studio, watches for failures. | `switch-proposal.html` page; Supabase Studio for data edits. |

## The weekly rhythm

```
Tue (session day)   →  Student opens QR  →  meals.html
                       Rates today's caterer (1–5 + optional comment ≤3)
                       Picks next week's meal preference
                       Writes:
                         caterer_feedback (rating)
                         students.meal_preference_id
                         students.last_submitted = today

Wed 8 PM            →  ./run orders generate          (register_orders.py)
                       1. Flip pending caterer switches
                          (sessions.incoming_caterer_id → caterer_id)
                       2. Clear next week's orders + weekly_orders
                       3. Per session, per student:
                            skip if absent/excluded/opted-out
                            honour meal_preference if compatible
                            else fallback (popularity ≥10, else variety)
                       4. Enforce min-qty per caterer
                          (proportional dissolve of violating items)
                       5. Write weekly_orders + orders
                          (one orders row per session+menu_item;
                           student list aggregated by orders_view)

Thu 3 PM            →  ./run orders send              (send_orders.py)
                       Format markdown body per caterer
                       Resolve effective on-site manager via
                         manager_substitutions for each session-date
                       Dispatch via Resend
                       Audit-log in scheduled_emails

Caterer day         →  Caterer delivers 5–10 min before dinner_time
                       On-site manager checks in students at meal pickup
                       (uses students.meal_preference + orders ticket
                       lookup to find the right boxed meal)

Continuously        →  ./run caterer evaluate         (evaluate_caterers.py)
                       Rolling-window check on caterer_feedback ratings
                       If a school's caterer has dropped:
                         pick a candidate caterer that covers all
                         students' diets and serves that region
                         create a caterer_switch_proposals row (Pending)
                         email the coordinator with a deep link to
                         /switch-proposal.html?id=<rec_id>

Coordinator decides →  Approve  →  /api equivalent / supabase call →
                                   execute_caterer_switch.py runs:
                                     sessions.incoming_caterer_id ← new
                                     students.meal_preference_id ← null
                                     proposal.status = Approved
                                   The next Wed 8 PM flip promotes
                                     status → Executed.
                       Reject   →  proposal.status = Rejected
```

## Dietary clarification loop (coordinator-initiated, term-start)

```
Coordinator runs     →  ./run dietary clarify <school>
  (after parent forms     Per caterer serving the school:
  are in and student        walk (menu items × student restriction union)
  restrictions are          through the 3-step ladder
  entered)                  Collect every MAYBE triple
                            Build dietary_clarification_requests row
                            Send one email per caterer listing open items
                            Print: caterer name, open-question count,
                                   7-day clock expiry
                          Also runs escalation sweep for prior-term requests

7 days later        →  ./run dietary escalate  (or auto-triggered at end of clarify)
  (or any time after)     Walk Open requests where sent_at + 7d < now()
                          Mark status='Escalated'
                          Write cache/notifications/clarify_<id>.md
                          Email COORDINATOR_EMAIL (fallback DEV_NOTIFICATION_EMAIL)

Coordinator follows →  Direct conversation with caterer
  up manually            Coordinator transcribes caterer's answers:
                           Compatible → INSERT into menu_item_dietary_tags
                           Contains   → record provisionally
                         When full restriction column answered Compatible/Contains
                           INSERT into caterer_legend_tags (earned-legend rule)
                         Update request status to Resolved in Supabase Studio
```

Note: MAYBE verdicts remain assignable in `register_orders.py` throughout.
The clarification loop is a hygiene pass that reduces MAYBEs over time; it
does not gate orders.

## Decision points (where business rules concentrate)

The places an agent is most likely to need to think carefully, with the
files where the rules currently live. Use graphify (`graphify explain
"<name>"`) for the implementation; this list is the *map*.

| Decision | Lives in |
|---|---|
| Is this student eligible to eat next week? | `register_orders.py → is_student_excluded` (absences, exclusions, opted-out) |
| Is item X compatible with student Y? | `scripts/support/compatibility.py → is_item_compatible` and `webapp/app.js → checkCompatibility` (mirror) |
| Should we honour an explicit `meal_preference`? | `register_orders.py` — yes unless `is_item_compatible` returns *definite no* |
| Which fallback mode (popularity vs variety)? | `register_orders.py` — ≥10 explicit preferences per caterer ⇒ popularity, else variety |
| How to dissolve a min-qty violation? | `register_orders.py → enforce_min_qty` — proportional reassignment, gated on dietary safety of every student on the violating item |
| Which on-site manager is on duty on date D? | `support.database.resolve_manager_id` — `manager_substitutions` for the date wins, else `sessions.on_site_manager_id` |
| Is a caterer rolling badly enough to swap? | `evaluate_caterers.py` — window, unique-rater count, candidate scoring |
| Can candidate caterer cover this school's students? | `evaluate_caterers.py → caterer_covers_all_students` — dietary coverage hard filter |
| Is a (item, restriction) verdict OK / NO / MAYBE? | `scripts/support/compatibility.py → item_verdict` — exposes three-state result used by clarify sweep |
| Has a clarification request gone unanswered for 7 days? | `escalate_dietary.py → _is_overdue` + `notify_coordinator` in `scripts/support/email.py` |

## Critical invariants

These are properties the workflow assumes; breaking one breaks the
business outcome silently. Add a test if you suspect a change might.

- **One `orders` row per (session, menu_item) per week** with the
  student list aggregated by `orders_view` (junction table:
  `order_students`). `quantity = len(student_ids)`.
- **`scheduled_emails` is an audit log.** It records what was sent, not
  what should be sent. Don't poll it expecting deferred dispatch.
- **`last_submitted == today` is a one-way roster lock**: a student
  who has submitted today vanishes from the picker on every device. The
  webapp also keeps a `localStorage` device-side lock. Both must hold
  for the prank-resistance property to work.
- **`incoming_caterer_id` is a deferred switch.** It is set by
  `execute_caterer_switch.py` on approval and consumed (`caterer_id ←
  incoming_caterer_id`; `incoming_caterer_id ← null`) at the start of
  the next `register_orders.py` run.
- **The Wednesday 8 PM cutoff is informational on the webapp**, hard
  in the order pipeline. The form will save a preference after 8 PM but
  next week's order is already frozen by then.
- **Migrations destroy and reseed.** They are not idempotent in the
  "merge-only-deltas" sense; they are idempotent in the "clear and
  reinsert" sense. Mid-term enrolment edits happen in Supabase Studio,
  not via `./run migrate students`.
