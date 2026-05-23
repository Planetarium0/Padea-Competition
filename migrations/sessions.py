import pandas as pd
from pathlib import Path
from scripts import support as s

s.load_env()
s.log.info("Migrating sessions.xlsx → Airtable")

xlsx_path = Path.cwd() / "resources" / "sessions.xlsx"
df = pd.read_excel(xlsx_path, sheet_name="sessions")

# ---- Validation -------------------------------------------------
expected = [
    "school",
    "region",
    "caterer",
    "date",
    "day",
    "manager",
    "manager-mobile",
    "start-time",
    "end-time",
    "dinner-time",
    "year-levels",
    "Building",
]
missing = [c for c in expected if c not in df.columns]
if missing:
    raise ValueError(f"Missing columns in sessions.xlsx: {missing}")

def excel_date_to_iso(num):
    """Convert Excel serial date (1900 system) to YYYY‑MM‑DD."""
    from datetime import datetime, timedelta

    epoch = datetime(1899, 12, 30)
    return (epoch + timedelta(days=int(num))).strftime("%Y-%m-%d")

records = []
for _, row in df.iterrows():
    school_name = str(row["school"]).strip()
    school_match = s.airtable_get(
        "Schools", filter_formula=f"{{School Name}}='{school_name}'"
    )
    school_id = school_match[0]["id"] if school_match else None

    caterer_name = str(row["caterer"]).strip()
    caterer_match = s.airtable_get(
        "Caterers", filter_formula=f"{{Caterer Name}}='{caterer_name}'"
    )
    caterer_id = caterer_match[0]["id"] if caterer_match else None

    manager_name = str(row["manager"]).strip()
    manager_match = s.airtable_get(
        "On‑Site Managers",
        filter_formula=f"{{Manager Name}}='{manager_name}'",
    )
    manager_id = manager_match[0]["id"] if manager_match else None

    rec = {
        "fields": {
            "School": [school_id] if school_id else None,
            "Region": str(row["region"]).strip(),
            "Caterer": [caterer_id] if caterer_id else None,
            "Date": excel_date_to_iso(row["date"]),
            "Day": str(row["day"]).strip(),
            "On‑Site Manager": [manager_id] if manager_id else None,
            "Start Time": str(row["start-time"]).strip(),
            "End Time": str(row["end-time"]).strip(),
            "Dinner Time": str(row["dinner-time"]).strip(),
            "Year Levels": str(row["year-levels"]).strip(),
            "Building": str(row["Building"]).strip(),
        }
    }
    records.append(rec)

# Batch upload (10 per request)
for i in range(0, len(records), 10):
    s.airtable_post("Sessions", records[i : i + 10])

s.log.info("Sessions migration completed.")
