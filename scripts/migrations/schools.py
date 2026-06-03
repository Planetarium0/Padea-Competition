from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

import pandas as pd

from support import Database, Region, SchoolFields, log


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Seeding Schools from sessions.xlsx → Supabase")
    db.Schools.clear()

    xlsx_path = Path.cwd() / "resources" / "sessions.xlsx"
    if not xlsx_path.is_file():
        log.error(f"sessions.xlsx not found at {xlsx_path}")
        sys.exit(1)

    df = pd.read_excel(xlsx_path, sheet_name="sessions")
    for col in ("school", "region"):
        if col not in df.columns:
            log.error(f"sessions.xlsx is missing the '{col}' column")
            sys.exit(1)

    seen: dict[str, str | None] = {}
    for _, row in df.iterrows():
        name = str(row["school"]).strip() if pd.notna(row["school"]) else None
        region = str(row["region"]).strip() if pd.notna(row["region"]) else None
        if name and name.lower() != "nan" and name not in seen:
            seen[name] = region

    records: list[SchoolFields] = []
    for name, region in seen.items():
        record: SchoolFields = {"name": name}
        if region:
            record["region"] = cast(Region, region)
        records.append(record)

    log.info(f"Seeding {len(records)} school(s)...")
    db.Schools.create(records)
    log.info("Schools seeded successfully.")


if __name__ == "__main__":
    run()
