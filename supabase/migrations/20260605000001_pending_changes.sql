-- Stores parent-requested field changes that require coordinator approval.
CREATE TABLE pending_changes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    parent_email            TEXT NOT NULL,
    student_id              UUID REFERENCES students(id) ON DELETE CASCADE,
    field_name              TEXT NOT NULL,
    current_value           JSONB,
    new_value               JSONB NOT NULL,
    reason                  TEXT,
    status                  TEXT NOT NULL DEFAULT 'Pending'
                            CHECK (status IN ('Pending', 'Approved', 'Denied')),
    notification_message_id TEXT,
    resolved_at             TIMESTAMPTZ,
    coordinator_message     TEXT,
    support_case_id         UUID REFERENCES support_cases(id) ON DELETE SET NULL
);

CREATE INDEX pending_changes_parent_idx
    ON pending_changes (parent_email, status);

CREATE INDEX pending_changes_notification_idx
    ON pending_changes (notification_message_id)
    WHERE notification_message_id IS NOT NULL;

ALTER TABLE pending_changes ENABLE ROW LEVEL SECURITY;
