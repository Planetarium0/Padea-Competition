# AI-powered support email

**Status:** All three phases implemented 2026-06-04.
**Depends on:** Phase B of `caterer-confirmed-dietary.md` (SendGrid Inbound
Parse infrastructure + `SupabaseInboundInbox` adapter must exist first).
**Touches:** new `scripts/actions/handle_support_email.py`, new
`supabase/migrations/<ts>_support_cases.sql`, new route in the inbound
Edge Function, `scripts/support/email.py` (no change needed — already
has `notify_coordinator`).

---

## 1. What this does

Parents email `support@<APP_DOMAIN>`. An LLM reads the email and acts
on it through a small, constrained tool set. Example: a parent reports
"my son is allergic to soy — it doesn't seem to be in the form." The
AI looks up the parent's children, finds the right restriction name,
adds it to `student_dietary_restrictions`, and confirms by reply.

If the sender isn't a known parent, the email is forwarded to
`COORDINATOR_EMAIL` and the LLM never runs.

---

## 2. Inbound routing

### Option A — root domain MX (preferred if no existing MX)

Add a SendGrid Inbound Parse MX record to the root domain. The shared
Edge Function `receive-dietary-reply` is extended (or a new Edge
Function `receive-support-email` is added) to route by `To` address:

- `To` matches `replies@reply.<APP_DOMAIN>` → dietary handler (existing)
- `To` matches `support@<APP_DOMAIN>` → support handler (new)
- anything else → log and return 200

### Option B — dedicated subdomain (if root domain MX already exists)

Add a `support.` subdomain MX record pointing to SendGrid Inbound
Parse. The support address becomes `support@support.<APP_DOMAIN>` or,
cleaner, use `help.` as the subdomain so the address is
`support@help.<APP_DOMAIN>`. A separate Edge Function
`receive-support-email` handles the route.

Either option feeds the same `support_inbound_messages` table and the
same `handle_support_email.py` action. The routing choice is
infrastructure-only.

---

## 3. Sandbox design

Three independent layers. All three must pass for a write to occur.

### Layer 1 — identity gate (before the LLM runs)

```python
students = db.Students.all(
    filter=lambda q: q.eq("parent_email", from_address)
)
if not students:
    notify_coordinator(
        "support-unrecognised-<message_id>",
        reason=f"Email from {from_address} — not a known parent. Forwarding raw.",
        ...
    )
    return
```

Unrecognised senders never reach the LLM. No reply is sent to them
(avoids confirming that the address exists or that the system read it).

### Layer 2 — constrained tool set

The LLM is given exactly four tools, implemented as Python functions
passed to `ask_llm` as tool definitions:

| Tool | What it does | What it cannot do |
|---|---|---|
| `list_students()` | Returns `[{id, name, year_level, dietary_requirement_ids}]` for students where `parent_email == sender`. | Cannot query other parents' students. |
| `list_dietary_restrictions()` | Returns `[{id, name}]` for all rows in `dietary_restrictions`. Read-only. | Cannot modify. |
| `add_dietary_restriction(student_id, restriction_id)` | Inserts into `student_dietary_restrictions` after re-validating `student.parent_email == sender` server-side. | Cannot remove. Cannot write to any other table. |
| `send_reply(body_text)` | Queues a plain-text reply to `from_address` via `schedule_email`. | Cannot email any other address. |

There is intentionally no `remove_dietary_restriction` tool. Removals
are coordinator-only, done in Supabase Studio.

### Layer 3 — DB-level enforcement

`add_dietary_restriction` validates at call time, not just at prompt
time:

```python
def add_dietary_restriction(student_id: str, restriction_id: str) -> str:
    student = db.Students.get(student_id)
    if not student or student.fields.get("parent_email") != sender_email:
        return "Error: student not found or not linked to this parent."
    restriction = db.DietaryRestrictions.get(restriction_id)
    if not restriction:
        return "Error: restriction not found."
    db.StudentDietaryRestrictions.create([{
        "student_id": student_id,
        "restriction_id": restriction_id,
    }])
    # Audit line appended to support_cases.messages (handled by caller).
    return f"Added {restriction.fields['name']} to {student.fields['name']}."
```

If a jailbreak manages to get the LLM to call `add_dietary_restriction`
with a `student_id` that doesn't belong to the sender, the server-side
check returns an error string and nothing is written.

---

## 4. Conversation flow

```
Parent emails support@<APP_DOMAIN>
   ↓
Edge Function writes to support_inbound_messages, returns 200
   ↓
./run support poll (or auto-tail of ./run dietary poll)
   ↓
Identity gate: look up students by parent_email
   ├── no match → notify_coordinator, stop
   └── match → proceed
   ↓
Open or find existing support_cases row for this parent
(thread by In-Reply-To → case message_id, else new case)
   ↓
call ask_llm with:
  - system prompt (§5)
  - full case message history
  - the four tools
   ↓
LLM calls tools zero or more times, then calls send_reply(...)
   ↓
Each tool call is appended to support_cases.messages with
timestamp and result
   ↓
send_reply dispatches via schedule_email (Reply-To omitted —
parent replies come back to support@ again, re-entering the flow)
```

Multi-turn conversations are supported naturally: the parent replies
to the confirmation email, which threads back to the same case via
`In-Reply-To`, and the LLM sees the full history on the next call.

---

## 5. System prompt (draft)

