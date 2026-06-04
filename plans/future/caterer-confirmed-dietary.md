# Caterer-confirmed dietary information

**Status:** Phase A (schema + sweep) and the core of Phase D (escalation + `notify_coordinator`) implemented 2026-06-04, against an earlier draft of this plan. Phase B (MailSlurp inbound adapter), Phase C (parser + iterative clarification), the weekly tag-write digest within Phase D, and Phase E (reactive triggers) are still to do. The earlier draft's caterer-facing webapp page is intentionally dropped — see §2 non-goals. A supporting `compatibility.item_verdict()` helper landed alongside Phase A.
**Touches:** `scripts/actions/clarify_dietary.py`, `scripts/actions/parse_dietary_reply.py`,
`scripts/actions/poll_dietary_inbox.py`, `scripts/actions/escalate_dietary.py`,
`scripts/support/inbound.py`, `scripts/support/email.py::notify_coordinator`,
`supabase/migrations/<new>.sql`. Compatibility logic in
`scripts/support/compatibility.py` and the order pipeline are
**unchanged**.

---

## 1. The problem in one paragraph

The compatibility ladder produces three verdicts per (item, restriction):
**OK** (positive tag covers the restriction's subset closure), **NO**
(legend coverage or name-keyword match), and the silent middle case
**MAYBE** (no information). `register_orders.py` collapses MAYBE →
assignable. That stays. The actual problem is that today there is no
structured way to **convert MAYBE into OK or NO** — only hand-edited
`menu_item_dietary_tags` rows in Studio and brittle name-keywords. The
caterer holds the missing information; we already email them; we have
nowhere to put their answer.

The fix is to **ask the caterer once per term, parse their free-form
reply with an LLM, ask the caterer a clarifying question if the parse
is uncertain, persist confirmed answers into the existing tag/legend
schema, and escalate to the coordinator if the caterer goes silent for
7 days**. The order pipeline reads tags as it does today.

## 2. Goals & non-goals

**Goals**

1. Every (item × restriction) MAYBE that affects a real enrolled student
   becomes a tracked question put to the caterer.
2. One email per (caterer × school) at term start opens the
   conversation; iterative LLM-driven clarification closes most of it
   without further coordinator effort.
3. Every tag write is preceded by a message where our interpretation
   was spelled out to the caterer in plain language and they replied
   without contradicting it.
4. Coordinator is notified only on (a) a caterer not answering within
   7 days of the original sweep, (b) the LLM unable to reach clean
   answers within the round cap, or (c) an inbound reply that can't be
   threaded back to a request.
5. Webapp's three-state badge becomes more accurate as caterers reply,
   without changing the algorithm.

**Non-goals**

- No two-tier safety-critical vs. permissive verdict. Compatibility
  algorithm is unchanged.
- No caterer-facing webapp page. Caterers reply by email.
- No real-time inbound webhook in v1. The inbox is polled by a `./run`
  verb (see §9).
- Per-student severity. Same treatment for all students with a given
  restriction.

## 3. Design — abstract

Treat **MAYBE as an open question**, not a default-accept. An open
question lives at the granularity *(caterer, menu_item, restriction)*.

State machine for one `dietary_clarification_request` (groups all
questions for a (caterer × sweep) pair):

```
  Open             after the sweep email is sent
   │
   ├── caterer replies → LLM parses
   │       ├── all answers high-confidence → write tags →
   │       │     all cells resolved? → Resolved
   │       │     else                  → stay Open (more questions
   │       │                             outstanding; await next reply)
   │       └── any low-confidence  → Clarifying
   │
  Clarifying       LLM has emitted a clarification question;
   │               we have replied in-thread and await caterer
   │               (max 2 rounds total; reset to Open after caterer
   │               answers)
   │
  Resolved         all cells in question_set answered + persisted
  Escalated        7-day deadline passed OR round-cap hit;
                   coordinator notified once
  Cancelled        manually closed (e.g. caterer dropped)
```

Provenance is not a new column. A row in `menu_item_dietary_tags` is a
row, regardless of source. For audit, the parse action appends one line
to `menu_items.notes` per write: `Nut Free confirmed by caterer
2026-06-10 via clarification CDR-23-greekcaterer`.

**Earned legend** survives unchanged in spirit: when the caterer has
explicitly accounted for every menu item under one restriction column
(Compatible or Contains, no "Don't know"), the parse action adds
`(caterer_id, restriction_id)` to `caterer_legend_tags`. From that
moment, the existing legend-coverage check yields NO for any item
without a positive tag under that restriction. The LLM extracts both
per-item facts *and* a "earned-legend?" flag from the conversation.

## 4. The term-start sweep — primary trigger

Trigger: **coordinator runs `./run dietary clarify <school>` manually**,
after parent forms have come back and `student_dietary_restrictions`
is current. No automated enrolment hook.

Algorithm:

1. Load students enrolled at the school, the caterers paired to its
   sessions, those caterers' menus, the existing tag + legend rows.
2. Compute the union of restrictions in that enrolment.
3. Per caterer, walk (their menu items × the union) through the
   existing 3-step ladder. Collect every triple where the verdict is
   MAYBE.
4. For each caterer with ≥1 MAYBE, insert a
   `dietary_clarification_requests` row with `status='Open'`,
   `sent_at=now()`, and `question_set` as JSONB
   `[{menu_item_id, restriction_id, answer: null}, …]`.
5. Send one email per caterer via `schedule_email`. From:
   `orders@padea.com.au` (Resend). **Reply-To: the shared MailSlurp
   inbox address.** Subject: `[<request_code>] Padea dietary check —
   <caterer name>`. Body: one row per menu item with the open
   restrictions listed, with a "please reply to this email" note. No
   form, no buttons.
6. Print a per-caterer summary: open question count, 7-day deadline.

## 5. Parse + iterative clarification — the new core

A new action `scripts/actions/parse_dietary_reply.py` is invoked by
the inbox poller (§9) whenever a reply lands against an open request.
It receives the full thread (original sweep + every send/reply since)
and the request's `question_set`.

It calls `support.ask_llm` with a prompt that returns a strict JSON
object:

```jsonc
{
  "confident_writes": [
    {"menu_item_id": "…", "restriction_id": "…", "answer": "compatible|contains"}
  ],
  "earned_legends": [
    {"restriction_id": "…", "rationale": "caterer said 'all our pasta is vegetarian'"}
  ],
  "clarification_questions": [
    // empty if everything confident
    "Just to confirm — the no-beef meals are: …, and the curry is the only one with beef. Is that right?"
  ],
  "still_unknown": [
    {"menu_item_id": "…", "restriction_id": "…"}
  ]
}
```

The action then:

- **If `clarification_questions` is non-empty** and the request has
  `clarification_rounds < 2`: increment `clarification_rounds`, set
  `status='Clarifying'`, compose a reply in-thread (set `In-Reply-To`
  to the last caterer message, keep the request code in the subject),
  send via Resend (Reply-To: MailSlurp again). Do not write any tags
  this round.
- **If `clarification_questions` is empty**: write the
  `confident_writes` as `menu_item_dietary_tags` rows (`INSERT ON
  CONFLICT DO NOTHING`); write the `earned_legends` as
  `caterer_legend_tags` rows; update `question_set` answers; append
  notes lines per touched menu item; if every cell is now answered,
  set `status='Resolved'`.
- **If round cap hit with clarifications still needed**: set
  `status='Escalated'`, call `notify_coordinator` (§6) with the full
  conversation.

The conversation is persisted as a `messages` JSONB array on the
request row: `[{direction, sent_at, message_id, body, parsed_extraction}]`.
That's the audit trail. If it outgrows JSONB later (it won't — bounded
by 2 rounds), split into a child table then.

