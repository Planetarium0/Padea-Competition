# scripts/migrate_caterer_contacts.py
import os
from pathlib import Path
import re
import json
from scripts import support as s
from scripts.support import ask_llm

s.load_env()
s.log.info("Migrating caterer‑contacts.pdf → Airtable")

pdf_path = Path.cwd() / "resources" / "caterer-contacts.pdf"
txt_path = Path.cwd() / "cache" / "caterer_contacts.txt"

# Simple PDF → text extraction (we already have a script that does this;
# re‑use it for consistency)
if not txt_path.is_file():
    from scripts.extract_pdfs import extract_as_text  # assumes existing helper
    extract_as_text(pdf_path, txt_path)

raw = txt_path.read_text(encoding="utf-8")
blocks = re.split(r"\n\s*\n", raw.strip())   # blank line separates blocks

records = []
for blk in blocks:
    lines = [l.strip() for l in blk.splitlines() if l.strip()]
    if not lines:
        continue

    # Basic parsing – we will **ask Claude** for any ambiguous mapping
    # Example prompt:
    prompt = f"""You are an AI assistant. Extract the following fields from this raw block of a caterer‑contacts PDF and output a JSON object with exactly these keys:
    - Caterer Name
    - Contact Name
    - Contact Email
    - Chef Name (optional)
    - Chef Email (optional)
    - Serves (comma‑separated school names)
    - Able to Serve (comma‑separated school names)
    - Notes (any remaining free‑form text)

    If a field cannot be confidently extracted, set its value to null and add a comment under a top‑level `"issues"` array.

    Block:
    ```
    {blk}
    ```
    """
    response = ask_llm(prompt)
    if response is NotImplemented:
        s.log.warning("LLM not configured – flagging block for manual review.")
        # Store as a manual‑review record
        records.append(
            {
                "fields": {
                    "Caterer Name": lines[0] if lines else None,
                    "Notes": f"Manual review needed – raw block: {blk[:200]}...",
                }
            }
        )
        continue

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        s.log.error("LLM returned malformed JSON – flagging for review.")
        continue

    # Build Airtable payload
    rec = {"fields": {}}
    # map directly
    for key in [
        "Caterer Name",
        "Contact Name",
        "Contact Email",
        "Chef Name",
        "Chef Email",
        "Notes",
    ]:
        rec["fields"][key] = data.get(key)

    # Resolve linked schools (multipleRecordLinks)
    def resolve_links(names):
        ids = []
        for name in (n.strip() for n in names.split(",")):
            # lookup by School Name in Airtable
            matches = s.airtable_get(
                "Schools", filter_formula=f"{{School Name}}='{name}'"
            )
            if matches:
                ids.append(matches[0]["id"])
        return ids

    rec["fields"]["Serves Schools"] = resolve_links(data.get("Serves", ""))
    rec["fields"]["Able to Serve Schools"] = resolve_links(
        data.get("Able to Serve", "")
    )
    records.append(rec)

# Batch upload (max 10 records)
for i in range(0, len(records), 10):
    s.airtable_post("Caterers", records[i : i + 10])

s.log.info("Caterer contacts migration finished.")
