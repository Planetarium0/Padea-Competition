import os
import sys
import re
import json
from pathlib import Path
from scripts import support as s

s.log.info("Migrating caterer-menus.pdf → Airtable (Menu Items)")

# Read extracted text
txt_path = Path.cwd() / "cache" / "caterer-menus.txt"
if not txt_path.is_file():
    s.log.error(f"Extracted menu text not found at {txt_path}. Please run PDF extraction first.")
    sys.exit(1)

raw_text = txt_path.read_text(encoding="utf-8")

# Clear Menu Items table
s.clear_table("Menu Items")

def parse_menus_heuristic(text):
    s.log.info("Using local heuristic menu parser...")
    
    # Locate each caterer's menu block
    # A block starts with "<Caterer Name> Menu ($..."
    header_pattern = r"([^\n(]+)\s*Menu\s*\(\$([\d.]+)\s*(including|excluding)\s*GST\s*per\s*item,\s*\$([\d.]+)\s*delivery\s*(per\s*school\s*per\s*trip|per\s*trip)?\)"
    
    matches = list(re.finditer(header_pattern, text))
    caterer_menus = []
    
    for idx, match in enumerate(matches):
        caterer_name = match.group(1).strip()
        item_price = float(match.group(2))
        gst_status = match.group(3).strip()
        delivery_fee = float(match.group(4))
        raw_structure = match.group(5)
        
        # Standardize structure
        if raw_structure:
            structure = "Per school per trip" if "school" in raw_structure.lower() else "Per trip"
        else:
            structure = "Per trip"

        price_includes_gst = (gst_status == "including")

        # Get the lines for this menu block
        start_pos = match.end()
        end_pos = matches[idx+1].start() if idx + 1 < len(matches) else len(text)
        menu_content = text[start_pos:end_pos].strip()
        
        items = []
        for line in menu_content.splitlines():
            line = line.strip()
            if not line or "dietary legend" in line.lower() or "gst" in line.lower() or "=" in line:
                continue
            
            # Parse line words to separate item name from dietary tags
            words = line.split()
            tags = []
            item_words = []
            for w in words:
                clean_w = w.strip(" ,()").upper()
                if clean_w in ["GF", "DF", "NF", "VO"]:
                    tags.append(clean_w)
                else:
                    item_words.append(w)
            
            item_name = " ".join(item_words).strip()
            if not item_name:
                continue

            # Convert tags to Airtable choice names
            dietary_choices = []
            for tag in tags:
                if tag == "GF":
                    dietary_choices.append("Gluten Free")
                elif tag == "DF":
                    dietary_choices.append("Dairy Free")
                elif tag == "NF":
                    dietary_choices.append("Nut Free")
                elif tag == "VO":
                    dietary_choices.append("Vegetarian")

            # Apply "Assume all non-pork meals are halal" rule
            if "pork" not in item_name.lower():
                dietary_choices.append("Halal")

            items.append({
                "Menu Item Name": item_name,
                "Dietary Tags": list(set(dietary_choices)),
                "Notes": None
            })

        caterer_menus.append({
            "Caterer Name": caterer_name,
            "Price per Item": item_price,
            "Price Includes GST": price_includes_gst,
            "Delivery Fee": delivery_fee,
            "Delivery Fee Structure": structure,
            "Items": items
        })
        
    return caterer_menus

parsed_menus = NotImplemented
key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if key:
    s.log.info("Using Claude LLM for batched menu parsing...")
    prompt = f"""You are a data extraction assistant.
Extract the menu items and delivery pricing structure for each caterer from the following raw menu text.
Return a JSON array of objects, where each object represents one caterer and has exactly these keys:
- "Caterer Name" (string, e.g. "Lakehouse Victoria Point")
- "Price per Item" (number, numeric price per item — caterers charge a flat per-item price across their whole menu)
- "Price Includes GST" (boolean, true if price includes GST, false if excluding GST)
- "Delivery Fee" (number, numeric delivery fee per trip)
- "Delivery Fee Structure" (string, either "Per trip" or "Per school per trip")
- "Items" (array of objects, where each object has:
    - "Menu Item Name" (string, e.g. "Shrimp Fried Rice")
    - "Dietary Tags" (array of strings, possible values: "Gluten Free", "Dairy Free", "Nut Free", "Vegetarian", "Halal")
    - "Notes" (string or null)
  )

Rules for Dietary Tags:
1. Map GF to "Gluten Free", DF to "Dairy Free", NF to "Nut Free", VO to "Vegetarian".
2. Critically: "Assume all non-pork meals are halal." If the item's name does not imply that it contains pork, automatically add the "Halal" tag.

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
    parsed_menus = parse_menus_heuristic(raw_text)

# Fetch Caterers to obtain record IDs
caterers_list = s.airtable_get("Caterers")
caterer_name_to_id = {c_rec["fields"]["Caterer Name"]: c_rec["id"] for c_rec in caterers_list}

# Fetch Dietary Restrictions for name → record-id lookup. The Menu Items
# 'Dietary Tags' field is now multipleRecordLinks → Dietary Restrictions.
diet_records = s.airtable_get("Dietary Restrictions")
diet_name_to_id = {r["fields"]["Restriction Name"]: r["id"] for r in diet_records}
if not diet_name_to_id:
    s.log.error("No Dietary Restrictions found in Airtable. Run the dietary "
                "restrictions migration first.")
    sys.exit(1)

# Update Caterers with pricing & deliver menu items
menu_items_records = []
caterer_updates = []

for menu in parsed_menus:
    caterer_name = menu["Caterer Name"]
    caterer_id = caterer_name_to_id.get(caterer_name)
    if not caterer_id:
        s.log.warning(f"Caterer '{caterer_name}' parsed from menus but not found in Caterers table. Skipping.")
        continue

    # Prepare caterer pricing update
    caterer_updates.append({
        "id": caterer_id,
        "fields": {
            "Delivery Fee": menu["Delivery Fee"],
            "Delivery Fee Structure": menu["Delivery Fee Structure"],
            "Price Includes GST": bool(menu["Price Includes GST"]),
            "Price per Item": menu["Price per Item"],
        }
    })

    # Prepare menu items
    for item in menu["Items"]:
        tag_ids = []
        for tag in item["Dietary Tags"]:
            rec_id = diet_name_to_id.get(tag)
            if rec_id:
                tag_ids.append(rec_id)
            else:
                s.log.warning(f"Dietary tag '{tag}' on item "
                              f"'{item['Menu Item Name']}' not in Dietary "
                              "Restrictions table — link dropped.")
        menu_items_records.append({
            "Menu Item Name": item["Menu Item Name"],
            "Caterer": [caterer_id],
            "Dietary Tags": tag_ids,
            "Notes": item.get("Notes")
        })

# 1. Update Caterers
if caterer_updates:
    s.log.info(f"Updating pricing structures for {len(caterer_updates)} caterers...")
    s.get_table("Caterers").batch_update(caterer_updates)

# 2. Insert Menu Items
if menu_items_records:
    s.log.info(f"Migrating {len(menu_items_records)} Menu Items...")
    s.airtable_post("Menu Items", menu_items_records)

s.log.info("Caterer menus migration completed successfully.")
