import os
import sys
import pandas as pd
import json
from pathlib import Path

# Add repository root to system path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts import support as s

s.log.info("Migrating students.xlsx → Airtable")

# Clear students table
s.clear_table("Students")

# Static schools data
SCHOOLS_DATA = [
    "Moreton Bay Boys' College",
    "John Paul College",
    "MacGregor State High School",
    "Indooroopilly State High School",
    "Loreto College",
    "Cannon Hill Anglican College"
]

def resolve_school_name(raw_header):
    parts = raw_header.split("-")
    raw_school = parts[0].strip()
    for std_name in SCHOOLS_DATA:
        if raw_school.lower() in std_name.lower():
            return std_name
    return None

xlsx_path = Path(__file__).parent.parent / "resources" / "students.xlsx"
xls = pd.ExcelFile(xlsx_path)

# 1. Collect all unique dietary requirements from all sheets
unique_dietary = set()
sheet_metadata = {} # sheet_name -> (school_name, day_name)

for name in xls.sheet_names:
    df_meta = pd.read_excel(xlsx_path, sheet_name=name, nrows=1)
    header_text = df_meta.columns[0]
    
    school_name = resolve_school_name(header_text)
    parts = header_text.split("-")
    day_name = parts[-1].strip() if len(parts) > 1 else ""
    
    if not school_name:
        s.log.warning(f"Could not resolve school name for sheet '{name}' (header: '{header_text}')")
        continue

    sheet_metadata[name] = (school_name, day_name)

    # Read sheet data
    df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)
    if "Dietary" in df.columns:
        for val in df["Dietary"].dropna():
            unique_dietary.add(str(val).strip())

s.log.info(f"Collected {len(unique_dietary)} unique dietary requirements strings across all sheets.")

# 2. Load or Build Dietary Mapping Cache
cache_path = Path(__file__).parent.parent / "cache" / "dietary_mappings.json"
cache_path.parent.mkdir(exist_ok=True)
dietary_mappings = {}

if cache_path.is_file():
    try:
        dietary_mappings = json.loads(cache_path.read_text(encoding="utf-8"))
        s.log.info(f"Loaded {len(dietary_mappings)} dietary mappings from cache.")
    except Exception as e:
        s.log.warning(f"Could not read dietary mapping cache: {e}")

# Identify missing mappings
missing_mappings = [d for d in unique_dietary if d not in dietary_mappings]

# Standarized Airtable dietary choices
STANDARD_DIETARY_CHOICES = [
    "Dairy Free", "Gluten Free", "Nut Free", "Vegetarian", "Halal", 
    "No Beef", "No Pork", "No Seafood", "No Shellfish", "No Fish", 
    "No Red Meat", "Opted out of Catering"
]

def map_dietary_heuristically(raw_val):
    cleaned = raw_val.strip()
    if cleaned.lower() == "opted out of catering":
        return ["Opted out of Catering"]
    
    choices = []
    # Split by comma
    parts = [p.strip().lower() for p in cleaned.split(",")]
    for p in parts:
        matched = False
        for std in STANDARD_DIETARY_CHOICES:
            if std.lower() in p:
                choices.append(std)
                matched = True
                break
        if not matched:
            # Special manual heuristic adjustments
            if "no beef" in p:
                choices.append("No Beef")
            elif "no pork" in p:
                choices.append("No Pork")
            elif "no fish" in p:
                choices.append("No Fish")
            elif "no seafood" in p:
                choices.append("No Seafood")
            elif "no shellfish" in p:
                choices.append("No Shellfish")
            elif "no red meat" in p:
                choices.append("No Red Meat")
    return list(set(choices))

