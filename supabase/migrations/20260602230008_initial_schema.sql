-- =============================================================================
-- Padea: Initial Schema Migration
-- Replaces Airtable with a fully-relational PostgreSQL schema.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Core Tables (topological order: no FKs reference tables defined later,
-- except the deferred constraints added at the end of this file)
-- ---------------------------------------------------------------------------

CREATE TABLE schools (
    id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name   TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE on_site_managers (
    id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name   TEXT NOT NULL,
    mobile TEXT,
    email  TEXT
);

CREATE TABLE caterers (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   TEXT NOT NULL,
    region                 TEXT NOT NULL,
    min_qty_4_items        INTEGER,
    min_qty_5_items        INTEGER,
    min_qty_6_items        INTEGER,
    price_per_item         NUMERIC(10, 2),
    contact_name           TEXT,
    contact_email          TEXT,
    chef_name              TEXT,
    chef_email             TEXT,
    chef_wants_cc          BOOLEAN NOT NULL DEFAULT false,
    delivery_fee           NUMERIC(10, 2),
    delivery_fee_structure TEXT CHECK (delivery_fee_structure IN ('Per trip', 'Per school per trip')),
    notes                  TEXT
);

CREATE TABLE dietary_restrictions (
    id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE menu_items (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    caterer_id    UUID NOT NULL REFERENCES caterers (id) ON DELETE CASCADE,
    is_variant    BOOLEAN NOT NULL DEFAULT false,
    variant_of_id UUID REFERENCES menu_items (id) ON DELETE SET NULL,
    notes         TEXT
);

-- Sessions reference caterers and schools (incoming_caterer_id nullable)
CREATE TABLE sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_code         TEXT NOT NULL UNIQUE,
    school_id            UUID NOT NULL REFERENCES schools (id),
    caterer_id           UUID NOT NULL REFERENCES caterers (id),
    incoming_caterer_id  UUID REFERENCES caterers (id),
    on_site_manager_id   UUID REFERENCES on_site_managers (id),
    day                  TEXT NOT NULL CHECK (day IN ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')),
    start_time           TIME,
    end_time             TIME,
    dinner_time          TIME,
    building             TEXT
);

CREATE TABLE students (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    year_level          INTEGER,
    subjects            TEXT,
    email               TEXT,
    parent_name         TEXT,
    parent_email        TEXT,
    parent_mobile       TEXT,
    meal_preference_id  UUID REFERENCES menu_items (id) ON DELETE SET NULL,
    last_submitted      DATE
);

CREATE TABLE manager_substitutions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    substitution_code      TEXT,
    session_id             UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    date                   DATE NOT NULL,
    substitute_manager_id  UUID NOT NULL REFERENCES on_site_managers (id)
);

CREATE TABLE absences (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    absence_code TEXT,
    student_id   UUID NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    session_id   UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    date         DATE NOT NULL,
    reason       TEXT
);

CREATE TABLE exclusions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    exclusion_code  TEXT,
    school_id       UUID NOT NULL REFERENCES schools (id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    reason          TEXT
);

CREATE TABLE caterer_feedback (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_code TEXT UNIQUE,
    student_id    UUID NOT NULL REFERENCES students (id) ON DELETE CASCADE,
    session_id    UUID NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    caterer_id    UUID NOT NULL REFERENCES caterers (id) ON DELETE CASCADE,
    rating        INTEGER CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    session_date  DATE NOT NULL
);

CREATE TABLE weekly_orders (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_code  TEXT UNIQUE,
    caterer_id  UUID NOT NULL REFERENCES caterers (id),
    week_start  DATE NOT NULL,
    total_meals INTEGER,
    total_cost  NUMERIC(10, 2),
    notes       TEXT
);

CREATE TABLE orders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_code      TEXT,
    weekly_order_id UUID NOT NULL REFERENCES weekly_orders (id) ON DELETE CASCADE,
    menu_item_id    UUID NOT NULL REFERENCES menu_items (id),
    session_id      UUID NOT NULL REFERENCES sessions (id),
    date            DATE NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0)
);

