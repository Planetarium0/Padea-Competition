-- =============================================================================
-- menu_item_unavailable_days: day-specific menu availability.
-- Tracks which weekdays a given menu item cannot be ordered.
-- =============================================================================

CREATE TABLE menu_item_unavailable_days (
    menu_item_id UUID REFERENCES menu_items (id) ON DELETE CASCADE,
    day          TEXT NOT NULL CHECK (day IN ('Monday','Tuesday','Wednesday','Thursday','Friday')),
    PRIMARY KEY  (menu_item_id, day)
);

ALTER TABLE menu_item_unavailable_days ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anon_read_menu_item_unavailable_days"
    ON menu_item_unavailable_days FOR SELECT TO anon USING (true);

-- ---------------------------------------------------------------------------
-- Recreate menu_items_view to include unavailable_days as an aggregated array.
-- Must DROP first — Postgres does not allow CREATE OR REPLACE when the column
-- list changes.
-- ---------------------------------------------------------------------------

DROP VIEW menu_items_view;

CREATE VIEW menu_items_view AS
SELECT
    m.*,
    COALESCE(
        ARRAY_AGG(DISTINCT mdt.restriction_id) FILTER (WHERE mdt.restriction_id IS NOT NULL),
        '{}'::uuid[]
    ) AS dietary_tag_ids,
    COALESCE(
        ARRAY_AGG(DISTINCT mid.day) FILTER (WHERE mid.day IS NOT NULL),
        '{}'::text[]
    ) AS unavailable_days
FROM menu_items m
LEFT JOIN menu_item_dietary_tags     mdt ON m.id = mdt.menu_item_id
LEFT JOIN menu_item_unavailable_days mid ON m.id = mid.menu_item_id
GROUP BY m.id;

-- ---------------------------------------------------------------------------
-- Seed Big Chicken's day-specific restrictions.
-- ---------------------------------------------------------------------------

INSERT INTO menu_item_unavailable_days (menu_item_id, day)
SELECT id, 'Tuesday' FROM menu_items WHERE name = 'Crispy Chicken Taco'
UNION ALL
SELECT id, 'Monday'  FROM menu_items WHERE name = 'Cali Burrito';
