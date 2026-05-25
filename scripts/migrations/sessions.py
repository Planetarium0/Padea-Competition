from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pandas as pd

from support import Database, DayName, OnSiteManagerFields, SessionFields, log


def _clean_str(val: Any) -> str | None:
    if pd.isna(val):
        return None
    return str(val).strip()


def _parse_date(val: Any) -> str | None:
    if pd.isna(val):
        return None
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    try:
        epoch = datetime(1899, 12, 30)
        return (epoch + timedelta(days=int(val))).strftime("%Y-%m-%d")
    except Exception:
        str_val = str(val).strip()
        if " " in str_val:
            str_val = str_val.split()[0]
        return str_val


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating sessions.xlsx → Airtable")
    db.Sessions.clear()
    db.OnSiteManagers.clear()

    xlsx_path = Path.cwd() / "resources" / "sessions.xlsx"
    if not xlsx_path.is_file():
        log.error(f"sessions.xlsx not found at {xlsx_path}")
        sys.exit(1)

    df = pd.read_excel(xlsx_path, sheet_name="sessions")
    expected = [
        "school", "region", "caterer", "date", "day", "manager",
        "manager-mobile", "start-time", "end-time", "dinner-time",
        "year-levels", "Building",
    ]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        log.error(f"Missing columns in sessions.xlsx: {missing}")
        sys.exit(1)

    managers_data: dict[str, str | None] = {}
    for _, row in df.iterrows():
        m_name = _clean_str(row["manager"])
        m_mobile = _clean_str(row["manager-mobile"])
        if m_name and m_name.lower() != "nan":
            if m_name not in managers_data:
                managers_data[m_name] = m_mobile
            elif m_mobile and not managers_data[m_name]:
                managers_data[m_name] = m_mobile

    managers_records: list[OnSiteManagerFields] = []
    for name, mobile in managers_data.items():
        manager_record: OnSiteManagerFields = {"Manager Name": name}
        if mobile:
            manager_record["Mobile"] = mobile
        managers_records.append(manager_record)
    log.info(f"Migrating {len(managers_records)} On-Site Managers...")
    db.OnSiteManagers.create(managers_records)

    school_name_to_id = {
        r.fields["School Name"]: r.id
        for r in db.Schools.all()
        if "School Name" in r.fields
    }
    caterer_name_to_id = {
        r.fields["Caterer Name"]: r.id
        for r in db.Caterers.all()
        if "Caterer Name" in r.fields
    }
    manager_name_to_id = {
        r.fields["Manager Name"]: r.id
        for r in db.OnSiteManagers.all()
        if "Manager Name" in r.fields
    }

    sessions_records: list[SessionFields] = []
    for _, row in df.iterrows():
        school_name = _clean_str(row["school"])
        if not school_name or school_name.lower() == "nan":
            continue

        school_id = school_name_to_id.get(school_name)
        if not school_id:
            log.warning(f"School '{school_name}' in sessions not found in Schools table. Skipping session.")
            continue

        caterer_name = _clean_str(row["caterer"])
        caterer_id = caterer_name_to_id.get(caterer_name) if caterer_name else None

        manager_name = _clean_str(row["manager"])
        manager_id = manager_name_to_id.get(manager_name) if manager_name else None

        session_date = _parse_date(row["date"])
        if not session_date:
            log.warning(f"Session at '{school_name}' missing a valid date. Skipping.")
            continue

        day_name = _clean_str(row["day"])
        session_id = f"{school_name} - {day_name}"

        record: SessionFields = {
            "Session ID": session_id,
            "School":     [school_id],
            "Date":       session_date,
        }
        if day_name:
            record["Day"] = cast(DayName, day_name)
        if caterer_id:
            record["Caterer"] = [caterer_id]
        if manager_id:
            record["On-Site Manager"] = [manager_id]
        for field_name, col in (
            ("Start Time",  "start-time"),
            ("End Time",    "end-time"),
            ("Dinner Time", "dinner-time"),
            ("Year Levels", "year-levels"),
            ("Building",    "Building"),
        ):
            value = _clean_str(row[col])
            if value:
                record[field_name] = value
        sessions_records.append(record)

    log.info(f"Migrating {len(sessions_records)} Sessions...")
    db.Sessions.create(sessions_records)
    log.info("Sessions migration completed successfully.")


if __name__ == "__main__":
    run()
