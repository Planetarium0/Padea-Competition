import pandas as pd
from pathlib import Path
from scripts import support as s

s.load_env()
s.log.info("Migrating caterers.xlsx → Airtable")

xlsx_path = Path.cwd() / "resources" / "caterers.xlsx"
df = pd.read_excel(xlsx_path, sheet_name="caterers")

# ---- Validation -------------------------------------------------
required = ["caterer", "region", "minimum order quantity for 4 menu items",
            "minimum order quantity for 5 menu items", "minimum order quantity for 6 menu items"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise ValueError(f"Missing expected columns in caterers.xlsx: {missing}")

# ---- Normalisation -----------------------------------------------
def clean(val):
    return None if pd.isna(val) else str(val).strip()

records = []
for _, row in df.iterrows():
    rec = {
        "fields": {
            "Caterer Name": clean(row["caterer"]),
            "Region": clean(row["region"]),
            "Min Qty 4 Items": clean(row["minimum order quantity for 4 menu items"]),
            "Min Qty 5 Items": clean(row["minimum order quantity for 5 menu items"]),
            "Min Qty 6 Items": clean(row["minimum order quantity for 6 menu items"]),
            # Delivery Fee & other fields will be filled later from other resources
        }
    }
    records.append(rec)

# ---- Batch upload (10 records per request) -----------------------
BATCH = 10
for i in range(0, len(records), BATCH):
    s.airtable_post("Caterers", records[i : i + BATCH])

s.log.info("Caterers migration completed.")
