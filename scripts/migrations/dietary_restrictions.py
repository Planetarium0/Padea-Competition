"""
Seed the Dietary Restrictions table from `scripts/dietary_data.py`.

This MUST run before `students.py` and `caterer_menus.py`, because both rely
on the name → record-id map for their linked-record dietary fields.
"""
import support as s
from data.dietary_data import DIETARY_HIERARCHY, all_restriction_names


s.log.info("Migrating Dietary Restrictions → Airtable")

s.clear_table("Dietary Restrictions")

# Pass 1: create every restriction with just its name. This guarantees every
# name we need to link to in pass 2 already exists.
names = all_restriction_names()
s.log.info(f"Creating {len(names)} Dietary Restriction records...")
s.airtable_post(
    "Dietary Restrictions",
    [{"Restriction Name": n} for n in names],
)

# Pass 2: build name → id map, then patch the Supersets links.
records = s.airtable_get("Dietary Restrictions")
name_to_id = {r["fields"]["Restriction Name"]: r["id"] for r in records}

updates = []
for name, supersets in DIETARY_HIERARCHY:
    if not supersets:
        continue
    rec_id = name_to_id.get(name)
    if not rec_id:
        s.log.warning(f"Dietary restriction '{name}' missing after creation — skipping links.")
        continue
    super_ids = [name_to_id[s_name] for s_name in supersets if s_name in name_to_id]
    if not super_ids:
        continue
    updates.append({"id": rec_id, "fields": {"Supersets": super_ids}})

if updates:
    s.log.info(f"Linking Supersets on {len(updates)} restrictions...")
    s.get_table("Dietary Restrictions").batch_update(updates)

s.log.info("Dietary Restrictions migration completed successfully.")
