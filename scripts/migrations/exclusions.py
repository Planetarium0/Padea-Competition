import os
import sys
import re
import json
from pathlib import Path
import support as s

s.log.info("Migrating exclusions.pdf → Airtable")

# Clear Exclusions table
s.clear_table("Exclusions")

# Read extracted text
txt_path = Path.cwd() / "cache" / "exclusions.txt"
if not txt_path.is_file():
    s.log.error(f"Extracted exclusions text not found at {txt_path}. Please run PDF extraction first.")
    sys.exit(1)

raw_text = txt_path.read_text(encoding="utf-8")

# Static list of schools for fallback mapping
SCHOOLS_LIST = [
    "Moreton Bay Boys' College",
    "John Paul College",
    "MacGregor State High School",
    "Indooroopilly State High School",
    "Loreto College",
    "Cannon Hill Anglican College"
]

def parse_exclusions_heuristic(text):
    s.log.info("Using local heuristic natural-language exclusion parser...")
    
    # Split text into sections starting with "Exclusion <Name>"
    blocks = re.split(r"Exclusion\s+\w+", text)
    results = []
    
    for blk in blocks:
        blk = blk.strip()
        if not blk:
            continue
            
        # Detect school
        matched_school = None
        for school in SCHOOLS_LIST:
            if school.lower() in blk.lower() or school.replace("'", "").lower() in blk.lower():
                matched_school = school
                break
        
        if not matched_school:
            # Try partial names
            if "indooroopilly" in blk.lower():
                matched_school = "Indooroopilly State High School"
            elif "loreto" in blk.lower():
                matched_school = "Loreto College"
            elif "cannon hill" in blk.lower():
                matched_school = "Cannon Hill Anglican College"

        # Detect date (May 2026 is standard)
        date_iso = None
        day_match = re.search(r"(\d+)(?:st|nd|rd|th)?\s+of\s+May", blk, re.IGNORECASE)
        if day_match:
            day = int(day_match.group(1))
            date_iso = f"2026-05-{day:02d}"

        # Detect affected year levels
        years = "All"
        if "all year levels" in blk.lower():
            years = "All"
        else:
            year_match = re.search(r"years?\s+([\d\s,and]+)", blk, re.IGNORECASE)
            if year_match:
                # Clean up years list
                years_raw = year_match.group(1).replace("and", ",").strip()
                years = ", ".join([y.strip() for y in years_raw.split(",") if y.strip()])

        # Detect reason: text between "due to" and end of sentence / new sentence
        reason = "Cancelled"
        reason_match = re.search(r"due to\s+([^.]+)", blk, re.IGNORECASE)
        if reason_match:
            reason = reason_match.group(1).strip()

        if matched_school and date_iso:
            results.append({
                "School": matched_school,
                "Date": date_iso,
                "Affected Year Levels": years,
                "Reason": reason
            })
            
    return results

parsed_exclusions = NotImplemented
key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if key:
    s.log.info("Using Claude LLM for batched exclusions parsing...")
    prompt = f"""You are a data extraction assistant.
Extract the cancelled school sessions from the following text.
Return a JSON array of objects, where each object represents one exclusion and has exactly these keys:
- "School" (string, the exact school name, e.g. "Indooroopilly State High School")
- "Date" (string, date in ISO YYYY-MM-DD format, e.g. "2026-05-04")
- "Affected Year Levels" (string, e.g. "All" or "12, 10")
- "Reason" (string, reason for cancellation, e.g. "Open Day")

Use these standard school names:
- "Moreton Bay Boys' College"
- "John Paul College"
- "MacGregor State High School"
- "Indooroopilly State High School"
- "Loreto College"
- "Cannon Hill Anglican College"

Assume the year is 2026 for all dates.

Raw Text:
```
{raw_text}
```
"""
    resp = s.ask_llm(prompt)
    if resp is not NotImplemented:
        try:
            json_str = resp
            if "```json" in resp:
                json_str = resp.split("```json")[1].split("```")[0].strip()
            elif "```" in resp:
                json_str = resp.split("```")[1].split("```")[0].strip()
            parsed_exclusions = json.loads(json_str)
            s.log.info("LLM successfully parsed all exclusions!")
        except Exception as e:
            s.log.error(f"LLM returned malformed JSON: {e}. Falling back to heuristic.")

if parsed_exclusions is NotImplemented or not parsed_exclusions:
    parsed_exclusions = parse_exclusions_heuristic(raw_text)

# Fetch School records for linking
schools_list = s.airtable_get("Schools")
school_name_to_id = {rec["fields"]["School Name"]: rec["id"] for rec in schools_list}

records = []
for data in parsed_exclusions:
    school_name = data["School"]
    school_id = school_name_to_id.get(school_name)
    if not school_id:
        s.log.warning(f"School '{school_name}' in exclusions not found in Schools table. Skipping.")
        continue

    exclusion_id = f"{school_name} - {data['Date']}"

    records.append({
        "Exclusion ID": exclusion_id,
        "School": [school_id],
        "Date": data["Date"],
        "Affected Year Levels": data["Affected Year Levels"],
        "Reason": data["Reason"]
    })

if records:
    s.log.info(f"Migrating {len(records)} Exclusions records...")
    s.airtable_post("Exclusions", records)
    s.log.info("Exclusions migration completed successfully.")
else:
    s.log.info("No valid exclusions to migrate.")
