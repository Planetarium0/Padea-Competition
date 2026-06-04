-- Support email cases: tracks parent support requests and their lifecycle.
-- Parents email support@help.<APP_DOMAIN>; the edge function parks messages
-- here; poll_support_inbox.py drains the table and drives handle_support_email.py.

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
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_code    TEXT UNIQUE NOT NULL,          -- e.g. SC-2026-AB12CD34
    parent_email TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'Open'
                 CHECK (status IN ('Open', 'Resolved', 'Escalated')),
    opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    messages     JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes        TEXT
);

CREATE INDEX support_cases_open_idx
    ON support_cases (parent_email, status)
    WHERE status = 'Open';

ALTER TABLE support_inbound_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_cases ENABLE ROW LEVEL SECURITY;
