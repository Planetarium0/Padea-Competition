import sys
import pandas as pd
from pathlib import Path
import support as s


def run():
    s.log.info("Migrating caterers.xlsx → Airtable")
    s.clear_table("Caterers")

    xlsx_path = Path.cwd() / "resources" / "caterers.xlsx"
    df = pd.read_excel(xlsx_path, sheet_name="caterers")

    required = [
        "caterer",
        "region",
        "minimum order quantity for 4 menu items",
        "minimum order quantity for 5 menu items",
        "minimum order quantity for 6 menu items",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        s.log.error(f"Missing expected columns in caterers.xlsx: {missing}")
        sys.exit(1)

    def clean_int(val):
        if pd.isna(val):
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    records = []
    for _, row in df.iterrows():
        raw_caterer = row["caterer"]
        if pd.isna(raw_caterer):
            continue

        caterer_name = str(raw_caterer).strip()
        if caterer_name.startswith("*") or caterer_name.lower() in ["nan", ""]:
            continue

        raw_region = row["region"]
        region = str(raw_region).strip() if pd.notna(raw_region) else None

        if not region:
            s.log.warning(f"Caterer '{caterer_name}' is missing a region — skipping.")
            continue

        if region not in ["Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"]:
            s.log.warning(f"Unexpected region '{region}' for caterer '{caterer_name}' — mapping anyway")

        records.append({
            "Caterer Name": caterer_name,
            "Region": region,
            "Min Qty 4 Items": clean_int(row["minimum order quantity for 4 menu items"]),
            "Min Qty 5 Items": clean_int(row["minimum order quantity for 5 menu items"]),
            "Min Qty 6 Items": clean_int(row["minimum order quantity for 6 menu items"]),
        })

    s.log.info(f"Migrating {len(records)} caterer(s)...")
    s.airtable_post("Caterers", records)
    s.log.info("Caterers migration completed successfully.")


if __name__ == "__main__":
    run()
