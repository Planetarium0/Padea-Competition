import os
import sys
from pathlib import Path

# Add the repository root to sys.path so we can import scripts
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts.support import base, log
from scripts.schema import TABLES_SCHEMA

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
                log.info(f"  Field '{name}' already exists. Skipping.")
                continue

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

    log.info("Schema update process completed successfully!")

if __name__ == "__main__":
    update_schema()
