from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from support import AbsenceFields, Database, log


@dataclass(frozen=True)
class _ParsedAbsence:
    school_name: str
    date: str  # ISO yyyy-mm-dd
    student_name: str


def _parse_date(date_str: str) -> str:
    parts = date_str.split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str


def _parse_absences(raw_text: str) -> list[_ParsedAbsence]:
    parsed: list[_ParsedAbsence] = []
    for blk in re.split(r"\n\s*\n", raw_text.strip()):
        lines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not lines:
            continue

        match = re.match(r"^([^-]+)-\s*([\d/]+)\s*Absences", lines[0])
        if not match:
            log.warning(f"Could not parse absence header line: '{lines[0]}'")
            continue

        school_name = match.group(1).strip()
        session_date = _parse_date(match.group(2).strip())

        for student_name in lines[1:]:
            if student_name.lower() == "nan" or not student_name:
                continue
            parsed.append(_ParsedAbsence(
                school_name=school_name,
                date=session_date,
                student_name=student_name,
            ))
    return parsed


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating absences.pdf → Supabase")
    db.Absences.clear()

    txt_path = Path.cwd() / "cache" / "absences.txt"
    if not txt_path.is_file():
        log.error(f"Extracted absences text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)

    raw_text = txt_path.read_text(encoding="utf-8")
    parsed_absences = _parse_absences(raw_text)
    log.info(f"Parsed {len(parsed_absences)} student absences from PDF.")

    student_name_to_id = {
        r.fields["name"]: r.id
        for r in db.Students.all()
        if "name" in r.fields
    }
    session_id_to_rec_id = {
        r.fields["session_code"]: r.id
        for r in db.Sessions.all()
        if "session_code" in r.fields
    }

    records: list[AbsenceFields] = []
    for abs_data in parsed_absences:
        student_id = student_name_to_id.get(abs_data.student_name)
        if not student_id:
            log.warning(
                f"Student '{abs_data.student_name}' absent at {abs_data.school_name} "
                f"but not found in Students table. Skipping."
            )
            continue

        day_name = datetime.strptime(abs_data.date, "%Y-%m-%d").strftime("%A")
        session_id = f"{abs_data.school_name} - {day_name}"
        sess_rec_id = session_id_to_rec_id.get(session_id)
        if not sess_rec_id:
            log.warning(f"No session '{session_id}' for absence of '{abs_data.student_name}'. Skipping.")
            continue

        records.append({
            "absence_code": f"{abs_data.student_name} - {abs_data.school_name} - {abs_data.date}",
            "student_id":   student_id,
            "session_id":   sess_rec_id,
            "date":         abs_data.date,
            "reason":       "Absent",
        })

    if records:
        log.info(f"Migrating {len(records)} Absences records...")
        db.Absences.create(records)
    log.info("Absences migration completed successfully.")


if __name__ == "__main__":
    run()
