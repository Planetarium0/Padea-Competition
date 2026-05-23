import os
import sys
import pandas as pd
from pathlib import Path

# Add repository root to system path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts import support as s

s.log.info("Migrating caterers.xlsx → Airtable")

# Seed Schools data map
SCHOOLS_DATA = {
    "Moreton Bay Boys' College": "Redlands",
    "John Paul College": "South Brisbane",
    "MacGregor State High School": "South Brisbane",
    "Indooroopilly State High School": "West Brisbane",
    "Loreto College": "Central Brisbane",
    "Cannon Hill Anglican College": "Central Brisbane"
}

# Clear tables for repeatable migration
s.clear_table("Caterers")
s.clear_table("Schools")

# Seed Schools
schools_records = []
for school_name, region in SCHOOLS_DATA.items():
    schools_records.append({
        "School Name": school_name,
        "Region": region
    })
s.log.info(f"Seeding {len(schools_records)} schools into Schools table...")
s.airtable_post("Schools", schools_records)

# Read caterers Excel
xlsx_path = Path(__file__).parent.parent / "resources" / "caterers.xlsx"
df = pd.read_excel(xlsx_path, sheet_name="caterers")

# Validation
required = [
    "caterer", 
    "region", 
    "minimum order quantity for 4 menu items",
    "minimum order quantity for 5 menu items", 
    "minimum order quantity for 6 menu items"
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
        s.log.warning(f"Caterer '{caterer_name}' is missing a region - skipping.")
        continue
    
    # Validation checks
    if region not in ["Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"]:
        s.log.warning(f"Unexpected region '{region}' for caterer '{caterer_name}' - mapping anyway")

    rec = {
        "Caterer Name": caterer_name,
        "Region": region,
        "Min Qty 4 Items": clean_int(row["minimum order quantity for 4 menu items"]),
        "Min Qty 5 Items": clean_int(row["minimum order quantity for 5 menu items"]),
        "Min Qty 6 Items": clean_int(row["minimum order quantity for 6 menu items"]),
    }
    records.append(rec)

s.log.info(f"Migrating {len(records)} caterers...")
s.airtable_post("Caterers", records)
s.log.info("Caterers migration completed successfully.")
