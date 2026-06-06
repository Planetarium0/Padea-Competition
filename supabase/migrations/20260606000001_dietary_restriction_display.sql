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
