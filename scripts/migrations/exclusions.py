import os
import sys
import re
import json
from pathlib import Path
import support as s


def _parse_exclusions_heuristic(text, canonical_schools):
    s.log.info("Using local heuristic natural-language exclusion parser...")

    def _match_school(blk):
        blk_clean = blk.lower().replace("'", "")
        for school in canonical_schools:
            if school.lower().replace("'", "") in blk_clean:
                return school
        return None

    results = []
    for blk in re.split(r"Exclusion\s+\w+", text):
        blk = blk.strip()
        if not blk:
            continue

        matched_school = _match_school(blk)

        date_iso  = None
        _MONTHS = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
        }
        date_match = re.search(
            r"(\d+)(?:st|nd|rd|th)?\s+of\s+([A-Za-z]+)(?:\s+(\d{4}))?",
            blk, re.IGNORECASE
        )
        if date_match:
            day   = int(date_match.group(1))
            month = _MONTHS.get(date_match.group(2).lower())
            year  = int(date_match.group(3)) if date_match.group(3) else 2026
            if month:
                date_iso = f"{year}-{month:02d}-{day:02d}"

        years = ["All"]
        if "all year levels" not in blk.lower():
            year_match = re.search(r"years?\s+([\d\s,and]+)", blk, re.IGNORECASE)
            if year_match:
                years_raw = year_match.group(1).replace("and", ",")
                parsed    = [y.strip() for y in years_raw.split(",") if y.strip().isdigit()]
                if parsed:
                    years = parsed

        reason       = "Cancelled"
        reason_match = re.search(r"due to\s+([^.]+)", blk, re.IGNORECASE)
        if reason_match:
            reason = reason_match.group(1).strip()

        if matched_school and date_iso:
            results.append({
                "School":                matched_school,
                "Date":                  date_iso,
                "Affected Year Levels":  years,
                "Reason":                reason,
            })

    return results


def run():
    s.log.info("Migrating exclusions.pdf → Airtable")
    s.clear_table("Exclusions")

    txt_path = Path.cwd() / "cache" / "exclusions.txt"
    if not txt_path.is_file():
        s.log.error(f"Extracted exclusions text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)
    raw_text = txt_path.read_text(encoding="utf-8")

    schools_at         = s.airtable_get("Schools")
    if not schools_at:
        s.log.error("No Schools found in Airtable. Run schools migration first.")
        sys.exit(1)
    canonical_schools  = [r["fields"]["School Name"] for r in schools_at]
    school_name_to_id  = {r["fields"]["School Name"]: r["id"] for r in schools_at}

    parsed_exclusions = NotImplemented
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if key:
        s.log.info("Using Claude LLM for batched exclusions parsing...")
        school_list_str = "\n".join(f'- "{n}"' for n in canonical_schools)
        prompt = f"""You are a data extraction assistant.
Extract the cancelled school sessions from the following text.
Return a JSON array of objects, where each object represents one exclusion and has exactly these keys:
- "School" (string, chosen from the standard school names below)
- "Date" (string, date in ISO YYYY-MM-DD format, e.g. "2026-05-04")
- "Affected Year Levels" (array of strings, each one of "All", "12", "11", "10", "9", "8", "7", "6")
- "Reason" (string, reason for cancellation)

Standard school names:
{school_list_str}

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
        parsed_exclusions = _parse_exclusions_heuristic(raw_text, canonical_schools)

    records = []
    for data in parsed_exclusions:
        school_name = data["School"]
        school_id   = school_name_to_id.get(school_name)
        if not school_id:
            s.log.warning(f"School '{school_name}' in exclusions not found in Schools table. Skipping.")
            continue

        years = data["Affected Year Levels"]
        if isinstance(years, str):
            years = [y.strip() for y in years.replace("and", ",").split(",") if y.strip()]

        records.append({
            "Exclusion ID":         f"{school_name} - {data['Date']}",
            "School":               [school_id],
            "Date":                 data["Date"],
            "Affected Year Levels": years,
            "Reason":               data["Reason"],
        })

    if records:
        s.log.info(f"Migrating {len(records)} Exclusions records...")
        s.airtable_post("Exclusions", records)
    s.log.info("Exclusions migration completed successfully.")


if __name__ == "__main__":
    run()
