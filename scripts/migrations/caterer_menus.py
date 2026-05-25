import os
import sys
import re
import json
from pathlib import Path
import support as s


def _parse_menus_heuristic(text):
    s.log.info("Using local heuristic menu parser...")
    header_pattern = (
        r"([^\n(]+)\s*Menu\s*\(\$([\d.]+)\s*(including|excluding)\s*GST\s*per\s*item,"
        r"\s*\$([\d.]+)\s*delivery\s*(per\s*school\s*per\s*trip|per\s*trip)?\)"
    )
    matches = list(re.finditer(header_pattern, text))
    caterer_menus = []
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

        items = []
        for line in menu_content.splitlines():
            line = line.strip()
            if not line or "dietary legend" in line.lower() or "gst" in line.lower() or "=" in line:
                continue
            tags       = []
            item_words = []
            for w in line.split():
                clean_w = w.strip(" ,()").upper()
                if clean_w in ("GF", "DF", "NF", "VO"):
                    tags.append(clean_w)
                else:
                    item_words.append(w)
            item_name = " ".join(item_words).strip()
            if not item_name:
                continue
            tag_map = {"GF": "Gluten Free", "DF": "Dairy Free", "NF": "Nut Free", "VO": "Vegetarian"}
            dietary = [tag_map[t] for t in tags if t in tag_map]
            _PORK_WORDS = ("pork", "bacon", "ham", "prosciutto", "pancetta", "lard", "salami", "chorizo")
            if not any(w in item_name.lower() for w in _PORK_WORDS):
                dietary.append("Halal")
            items.append({"Menu Item Name": item_name, "Dietary Tags": list(set(dietary)), "Notes": None})

        caterer_menus.append({
            "Caterer Name":         caterer_name,
            "Price per Item":       item_price,
            "Price Includes GST":   price_incl_gst,
            "Delivery Fee":         delivery_fee,
            "Delivery Fee Structure": structure,
            "Items":                items,
        })
    return caterer_menus


def run():
    s.log.info("Migrating caterer-menus.pdf → Airtable (Menu Items)")
    s.clear_table("Menu Items")

    txt_path = Path.cwd() / "cache" / "caterer-menus.txt"
    if not txt_path.is_file():
        s.log.error(f"Extracted menu text not found at {txt_path}. Run PDF extraction first.")
        sys.exit(1)
    raw_text = txt_path.read_text(encoding="utf-8")

    parsed_menus = NotImplemented
    key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    if key:
        s.log.info("Using Claude LLM for batched menu parsing...")
        prompt = f"""You are a data extraction assistant.
Extract the menu items and delivery pricing structure for each caterer from the following raw menu text.
Return a JSON array of objects, where each object represents one caterer and has exactly these keys:
- "Caterer Name" (string, e.g. "Lakehouse Victoria Point")
- "Price per Item" (number, flat per-item price)
- "Price Includes GST" (boolean)
- "Delivery Fee" (number)
- "Delivery Fee Structure" (string, either "Per trip" or "Per school per trip")
- "Items" (array of objects with "Menu Item Name", "Dietary Tags", "Notes")

Dietary tag rules:
1. Map GF→"Gluten Free", DF→"Dairy Free", NF→"Nut Free", VO→"Vegetarian".
2. Add "Halal" to any item whose name does not imply pork.

Raw Menu Text:
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
                parsed_menus = json.loads(json_str)
                s.log.info("LLM successfully parsed all menus!")
            except Exception as e:
                s.log.error(f"LLM returned malformed JSON: {e}. Falling back to heuristic.")

    if parsed_menus is NotImplemented or not parsed_menus:
        parsed_menus = _parse_menus_heuristic(raw_text)

    caterers_list      = s.airtable_get("Caterers")
    caterer_name_to_id = {c["fields"]["Caterer Name"]: c["id"] for c in caterers_list}

    diet_records   = s.airtable_get("Dietary Restrictions")
    diet_name_to_id = {r["fields"]["Restriction Name"]: r["id"] for r in diet_records}
    if not diet_name_to_id:
        s.log.error("No Dietary Restrictions found. Run dietary_restrictions migration first.")
        sys.exit(1)

    menu_items_records = []
    caterer_updates    = []

    for menu in parsed_menus:
        caterer_name = menu["Caterer Name"]
        caterer_id   = caterer_name_to_id.get(caterer_name)
        if not caterer_id:
            s.log.warning(f"Caterer '{caterer_name}' not found in Caterers table — skipping.")
            continue

        caterer_updates.append({"id": caterer_id, "fields": {
            "Delivery Fee":           menu["Delivery Fee"],
            "Delivery Fee Structure": menu["Delivery Fee Structure"],
            "Price Includes GST":     bool(menu["Price Includes GST"]),
            "Price per Item":         menu["Price per Item"],
        }})

        for item in menu["Items"]:
            tag_ids = []
            for tag in item["Dietary Tags"]:
                rec_id = diet_name_to_id.get(tag)
                if rec_id:
                    tag_ids.append(rec_id)
                else:
                    s.log.warning(f"Dietary tag '{tag}' on '{item['Menu Item Name']}' not found — link dropped.")
            menu_items_records.append({
                "Menu Item Name": item["Menu Item Name"],
                "Caterer":        [caterer_id],
                "Dietary Tags":   tag_ids,
                "Notes":          item.get("Notes"),
            })

    if caterer_updates:
        s.log.info(f"Updating pricing for {len(caterer_updates)} caterer(s)...")
        s.get_table("Caterers").batch_update(caterer_updates)
    if menu_items_records:
        s.log.info(f"Migrating {len(menu_items_records)} Menu Item(s)...")
        s.airtable_post("Menu Items", menu_items_records)

    s.log.info("Caterer menus migration completed successfully.")


if __name__ == "__main__":
    run()
