from data.dietary_data import all_restriction_names
import sys
import pandas as pd
from pathlib import Path
import support as s


def _resolve_school_name(raw_header, canonical_schools):
    raw_clean = raw_header.split("-")[0].strip().lower().replace("'", "")
    for std in canonical_schools:
        if raw_clean in std.lower().replace("'", ""):
            return std
    return None


def run():
    s.log.info("Migrating students.xlsx → Airtable")
    s.clear_table("Students")

    schools_at        = s.airtable_get("Schools")
    if not schools_at:
        s.log.error("No Schools found in Airtable. Run schools migration first.")
        sys.exit(1)
    canonical_schools = [r["fields"]["School Name"] for r in schools_at]

    xlsx_path = Path.cwd() / "resources" / "students.xlsx"
    if not xlsx_path.is_file():
        s.log.error(f"students.xlsx not found at {xlsx_path}")
        sys.exit(1)
    xls = pd.ExcelFile(xlsx_path)

    # Pass 1: collect unique dietary strings and sheet metadata.
    unique_dietary = set()
    sheet_metadata = {}  # sheet_name -> (school_name, day_name)

    for name in xls.sheet_names:
        df_meta     = pd.read_excel(xlsx_path, sheet_name=name, nrows=1)
        header_text = df_meta.columns[0]

        school_name = _resolve_school_name(header_text, canonical_schools)
        parts       = header_text.split("-")
        day_name    = parts[-1].strip() if len(parts) > 1 else ""

        if not school_name:
            s.log.warning(f"Could not resolve school name for sheet '{name}' (header: '{header_text}')")
            continue

        sheet_metadata[name] = (school_name, day_name)

        df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)
        if "Dietary" in df.columns:
            for val in df["Dietary"].dropna():
                unique_dietary.add(str(val).strip())

    s.log.info(f"Collected {len(unique_dietary)} unique dietary requirement strings across all sheets.")

    # Pass 2: build dietary mapping via heuristic (comma-split + exact match).
    STANDARD_DIETARY_CHOICES = {name.lower(): name for name in all_restriction_names()}

    def map_dietary(raw_val):
        choices = []
        for part in raw_val.split(","):
            part = part.strip()
            if not part:
                continue
            std = STANDARD_DIETARY_CHOICES.get(part.lower())
            if std:
                choices.append(std)
            else:
                s.log.error(f"Unrecognised dietary restriction: '{part}' (from '{raw_val}')")
        return list(dict.fromkeys(choices))

    dietary_mappings = {raw: map_dietary(raw) for raw in unique_dietary}

    # Pass 3: fetch linked records.
    sessions_list     = s.airtable_get("Sessions")
    school_name_by_id = {r["id"]: r["fields"].get("School Name", "") for r in schools_at}

    diet_records    = s.airtable_get("Dietary Restrictions")
    diet_name_to_id = {r["fields"]["Restriction Name"]: r["id"] for r in diet_records}
    if not diet_name_to_id:
        s.log.error("No Dietary Restrictions found. Run dietary_restrictions migration first.")
        sys.exit(1)

    session_lookup = {}  # (school_name, day) -> [session_record_id, ...]
    for sess in sessions_list:
        fields       = sess["fields"]
        sess_day     = fields.get("Day")
        school_links = fields.get("School", [])
        if not school_links or not sess_day:
            continue
        school_name = school_name_by_id.get(school_links[0])
        if not school_name:
            continue
        session_lookup.setdefault((school_name, sess_day), []).append(sess["id"])

    s.log.info(f"Loaded {len(sessions_list)} sessions for enrollment linking.")

    # Pass 4: build student records.
    def clean_int(val):
        if pd.isna(val):
            return None
        try:
            return int(val)
        except Exception:
            return None

    def clean_str(val):
        if pd.isna(val):
            return None
        return str(val).strip()

    records = []
    for name in xls.sheet_names:
        if name not in sheet_metadata:
            continue

        school_name, day_name = sheet_metadata[name]
        df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)

        required = ["Student", "Year Level", "Subjects", "Dietary", "Student Email"]
        missing  = [c for c in required if c not in df.columns]
        if missing:
            s.log.warning(f"Sheet '{name}' is missing columns {missing}. Skipping sheet.")
            continue

        student_sessions = session_lookup.get((school_name, day_name), [])

        for _, row in df.iterrows():
            student_name = str(row["Student"]).strip()
            if pd.isna(row["Student"]) or student_name.lower() in ["nan", ""]:
                continue

            raw_dietary     = str(row["Dietary"]).strip() if pd.notna(row["Dietary"]) else None
            dietary_choices = dietary_mappings.get(raw_dietary, []) if raw_dietary else []
            dietary_ids     = []
            for choice in dietary_choices:
                rec_id = diet_name_to_id.get(choice)
                if rec_id:
                    dietary_ids.append(rec_id)
                else:
                    s.log.warning(f"Dietary restriction '{choice}' not in Dietary Restrictions table "
                                  f"— student '{student_name}' will be missing this link.")

            records.append({
                "Student Name":         student_name,
                "Year Level":           clean_int(row["Year Level"]),
                "Subjects":             clean_str(row["Subjects"]),
                "Dietary Requirements": dietary_ids,
                "Student Email":        clean_str(row["Student Email"]),
                "Parent Name":          clean_str(row.get("Parent")),
                "Parent Email":         clean_str(row.get("Parent Email")),
                "Parent Mobile":        clean_str(row.get("Parent Mobile")),
                "Sessions":             student_sessions if student_sessions else None,
            })

    s.log.info(f"Migrating {len(records)} Students...")
    s.airtable_post("Students", records)
    s.log.info("Students migration completed successfully.")


if __name__ == "__main__":
    run()