if missing_mappings:
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    parsed_mappings = None

    if key:
        s.log.info(f"Prompting Claude LLM to translate {len(missing_mappings)} missing dietary strings...")
        prompt = f"""You are a dietary taxonomy expert.
Map the following list of raw dietary strings to a subset of standard Padea dietary choices.
Standard Choices:
{json.dumps(STANDARD_DIETARY_CHOICES, indent=2)}

Return a JSON object where the keys are the raw strings exactly as provided, and the values are JSON arrays of standard choices. If a string has no matching choice, use an empty array.

Raw Strings to Map:
{json.dumps(missing_mappings, indent=2)}
"""
        resp = s.ask_llm(prompt)
        if resp is not NotImplemented:
            try:
                json_str = resp
                if "```json" in resp:
                    json_str = resp.split("```json")[1].split("```")[0].strip()
                elif "```" in resp:
                    json_str = resp.split("```")[1].split("```")[0].strip()
                parsed_mappings = json.loads(json_str)
                s.log.info("LLM successfully mapped the dietary requirements!")
            except Exception as e:
                s.log.error(f"LLM returned malformed JSON: {e}")

    # Merge mappings from LLM or Heuristics
    for m in missing_mappings:
        if parsed_mappings and m in parsed_mappings:
            dietary_mappings[m] = parsed_mappings[m]
        else:
            dietary_mappings[m] = map_dietary_heuristically(m)

    # Save cache
    try:
        cache_path.write_text(json.dumps(dietary_mappings, indent=4), encoding="utf-8")
        s.log.info("Dietary mapping cache updated.")
    except Exception as e:
        s.log.error(f"Failed to write dietary mappings cache: {e}")

# 3. Fetch active sessions to resolve linked student sessions
sessions_list = s.airtable_get("Sessions")
schools_list  = s.airtable_get("Schools")
school_name_by_id = {r["id"]: r["fields"].get("School Name", "") for r in schools_list}

# Fetch Dietary Restrictions for name → record-id lookup. Required because the
# Students.'Dietary Requirements' field is now a multipleRecordLinks reference
# rather than multipleSelects.
diet_records = s.airtable_get("Dietary Restrictions")
diet_name_to_id = {r["fields"]["Restriction Name"]: r["id"] for r in diet_records}
if not diet_name_to_id:
    s.log.error("No Dietary Restrictions found in Airtable. Run the dietary "
                "restrictions migration first.")
    sys.exit(1)

# Dictionary to look up sessions by (School Name, Day)
session_lookup = {}  # (school_name, day) -> list of session_record_ids
for sess in sessions_list:
    fields = sess["fields"]
    sess_id = sess["id"]
    sess_day = fields.get("Day")
    school_links = fields.get("School", [])

    if not school_links or not sess_day:
        continue

    school_name = school_name_by_id.get(school_links[0])
    if not school_name:
        continue

    key_pair = (school_name, sess_day)
    if key_pair not in session_lookup:
        session_lookup[key_pair] = []
    session_lookup[key_pair].append(sess_id)

s.log.info(f"Loaded {len(sessions_list)} sessions for enrollment linking.")

# 4. Read students and construct Airtable records
records = []
for name in xls.sheet_names:
    if name not in sheet_metadata:
        continue
    
    school_name, day_name = sheet_metadata[name]
    df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)
    
    required = ["Student", "Year Level", "Subjects", "Dietary", "Student Email"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        s.log.warning(f"Sheet '{name}' is missing columns {missing}. Skipping sheet.")
        continue

    # Get matching session record IDs for this school/day
    student_sessions = session_lookup.get((school_name, day_name), [])

    for _, row in df.iterrows():
        student_name = str(row["Student"]).strip()
        if pd.isna(row["Student"]) or student_name.lower() in ["nan", ""]:
            continue

        raw_dietary = str(row["Dietary"]).strip() if pd.notna(row["Dietary"]) else None
        dietary_choices = dietary_mappings.get(raw_dietary, []) if raw_dietary else []
        # Translate dietary choice names → Dietary Restrictions record IDs.
        dietary_ids = []
        for choice in dietary_choices:
            rec_id = diet_name_to_id.get(choice)
            if rec_id:
                dietary_ids.append(rec_id)
            else:
                s.log.warning(f"Dietary restriction '{choice}' not in Dietary "
                              f"Restrictions table — student '{student_name}' "
                              "will be missing this link.")

        def clean_int(val):
            if pd.isna(val):
                return None
            try:
                return int(val)
            except:
                return None

        def clean_str(val):
            if pd.isna(val):
                return None
            return str(val).strip()

        rec = {
            "Student Name": student_name,
            "Year Level": clean_int(row["Year Level"]),
            "Subjects": clean_str(row["Subjects"]),
            "Dietary Requirements": dietary_ids,
            "Student Email": clean_str(row["Student Email"]),
            "Parent Name": clean_str(row.get("Parent")),
            "Parent Email": clean_str(row.get("Parent Email")),
            "Parent Mobile": clean_str(row.get("Parent Mobile")),
            "Sessions": student_sessions if student_sessions else None
        }
        records.append(rec)

s.log.info(f"Migrating {len(records)} Students...")
s.airtable_post("Students", records)
s.log.info("Students migration completed successfully.")
