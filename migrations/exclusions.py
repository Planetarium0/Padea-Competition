import re, json
from pathlib import Path
from scripts import support as s
from scripts.support import ask_llm

s.load_env()
s.log.info("Migrating exclusions.pdf → Airtable")

pdf_path = Path.cwd() / "resources" / "exclusions.pdf"
txt_path = Path.cwd() / "cache" / "exclusions.txt"

if not txt_path.is_file():
    from scripts.extract_pdfs import extract_as_text
    extract_as_text(pdf_path, txt_path)

raw = txt_path.read_text(encoding="utf-8")
blocks = re.split(r"\n\s*\n", raw.strip())

PROMPT_TEMPLATE = """Extract an exclusion record from the following raw block. Return a JSON with keys:
- School (string)
- Date (ISO YYYY-MM-DD)
- Affected Year Levels (string, e.g. "All" or "12, 10")
- Reason (string)

If any field cannot be determined, set its value to null.
Block:
```
{block}
```
"""

records = []
for blk in blocks:
    # Let Claude handle the parsing – the PDF is highly free‑form.
    prompt = PROMPT_TEMPLATE.format(block=blk)
    resp = ask_llm(prompt)
    if resp is NotImplemented:
        s.log.warning("LLM not configured – flagging block for manual review.")
        continue

    try:
        data = json.loads(resp)
    except json.JSONDecodeError:
        s.log.error("Malformed JSON from LLM – skipping block.")
        continue

    # Resolve School link
    school_name = data.get("School")
    school_id = None
    if school_name:
        matches = s.airtable_get(
            "Schools", filter_formula=f"{{School Name}}='{school_name}'"
        )
        school_id = matches[0]["id"] if matches else None

    rec = {
        "fields": {
            "School": [school_id] if school_id else None,
            "Date": data.get("Date"),
            "Affected Year Levels": data.get("Affected Year Levels"),
            "Reason": data.get("Reason"),
        }
    }
    records.append(rec)

# Upload
for i in range(0, len(records), 10):
    s.airtable_post("Exclusions", records[i : i + 10])

s.log.info("Exclusions migration completed.")
