#!/usr/bin/env python3
"""
Schema‑update script for the Padea Airtable base.

- Adds the new fields described in the implementation plan.
- Creates the `Exclusions` table.
- Writes a `schema_map.json` file that maps logical names → Airtable field IDs.
"""

import os
import json
import urllib.request
import time
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()


BASE_ID = "appTaP4DLPhZJICMH"  # Padea Catering Management
API_KEY = os.getenv("AIRTABLE_API_KEY")
if not API_KEY:
    raise RuntimeError("AIRTABLE_API_KEY not set in environment")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# Mapping of logical table names → Airtable table IDs (taken from earlier `list_tables.py` output)
TABLE_IDS = {
    "Caterers": "tblABs6GX6iGaK9pC",
    "Schools": "tblfqWHfqIGKKaFlD",
    "Sessions": "tbl6tZRKlxMfZnTcP",
    "Students": "tblV6R8bJVai1mX5Q",
}

# Helper to POST a new field
def create_field(table_id: str, field_body: dict) -> dict:
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{table_id}/fields"
    data = json.dumps(field_body).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 422:
            # Likely the field already exists – fetch its definition via GET (optional) or just warn
            print(f"[WARN] Field `{field_body.get('name')}` may already exist in table {table_id}. Skipping.")
            return {}
        else:
            raise

# Helper to POST a new table
def create_table(table_body: dict) -> dict:
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    data = json.dumps(table_body).encode()
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print(f"[WARN] Table `{table_body.get('name')}` may already exist. Skipping.")
            return {}
        else:
            raise

# -------------------------------------------------------------------------
# Field definitions per table (matches the Implementation Plan)

NEW_FIELDS = {
    "Caterers": [
        {
            "name": "Region",
            "type": "singleLineText",
            "description": "Geographic region where the caterer operates",
        },
        {
            "name": "Min Qty 4 Items",
            "type": "number",
            "description": "Minimum order quantity for 4 menu items",
        },
        {
            "name": "Min Qty 5 Items",
            "type": "number",
            "description": "Minimum order quantity for 5 menu items",
        },
        {
            "name": "Min Qty 6 Items",
            "type": "number",
            "description": "Minimum order quantity for 6 menu items",
        },
        {
            "name": "Delivery Fee",
            "type": "currency",
            "description": "Flat delivery fee for the caterer",
        },
        {
            "name": "Delivery Fee Type",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "Per school per trip"},
                    {"name": "Per trip"},
                    {"name": "Free"},
                ]
            },
            "description": "How the delivery fee is applied",
        },
        {
            "name": "Tax Treatment",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "Including GST"},
                    {"name": "Excluding GST"},
                ]
            },
            "description": "Whether the listed price includes GST",
        },
        {
            "name": "Chef Name",
            "type": "singleLineText",
            "description": "Name of the chef contact",
        },
        {
            "name": "Chef Email",
            "type": "email",
            "description": "Email of the chef contact",
        },
        {
            "name": "Able to Serve Schools",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": TABLE_IDS["Schools"]},
            "description": "Schools the caterer is eligible to serve",
        },
    ],
    "Schools": [
        {"name": "Region", "type": "singleLineText", "description": "Region of the school"},
    ],
    "Sessions": [
        {"name": "Dinner Time", "type": "singleLineText", "description": "Scheduled dinner break"},
        {"name": "Building", "type": "singleLineText", "description": "Building/room for the session"},
        {"name": "Year Levels", "type": "singleLineText", "description": "Comma‑separated list of year levels"},
    ],
    "Students": [
        {"name": "Student Email", "type": "email", "description": "Student's email address"},
        {"name": "Year Level", "type": "number", "description": "Year level of the student"},
        {"name": "Subjects", "type": "singleLineText", "description": "Tutoring subjects"},
    ],
}

# -------------------------------------------------------------------------
# Create Exclusions table (new)

EXCLUSIONS_TABLE = {
    "name": "Exclusions",
    "description": "Calendar cancellations and partial exclusions",
    "primaryField": {"name": "Exclusion ID", "type": "autoNumber"},
    "fields": [
        {
            "name": "School",
            "type": "multipleRecordLinks",
            "options": {"linkedTableId": TABLE_IDS["Schools"]},
        },
        {"name": "Date", "type": "date"},
        {"name": "Affected Year Levels", "type": "singleLineText"},
        {"name": "Reason", "type": "singleLineText"},
    ],
}

# -------------------------------------------------------------------------
# Execution

def main():
    schema_map = {}

    # 1️⃣ Add new fields to existing tables
    for table_name, fields in NEW_FIELDS.items():
        table_id = TABLE_IDS[table_name]
        schema_map[table_name] = {}
        print(f"--- Updating {table_name} ({table_id}) ---")
        for field in fields:
            result = create_field(table_id, field)
            if result:
                field_id = result["id"]
                schema_map[table_name][field["name"]] = field_id
                print(f"Created field {field['name']} → {field_id}")
            else:
                print(f"[INFO] Field {field['name']} not created (may already exist)")
            time.sleep(0.5)  # gentle rate‑limit

    # 2️⃣ Create Exclusions table
    print("\n--- Creating Exclusions table ---")
    excl_result = create_table(EXCLUSIONS_TABLE)
    if excl_result:               # table was just created
        excl_table_id = excl_result["id"]
        schema_map["Exclusions"] = {"table_id": excl_table_id}
        # Add its fields to the map (place‑holder names – actual IDs will be fetched later if needed)
        for fld in EXCLUSIONS_TABLE["fields"]:
            schema_map["Exclusions"][fld["name"]] = fld["name"]
    else:
        # Table already existed – fetch its ID via a simple GET request
        url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
        req = urllib.request.Request(url, headers=HEADERS, method="GET")
        with urllib.request.urlopen(req) as resp:
            tables = json.load(resp)["tables"]
            excl_table_id = next((t["id"] for t in tables if t["name"] == EXCLUSIONS_TABLE["name"]), None)
        if excl_table_id:
            schema_map["Exclusions"] = {"table_id": excl_table_id}
        else:
            print("[WARN] Exclusions table not found after GET; proceeding without ID.")
            schema_map["Exclusions"] = {"table_id": None}


    # 3️⃣ Persist the mapping for later scripts
    out_path = os.path.join(os.path.dirname(__file__), "schema_map.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(schema_map, f, indent=2)
    print(f"\nSchema map written to {out_path}")

if __name__ == "__main__":
    main()
