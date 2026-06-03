from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

from data.dietary_data import all_restriction_names
from support import Database, StudentFields, log


def _resolve_school_name(raw_header: str, canonical_schools: list[str]) -> str | None:
    raw_clean = raw_header.split("-")[0].strip().lower().replace("'", "")
    for std in canonical_schools:
        if raw_clean in std.lower().replace("'", ""):
            return std
    return None


def _clean_int(val: Any) -> int | None:
    if pd.isna(val):
        return None
    try:
        return int(val)
    except Exception:
        return None


def _clean_str(val: Any) -> str | None:
    if pd.isna(val):
        return None
    return str(val).strip()


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating students.xlsx → Supabase")
    db.Students.clear()

    schools = db.Schools.all()
    if not schools:
        log.error("No Schools found in Airtable. Run schools migration first.")
        sys.exit(1)
    canonical_schools = [r.fields["name"] for r in schools if "name" in r.fields]

    xlsx_path = Path.cwd() / "resources" / "students.xlsx"
    if not xlsx_path.is_file():
        log.error(f"students.xlsx not found at {xlsx_path}")
        sys.exit(1)
    xls = pd.ExcelFile(xlsx_path)

    # Pass 1: collect unique dietary strings and sheet metadata.
    unique_dietary: set[str] = set()
    sheet_metadata: dict[str, tuple[str, str]] = {}

    for name in xls.sheet_names:
        df_meta = pd.read_excel(xlsx_path, sheet_name=name, nrows=1)
        header_text = df_meta.columns[0]

        school_name = _resolve_school_name(header_text, canonical_schools)
        parts = header_text.split("-")
        day_name = parts[-1].strip() if len(parts) > 1 else ""

        if not school_name:
            log.warning(f"Could not resolve school name for sheet '{name}' (header: '{header_text}')")
            continue

        sheet_metadata[name] = (school_name, day_name)

        df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)
        if "Dietary" in df.columns:
            for val in df["Dietary"].dropna():
                unique_dietary.add(str(val).strip())

    log.info(f"Collected {len(unique_dietary)} unique dietary requirement strings across all sheets.")

    # Pass 2: build dietary mapping via heuristic (comma-split + exact match).
    standard_choices = {n.lower(): n for n in all_restriction_names()}

    def map_dietary(raw_val: str) -> list[str]:
        choices: list[str] = []
        for part in raw_val.split(","):
            part = part.strip()
            if not part:
                continue
            std = standard_choices.get(part.lower())
            if std:
                choices.append(std)
            else:
                log.error(f"Unrecognised dietary restriction: '{part}' (from '{raw_val}')")
        return list(dict.fromkeys(choices))

    dietary_mappings = {raw: map_dietary(raw) for raw in unique_dietary}

    # Pass 3: fetch linked records.
    sessions = db.Sessions.all()

    diet_records = db.DietaryRestrictions.all()
    diet_name_to_id = {
        r.fields["name"]: r.id
        for r in diet_records
        if "name" in r.fields
    }
    if not diet_name_to_id:
        log.error("No Dietary Restrictions found. Run dietary_restrictions migration first.")
        sys.exit(1)

    school_id_to_name = {r.id: r.fields.get("name", "") for r in schools}

    session_lookup: dict[tuple[str, str], list[str]] = {}
    for sess in sessions:
        fields = sess.fields
        sess_day = fields.get("day")
        school_id = fields.get("school_id")
        if not school_id or not sess_day:
            continue
        school_name = school_id_to_name.get(school_id)
        if not school_name:
            continue
        session_lookup.setdefault((school_name, sess_day), []).append(sess.id)

    log.info(f"Loaded {len(sessions)} sessions for enrollment linking.")

    # Pass 4: build student records.
    records: list[StudentFields] = []
    for name in xls.sheet_names:
        if name not in sheet_metadata:
            continue

        school_name, day_name = sheet_metadata[name]
        df = pd.read_excel(xlsx_path, sheet_name=name, skiprows=2)

        required = ["Student", "Year Level", "Subjects", "Dietary", "Student Email"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            log.warning(f"Sheet '{name}' is missing columns {missing}. Skipping sheet.")
            continue

        student_sessions = session_lookup.get((school_name, day_name), [])

        for _, row in df.iterrows():
            student_name = str(row["Student"]).strip()
            if pd.isna(row["Student"]) or student_name.lower() in ["nan", ""]:
                continue

            raw_dietary = str(row["Dietary"]).strip() if pd.notna(row["Dietary"]) else None
            dietary_choices = dietary_mappings.get(raw_dietary, []) if raw_dietary else []
            dietary_ids: list[str] = []
            for choice in dietary_choices:
                rec_id = diet_name_to_id.get(choice)
                if rec_id:
                    dietary_ids.append(rec_id)
                else:
                    log.warning(
                        f"Dietary restriction '{choice}' not in Dietary Restrictions table "
                        f"— student '{student_name}' will be missing this link."
                    )

            record: StudentFields = {"name": student_name}
            year_level = _clean_int(row["Year Level"])
            if year_level is not None:
                record["year_level"] = year_level
            for field_name, source in (
                ("subjects",      row["Subjects"]),
                ("email",         row["Student Email"]),
                ("parent_name",   row.get("Parent")),
                ("parent_email",  row.get("Parent Email")),
                ("parent_mobile", row.get("Parent Mobile")),
            ):
                value = _clean_str(source)
                if value:
                    record[field_name] = value
            if dietary_ids:
                record["dietary_requirement_ids"] = dietary_ids
            if student_sessions:
                record["session_ids"] = student_sessions
            records.append(record)

    log.info(f"Migrating {len(records)} Students...")
    db.Students.create(records)
    log.info("Students migration completed successfully.")


if __name__ == "__main__":
    run()