The whole flow has to be tested against a **scripted-caterer fixture**:
`scripts/tests/test_parse_dietary_reply.py` table-drives ~15 realistic
reply patterns — sweeping confirmations, partial answers, "X is fine
but Y on request", typos, threaded quotes, follow-up questions instead
of answers. Each fixture has the expected `confident_writes`,
`clarification_questions`, and final state after the loop runs to
completion. This is the lever that keeps the LLM honest.

## 6. Escalation rules

A new action `scripts/actions/escalate_dietary.py`
(`./run dietary escalate`), also invoked at the tail of every other
`./run dietary …` verb so the deadline checks aren't a separate cron
in v1. It walks rows where any of:

- `status='Open' OR 'Clarifying'` AND `sent_at + INTERVAL '7 days' < now()`.
- `status='Escalated'` already (idempotent dedupe; re-emit only if
  the prior notification artifact is missing).

For each, it sets `status='Escalated'` (if not already) and calls
`notify_coordinator(...)` — a new sibling to `escalate_to_dev` in
`support.email`, same artifact-first pattern
(`cache/notifications/clarify_<request_id>.md` written first, then
best-effort email to `COORDINATOR_EMAIL`, falling back to
`DEV_NOTIFICATION_EMAIL`).

The parse action also calls `notify_coordinator` directly when the
round cap is hit (separate `notification_reason` field on the
artifact: `silent_caterer` vs `parse_stuck`).

