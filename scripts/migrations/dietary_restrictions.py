from __future__ import annotations

from support import Database, DietaryRestrictionFields, log
from data.dietary_data import ALLERGY_RESTRICTIONS, DIETARY_HIERARCHY, all_restriction_names


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating Dietary Restrictions → Airtable")
    db.DietaryRestrictions.clear()

    # Pass 1: create every restriction with just its name + Is Allergy flag so
    # every record exists before we try to link Supersets in pass 2.
    names = all_restriction_names()
    log.info(f"Creating {len(names)} Dietary Restriction records...")
    seed_records: list[DietaryRestrictionFields] = [
        {"Restriction Name": n, "Is Allergy": n in ALLERGY_RESTRICTIONS}
        for n in names
    ]
    db.DietaryRestrictions.create(seed_records)

    # Pass 2: build name → id map, then patch the Supersets self-links.
    records = db.DietaryRestrictions.all()
    name_to_id: dict[str, str] = {
        r.fields["Restriction Name"]: r.id
        for r in records
        if "Restriction Name" in r.fields
    }

    updates: list[dict[str, object]] = []
    for name, supersets in DIETARY_HIERARCHY:
        if not supersets:
            continue
        rec_id = name_to_id.get(name)
        if not rec_id:
            log.warning(f"Dietary restriction '{name}' missing after creation — skipping links.")
            continue
        super_ids = [name_to_id[sn] for sn in supersets if sn in name_to_id]
        if super_ids:
            updates.append({"id": rec_id, "fields": {"Supersets": super_ids}})

    if updates:
        log.info(f"Linking Supersets on {len(updates)} restrictions...")
        db.DietaryRestrictions.batch_update(updates)

    log.info("Dietary Restrictions migration completed successfully.")


if __name__ == "__main__":
    run()
