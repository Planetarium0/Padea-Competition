# scripts/migrate_caterer_menus.py
import re, json
from pathlib import Path
from scripts import support as s
from scripts.support import ask_llm

s.load_env()
s.log.info("Migrating caterer‑menus.pdf → Airtable (Menu Items)")

pdf_path = Path.cwd() / "resources" / "caterer-menus.pdf"
txt_path = Path.cwd() / "cache" / "caterer_menus.txt"

if not txt_path.is_file():
    from scripts.extract_pdfs import extract_as_text
    extract_as_text(pdf_path, txt_path)

raw = txt_path.read_text(encoding="utf-8")
lines = [l.strip() for l in raw.splitlines() if l.strip()]

records = []
for line in lines:
    # Simple pattern:  "<Item Name> <price> <optional tags>"
    # We'll ask Claude to be robust – especially for weird separators.
    prompt = f"""Parse this menu line and output JSON with keys:
    - Menu Item Name
    - Price (numeric)
    - Dietary Tags (list, possible values: Gluten Free, Dairy Free, Nut Free, Vegetarian)
    - Notes (any leftover text)

    Line:
    `{line}`
    """
    resp = ask_llm(prompt)
    if resp is NotImplemented:
        s.log.warning("LLM not configured – storing for manual review.")
        records.append(
            {
                "fields": {
                    "Menu Item Name": line.split()[0],
                    "Notes": f"Manual review required – raw line: {line}",
                }
            }
        )
        continue

    try:
        parsed = json.loads(resp)
    except json.JSONDecodeError:
        s.log.error("LLM malformed JSON for line: %s", line)
        continue

    # Resolve Caterer link – we assume the menu PDF is for a single caterer,
    # the filename often includes the caterer name.
    caterer_name = Path(pdf_path).stem.split("-")[0].replace("_", " ").title()
    matches = s.airtable_get(
        "Caterers", filter_formula=f"{{Caterer Name}}='{caterer_name}'"
    )
    caterer_id = matches[0]["id"] if matches else None

    rec = {
        "fields": {
            "Menu Item Name": parsed.get("Menu Item Name"),
            "Price": parsed.get("Price"),
            "Dietary Tags": parsed.get("Dietary Tags", []),
            "Caterer": [caterer_id] if caterer_id else None,
            "Notes": parsed.get("Notes"),
        }
    }
    records.append(rec)

# Batch upload
for i in range(0, len(records), 10):
    s.airtable_post("Menu Items", records[i : i + 10])

s.log.info("Caterer menus migration done.")
