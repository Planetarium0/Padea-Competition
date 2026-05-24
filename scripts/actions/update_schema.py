import sys

from support import base, log
from data.schema import TABLES_SCHEMA

# The personal access token used to push schema changes can rename but not
# delete tables/fields. Anything in Airtable that's no longer in TABLES_SCHEMA
# is renamed with this prefix so a human can delete it from the Airtable UI.
DELETED_PREFIX = "(deleted) "


def update_schema():
    if not base:
        log.error("Airtable Base not configured. Exiting.")
        sys.exit(1)

    log.info("Starting schema update process (idempotent mode)...")

    # 1. Fetch existing tables
    try:
        existing_tables_list = base.tables()
        existing_tables = {t.name: t for t in existing_tables_list}
        table_ids = {t.name: t.id for t in existing_tables_list}
        log.info(f"Existing tables in base: {list(existing_tables.keys())}")
    except Exception as e:
        log.error(f"Error fetching existing tables: {e}")
        sys.exit(1)

    # 2. Create missing tables with primary key
    table_mappings = {}  # table_name -> Table object

    for table_name, spec in TABLES_SCHEMA.items():
        primary_field = spec["primary"]
        
        if table_name in existing_tables:
            log.info(f"Table '{table_name}' already exists. Reusing it.")
            tbl = existing_tables[table_name]
            table_mappings[table_name] = tbl
            table_ids[table_name] = tbl.id
        else:
            log.info(f"Creating table '{table_name}' with primary key '{primary_field['name']}'...")
            try:
                tbl = base.create_table(
                    name=table_name,
                    fields=[{
                        "name": primary_field["name"],
                        "type": primary_field["type"]
                    }],
                    description=f"Table for {table_name} - managed programmatically"
                )
                table_mappings[table_name] = tbl
                table_ids[table_name] = tbl.id
                log.info(f"Created table '{table_name}' with ID: {tbl.id}")
            except Exception as e:
                log.error(f"Failed to create table '{table_name}': {e}")
                sys.exit(1)

    # 3. Add all non-primary fields to the tables if they don't exist
    for table_name, spec in TABLES_SCHEMA.items():
        tbl = table_mappings[table_name]
        log.info(f"Syncing fields for table '{table_name}'...")
        
        # Get existing fields in Airtable
        try:
            # Re-fetch or inspect current fields in this table schema
            tbl_schema = tbl.schema()
            existing_fields = {f.name: f for f in tbl_schema.fields}
        except Exception as e:
            log.error(f"Failed to fetch fields for table '{table_name}': {e}")
            continue

        for field in spec["fields"]:
            name = field["name"]
            field_type = field["type"]
            options = field.get("options", {}).copy()

            if name in existing_fields:
                existing_field = existing_fields[name]
                existing_type = existing_field.type
                if existing_type == field_type:
                    log.info(f"  Field '{name}' already exists. Skipping.")
                    continue

                # Type changed in the spec. Airtable doesn't let us mutate the
                # field's type directly, but we can rename the old field with
                # the (deleted) prefix (non-destructive — data is preserved on
                # the orphan field) and fall through to create a fresh field
                # of the new type.
                new_old_name = DELETED_PREFIX + name
                log.warning(
                    f"  Type mismatch on '{name}': existing='{existing_type}', "
                    f"spec='{field_type}'. Renaming to '{new_old_name}' and "
                    "recreating with the new type."
                )
                try:
                    existing_field.name = new_old_name
                    existing_field.save()
                except Exception as e:
                    log.error(f"  Failed to rename mistyped field '{name}': {e}")
                    continue
                # Fall through to the create-field block below.

            # If it's a relational field, inject the target table ID
            if field_type == "multipleRecordLinks":
                target_table = field["link_target"]
                target_id = table_ids.get(target_table)
                if not target_id:
                    log.error(f"Unknown target table '{target_table}' for relational field '{name}' in table '{table_name}'")
                    continue
                options["linkedTableId"] = target_id

            log.info(f"  Adding field '{name}' (type: {field_type})...")
            try:
                tbl.create_field(
                    name=name,
                    type=field_type,
                    options=options if options else None
                )
            except Exception as e:
                log.error(f"Failed to add field '{name}' to table '{table_name}': {e}")
                continue

    # 4. Apply inverse_name renames on any multipleRecordLinks fields that
    #    declare one (so Airtable's default "From field: …" back-link gets a
    #    proper name).
    apply_inverse_link_names(table_mappings)

    # 5. Mark orphan tables/fields for deletion by prefixing with "(deleted) "
    mark_orphans_for_deletion(table_mappings)

    log.info("Schema update process completed successfully!")


