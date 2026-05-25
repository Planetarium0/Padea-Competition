import sys
import pandas as pd
from pathlib import Path
import support as s


def _clean_str(val):
    if pd.isna(val):
        return None
    return str(val).strip()


def _parse_date(val):
    if pd.isna(val):
        return None
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    try:
        from datetime import datetime, timedelta
        epoch = datetime(1899, 12, 30)
        return (epoch + timedelta(days=int(val))).strftime("%Y-%m-%d")
    except Exception:
        str_val = str(val).strip()
        if " " in str_val:
            str_val = str_val.split()[0]
        return str_val


def run():
    s.log.info("Migrating sessions.xlsx → Airtable")
    s.clear_table("Sessions")
    s.clear_table("On-Site Managers")

    xlsx_path = Path.cwd() / "resources" / "sessions.xlsx"
    if not xlsx_path.is_file():
        s.log.error(f"sessions.xlsx not found at {xlsx_path}")
        sys.exit(1)

    df = pd.read_excel(xlsx_path, sheet_name="sessions")
    expected = [
        "school", "region", "caterer", "date", "day", "manager",
        "manager-mobile", "start-time", "end-time", "dinner-time",
        "year-levels", "Building"
    ]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        s.log.error(f"Missing columns in sessions.xlsx: {missing}")
        sys.exit(1)

    managers_data = {}
    for _, row in df.iterrows():
        m_name   = _clean_str(row["manager"])
        m_mobile = _clean_str(row["manager-mobile"])
        if m_name and m_name.lower() != "nan":
            if m_name not in managers_data:
                managers_data[m_name] = m_mobile
            elif m_mobile and not managers_data[m_name]:
                managers_data[m_name] = m_mobile

    managers_records = [{"Manager Name": name, "Mobile": mobile}
                        for name, mobile in managers_data.items()]
    s.log.info(f"Migrating {len(managers_records)} On-Site Managers...")
    s.airtable_post("On-Site Managers", managers_records)

    schools_list       = s.airtable_get("Schools")
    school_name_to_id  = {rec["fields"]["School Name"]: rec["id"] for rec in schools_list}

    caterers_list      = s.airtable_get("Caterers")
    caterer_name_to_id = {rec["fields"]["Caterer Name"]: rec["id"] for rec in caterers_list}

    managers_list      = s.airtable_get("On-Site Managers")
    manager_name_to_id = {rec["fields"]["Manager Name"]: rec["id"] for rec in managers_list}

    sessions_records = []
    for _, row in df.iterrows():
        school_name = _clean_str(row["school"])
        if not school_name or school_name.lower() == "nan":
            continue

        school_id = school_name_to_id.get(school_name)
        if not school_id:
            s.log.warning(f"School '{school_name}' in sessions not found in Schools table. Skipping session.")
            continue

        caterer_name = _clean_str(row["caterer"])
        caterer_id   = caterer_name_to_id.get(caterer_name)

        manager_name = _clean_str(row["manager"])
        manager_id   = manager_name_to_id.get(manager_name)

        session_date = _parse_date(row["date"])
        if not session_date:
            s.log.warning(f"Session at '{school_name}' missing a valid date. Skipping.")
            continue

        day_name   = _clean_str(row["day"])
        session_id = f"{school_name} - {day_name}"

        sessions_records.append({
            "Session ID":      session_id,
            "School":          [school_id],
            "Region":          _clean_str(row["region"]),
            "Caterer":         [caterer_id] if caterer_id else None,
            "Date":            session_date,
            "Day":             day_name,
            "On-Site Manager": [manager_id] if manager_id else None,
            "Start Time":      _clean_str(row["start-time"]),
            "End Time":        _clean_str(row["end-time"]),
            "Dinner Time":     _clean_str(row["dinner-time"]),
            "Year Levels":     _clean_str(row["year-levels"]),
            "Building":        _clean_str(row["Building"]),
        })

    s.log.info(f"Migrating {len(sessions_records)} Sessions...")
    s.airtable_post("Sessions", sessions_records)
    s.log.info("Sessions migration completed successfully.")


if __name__ == "__main__":
    run()
