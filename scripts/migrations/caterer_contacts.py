from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from support import Database, log, ask_llm


class _ParsedContact(TypedDict, total=False):
    Caterer_Name: str  # placeholder; we read by exact key below


def _resolve_school(raw_name: str, canonical_schools: list[str]) -> str | None:
    """Case-insensitive substring match of a raw school name against
    the canonical list fetched from Airtable. Handles abbreviations
    (e.g. "MacGregor State High") and apostrophe variants."""
    raw_clean = raw_name.lower().replace("'", "")
    for std in canonical_schools:
        std_clean = std.lower().replace("'", "")
        if raw_clean in std_clean or std_clean in raw_clean:
            return std
    return None


def _clean_school_names(raw_str: str, canonical_schools: list[str]) -> list[str]:
    if not raw_str:
        return []
    parts = [p.strip() for p in raw_str.replace(" and ", ", ").split(",") if p.strip()]
    resolved: list[str] = []
    for part in parts:
        std = _resolve_school(part, canonical_schools)
        if std:
            resolved.append(std)
        else:
            log.warning(f"Unrecognised school name in contacts: '{part}'")
    return list(dict.fromkeys(resolved))


def _parse_contacts_heuristic(
    text: str,
    canonical_schools: list[str],
) -> list[dict[str, Any]]:
    log.info("Using local heuristic contact parser...")
    blocks = re.split(r"\n\s*\n", text.strip())
    results: list[dict[str, Any]] = []
    for blk in blocks:
        lines = [l.strip() for l in blk.splitlines() if l.strip()]
        if not lines:
            continue

        caterer_name = lines[0]
        contact_name: str | None = None
        contact_email: str | None = None
        chef_name: str | None = None
        chef_email: str | None = None
        chef_wants_cc = False
        able_to_serve: list[str] = []
        notes: list[str] = []

        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        emails_found: list[str] = []
        for l in lines:
            emails_found.extend(re.findall(email_pattern, l))

        for l in lines[1:]:
            if l.startswith("Able to serve:"):
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
            contact_name = chef_name
            chef_email = contact_email
            chef_wants_cc = True

        results.append({
            "Caterer Name":          caterer_name,
            "Contact Name":          contact_name,
            "Contact Email":         contact_email,
            "Chef Name":             chef_name,
            "Chef Email":            chef_email,
            "Chef Wants CC":         chef_wants_cc,
            "Able to Serve Schools": able_to_serve,
            "Notes":                 " | ".join(notes) if notes else None,
        })
    return results


def _extract_json_block(resp: str) -> str:
    if "```json" in resp:
        return resp.split("```json")[1].split("```")[0].strip()
    if "```" in resp:
        return resp.split("```")[1].split("```")[0].strip()
    return resp


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating caterer-contacts.pdf → Supabase")

    txt_path = Path.cwd() / "cache" / "caterer-contacts.txt"
    if not txt_path.is_file():
        log.error(f"Extracted contact text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)
    raw_text = txt_path.read_text(encoding="utf-8")

    schools_records = db.Schools.all()
    if not schools_records:
        log.error("No Schools found in Airtable. Run schools migration first.")
        sys.exit(1)
    canonical_schools = [r.fields["name"] for r in schools_records if "name" in r.fields]
    school_name_to_id = {r.fields["name"]: r.id for r in schools_records if "name" in r.fields}

    parsed_data: list[dict[str, Any]] | None = None
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if key:
        log.info("Using Claude LLM for batched contact parsing...")
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
- "Able to Serve Schools" (array of strings from the standard list below)
- "Notes" (string or null)

Standard school names:
{school_list_str}

Raw Text:
```
{raw_text}
```
"""
        resp = ask_llm(prompt)
        if resp:
            try:
                parsed_data = json.loads(_extract_json_block(resp))
                log.info("LLM successfully parsed all contact blocks!")
            except Exception as e:
                log.error(f"LLM returned malformed JSON: {e}. Falling back to heuristic.")

    if not parsed_data:
        parsed_data = _parse_contacts_heuristic(raw_text, canonical_schools)

    caterers_records = db.Caterers.all()
    caterer_name_to_id = {
        c.fields["name"]: c.id
        for c in caterers_records
        if "name" in c.fields
    }

    update_batch: list[dict[str, Any]] = []
    for data in parsed_data:
        caterer_name = data["Caterer Name"]
        rec_id = caterer_name_to_id.get(caterer_name)
        if not rec_id:
            log.warning(f"Caterer '{caterer_name}' not found in Caterers table — skipping.")
            continue

        able_ids = [school_name_to_id[n] for n in data["Able to Serve Schools"] if n in school_name_to_id]

        update_batch.append({
            "id":                    rec_id,
            "contact_name":          data["Contact Name"],
            "contact_email":         data["Contact Email"],
            "chef_name":             data["Chef Name"],
            "chef_email":            data["Chef Email"],
            "chef_wants_cc":         bool(data["Chef Wants CC"]),
            "notes":                 data["Notes"],
            "able_to_serve_school_ids": able_ids,
        })

    if update_batch:
        log.info(f"Updating {len(update_batch)} caterer(s) with contact details...")
        db.Caterers.batch_update(update_batch)

    log.info("Caterer contacts migration completed successfully.")


if __name__ == "__main__":
    run()