Coordinator oversight outside the escalation path: a **weekly tag-write
digest** — a low-priority `notify_coordinator` listing every
`menu_item_dietary_tags` / `caterer_legend_tags` row written by the
parser in the past 7 days, linked to the source conversation. The
coordinator has 7 days to raise a concern; otherwise the tags stand.
Implementation is a thin SQL query + email; not a phase of its own.

## 7. Reactive triggers (smaller, same algorithm)

Same shape as the term-start sweep, narrower scope. Each is a separate
`./run` verb, coordinator-initiated:

- `execute_caterer_switch.py` ends by calling `clarify_dietary(school,
  caterer=new)`.
- `./run dietary clarify <school> --restriction <name>` — asks just
  that restriction across the school's caterers.
- `./run dietary clarify-item <menu_item_id>` — asks just that item
  across every school the caterer serves.

All three write a fresh request row, start their own 7-day clock, and
feed the same parse-iterate loop.

## 8. Schema changes

One migration, `<ts>_dietary_clarification.sql`:

```sql
CREATE TABLE dietary_clarification_requests (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_code          TEXT UNIQUE NOT NULL,
    caterer_id            UUID NOT NULL REFERENCES caterers (id) ON DELETE CASCADE,
    school_id             UUID REFERENCES schools (id) ON DELETE SET NULL,
    sent_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at          TIMESTAMPTZ,
    clarification_rounds  INT NOT NULL DEFAULT 0,
    status                TEXT NOT NULL DEFAULT 'Open'
                          CHECK (status IN ('Open','Clarifying','Resolved','Escalated','Cancelled')),
    question_set          JSONB NOT NULL,
    messages              JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes                 TEXT
);

CREATE INDEX dietary_clarification_active_idx
    ON dietary_clarification_requests (status, sent_at)
    WHERE status IN ('Open','Clarifying');

ALTER TABLE dietary_clarification_requests ENABLE ROW LEVEL SECURITY;
-- service-key-only writes; no anon write policy needed.
```

`menu_item_dietary_tags`, `caterer_legend_tags`, `menu_items.notes`
are unchanged.

**Important**: because all writes happen server-side using the service
key, this plan **does not depend on the RLS gap** in
`principles.md §6`. That's a large simplification compared to the
prior form-based design.

## 9. Inbound mail adapter

`scripts/support/inbound.py` defines a thin interface:

```python
class InboundMailbox(Protocol):
    def fetch_new(self, since: datetime) -> list[InboundMessage]: ...
    def mark_seen(self, message_id: str) -> None: ...
```

`InboundMessage` exposes `message_id`, `in_reply_to`, `subject`,
`from_address`, `body_text`, `received_at`.

v1 implementation: `MailSlurpInbox` using the `mailslurp-client` Python
SDK and a single shared inbox configured by env var `MAILSLURP_INBOX_ID`
+ `MAILSLURP_API_KEY`. The MailSlurp address is also written to a
constant used by the sweep + parse actions as the `Reply-To` value.

A new action `scripts/actions/poll_dietary_inbox.py`
(`./run dietary poll`) drains the inbox:

1. For each new message, try to thread to a request:
   - First by `In-Reply-To` (if it matches the `message_id` of any
     prior outbound on a request),
   - else by extracting the request code from the subject (`[CDR-…]`),
   - else **park it**: insert into a small `dietary_unthreaded_replies`
     table (id, received_at, raw_jsonb) and `notify_coordinator` once
     per week with the parked list. Park-rather-than-drop because a
     misthreaded reply is information we don't want to lose.
