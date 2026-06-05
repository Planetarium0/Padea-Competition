-- Add pending_dietary_clarify flag to caterers.
-- Set automatically by approve_caterer_switch when a new caterer is assigned
-- to a session; consumed (and cleared) by the daily dietary clarify sweep.
ALTER TABLE caterers
    ADD COLUMN IF NOT EXISTS pending_dietary_clarify BOOLEAN NOT NULL DEFAULT false;

-- Recreate approve_caterer_switch to also set the flag on the incoming caterer.
CREATE OR REPLACE FUNCTION approve_caterer_switch(
    p_proposal_id UUID
) RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_session_id          UUID;
    v_incoming_caterer_id UUID;
BEGIN
    SELECT session_id, incoming_caterer_id
    INTO v_session_id, v_incoming_caterer_id
    FROM caterer_switch_proposals
    WHERE id = p_proposal_id
      AND status IN ('Pending', 'Approved');

    IF v_session_id IS NULL THEN
        RAISE EXCEPTION 'Proposal % not found or not in an approvable state', p_proposal_id;
    END IF;

    -- Point the session at the incoming caterer
    UPDATE sessions
    SET incoming_caterer_id = v_incoming_caterer_id
    WHERE id = v_session_id;

    -- Clear meal preferences for all students enrolled in this session
    UPDATE students s
    SET meal_preference_id = NULL
    FROM student_sessions ss
    WHERE ss.session_id = v_session_id
      AND ss.student_id = s.id;

    -- Mark proposal approved
    UPDATE caterer_switch_proposals
    SET status = 'Approved'
    WHERE id = p_proposal_id;

    -- Flag incoming caterer for dietary clarification at next daily sweep
    UPDATE caterers
    SET pending_dietary_clarify = true
    WHERE id = v_incoming_caterer_id;
END;
$$;
