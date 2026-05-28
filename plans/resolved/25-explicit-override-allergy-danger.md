# Problem: Explicit Override of Medical Allergies is a Liability

## Context
In both the frontend webapp and the backend ordering engine, a student's explicit `Meal Preference` is honored even if it violates their declared dietary requirements. A warning modal is shown to the student in the webapp, but after a simple confirmation click, they are permitted to place the order anyway. The backend logs a warning but proceeds with the order.

## Problem Description
While this leniency makes sense for *lifestyle preferences* (e.g., a Vegetarian student choosing to eat a beef dish once in a while), it is a major health and legal hazard for *medical restrictions* (e.g., anaphylactic Nut Free, or Celiac/Gluten Free). 

High school students are minors. If a student with a severe peanut allergy makes a mistake, is dared by a classmate, or has their name selected as a prank, the system will programmatically order and deliver a box labeled with their name containing that allergen. 

In a school environment, minors cannot legally override parental-approved medical dietary restrictions.

## Proposed Solution (AI Actionable)
We need to split the dietary taxonomy into **Medical Allergies** and **Lifestyle Preferences**:

1. **Update Data Schema:**
   Add a boolean field `Is Allergy` to the `Dietary Restrictions` table in Airtable (and update `data/schema.py`). Ensure `Nut Free`, `Gluten Free`, (and others marked as medical) have `Is Allergy = True`.

2. **Webapp Implementation (`webapp/app.js`):**
   - If a menu item is incompatible with a student's restriction and that restriction is a **Lifestyle Preference** (`Is Allergy = False`): Keep the current behavior (show a warning confirm modal, allow selection on confirmation).
   - If a menu item is incompatible with a student's restriction and that restriction is a **Medical Allergy** (`Is Allergy = True`): **Hard block** the choice. Disable the button in the UI, mark it in red, and show a message: *"Option disabled due to registered allergy. Talk to the on-site manager for manual overrides."*

3. **Backend Ordering Implementation (`scripts/support/compatibility.py` and `register_orders.py`):**
   - In `is_item_compatible`, if the compatibility check fails due to an `Is Allergy = True` restriction, do **not** honor the student's explicit override. Force-swap them to a compatible item (just as you would if they had no preference) and flag a severe warning to the administrator.