-- caterer_switch_proposals is defined before scheduled_emails so the FK
-- on scheduled_emails.caterer_switch_proposal_id can reference it.
CREATE TABLE caterer_switch_proposals (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_code        TEXT UNIQUE,
    session_id           UUID NOT NULL REFERENCES sessions (id),
    outgoing_caterer_id  UUID NOT NULL REFERENCES caterers (id),
    incoming_caterer_id  UUID NOT NULL REFERENCES caterers (id),
    avg_rating           NUMERIC(3, 2),
    sessions_sampled     INTEGER,
    unique_raters        INTEGER,
    proposed_on          DATE,
    effective_week       DATE,
    status               TEXT NOT NULL DEFAULT 'Pending'
                         CHECK (status IN ('Pending', 'Approved', 'Rejected', 'Executed')),
    notes                TEXT
);

CREATE TABLE scheduled_emails (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_code                  TEXT UNIQUE,
    to_address                  TEXT NOT NULL,
    cc_address                  TEXT,
    subject                     TEXT NOT NULL,
    body                        TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'Queued'
                                CHECK (status IN ('Queued', 'Send Immediately', 'Sent', 'Failed')),
    weekly_order_id             UUID REFERENCES weekly_orders (id),
    caterer_switch_proposal_id  UUID REFERENCES caterer_switch_proposals (id),
    send_date                   DATE,
    sent_at                     TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Junction Tables
-- ---------------------------------------------------------------------------

CREATE TABLE student_sessions (
    student_id  UUID REFERENCES students (id) ON DELETE CASCADE,
    session_id  UUID REFERENCES sessions (id) ON DELETE CASCADE,
    PRIMARY KEY (student_id, session_id)
);

CREATE TABLE student_dietary_restrictions (
    student_id     UUID REFERENCES students (id) ON DELETE CASCADE,
    restriction_id UUID REFERENCES dietary_restrictions (id) ON DELETE CASCADE,
    PRIMARY KEY (student_id, restriction_id)
);

CREATE TABLE menu_item_dietary_tags (
    menu_item_id   UUID REFERENCES menu_items (id) ON DELETE CASCADE,
    restriction_id UUID REFERENCES dietary_restrictions (id) ON DELETE CASCADE,
    PRIMARY KEY (menu_item_id, restriction_id)
);

-- Self-referential: a restriction's supersets (e.g. "Vegan" is a superset of "Vegetarian")
CREATE TABLE dietary_restriction_supersets (
    restriction_id UUID REFERENCES dietary_restrictions (id) ON DELETE CASCADE,
    superset_id    UUID REFERENCES dietary_restrictions (id) ON DELETE CASCADE,
    PRIMARY KEY (restriction_id, superset_id)
);

-- Schools a caterer is able to serve
CREATE TABLE caterer_schools (
    caterer_id UUID REFERENCES caterers (id) ON DELETE CASCADE,
    school_id  UUID REFERENCES schools (id) ON DELETE CASCADE,
    PRIMARY KEY (caterer_id, school_id)
);

-- Caterer dietary legend tags
CREATE TABLE caterer_legend_tags (
    caterer_id     UUID REFERENCES caterers (id) ON DELETE CASCADE,
    restriction_id UUID REFERENCES dietary_restrictions (id) ON DELETE CASCADE,
    PRIMARY KEY (caterer_id, restriction_id)
);

-- Individual student assignments within an order (replaces Airtable multi-link quantity hack)
CREATE TABLE order_students (
    order_id   UUID REFERENCES orders (id) ON DELETE CASCADE,
    student_id UUID REFERENCES students (id) ON DELETE CASCADE,
    PRIMARY KEY (order_id, student_id)
);

-- Multi-value year-levels on sessions and exclusions
CREATE TABLE session_year_levels (
    session_id UUID REFERENCES sessions (id) ON DELETE CASCADE,
    year_level TEXT NOT NULL,
    PRIMARY KEY (session_id, year_level)
);

CREATE TABLE exclusion_year_levels (
    exclusion_id UUID REFERENCES exclusions (id) ON DELETE CASCADE,
    year_level   TEXT NOT NULL,
    PRIMARY KEY (exclusion_id, year_level)
);

-- ---------------------------------------------------------------------------
-- Indexes (query-pattern-driven)
-- ---------------------------------------------------------------------------

CREATE INDEX idx_sessions_caterer           ON sessions (caterer_id);
CREATE INDEX idx_sessions_school            ON sessions (school_id);
CREATE INDEX idx_sessions_manager           ON sessions (on_site_manager_id);
CREATE INDEX idx_menu_items_caterer         ON menu_items (caterer_id);
CREATE INDEX idx_orders_date_session        ON orders (date, session_id);
CREATE INDEX idx_orders_weekly_order        ON orders (weekly_order_id);
CREATE INDEX idx_order_students_student     ON order_students (student_id);
CREATE INDEX idx_student_sessions_session   ON student_sessions (session_id);
CREATE INDEX idx_absences_date              ON absences (date);
CREATE INDEX idx_absences_student           ON absences (student_id);
CREATE INDEX idx_exclusions_date            ON exclusions (date);
CREATE INDEX idx_caterer_feedback_lookup    ON caterer_feedback (student_id, caterer_id);
CREATE INDEX idx_caterer_feedback_session   ON caterer_feedback (session_id);
CREATE INDEX idx_manager_subs_session_date  ON manager_substitutions (session_id, date);
CREATE INDEX idx_weekly_orders_week         ON weekly_orders (week_start);
CREATE INDEX idx_proposals_status           ON caterer_switch_proposals (status);
CREATE INDEX idx_scheduled_emails_status    ON scheduled_emails (status);

-- ---------------------------------------------------------------------------
-- Views (for Python backend — aggregate junction rows into UUID arrays)
-- ---------------------------------------------------------------------------

CREATE VIEW students_view AS
SELECT
    s.*,
    COALESCE(
        ARRAY_AGG(DISTINCT sdr.restriction_id) FILTER (WHERE sdr.restriction_id IS NOT NULL),
        '{}'::uuid[]
    ) AS dietary_requirement_ids,
    COALESCE(
        ARRAY_AGG(DISTINCT ss.session_id) FILTER (WHERE ss.session_id IS NOT NULL),
        '{}'::uuid[]
    ) AS session_ids
FROM students s
LEFT JOIN student_dietary_restrictions sdr ON s.id = sdr.student_id
LEFT JOIN student_sessions ss ON s.id = ss.student_id
GROUP BY s.id;

CREATE VIEW sessions_view AS
SELECT
    s.*,
    COALESCE(
        ARRAY_AGG(DISTINCT syl.year_level) FILTER (WHERE syl.year_level IS NOT NULL),
        '{}'::text[]
    ) AS year_levels
FROM sessions s
LEFT JOIN session_year_levels syl ON s.id = syl.session_id
GROUP BY s.id;

CREATE VIEW caterers_view AS
SELECT
    c.*,
    COALESCE(
        ARRAY_AGG(DISTINCT clt.restriction_id) FILTER (WHERE clt.restriction_id IS NOT NULL),
        '{}'::uuid[]
    ) AS legend_tag_ids,
    COALESCE(
        ARRAY_AGG(DISTINCT cs.school_id) FILTER (WHERE cs.school_id IS NOT NULL),
        '{}'::uuid[]
    ) AS able_to_serve_school_ids
FROM caterers c
LEFT JOIN caterer_legend_tags clt ON c.id = clt.caterer_id
LEFT JOIN caterer_schools cs ON c.id = cs.caterer_id
GROUP BY c.id;

CREATE VIEW menu_items_view AS
SELECT
    m.*,
    COALESCE(
        ARRAY_AGG(DISTINCT mdt.restriction_id) FILTER (WHERE mdt.restriction_id IS NOT NULL),
        '{}'::uuid[]
    ) AS dietary_tag_ids
FROM menu_items m
LEFT JOIN menu_item_dietary_tags mdt ON m.id = mdt.menu_item_id
GROUP BY m.id;

CREATE VIEW dietary_restrictions_view AS
SELECT
    dr.*,
    COALESCE(
        ARRAY_AGG(DISTINCT drs.superset_id) FILTER (WHERE drs.superset_id IS NOT NULL),
        '{}'::uuid[]
    ) AS superset_ids,
    COALESCE(
        ARRAY_AGG(DISTINCT drs2.restriction_id) FILTER (WHERE drs2.restriction_id IS NOT NULL),
        '{}'::uuid[]
    ) AS subset_ids
FROM dietary_restrictions dr
LEFT JOIN dietary_restriction_supersets drs  ON dr.id = drs.restriction_id
LEFT JOIN dietary_restriction_supersets drs2 ON dr.id = drs2.superset_id
GROUP BY dr.id;

CREATE VIEW orders_view AS
SELECT
    o.*,
    COALESCE(
        ARRAY_AGG(DISTINCT os.student_id) FILTER (WHERE os.student_id IS NOT NULL),
        '{}'::uuid[]
    ) AS student_ids
FROM orders o
LEFT JOIN order_students os ON o.id = os.order_id
GROUP BY o.id;

CREATE VIEW exclusions_view AS
SELECT
    e.*,
    COALESCE(
        ARRAY_AGG(DISTINCT eyl.year_level) FILTER (WHERE eyl.year_level IS NOT NULL),
        '{}'::text[]
    ) AS year_levels
FROM exclusions e
LEFT JOIN exclusion_year_levels eyl ON e.id = eyl.exclusion_id
GROUP BY e.id;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE schools                       ENABLE ROW LEVEL SECURITY;
ALTER TABLE on_site_managers              ENABLE ROW LEVEL SECURITY;
ALTER TABLE caterers                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE dietary_restrictions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_items                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE students                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE manager_substitutions         ENABLE ROW LEVEL SECURITY;
ALTER TABLE absences                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE exclusions                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE caterer_feedback              ENABLE ROW LEVEL SECURITY;
ALTER TABLE weekly_orders                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders                        ENABLE ROW LEVEL SECURITY;
ALTER TABLE caterer_switch_proposals      ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_emails              ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_sessions              ENABLE ROW LEVEL SECURITY;
ALTER TABLE student_dietary_restrictions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_item_dietary_tags        ENABLE ROW LEVEL SECURITY;
ALTER TABLE dietary_restriction_supersets ENABLE ROW LEVEL SECURITY;
ALTER TABLE caterer_schools               ENABLE ROW LEVEL SECURITY;
ALTER TABLE caterer_legend_tags           ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_students                ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_year_levels           ENABLE ROW LEVEL SECURITY;
ALTER TABLE exclusion_year_levels         ENABLE ROW LEVEL SECURITY;

-- Public reference data: anon can read
CREATE POLICY "anon_read_schools"
    ON schools FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_on_site_managers"
    ON on_site_managers FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_caterers"
    ON caterers FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_dietary_restrictions"
    ON dietary_restrictions FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_menu_items"
    ON menu_items FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_sessions"
    ON sessions FOR SELECT TO anon USING (true);

-- Junction tables for public reference data: anon can read
CREATE POLICY "anon_read_caterer_legend_tags"
    ON caterer_legend_tags FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_caterer_schools"
    ON caterer_schools FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_menu_item_dietary_tags"
    ON menu_item_dietary_tags FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_dietary_restriction_supersets"
    ON dietary_restriction_supersets FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_session_year_levels"
    ON session_year_levels FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_student_sessions"
    ON student_sessions FOR SELECT TO anon USING (true);

-- Student data: anon can read and write (URL-obscurity security model, same as current Airtable setup)
CREATE POLICY "anon_read_students"
    ON students FOR SELECT TO anon USING (true);
CREATE POLICY "anon_update_students"
    ON students FOR UPDATE TO anon USING (true) WITH CHECK (true);
CREATE POLICY "anon_read_student_dietary"
    ON student_dietary_restrictions FOR SELECT TO anon USING (true);
CREATE POLICY "anon_all_student_dietary"
    ON student_dietary_restrictions FOR ALL TO anon USING (true) WITH CHECK (true);

-- Orders and assignments: anon can read (for ticket lookup) and RPC writes
CREATE POLICY "anon_read_orders"
    ON orders FOR SELECT TO anon USING (true);
CREATE POLICY "anon_read_order_students"
    ON order_students FOR SELECT TO anon USING (true);

-- Caterer feedback: anon can read and write
CREATE POLICY "anon_read_caterer_feedback"
    ON caterer_feedback FOR SELECT TO anon USING (true);
CREATE POLICY "anon_all_caterer_feedback"
    ON caterer_feedback FOR ALL TO anon USING (true) WITH CHECK (true);

-- Switch proposals: anon can read (for switch-proposal.html) and update (reject)
CREATE POLICY "anon_read_caterer_switch_proposals"
    ON caterer_switch_proposals FOR SELECT TO anon USING (true);
CREATE POLICY "anon_update_caterer_switch_proposals"
    ON caterer_switch_proposals FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- weekly_orders, scheduled_emails, absences, exclusions, manager_substitutions,
-- exclusion_year_levels: no anon policies — service_role only (bypasses RLS)

-- ---------------------------------------------------------------------------
-- RPC Function: override_order
-- Atomically moves a student from their current order to a new meal.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION override_order(
    p_student_id       UUID,
    p_session_id       UUID,
    p_new_menu_item_id UUID,
    p_date             DATE DEFAULT CURRENT_DATE
) RETURNS VOID
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_current_order_id UUID;
    v_target_order_id  UUID;
    v_weekly_order_id  UUID;
BEGIN
    -- Find the order this student is currently assigned to today in this session
    SELECT o.id, o.weekly_order_id
    INTO v_current_order_id, v_weekly_order_id
    FROM orders o
    JOIN order_students os ON o.id = os.order_id
    WHERE o.date = p_date
      AND o.session_id = p_session_id
      AND os.student_id = p_student_id
    LIMIT 1;

    IF v_current_order_id IS NULL THEN
        RAISE EXCEPTION 'No order found for student % in session % on %',
            p_student_id, p_session_id, p_date;
    END IF;

    -- Nothing to do if student is already on this meal
    IF EXISTS (
        SELECT 1 FROM orders
        WHERE id = v_current_order_id AND menu_item_id = p_new_menu_item_id
    ) THEN
        RETURN;
    END IF;

    -- Find existing target order for same session/date/menu_item
    SELECT id INTO v_target_order_id
    FROM orders
    WHERE date = p_date
      AND session_id = p_session_id
      AND menu_item_id = p_new_menu_item_id
    LIMIT 1;

    -- Remove student from current order
    DELETE FROM order_students
    WHERE order_id = v_current_order_id AND student_id = p_student_id;

    UPDATE orders SET quantity = quantity - 1 WHERE id = v_current_order_id;

    -- Delete current order if now empty
    DELETE FROM orders WHERE id = v_current_order_id AND quantity <= 0;

    -- Add student to target order (create if needed)
    IF v_target_order_id IS NULL THEN
        INSERT INTO orders (id, weekly_order_id, menu_item_id, session_id, date, quantity, order_code)
        VALUES (
            gen_random_uuid(),
            v_weekly_order_id,
            p_new_menu_item_id,
            p_session_id,
            p_date,
            1,
            'OVR-' || substring(p_student_id::text, 1, 8)
        )
        RETURNING id INTO v_target_order_id;
    ELSE
        UPDATE orders SET quantity = quantity + 1 WHERE id = v_target_order_id;
    END IF;

    INSERT INTO order_students (order_id, student_id)
    VALUES (v_target_order_id, p_student_id);
END;
$$;

-- ---------------------------------------------------------------------------
-- RPC Function: approve_caterer_switch
-- Atomically approves a switch proposal: updates session incoming_caterer_id
-- and clears meal preferences for all enrolled students.
-- ---------------------------------------------------------------------------

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
END;
$$;

-- Allow anon to call both RPC functions (webapp invokes these directly)
GRANT EXECUTE ON FUNCTION override_order(UUID, UUID, UUID, DATE) TO anon;
GRANT EXECUTE ON FUNCTION approve_caterer_switch(UUID) TO anon;
