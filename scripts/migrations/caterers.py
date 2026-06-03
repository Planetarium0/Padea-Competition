from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import pandas as pd

from support import CatererFields, Database, Region, log

_VALID_REGIONS = {"Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"}


def _clean_int(val: Any) -> int | None:
    if pd.isna(val):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating caterers.xlsx → Supabase")
    db.Caterers.clear()

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
        log.error(f"Missing expected columns in caterers.xlsx: {missing}")
        sys.exit(1)

    records: list[CatererFields] = []
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
            log.warning(f"Caterer '{caterer_name}' is missing a region — skipping.")
            continue

        if region not in _VALID_REGIONS:
            log.warning(f"Unexpected region '{region}' for caterer '{caterer_name}' — mapping anyway")

        record: CatererFields = {
            "name": caterer_name,
            "region": cast(Region, region),
        }
        min4 = _clean_int(row["minimum order quantity for 4 menu items"])
        min5 = _clean_int(row["minimum order quantity for 5 menu items"])
        min6 = _clean_int(row["minimum order quantity for 6 menu items"])
        if min4 is not None:
            record["min_qty_4_items"] = min4
        if min5 is not None:
            record["min_qty_5_items"] = min5
        if min6 is not None:
            record["min_qty_6_items"] = min6
        records.append(record)

    log.info(f"Migrating {len(records)} caterer(s)...")
    db.Caterers.create(records)
    log.info("Caterers migration completed successfully.")


if __name__ == "__main__":
    run()
