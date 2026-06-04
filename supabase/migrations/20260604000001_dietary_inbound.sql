-- Extend dietary_clarification_requests for Phase B/C:
--   add Clarifying status, clarification_rounds, messages, reply_to_address.
-- Create dietary_inbound_messages to park caterer email replies.

-- 1. Drop old CHECK constraint and replace with one that includes 'Clarifying'.
ALTER TABLE dietary_clarification_requests
    DROP CONSTRAINT dietary_clarification_requests_status_check;

ALTER TABLE dietary_clarification_requests
    ADD CONSTRAINT dietary_clarification_requests_status_check
    CHECK (status IN ('Open', 'Clarifying', 'Resolved', 'Escalated', 'Cancelled'));

-- 2. New columns.
ALTER TABLE dietary_clarification_requests
    ADD COLUMN clarification_rounds INT NOT NULL DEFAULT 0;

ALTER TABLE dietary_clarification_requests
    ADD COLUMN messages JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE dietary_clarification_requests
    ADD COLUMN reply_to_address TEXT;

-- 3. Replace the old partial index with one that covers both Open and Clarifying.
DROP INDEX dietary_clarification_open_idx;

CREATE INDEX dietary_clarification_active_idx
    ON dietary_clarification_requests (status, sent_at)
    WHERE status IN ('Open', 'Clarifying');

-- 4. Inbound email table — one row per caterer reply received by the webhook.
CREATE TABLE dietary_inbound_messages (
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

CREATE INDEX dietary_inbound_unseen_idx
    ON dietary_inbound_messages (received_at)
    WHERE seen = false;

ALTER TABLE dietary_inbound_messages ENABLE ROW LEVEL SECURITY;
