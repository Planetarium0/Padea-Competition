import os
import sys
import re
import json
from pathlib import Path
import support as s

s.log.info("Migrating caterer-contacts.pdf → Airtable")

# Read extracted text
txt_path = Path.cwd() / "cache" / "caterer-contacts.txt"
if not txt_path.is_file():
    s.log.error(f"Extracted contact text not found at {txt_path}. Please run PDF extraction first.")
    sys.exit(1)

raw_text = txt_path.read_text(encoding="utf-8")

# Standard school mapping
SCHOOL_MAP = {
    "Moreton Bay Boys College": "Moreton Bay Boys' College",
    "Moreton Bay Boys' College": "Moreton Bay Boys' College",
    "John Paul College": "John Paul College",
    "MacGregor State High School": "MacGregor State High School",
    "MacGregor State High": "MacGregor State High School",
    "Indooroopilly State High School": "Indooroopilly State High School",
    "Loreto College": "Loreto College",
    "Cannon Hill Anglican College": "Cannon Hill Anglican College"
}

def clean_school_names(raw_str):
    if not raw_str:
        return []
    # Replace 'and' with comma to split easily
    cleaned = raw_str.replace(" and ", ", ")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    resolved = []
    for p in parts:
        matched = False
        for key, std_name in SCHOOL_MAP.items():
            if key.lower() in p.lower():
                resolved.append(std_name)
                matched = True
                break
        if not matched:
            s.log.warning(f"Unrecognized school name in raw string: '{p}'")
    return list(set(resolved))

def parse_contacts_heuristic(text):
    """Fallback high-fidelity parser for caterer contacts using regex/heuristics."""
    s.log.info("Using local heuristic contact parser...")
    blocks = re.split(r"\n\s*\n", text.strip())
    results = []
    for blk in blocks:
        lines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not lines:
            continue
        
        caterer_name = lines[0]
        contact_name = None
        contact_email = None
        chef_name = None
        chef_email = None
        chef_wants_cc = False
        serves = []
        able_to_serve = []
        notes = []

        # Find emails and links
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        emails_found = []
        for l in lines:
            matches = re.findall(email_pattern, l)
            if matches:
                emails_found.extend(matches)

        # Parse line by line
        for l in lines[1:]:
            if l.startswith("Serves:"):
                serves = clean_school_names(l.replace("Serves:", "").strip())
            elif l.startswith("Able to serve:"):
                able_to_serve = clean_school_names(l.replace("Able to serve:", "").strip())
            elif "chef" in l.lower():
                # Line matches James Chern (chef – does not want to be cc’ed)
                # or Medium Giraffe (chef – wants to be cc’ed)
                name_match = re.match(r"^([^(]+)", l)
                if name_match:
                    chef_name = name_match.group(1).strip()
                if "does not want to be cc" in l.lower():
                    chef_wants_cc = False
                elif "wants to be cc" in l.lower():
                    chef_wants_cc = True
            elif "@" in l:
                continue
            elif "contact for orders" in l:
                name_match = re.match(r"^([^(]+)", l)
                if name_match:
                    contact_name = name_match.group(1).strip()
            else:
                notes.append(l)

        # Assign emails based on order found
        if emails_found:
            contact_email = emails_found[0]
            if len(emails_found) > 1:
                chef_email = emails_found[1]

        # For Big Mom who is contact and chef
        if "main point of contact and chef" in blk.lower():
            chef_name = contact_name
            chef_email = contact_email
            chef_wants_cc = True

        results.append({
            "Caterer Name": caterer_name,
            "Contact Name": contact_name,
            "Contact Email": contact_email,
            "Chef Name": chef_name,
            "Chef Email": chef_email,
            "Chef Wants CC": chef_wants_cc,
            "Serves Schools": serves,
            "Able to Serve Schools": able_to_serve,
            "Notes": " | ".join(notes) if notes else None
        })
    return results

# Ask LLM if key is available, else use fallback
parsed_data = NotImplemented
key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if key:
    s.log.info("Using Claude LLM for batched contact parsing...")
    prompt = f"""You are a data extraction assistant.
Extract contact information for each caterer from the following raw text.
Return a JSON array of objects, where each object represents one caterer and has exactly these keys:
- "Caterer Name" (string, e.g. "Lakehouse Victoria Point")
- "Contact Name" (string, name of primary contact person)
- "Contact Email" (string, email of primary contact person)
- "Chef Name" (string, name of chef, or null if not mentioned or same as contact)
- "Chef Email" (string, email of chef, or null if not mentioned or same as contact)
- "Chef Wants CC" (boolean, true if mentioned as wanting to be cc'ed, false if mentioned as not wanting to be cc'ed or not mentioned)
- "Serves Schools" (array of strings, e.g. ["Moreton Bay Boys' College"])
- "Able to Serve Schools" (array of strings, e.g. ["Moreton Bay Boys' College", "Cannon Hill Anglican College"])
- "Notes" (string, any additional info or null)

Use these standard school names:
- "Moreton Bay Boys' College"
- "John Paul College"
- "MacGregor State High School"
- "Indooroopilly State High School"
- "Loreto College"
- "Cannon Hill Anglican College"

Raw Text:
```
{raw_text}
```
"""
    resp = s.ask_llm(prompt)
    if resp is not NotImplemented:
        try:
            # Locate JSON block in response
            json_str = resp
            if "```json" in resp:
                json_str = resp.split("```json")[1].split("```")[0].strip()
            elif "```" in resp:
                json_str = resp.split("```")[1].split("```")[0].strip()
            parsed_data = json.loads(json_str)
            s.log.info("LLM successfully parsed all contact blocks!")
        except Exception as e:
            s.log.error(f"LLM returned malformed JSON: {e}. Falling back to heuristic.")

if parsed_data is NotImplemented or not parsed_data:
    parsed_data = parse_contacts_heuristic(raw_text)

# Fetch School records for linking
schools_list = s.airtable_get("Schools")
school_name_to_id = {s_rec["fields"]["School Name"]: s_rec["id"] for s_rec in schools_list}

# Fetch Caterer records for updating
caterers_list = s.airtable_get("Caterers")
caterer_name_to_id = {c_rec["fields"]["Caterer Name"]: c_rec["id"] for c_rec in caterers_list}

# Update Caterers in batch
update_batch = []
for data in parsed_data:
    caterer_name = data["Caterer Name"]
    rec_id = caterer_name_to_id.get(caterer_name)
    if not rec_id:
        s.log.warning(f"Caterer '{caterer_name}' parsed from contact list but not found in Caterers table. Skipping.")
        continue

    # Resolve linked schools
    serves_ids = [school_name_to_id[s_name] for s_name in data["Serves Schools"] if s_name in school_name_to_id]
    able_ids = [school_name_to_id[s_name] for s_name in data["Able to Serve Schools"] if s_name in school_name_to_id]

    update_batch.append({
        "id": rec_id,
        "fields": {
            "Contact Name": data["Contact Name"],
            "Contact Email": data["Contact Email"],
            "Chef Name": data["Chef Name"],
            "Chef Email": data["Chef Email"],
            "Chef Wants CC": bool(data["Chef Wants CC"]),
            "Notes": data["Notes"],
            "Serves Schools": serves_ids,
            "Able to Serve Schools": able_ids
        }
    })

if update_batch:
    s.log.info(f"Updating {len(update_batch)} caterers with contact details...")
    table = s.get_table("Caterers")
    table.batch_update(update_batch)

s.log.info("Caterer contacts migration completed successfully.")