```
You are the Padea dietary support assistant. You help parents update
their children's dietary requirements in the Padea meal ordering
system.

You have access to four tools: list_students, list_dietary_restrictions,
add_dietary_restriction, and send_reply. You cannot remove dietary
requirements — direct the parent to contact the coordinator if removal
is needed.

Rules:
- Only act on students returned by list_students. Never guess student IDs.
- Only add restrictions that appear in list_dietary_restrictions. If the
  parent describes a restriction that isn't in the list, tell them you've
  noted it and that a coordinator will follow up — do not add a made-up
  restriction.
- For clear requests, add the restriction and confirm in your reply.
- For ambiguous requests, ask a single clarifying question before acting.
- Always end by calling send_reply. Never leave a parent without a response.
- Be brief and friendly. One or two sentences per reply.
```

The prompt is stored in `scripts/actions/handle_support_email.py`,
not in a DB table, so changes go through code review.

---

## 6. Unknown restrictions

If the parent describes something not in `dietary_restrictions` (e.g.
"soy allergy" when "Soy Free" doesn't exist), the LLM:

1. Calls `list_dietary_restrictions()` — confirms no match.
2. Calls `send_reply("Thanks for letting us know. We've noted Alex's
   soy allergy and a coordinator will be in touch to update your
   account.")`.
3. The action logs a `notify_coordinator` call with the original email
   and "unknown restriction: soy allergy for student X".

This is the same pattern as the dietary clarification escalation.
Nothing is written to the DB except the case record. The coordinator
can then add "Soy Free" to `dietary_restrictions` (a migration) and
process the case manually.

---

## 7. Schema

```sql
CREATE TABLE support_inbound_messages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen          BOOLEAN NOT NULL DEFAULT false,
    from_address  TEXT NOT NULL,
    subject       TEXT,
    body_text     TEXT,
    message_id    TEXT,
    in_reply_to   TEXT,
    to_address    TEXT,
    raw_payload   JSONB
);

CREATE INDEX support_inbound_unseen_idx
    ON support_inbound_messages (received_at)
    WHERE seen = false;

CREATE TABLE support_cases (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_code      TEXT UNIQUE NOT NULL,
    parent_email   TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'Open'
                   CHECK (status IN ('Open', 'Resolved', 'Escalated')),
    opened_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ,
    messages       JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{direction, sent_at, message_id, body, tool_calls?: [...]}]
    notes          TEXT
);

CREATE INDEX support_cases_open_idx
    ON support_cases (parent_email, status)
    WHERE status = 'Open';

ALTER TABLE support_inbound_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_cases             ENABLE ROW LEVEL SECURITY;
-- service-key-only; no anon access.
```

No new junction tables. `StudentDietaryRestrictions` writes go through
the existing `student_dietary_restrictions` table and the existing
`db.StudentDietaryRestrictions` wrapper.

---

## 8. New env var

```
SUPPORT_EMAIL=support@<APP_DOMAIN>   # or support@help.<APP_DOMAIN> depending
                                     # on routing option chosen (§2)
                                     # used by handle_support_email to validate
                                     # the To address and to send replies from
```

If `SUPPORT_EMAIL` is unset, `./run support poll` logs a warning and
exits cleanly — no crash.

---

## 9. ./run verb

```bash
./run support poll [--dry-run]   # drain support_inbound_messages, run handler
```

Can be tailed onto `./run dietary poll` in a single coordinator step,
or run independently.

---

## 10. Implementation phases

**Phase 1 — schema + identity gate + escalation path:**
Migration; TypedDict + Pydantic for `support_cases`; inbound routing
in the Edge Function; the `handle_support_email` action that only
does the identity gate and `notify_coordinator` (LLM not yet wired in).
Tests: unrecognised sender → `notify_coordinator`, no DB write; known
parent → case row created.

**Phase 2 — LLM tool loop:**
Wire in `ask_llm` with the four tools; implement `add_dietary_restriction`
with the server-side re-check; implement `send_reply`. Tests: known
restriction → row inserted + reply sent; unknown restriction → escalated,
no insert; wrong student_id (cross-parent attempt) → tool returns error,
no insert; ambiguous email → LLM sends clarifying question, no insert.

**Phase 3 — multi-turn threading:**
Thread replies to existing open cases via `In-Reply-To`; append to
`messages` JSONB; LLM sees full history. Tests: parent replies with
"yes" to confirm → restriction added; parent replies with "actually
it's dairy not soy" → correct restriction added.

---

## 11. Open questions

- **Coordinator can also email support@.** The coordinator's email may
  or may not be a `parent_email` in the DB. If it is (unlikely), they'd
  go through the normal flow. If it isn't, they'd be treated as an
  unknown sender and get notified to themselves — confusing. Simple fix:
  check `from_address == COORDINATOR_EMAIL` first and route those
  directly to `notify_coordinator` before the parent identity gate.
- **Auto-resolve.** Should cases auto-close after the LLM sends a
  `send_reply` with no outstanding ambiguities? Or stay `Open` until a
  fixed timeout? Recommendation: auto-resolve after the LLM's final
  `send_reply` call if no tool calls were left pending. Reopen on a
  follow-up reply from the parent.
- **Rate limiting.** A parent (or a script) could spam the support
  address. Simple guard: if a `parent_email` has > N open cases (e.g.
  3), skip LLM processing and `notify_coordinator`. Cheap to add.

---

*Last updated 2026-06-04.*
