import sys
import pandas as pd
from pathlib import Path
import support as s


def run():
    s.log.info("Seeding Schools from sessions.xlsx → Airtable")
    s.clear_table("Schools")

    xlsx_path = Path.cwd() / "resources" / "sessions.xlsx"
    if not xlsx_path.is_file():
        s.log.error(f"sessions.xlsx not found at {xlsx_path}")
        sys.exit(1)

    df = pd.read_excel(xlsx_path, sheet_name="sessions")
    for col in ("school", "region"):
        if col not in df.columns:
            s.log.error(f"sessions.xlsx is missing the '{col}' column")
            sys.exit(1)

    seen = {}
    for _, row in df.iterrows():
        name   = str(row["school"]).strip()  if pd.notna(row["school"])  else None
        region = str(row["region"]).strip()  if pd.notna(row["region"])  else None
        if name and name.lower() != "nan" and name not in seen:
            seen[name] = region

    records = [{"School Name": name, "Region": region} for name, region in seen.items()]
    s.log.info(f"Seeding {len(records)} school(s)...")
    s.airtable_post("Schools", records)
    s.log.info("Schools seeded successfully.")


if __name__ == "__main__":
    run()
