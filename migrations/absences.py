import re, json
from pathlib import Path
from scripts import support as s
from scripts.support import ask_llm

s.load_env()
s.log.info("Migrating absences.pdf → Airtable")

pdf_path = Path.cwd() / "resources" / "absences.pdf"
txt_path = Path.cwd() / "cache" / "absences.txt"

if not txt_path.is_file():
    from scripts.extract_pdfs import extract_as_text
    extract_as_text(pdf_path, txt_path)

raw = txt_path.read_text(encoding="utf-8")
# Blocks start with "School - DD/MM/YYYY Absences"
blocks = re.split(r"\n\s*\n", raw.strip())

records = []
for blk in blocks:
    header_match = re.search(r"(.+)\s*-\s*(\d{2}/\d{2}/\d{4})\s*Absences", blk, re.I)
    if not header_match:
        s.log.warning("Unrecognised block – flagging for review.")
        continue

    school_name, date_str = header_match.groups()
    # Convert to ISO
    from datetime import datetime

    date_iso = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")

    # Build list of student names (lines after header)
    student_lines = [l.strip() for l in blk.splitlines()[1:] if l.strip()]

    for name in student_lines:
        # Find Student record
        student_match = s.airtable_get(
            "Students", filter_formula=f"{{Student Name}}='{name}'"
        )
        student_id = student_match[0]["id"] if student_match else None

        # Find Session that matches school+date
        session_match = s.airtable_get(
            "Sessions",
            filter_formula=f"AND({{School}}='{school_name}', {{Date}}='{date_iso}')",
        )
        session_id = session_match[0]["id"] if session_match else None

        rec = {
            "fields": {
                "Student": [student_id] if student_id else None,
                "Session": [session_id] if session_id else None,
                "Date": date_iso,
                "Reason": "Absence (reported)",
            }
        }
        records.append(rec)

# Upload
for i in range(0, len(records), 10):
    s.airtable_post("Absences", records[i : i + 10])

s.log.info("Absences migration finished.")
