import os
import sys
import re
from pathlib import Path

# Add repository root to system path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts import support as s

s.log.info("Migrating absences.pdf → Airtable")

# Clear Absences table
s.clear_table("Absences")

# Read extracted text
txt_path = Path(__file__).parent.parent / "cache" / "absences.txt"
if not txt_path.is_file():
    s.log.error(f"Extracted absences text not found at {txt_path}. Please run PDF extraction first.")
    sys.exit(1)

raw_text = txt_path.read_text(encoding="utf-8")

# Parse date helper
def parse_date(date_str):
    parts = date_str.split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str

# Parse raw text blocks
blocks = re.split(r"\n\s*\n", raw_text.strip())
parsed_absences = []

for blk in blocks:
    lines = [l.strip() for l in blk.splitlines() if l.strip()]
    if not lines:
        continue
    
    header = lines[0]
    # Header format: Moreton Bay Boys' College - 02/05/2026 Absences
    match = re.match(r"^([^-]+)-\s*([\d/]+)\s*Absences", header)
    if not match:
        s.log.warning(f"Could not parse absence header line: '{header}'")
        continue

    school_name = match.group(1).strip()
    raw_date = match.group(2).strip()
    session_date = parse_date(raw_date)

    for student_name in lines[1:]:
        if student_name.lower() == "nan" or not student_name:
            continue
        parsed_absences.append({
            "school_name": school_name,
            "date": session_date,
            "student_name": student_name
        })

s.log.info(f"Parsed {len(parsed_absences)} student absences from PDF.")

# Fetch Student & Session mapping
students_list = s.airtable_get("Students")
student_name_to_id = {rec["fields"]["Student Name"]: rec["id"] for rec in students_list}

sessions_list = s.airtable_get("Sessions")
session_id_to_rec_id = {rec["fields"]["Session ID"]: rec["id"] for rec in sessions_list}

records = []
for abs_data in parsed_absences:
    s_name = abs_data["student_name"]
    s_id = student_name_to_id.get(s_name)
    if not s_id:
        s.log.warning(f"Student '{s_name}' absent at {abs_data['school_name']} but not found in Students table. Skipping.")
        continue

    # Construct the Session ID: School Name - Date
    session_id = f"{abs_data['school_name']} - {abs_data['date']}"
    sess_rec_id = session_id_to_rec_id.get(session_id)
    if not sess_rec_id:
        s.log.warning(f"Session '{session_id}' not found in Sessions table for absence of '{s_name}'. Skipping.")
        continue

    records.append({
        "Absence ID": f"{s_name} - {session_id}",
        "Student": [s_id],
        "Session": [sess_rec_id],
        "Date": abs_data["date"],
        "Reason": "Absent"
    })

if records:
    s.log.info(f"Migrating {len(records)} Absences records...")
    s.airtable_post("Absences", records)
    s.log.info("Absences migration completed successfully.")
else:
    s.log.info("No valid absence records to migrate.")
