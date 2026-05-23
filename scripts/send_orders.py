"""
send_orders.py — Format and log caterer order emails.

Reads Weekly Orders with Status="Draft" from Airtable, formats a structured
email for each caterer, and logs it to stdout + output/emails/.

Does NOT actually send emails — this is a testing/preview tool.

Usage:
  python scripts/send_orders.py [--preview]
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

# Add repository root to system path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from scripts import support as s

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "emails"


def load_draft_orders():
    """Load all Weekly Orders with Status=Draft."""
    orders = s.airtable_get("Weekly Orders", filter_formula="{Status}='Draft'")
    s.log.info(f"Found {len(orders)} draft orders")
    return orders


def load_order_details(order_record):
    """Load all related data for a single Weekly Order."""
    order_id = order_record["id"]
    fields = order_record["fields"]

    # Get caterer info
    caterer_id = fields.get("Caterer", [None])[0]
    caterer = None
    if caterer_id:
        recs = s.airtable_get("Caterers", filter_formula=f"RECORD_ID()='{caterer_id}'")
        caterer = recs[0]["fields"] if recs else {}

    # Get line items for this order
    line_items = s.airtable_get(
        "Order Line Items",
        filter_formula=f"FIND('{order_id}', {{Line Item ID}})"
    )

    # Resolve each line item's session and menu item details
    resolved_items = []
    for li in line_items:
        li_fields = li["fields"]
        session_id = li_fields.get("Session", [None])[0]
        menu_item_id = li_fields.get("Menu Item", [None])[0]

        session_fields = {}
        if session_id:
            recs = s.airtable_get("Sessions", filter_formula=f"RECORD_ID()='{session_id}'")
            if recs:
                session_fields = recs[0]["fields"]
                # Resolve school name
                school_links = session_fields.get("School", [])
                if school_links:
                    school_recs = s.airtable_get("Schools", filter_formula=f"RECORD_ID()='{school_links[0]}'")
                    if school_recs:
                        session_fields["_school_name"] = school_recs[0]["fields"].get("School Name", "?")
                # Resolve on-site manager
                mgr_links = session_fields.get("On-Site Manager", [])
                if mgr_links:
                    mgr_recs = s.airtable_get("On-Site Managers", filter_formula=f"RECORD_ID()='{mgr_links[0]}'")
                    if mgr_recs:
                        session_fields["_manager_name"] = mgr_recs[0]["fields"].get("Manager Name", "?")
                        session_fields["_manager_mobile"] = mgr_recs[0]["fields"].get("Mobile", "?")

        menu_item_fields = {}
        if menu_item_id:
            recs = s.airtable_get("Menu Items", filter_formula=f"RECORD_ID()='{menu_item_id}'")
            if recs:
                menu_item_fields = recs[0]["fields"]

        resolved_items.append({
            "quantity": li_fields.get("Quantity", 0),
            "session": session_fields,
            "menu_item": menu_item_fields,
        })

    return caterer, resolved_items


def format_email(order_fields, caterer, line_items):
    """Format a structured order email."""
    order_id = order_fields.get("Order ID", "?")
    round_label = order_fields.get("Round", "?")
    week_start = order_fields.get("Week Start", "?")
    total_meals = order_fields.get("Total Meals", 0)
    total_cost = order_fields.get("Total Cost", 0)

    caterer_name = caterer.get("Caterer Name", "?") if caterer else "?"
    contact_name = caterer.get("Contact Name", "there") if caterer else "there"
    contact_email = caterer.get("Contact Email", "?") if caterer else "?"
    chef_email = caterer.get("Chef Email") if caterer else None
    chef_wants_cc = caterer.get("Chef Wants CC", False) if caterer else False
    delivery_fee = caterer.get("Delivery Fee", 0) if caterer else 0
    fee_structure = caterer.get("Delivery Fee Structure", "Per trip") if caterer else "Per trip"

    # Format week start nicely
    try:
        ws_date = datetime.strptime(week_start, "%Y-%m-%d")
        week_display = ws_date.strftime("%-d %B %Y")
    except (ValueError, TypeError):
        week_display = week_start

    # Group line items by session
    by_session = defaultdict(list)
    for li in line_items:
        sess = li["session"]
        sess_key = sess.get("Session ID", "Unknown")
        by_session[sess_key].append(li)

    # Build email
    lines = []
    lines.append(f"Subject: Padea Meal Order — Week of {week_display} ({round_label})")
    lines.append("")

    to_line = f"To: {contact_email}"
    if chef_wants_cc and chef_email:
        to_line += f"  CC: {chef_email}"
    lines.append(to_line)
    lines.append("")
    lines.append(f"Hi {contact_name.split()[0] if contact_name else 'there'},")
    lines.append("")
    lines.append(f"Here is the meal order for {caterer_name} for the week of {week_display}:")
    lines.append("")

    num_deliveries = 0
    for sess_key, items in sorted(by_session.items()):
        sess = items[0]["session"]
        day = sess.get("Day", "?")
        school_name = sess.get("_school_name", "?")
        delivery_time = sess.get("Dinner Time", "?")
        building = sess.get("Building", "?")
        manager_name = sess.get("_manager_name")
        manager_mobile = sess.get("_manager_mobile")

        lines.append(f"┌{'─'*58}┐")
        lines.append(f"│ {day.upper():56s} │")
        lines.append(f"│ {school_name:56s} │")

        delivery_info = f"Deliver by: {delivery_time}"
        if building:
            delivery_info += f" | Building: {building}"
        lines.append(f"│ {delivery_info:56s} │")

        if manager_name:
            mgr_info = f"On-site manager: {manager_name}"
            if manager_mobile:
                mgr_info += f" ({manager_mobile})"
            lines.append(f"│ {mgr_info:56s} │")

        lines.append(f"│{'':58s}│")

        session_total = 0
        for li in sorted(items, key=lambda x: -x["quantity"]):
            item_name = li["menu_item"].get("Menu Item Name", "?")
            qty = li["quantity"]
            item_line = f"  {item_name:42s} ×{qty}"
            lines.append(f"│{item_line:58s}│")
            session_total += qty

        lines.append(f"│{'':58s}│")
        lines.append(f"│  {'─'*54}  │")
        subtotal_line = f"  {'Subtotal':42s} ×{session_total}"
        lines.append(f"│{subtotal_line:58s}│")
        lines.append(f"└{'─'*58}┘")
        lines.append("")
        num_deliveries += 1

    # Delivery fee calculation
    if fee_structure == "Per school per trip":
        total_delivery = delivery_fee * num_deliveries
        fee_note = f"{num_deliveries} deliveries × ${delivery_fee:.2f}"
    else:
        total_delivery = delivery_fee
        fee_note = f"${delivery_fee:.2f} per trip"

    lines.append(f"GRAND TOTAL: {total_meals} meals")
    lines.append(f"Delivery fee: ${total_delivery:.2f} ({fee_note})")
    lines.append("")
    lines.append("Thanks,")
    lines.append("Padea")

    return "\n".join(lines)


def process_orders(preview_only=False):
    """Process all draft orders."""
    orders = load_draft_orders()

    if not orders:
        s.log.info("No draft orders to process.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for order in orders:
        order_fields = order["fields"]
        order_id = order_fields.get("Order ID", "unknown")

        s.log.info(f"Processing order: {order_id}")

        caterer, line_items = load_order_details(order)
        email_text = format_email(order_fields, caterer, line_items)

        # Log to stdout
        print("\n" + "=" * 62)
        print(email_text)
        print("=" * 62)

        # Save to file
        safe_name = order_id.replace(" ", "_").replace("—", "-").replace("/", "-")
        email_path = OUTPUT_DIR / f"{safe_name}.txt"
        email_path.write_text(email_text, encoding="utf-8")
        s.log.info(f"Email saved to: {email_path}")

        if not preview_only:
            # Mark as "Sent" in Airtable (even though we didn't actually send)
            s.log.info(f"[LOG] Email would be sent to: {caterer.get('Contact Email', '?')}")
            try:
                table = s.get_table("Weekly Orders")
                table.update(order["id"], {"Status": "Sent"})
                s.log.info(f"Order status updated to 'Sent'")
            except Exception as e:
                s.log.error(f"Failed to update order status: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Format and log caterer order emails")
    parser.add_argument(
        "--preview", action="store_true",
        help="Preview emails without marking orders as sent"
    )
    args = parser.parse_args()

    process_orders(preview_only=args.preview)