2. For each threaded reply, invoke `parse_dietary_reply` against the
   matched request.
3. Mark the message seen.

This is the only piece of the plan that talks to MailSlurp.
Production-time swap (Postmark / Mailgun / Gmail MCP — the latter is
already available in this project's MCP toolset) is a one-file change:
implement the same `InboundMailbox` interface against the new vendor,
swap the env-var-driven constructor. The rest of the system doesn't
know which inbox provider is wired in.

## 10. Implementation phases

**Phase A — schema + sweep** *(done 2026-06-04)*. Migration
`20260604000000_dietary_clarification.sql`; Pydantic
`DietaryClarificationRequest` + TypedDict `DietaryClarificationRequestFields`
+ `ClarificationStatus` literal; `db.DietaryClarificationRequests`
table + `MockDatabase` mirror; `scripts/actions/clarify_dietary.py`
(sweep — sends emails, opens requests; also tail-calls escalation);
`scripts/tests/test_clarify_dietary.py` (16 tests covering
`compute_question_set`, `school_restriction_union`, `has_open_request`,
`run_sweep`). Supporting helper `compatibility.item_verdict()` added
as a peer to `item_incompatibility_ids`, returning `"OK" | "MAYBE" |
"NO"` — used by the sweep today, will be used by the parser in Phase
C. ./run verb: `dietary clarify <school>`.

**Phase B — inbound adapter + threading** *(todo)*.
`support/inbound.py` (Protocol + `InboundMessage` dataclass),
`MailSlurpInbox` impl using `mailslurp-client`, env vars
`MAILSLURP_INBOX_ID` / `MAILSLURP_API_KEY`,
`scripts/actions/poll_dietary_inbox.py`,
`dietary_unthreaded_replies` table for the park-on-failure path.
Tests must cover threading by `In-Reply-To`, by subject code, and the
park-on-failure branch. The sweep already sets the request code in
its subject (per §4 step 5), so the subject-threading path has the
data it needs once this lands.

**Phase C — parser + iterative loop** *(todo)*.
`scripts/actions/parse_dietary_reply.py`,
`scripts/tests/test_parse_dietary_reply.py` with the scripted-caterer
fixture corpus. This is the highest-risk component; do not ship
without the fixture coverage. Phase C depends on Phase B (no caterer
replies will be threaded back to a request until the poller exists).

**Phase D — escalation + coordinator notify + digest**
*(core done 2026-06-04; digest todo)*. Done:
`scripts/actions/escalate_dietary.py` (status transitions on overdue
requests; dedupes on `status='Escalated'`),
`support.email.notify_coordinator` (artifact-first under
`cache/notifications/`, emails `COORDINATOR_EMAIL` falling back to
`DEV_NOTIFICATION_EMAIL`), `scripts/tests/test_escalate_dietary.py`
(8 tests). ./run verb: `dietary escalate`. Still to do: the weekly
tag-write digest (§6) — empty today because no parser-written tags
exist yet; revisit after Phase C lands.

**Phase E — reactive triggers** *(todo)*. Hook from
`execute_caterer_switch.py`; `--restriction` and `clarify-item`
flags on the dietary verb group. Lower priority; can land after a
term of operating just on the term-start sweep.

Phases A–D are the minimum useful slice. Phase E is incremental.

## 11. Open questions

- **Round cap value.** 2 is a guess. May want 3 if real replies show
  one round of clarification routinely uncovers a new question.
- **Per-restriction confidence thresholds.** The LLM emits "confident"
  vs "needs clarification" today as a binary; for restrictions with
  high-cost mistakes (allergens) we may want to force a clarification
  round even when the LLM says it's confident. Tunable in the parser
  prompt; defer until the fixture corpus surfaces real failures.
- **Caterer prefers phone.** The clarification email can include "or
  call <coordinator>" as a footer; replies via that path get manually
  recorded via a `./run dietary record <request_id>` admin verb.
  Cheap to add later.
- **Threading robustness.** v1 uses `In-Reply-To` + subject code. If
  parking becomes common, add a per-request unique MailSlurp address
  in v2 — that makes mis-threading impossible at the cost of inbox
  quota.

---

*Last updated 2026-06-04.*
