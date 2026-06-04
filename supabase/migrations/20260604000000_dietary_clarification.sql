-- Dietary clarification requests: tracks per-caterer dietary information
-- requests and their lifecycle (Open → Resolved / Escalated / Cancelled).

CREATE TABLE dietary_clarification_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_code  TEXT UNIQUE NOT NULL,     -- e.g. CDR-2026-W23-CAFEDELUXE-sAlpha0
    caterer_id    UUID NOT NULL REFERENCES caterers (id) ON DELETE CASCADE,
    school_id     UUID REFERENCES schools (id) ON DELETE SET NULL,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at  TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'Open'
                  CHECK (status IN ('Open', 'Resolved', 'Escalated', 'Cancelled')),
    question_set  JSONB NOT NULL,           -- [{menu_item_id, restriction_id}]
    notes         TEXT
);

CREATE INDEX dietary_clarification_open_idx
    ON dietary_clarification_requests (status, sent_at)
    WHERE status = 'Open';

ALTER TABLE dietary_clarification_requests ENABLE ROW LEVEL SECURITY;