def apply_inverse_link_names(table_mappings):
    """For each spec field that declares `inverse_name`, locate the auto-created
    inverse link field on the target table and rename it. Idempotent."""
    log.info("Applying inverse_name overrides on linked fields...")
    for table_name, spec in TABLES_SCHEMA.items():
        for field in spec["fields"]:
            desired = field.get("inverse_name")
            if not desired or field["type"] != "multipleRecordLinks":
                continue

            owning_tbl = table_mappings[table_name]
            target_tbl = table_mappings.get(field["link_target"])
            if not target_tbl:
                log.warning(f"  Target table '{field['link_target']}' missing; "
                            f"can't apply inverse_name for '{field['name']}'.")
                continue

            # Find the owning field's record on the owning table, then resolve
            # its inverse via options.inverse_link_field_id, then look that ID
            # up on the target table's schema.
            try:
                owning_schema = owning_tbl.schema(force=True)
            except Exception as e:
                log.error(f"  Couldn't refetch schema for '{table_name}': {e}")
                continue
            owning_field = next((f for f in owning_schema.fields if f.name == field["name"]), None)
            if not owning_field:
                continue
            inverse_id = getattr(getattr(owning_field, "options", None),
                                 "inverse_link_field_id", None)
            if not inverse_id:
                continue

            try:
                target_schema = target_tbl.schema(force=True)
            except Exception as e:
                log.error(f"  Couldn't refetch schema for '{field['link_target']}': {e}")
                continue
            inverse_field = next((f for f in target_schema.fields if f.id == inverse_id), None)
            if not inverse_field:
                continue
            if inverse_field.name == desired:
                log.info(f"  Inverse of '{table_name}.{field['name']}' already "
                         f"named '{desired}'. Skipping.")
                continue

            log.info(f"  Renaming inverse of '{table_name}.{field['name']}' "
                     f"from '{inverse_field.name}' to '{desired}'")
            try:
                inverse_field.name = desired
                inverse_field.save()
            except Exception as e:
                log.error(f"  Failed to rename inverse link: {e}")


def mark_orphans_for_deletion(table_mappings):
    """Rename any Airtable table/field that's no longer in TABLES_SCHEMA with
    the DELETED_PREFIX. Skips items already prefixed (idempotent) and skips
    auto-created back-link fields of managed multipleRecordLinks fields."""
    log.info("Scanning for orphan tables/fields to mark for deletion...")

    # Build the set of field IDs we own. A field is "managed" if either:
    #   (a) its name matches a primary or fields[] entry in the spec, OR
    #   (b) it's the auto-created back-link of a managed multipleRecordLinks
    #       field (Airtable creates these on the link's target table; we'd
    #       otherwise mistake them for orphans since they're not in the spec).
    managed_field_ids = set()
    for table_name, spec in TABLES_SCHEMA.items():
        tbl = table_mappings[table_name]
        try:
            tbl_schema = tbl.schema(force=True)
        except Exception as e:
            log.error(f"Failed to refetch schema for '{table_name}': {e}")
            continue

        expected_names = {spec["primary"]["name"]} | {f["name"] for f in spec["fields"]}
        for fs in tbl_schema.fields:
            if fs.name not in expected_names:
                continue
            managed_field_ids.add(fs.id)
            inverse_id = getattr(getattr(fs, "options", None), "inverse_link_field_id", None)
            if inverse_id:
                managed_field_ids.add(inverse_id)

    # Mark orphan TABLES (anything in the base whose name isn't in the spec).
    try:
        all_tables = base.tables(force=True)
    except Exception as e:
        log.error(f"Failed to refetch tables: {e}")
        all_tables = []

    schema_table_names = set(TABLES_SCHEMA.keys())
    for tbl in all_tables:
        if tbl.name in schema_table_names:
            continue
        if tbl.name.startswith(DELETED_PREFIX):
            log.info(f"Table '{tbl.name}' already marked. Skipping.")
            continue
        new_name = DELETED_PREFIX + tbl.name
        log.info(f"Marking table '{tbl.name}' for deletion -> '{new_name}'")
        try:
            ts = tbl.schema(force=True)
            ts.name = new_name
            ts.save()
        except Exception as e:
            log.error(f"Failed to rename table '{tbl.name}': {e}")

    # Mark orphan FIELDS within each managed table.
    for table_name in TABLES_SCHEMA:
        tbl = table_mappings[table_name]
        try:
            tbl_schema = tbl.schema(force=True)
        except Exception as e:
            log.error(f"Failed to refetch schema for '{table_name}': {e}")
            continue

        primary_field_id = tbl_schema.primary_field_id
        for fs in tbl_schema.fields:
            if fs.id in managed_field_ids:
                continue
            if fs.id == primary_field_id:
                # Airtable disallows renaming the primary in a way that breaks
                # the table; leave it for the operator to resolve manually.
                log.warning(f"  Primary field '{fs.name}' on '{table_name}' is not in spec but won't be auto-marked.")
                continue
            if fs.name.startswith(DELETED_PREFIX):
                log.info(f"  Field '{fs.name}' on '{table_name}' already marked. Skipping.")
                continue
            new_name = DELETED_PREFIX + fs.name
            log.info(f"  Marking field '{fs.name}' on '{table_name}' for deletion -> '{new_name}'")
            try:
                fs.name = new_name
                fs.save()
            except Exception as e:
                log.error(f"  Failed to rename field '{fs.name}' on '{table_name}': {e}")

if __name__ == "__main__":
    update_schema()
