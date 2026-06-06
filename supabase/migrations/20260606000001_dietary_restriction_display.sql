-- Add display fields to dietary_restrictions so agents can populate them
-- when creating new restrictions, and the webapp can read them from the DB
-- instead of relying on hard-coded JS constants.

ALTER TABLE dietary_restrictions
    ADD COLUMN tag_short         TEXT,
    ADD COLUMN constraint_phrase TEXT;

UPDATE dietary_restrictions SET
    tag_short = CASE name
        WHEN 'Gluten Free'  THEN 'GF'
        WHEN 'Dairy Free'   THEN 'DF'
        WHEN 'Nut Free'     THEN 'NF'
        WHEN 'Vegetarian'   THEN 'Veg'
        WHEN 'Vegan'        THEN 'Vegan'
        WHEN 'Halal'        THEN 'Halal'
        WHEN 'Kosher'       THEN 'Kosher'
        WHEN 'Pescatarian'  THEN 'Pesc'
        ELSE NULL
    END,
    constraint_phrase = CASE name
        WHEN 'Gluten Free'   THEN 'gluten'
        WHEN 'Dairy Free'    THEN 'dairy'
        WHEN 'Nut Free'      THEN 'nuts'
        WHEN 'Vegetarian'    THEN 'meat'
        WHEN 'Vegan'         THEN 'animal products'
        WHEN 'Pescatarian'   THEN 'non-fish meat'
        WHEN 'Halal'         THEN 'non-halal ingredients'
        WHEN 'Kosher'        THEN 'non-kosher ingredients'
        WHEN 'No Beef'       THEN 'beef'
        WHEN 'No Pork'       THEN 'pork'
        WHEN 'No Lamb'       THEN 'lamb'
        WHEN 'No Fish'       THEN 'fish'
        WHEN 'No Shellfish'  THEN 'shellfish'
        WHEN 'No Seafood'    THEN 'seafood'
        WHEN 'No Red Meat'   THEN 'red meat'
        ELSE NULL
    END;

-- Recreate view to expose the new columns (PostgreSQL freezes SELECT * at
-- view creation time, so adding columns to the base table requires a
-- DROP + CREATE to include them).
DROP VIEW dietary_restrictions_view;

CREATE VIEW dietary_restrictions_view AS
SELECT
    dr.id,
    dr.name,
    dr.tag_short,
    dr.constraint_phrase,
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
