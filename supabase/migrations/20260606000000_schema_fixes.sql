-- =============================================================================
-- Schema fixes, constraints, and new school_terms table.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Fix FK constraints on scheduled_emails so weekly_orders can be cleared.
--    Use ON DELETE SET NULL: the email audit row is preserved but its FK
--    reference is nulled so deletion of the parent rows is not blocked.
-- ---------------------------------------------------------------------------

ALTER TABLE scheduled_emails
    DROP CONSTRAINT IF EXISTS scheduled_emails_weekly_order_id_fkey;

ALTER TABLE scheduled_emails
    ADD CONSTRAINT scheduled_emails_weekly_order_id_fkey
    FOREIGN KEY (weekly_order_id) REFERENCES weekly_orders (id) ON DELETE SET NULL;

ALTER TABLE scheduled_emails
    DROP CONSTRAINT IF EXISTS scheduled_emails_caterer_switch_proposal_id_fkey;

ALTER TABLE scheduled_emails
    ADD CONSTRAINT scheduled_emails_caterer_switch_proposal_id_fkey
    FOREIGN KEY (caterer_switch_proposal_id) REFERENCES caterer_switch_proposals (id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- 2. Add UNIQUE constraints to audit code columns.
--    Postgres UNIQUE allows multiple NULLs, so existing NULL-coded rows are
--    unaffected. Prevents duplicate non-NULL codes from being inserted.
-- ---------------------------------------------------------------------------

ALTER TABLE absences
    ADD CONSTRAINT absences_absence_code_key UNIQUE (absence_code);

ALTER TABLE manager_substitutions
    ADD CONSTRAINT manager_substitutions_substitution_code_key UNIQUE (substitution_code);

ALTER TABLE exclusions
    ADD CONSTRAINT exclusions_exclusion_code_key UNIQUE (exclusion_code);

-- ---------------------------------------------------------------------------
-- 3. Cycle-detection trigger on dietary_restriction_supersets.
--    Prevents a (restriction_id, superset_id) edge from being inserted if it
--    would make the hierarchy non-DAG (i.e. restriction_id is already
--    reachable from superset_id via existing edges).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION check_dietary_restriction_acyclic()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        WITH RECURSIVE reachable(id) AS (
            SELECT NEW.superset_id
            UNION ALL
            SELECT drs.superset_id
            FROM dietary_restriction_supersets drs
            JOIN reachable r ON drs.restriction_id = r.id
        )
        SELECT 1 FROM reachable WHERE id = NEW.restriction_id
    ) THEN
        RAISE EXCEPTION
            'dietary_restriction_supersets: adding (%, %) would create a cycle',
            NEW.restriction_id, NEW.superset_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER enforce_dietary_restriction_acyclic
BEFORE INSERT OR UPDATE ON dietary_restriction_supersets
FOR EACH ROW EXECUTE FUNCTION check_dietary_restriction_acyclic();

-- ---------------------------------------------------------------------------
-- 4. school_terms table.
--    Stores named term date ranges used for caterer-switch deduplication.
--    Replaces hardcoded QLD_TERM_STARTS in evaluate_caterers.py.
-- ---------------------------------------------------------------------------

CREATE TABLE school_terms (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    term_code  TEXT NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    CONSTRAINT school_terms_date_order CHECK (end_date > start_date)
);

ALTER TABLE school_terms ENABLE ROW LEVEL SECURITY;

-- Seed 2026 Queensland school terms.
INSERT INTO school_terms (term_code, start_date, end_date) VALUES
    ('2026-T1', '2026-01-27', '2026-04-03'),
    ('2026-T2', '2026-04-20', '2026-06-26'),
    ('2026-T3', '2026-07-14', '2026-09-18'),
    ('2026-T4', '2026-10-05', '2026-12-04');
