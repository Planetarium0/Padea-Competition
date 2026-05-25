import os
import sys
import re
import json
from pathlib import Path
import support as s


def _resolve_school(raw_name, canonical_schools):
    """Case-insensitive substring match of a raw school name against
    the canonical list fetched from Airtable. Handles abbreviations
    (e.g. "MacGregor State High") and apostrophe variants."""
    raw_clean = raw_name.lower().replace("'", "")
    for std in canonical_schools:
        std_clean = std.lower().replace("'", "")
        if raw_clean in std_clean or std_clean in raw_clean:
            return std
    return None


def _clean_school_names(raw_str, canonical_schools):
    if not raw_str:
        return []
    parts = [p.strip() for p in raw_str.replace(" and ", ", ").split(",") if p.strip()]
    resolved = []
    for part in parts:
        std = _resolve_school(part, canonical_schools)
        if std:
            resolved.append(std)
        else:
            s.log.warning(f"Unrecognised school name in contacts: '{part}'")
    return list(dict.fromkeys(resolved))


def _parse_contacts_heuristic(text, canonical_schools):
    s.log.info("Using local heuristic contact parser...")
    blocks = re.split(r"\n\s*\n", text.strip())
    results = []
    for blk in blocks:
        lines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not lines:
            continue

        caterer_name  = lines[0]
        contact_name  = None
        contact_email = None
        chef_name     = None
        chef_email    = None
        chef_wants_cc = False
        serves        = []
        able_to_serve = []
        notes         = []

        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        emails_found  = []
        for l in lines:
            emails_found.extend(re.findall(email_pattern, l))

        for l in lines[1:]:
            if l.startswith("Serves:"):
                serves = _clean_school_names(l.replace("Serves:", "").strip(), canonical_schools)
            elif l.startswith("Able to serve:"):
                able_to_serve = _clean_school_names(l.replace("Able to serve:", "").strip(), canonical_schools)
            elif "chef" in l.lower():
                name_match = re.match(r"^([^(]+)", l)
                if name_match:
                    chef_name = name_match.group(1).strip()
                chef_wants_cc = "wants to be cc" in l.lower() and "does not" not in l.lower()
            elif "@" in l:
                continue
            elif "contact for orders" in l.lower():
                name_match = re.match(r"^([^(]+)", l)
                if name_match:
                    contact_name = name_match.group(1).strip()
            else:
                notes.append(l)

        if emails_found:
            contact_email = emails_found[0]
            if len(emails_found) > 1:
                chef_email = emails_found[1]

        if "main point of contact and chef" in blk.lower():
            chef_name     = contact_name
            chef_email    = contact_email
            chef_wants_cc = True

        results.append({
            "Caterer Name":         caterer_name,
            "Contact Name":         contact_name,
            "Contact Email":        contact_email,
            "Chef Name":            chef_name,
            "Chef Email":           chef_email,
            "Chef Wants CC":        chef_wants_cc,
            "Serves Schools":       serves,
            "Able to Serve Schools": able_to_serve,
            "Notes":                " | ".join(notes) if notes else None,
        })
    return results


def run():
    s.log.info("Migrating caterer-contacts.pdf → Airtable")

    txt_path = Path.cwd() / "cache" / "caterer-contacts.txt"
    if not txt_path.is_file():
        s.log.error(f"Extracted contact text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)
    raw_text = txt_path.read_text(encoding="utf-8")

    # Canonical school names come from the already-migrated Schools table.
    schools_at = s.airtable_get("Schools")
    if not schools_at:
        s.log.error("No Schools found in Airtable. Run schools migration first.")
        sys.exit(1)
    canonical_schools  = [r["fields"]["School Name"] for r in schools_at]
    school_name_to_id  = {r["fields"]["School Name"]: r["id"] for r in schools_at}

    parsed_data = NotImplemented
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if key:
        s.log.info("Using Claude LLM for batched contact parsing...")
        school_list_str = "\n".join(f'- "{n}"' for n in canonical_schools)
        prompt = f"""You are a data extraction assistant.
Extract contact information for each caterer from the following raw text.
Return a JSON array of objects, where each object represents one caterer and has exactly these keys:
- "Caterer Name" (string)
- "Contact Name" (string, name of primary contact, or null)
- "Contact Email" (string, or null)
- "Chef Name" (string, or null)
- "Chef Email" (string, or null)
- "Chef Wants CC" (boolean)
- "Serves Schools" (array of strings from the standard list below)
- "Able to Serve Schools" (array of strings from the standard list below)
- "Notes" (string or null)

Standard school names:
{school_list_str}

Raw Text:
```
{raw_text}
```
"""
        resp = s.ask_llm(prompt)
        if resp is not NotImplemented:
            try:
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
        parsed_data = _parse_contacts_heuristic(raw_text, canonical_schools)

    caterers_list      = s.airtable_get("Caterers")
    caterer_name_to_id = {c["fields"]["Caterer Name"]: c["id"] for c in caterers_list}

    update_batch = []
    for data in parsed_data:
        caterer_name = data["Caterer Name"]
        rec_id = caterer_name_to_id.get(caterer_name)
        if not rec_id:
            s.log.warning(f"Caterer '{caterer_name}' not found in Caterers table — skipping.")
            continue

        serves_ids = [school_name_to_id[n] for n in data["Serves Schools"]       if n in school_name_to_id]
        able_ids   = [school_name_to_id[n] for n in data["Able to Serve Schools"] if n in school_name_to_id]

        update_batch.append({
            "id": rec_id,
            "fields": {
                "Contact Name":          data["Contact Name"],
                "Contact Email":         data["Contact Email"],
                "Chef Name":             data["Chef Name"],
                "Chef Email":            data["Chef Email"],
                "Chef Wants CC":         bool(data["Chef Wants CC"]),
                "Notes":                 data["Notes"],
                "Serves Schools":        serves_ids,
                "Able to Serve Schools": able_ids,
            },
        })

    if update_batch:
        s.log.info(f"Updating {len(update_batch)} caterer(s) with contact details...")
        s.get_table("Caterers").batch_update(update_batch)

    s.log.info("Caterer contacts migration completed successfully.")


if __name__ == "__main__":
    run()
