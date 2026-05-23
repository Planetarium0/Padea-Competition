# scripts/migrate_students.py
import pandas as pd
from pathlib import Path
from scripts import support as s
from scripts.support import ask_llm
import json

s.load_env()
s.log.info("Migrating students.xlsx → Airtable")

xlsx_path = Path.cwd() / "resources" / "students.xlsx"
# There are many sheets – we iterate over all of them
sheets = pd.read_excel(xlsx_path, sheet_name=None)

def map_dietary(raw):
    """Ask Claude to map raw dietary strings to Airtable multi‑select options."""
    prompt = f"""You are an AI that knows the Padea dietary taxonomy (Gluten Free, Dairy Free, Nut Free, Vegetarian, Halal, etc.). 
Given this raw string from the Excel sheet, output a JSON array of the appropriate tags. 
If you cannot determine a tag, omit it.

Raw string: `{raw}`
"""
    resp = ask_llm(prompt)
    if resp is NotImplemented:
        s.log.warning("LLM not configured – returning empty list for dietary.")
        return []
    try:
        return json.loads(resp)
    except json.JSONDecodeError:
        s.log.error("LLM returned malformed JSON for dietary mapping.")
        return []

records = []
for sheet_name, df in sheets.items():
    # Basic sanity: required columns
    required = ["Student", "Year Level", "Subjects", "Dietary", "Student Email"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        s.log.warning("Sheet %s missing columns %s – skipping.", sheet_name, missing)
        continue

    for _, row in df.iterrows():
        student_name = str(row["Student"]).strip()
        # Link to Session – we assume the sheet name contains the session identifier
        session_match = s.airtable_get(
            "Sessions", filter_formula=f"{{Session Name}}='{sheet_name}'"
        )
        session_id = session_match[0]["id"] if session_match else None

        rec = {
            "fields": {
                "Student Name": student_name,
                "Year Level": int(row["Year Level"]) if pd.notna(row["Year Level"]) else None,
                "Subjects": str(row["Subjects"]).strip(),
                "Dietary Requirements": map_dietary(str(row["Dietary"])),
                "Student Email": str(row["Student Email"]).strip(),
                "Session": [session_id] if session_id else None,
            }
        }
        records.append(rec)

# Upload
for i in range(0, len(records), 10):
    s.airtable_post("Students", records[i : i + 10])

s.log.info("Students migration completed.")
