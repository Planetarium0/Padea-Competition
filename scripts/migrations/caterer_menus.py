from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from support import Database, MenuItemFields, log, ask_llm


def _parse_menus_heuristic(text: str) -> list[dict[str, Any]]:
    log.info("Using local heuristic menu parser...")
    header_pattern = (
        r"([^\n(]+)\s*Menu\s*\(\$([\d.]+)\s*(including|excluding)\s*GST\s*per\s*item,"
        r"\s*\$([\d.]+)\s*delivery\s*(per\s*school\s*per\s*trip|per\s*trip)?\)"
    )
    matches = list(re.finditer(header_pattern, text))
    caterer_menus: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        caterer_name     = match.group(1).strip()
        item_price       = float(match.group(2))
        gst_status       = match.group(3).strip()
        delivery_fee     = float(match.group(4))
        raw_structure    = match.group(5)
        structure        = "Per school per trip" if raw_structure and "school" in raw_structure.lower() else "Per trip"
        price_incl_gst   = (gst_status == "including")

        start_pos    = match.end()
        end_pos      = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        menu_content = text[start_pos:end_pos].strip()

        items: list[dict[str, Any]] = []
        for line in menu_content.splitlines():
            line = line.strip()
            if not line or "dietary legend" in line.lower() or "gst" in line.lower() or "=" in line:
                continue
            flags: list[str] = []
            item_words: list[str] = []
            for w in line.split():
                clean_w = w.strip(" ,()").upper()
                if clean_w in ("GF", "DF", "NF", "VO"):
                    flags.append(clean_w)
                else:
                    item_words.append(w)
            item_name = " ".join(item_words).strip()
            if not item_name:
                continue
            # VO means a vegetarian *variant* exists, not that the item itself is
            # vegetarian. Exclude it from the base item's tags; a companion variant
            # record will be created after the base items are inserted.
            base_tag_map = {"GF": "Gluten Free", "DF": "Dairy Free", "NF": "Nut Free"}
            dietary = [base_tag_map[f] for f in flags if f in base_tag_map]
            _PORK_WORDS = ("pork", "bacon", "ham", "prosciutto", "pancetta", "lard", "salami", "chorizo")
            if not any(w in item_name.lower() for w in _PORK_WORDS):
                dietary.append("Halal")
            items.append({
                "Menu Item Name":        item_name,
                "Dietary Tags":          list(set(dietary)),
                "Has Vegetarian Option": "VO" in flags,
                "Notes":                 None,
            })

        caterer_menus.append({
            "Caterer Name":           caterer_name,
            "Price per Item":         item_price,
            "Price Includes GST":     price_incl_gst,
            "Delivery Fee":           delivery_fee,
            "Delivery Fee Structure": structure,
            "Items":                  items,
        })
    return caterer_menus


def _extract_json_block(resp: str) -> str:
    if "```json" in resp:
        return resp.split("```json")[1].split("```")[0].strip()
    if "```" in resp:
        return resp.split("```")[1].split("```")[0].strip()
    return resp


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    log.info("Migrating caterer-menus.pdf → Airtable (Menu Items)")
    db.MenuItems.clear()

    txt_path = Path.cwd() / "cache" / "caterer-menus.txt"
    if not txt_path.is_file():
        # TODO: import PDF extraction
        log.error(f"Extracted menu text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)
    raw_text = txt_path.read_text(encoding="utf-8")

    parsed_menus: list[dict[str, Any]] | None = None
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if key:
        log.info("Using Claude LLM for batched menu parsing...")
        prompt = f"""You are a data extraction assistant.
Extract the menu items and delivery pricing structure for each caterer from the following raw menu text.
Return a JSON array of objects, where each object represents one caterer and has exactly these keys:
- "Caterer Name" (string, e.g. "Lakehouse Victoria Point")
- "Price per Item" (number, flat per-item price)
- "Price Includes GST" (boolean)
- "Delivery Fee" (number)
- "Delivery Fee Structure" (string, either "Per trip" or "Per school per trip")
- "Items" (array of objects with "Menu Item Name", "Dietary Tags", "Has Vegetarian Option", "Notes")

Dietary tag rules:
1. Map GF→"Gluten Free", DF→"Dairy Free", NF→"Nut Free".
2. VO means a vegetarian variant exists alongside the standard item — do NOT add "Vegetarian"
   to "Dietary Tags". Instead set "Has Vegetarian Option": true on that item.
3. Add "Halal" to any item whose name does not imply pork.

Raw Menu Text:
```
{raw_text}
```
"""
        resp = ask_llm(prompt)
        if resp:
            try:
                parsed_menus = json.loads(_extract_json_block(resp))
                log.info("LLM successfully parsed all menus!")
            except Exception as e:
                log.error(f"LLM returned malformed JSON: {e}. Falling back to heuristic.")

    if not parsed_menus:
        parsed_menus = _parse_menus_heuristic(raw_text)

    caterers_records = db.Caterers.all()
    caterer_name_to_id = {
        c.fields["Caterer Name"]: c.id
        for c in caterers_records
        if "Caterer Name" in c.fields
    }

    diet_records = db.DietaryRestrictions.all()
    diet_name_to_id = {
        r.fields["Restriction Name"]: r.id
        for r in diet_records
        if "Restriction Name" in r.fields
    }
    if not diet_name_to_id:
        log.error("No Dietary Restrictions found. Run dietary_restrictions migration first.")
        sys.exit(1)

    # (item_fields, has_vo, base_tag_ids) — tracked so we can build variants after insertion.
    pending_items: list[tuple[MenuItemFields, bool, list[str]]] = []
    caterer_updates: list[dict[str, Any]] = []

    for menu in parsed_menus:
        caterer_name = menu["Caterer Name"]
        caterer_id = caterer_name_to_id.get(caterer_name)
        if not caterer_id:
            log.warning(f"Caterer '{caterer_name}' not found in Caterers table — skipping.")
            continue

        price = float(menu["Price per Item"])
        if not menu["Price Includes GST"]:
            price = round(price * 1.10, 2)
        caterer_updates.append({"id": caterer_id, "fields": {
            "Delivery Fee":           menu["Delivery Fee"],
            "Delivery Fee Structure": menu["Delivery Fee Structure"],
            "Price Includes GST":     True,
            "Price per Item":         price,
        }})

        for item in menu["Items"]:
            tag_ids: list[str] = []
            for tag in item["Dietary Tags"]:
                rec_id = diet_name_to_id.get(tag)
                if rec_id:
                    tag_ids.append(rec_id)
                else:
                    log.warning(f"Dietary tag '{tag}' on '{item['Menu Item Name']}' not found — link dropped.")
            menu_record: MenuItemFields = {
                "Menu Item Name": item["Menu Item Name"],
                "Caterer":        [caterer_id],
                "Dietary Tags":   tag_ids,
            }
            note = item.get("Notes")
            if note:
                menu_record["Notes"] = note
            has_vo = bool(item.get("Has Vegetarian Option"))
            pending_items.append((menu_record, has_vo, tag_ids))

    if caterer_updates:
        log.info(f"Updating pricing for {len(caterer_updates)} caterer(s)...")
        db.Caterers.batch_update(caterer_updates)

    if not pending_items:
        log.info("Caterer menus migration completed successfully.")
        return

    # Pass 1 — insert all base items (VO items are not vegetarian themselves).
    base_records = [fields for fields, _, _ in pending_items]
    log.info(f"Migrating {len(base_records)} Menu Item(s)...")
    created = db.MenuItems.create(base_records)

    # Pass 2 — create a vegetarian variant for each VO-flagged item.
    veg_id = diet_name_to_id.get("Vegetarian")
    variant_records: list[MenuItemFields] = []
    for created_rec, (_, has_vo, base_tag_ids) in zip(created, pending_items):
        if not has_vo:
            continue
        variant_tag_ids = list(base_tag_ids)  # inherit GF/DF/NF/Halal from base
        if veg_id and veg_id not in variant_tag_ids:
            variant_tag_ids.append(veg_id)
        variant_name = f"{created_rec.fields['Menu Item Name']} (Vegetarian Option)"
        caterer_link = created_rec.fields.get("Caterer") or []
        variant_records.append({
            "Menu Item Name": variant_name,
            "Caterer":        caterer_link,
            "Dietary Tags":   variant_tag_ids,
            "Is Variant":     True,
            "Variant Of":     [created_rec.id],
        })

    if variant_records:
        log.info(f"Creating {len(variant_records)} vegetarian variant(s)...")
        db.MenuItems.create(variant_records)

    log.info("Caterer menus migration completed successfully.")


if __name__ == "__main__":
    run()
