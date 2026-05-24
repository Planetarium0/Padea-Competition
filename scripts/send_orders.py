"""
send_orders.py — Format and send (log) caterer order emails for next week.

Reads all Weekly Orders with Status='Draft', aggregates the per-student Orders
records linked to each into per-session item counts, formats a caterer email,
and logs it to output/emails/ via send_email().

Does NOT actually send email — send_email() is a stub that writes to disk.

Usage:
  python scripts/send_orders.py [--preview]
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path
from collections import defaultdict

sys.path.append(str(Path(__file__).parent.parent.absolute()))
from scripts import support as s

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "emails"


# ---------------------------------------------------------------------------
# Fake send_email — logs to output/emails/ instead of actually sending
# ---------------------------------------------------------------------------

def send_email(to_email, cc_email, subject, body, filename_hint="email"):
    """Stub: write the email to output/emails/ rather than sending it."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_name  = filename_hint.replace(" ", "_").replace("—", "-").replace("/", "-")
    email_path = OUTPUT_DIR / f"{safe_name}.txt"

    header_lines = [f"To: {to_email}"]
    if cc_email:
        header_lines.append(f"CC: {cc_email}")
    header_lines.append(f"Subject: {subject}")
    header_lines.append("")

    email_path.write_text("\n".join(header_lines) + body, encoding="utf-8")
    s.log.info(f"[FAKE SEND] Email logged to: {email_path}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_draft_orders():
    orders = s.airtable_get("Weekly Orders", filter_formula="{Status}='Draft'")
    s.log.info(f"Found {len(orders)} draft Weekly Orders")
    return orders


def load_order_details(weekly_order_record):
    """
    Aggregate individual Orders records for a Weekly Order into line items.

    Returns (caterer_fields, line_items) where each line item is:
      {"quantity": int, "session": session_fields_dict, "menu_item": item_fields_dict}
    The session dict has extra keys "_school_name", "_manager_name", "_manager_mobile".
    """
    wo_id     = weekly_order_record["id"]
    wo_fields = weekly_order_record["fields"]

    caterer_id     = (wo_fields.get("Caterer") or [None])[0]
    caterer_fields = {}
    if caterer_id:
        rec = s.get_table("Caterers").get(caterer_id)
        caterer_fields = rec["fields"] if rec else {}

    # Fetch all per-student Orders for this Weekly Order
    individual_orders = s.airtable_get(
        "Orders",
        filter_formula=f"FIND('{wo_id}', ARRAYJOIN({{Weekly Order}}))"
    )
    s.log.info(f"  Found {len(individual_orders)} individual order records")

    # Aggregate: session_id → item_id → count
    session_item_counts = defaultdict(lambda: defaultdict(int))
    all_session_ids = set()
    all_item_ids    = set()

    for order in individual_orders:
        sess_id  = (order["fields"].get("Session")   or [None])[0]
        item_id  = (order["fields"].get("Menu Item") or [None])[0]
        quantity = order["fields"].get("Quantity", 1)
        if sess_id and item_id:
            session_item_counts[sess_id][item_id] += quantity
            all_session_ids.add(sess_id)
            all_item_ids.add(item_id)

    sessions_tbl  = s.get_table("Sessions")
    items_tbl     = s.get_table("Menu Items")
    schools_tbl   = s.get_table("Schools")
    managers_tbl  = s.get_table("On-Site Managers")

    session_map = {}
    for sid in all_session_ids:
        rec = sessions_tbl.get(sid)
        if not rec:
            continue
        sf = rec["fields"]
        school_links = sf.get("School") or []
        if school_links:
            s_rec = schools_tbl.get(school_links[0])
            if s_rec:
                sf["_school_name"] = s_rec["fields"].get("School Name", "?")
        mgr_links = sf.get("On-Site Manager") or []
        if mgr_links:
            m_rec = managers_tbl.get(mgr_links[0])
            if m_rec:
                sf["_manager_name"]   = m_rec["fields"].get("Manager Name", "?")
                sf["_manager_mobile"] = m_rec["fields"].get("Mobile", "?")
        session_map[sid] = sf

    item_map = {}
    for mid in all_item_ids:
        rec = items_tbl.get(mid)
        if rec:
            item_map[mid] = rec["fields"]

    line_items = [
        {
            "quantity":  count,
            "session":   session_map.get(sess_id, {}),
            "menu_item": item_map.get(item_id, {}),
        }
        for sess_id, item_counts in session_item_counts.items()
        for item_id, count in item_counts.items()
    ]

    return caterer_fields, line_items


# ---------------------------------------------------------------------------
# Email formatting
# ---------------------------------------------------------------------------

def format_email_body(wo_fields, caterer_fields, line_items):
    """Return the email body (without To/CC/Subject headers)."""
    week_start  = wo_fields.get("Week Start", "?")
    total_meals = wo_fields.get("Total Meals", 0)

    caterer_name  = caterer_fields.get("Caterer Name", "?")
    contact_name  = caterer_fields.get("Contact Name", "there") or "there"
    delivery_fee  = caterer_fields.get("Delivery Fee", 0) or 0
    fee_structure = caterer_fields.get("Delivery Fee Structure", "Per trip")

    try:
        week_display = datetime.strptime(week_start, "%Y-%m-%d").strftime("%-d %B %Y")
    except (ValueError, TypeError):
        week_display = week_start

    # Group line items by session
    by_session = defaultdict(list)
    for li in line_items:
        by_session[li["session"].get("Session ID", "unknown")].append(li)

    lines = []
    lines.append(f"Hi {contact_name.split()[0]},")
    lines.append("")
    lines.append(f"Here is the meal order for {caterer_name} for the week of {week_display}:")
    lines.append("")

    num_deliveries = 0
    for sess_key in sorted(by_session):
        items = by_session[sess_key]
        sess  = items[0]["session"]

        day            = sess.get("Day", "?")
        school_name    = sess.get("_school_name", "?")
        dinner_time    = sess.get("Dinner Time", "?")
        building       = sess.get("Building", "?")
        manager_name   = sess.get("_manager_name")
        manager_mobile = sess.get("_manager_mobile")

        lines.append(f"┌{'─'*58}┐")
        lines.append(f"│ {day.upper():56s} │")
        lines.append(f"│ {school_name:56s} │")

        delivery_info = f"Deliver by: {dinner_time}"
        if building:
            delivery_info += f" | Building: {building}"
        lines.append(f"│ {delivery_info:56s} │")

        if manager_name:
            mgr_str = f"On-site manager: {manager_name}"
            if manager_mobile:
                mgr_str += f" ({manager_mobile})"
            lines.append(f"│ {mgr_str:56s} │")

        lines.append(f"│{'':58s}│")

        session_total = 0
        for li in sorted(items, key=lambda x: -x["quantity"]):
            item_name = li["menu_item"].get("Menu Item Name", "?")
            qty       = li["quantity"]
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


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_orders(preview_only=False):
    draft_orders = load_draft_orders()
    if not draft_orders:
        s.log.info("No draft orders to process.")
        return

    for wo_record in draft_orders:
        wo_fields    = wo_record["fields"]
        wo_id_label  = wo_fields.get("Order ID", wo_record["id"])
        s.log.info(f"\nProcessing: {wo_id_label}")

        caterer_fields, line_items = load_order_details(wo_record)

        if not line_items:
            s.log.warning(f"No order records found for '{wo_id_label}' — skipping.")
            continue

        week_start = wo_fields.get("Week Start", "?")
        try:
            week_display = datetime.strptime(week_start, "%Y-%m-%d").strftime("%-d %B %Y")
        except (ValueError, TypeError):
            week_display = week_start

        contact_email = caterer_fields.get("Contact Email", "")
        chef_email    = (
            caterer_fields.get("Chef Email")
            if caterer_fields.get("Chef Wants CC")
            else None
        )
        subject  = f"Padea Meal Order — Week of {week_display}"
        body     = format_email_body(wo_fields, caterer_fields, line_items)

        # Print to stdout
        print(f"\n{'='*62}")
        to_line = f"To: {contact_email}"
        if chef_email:
            to_line += f"  CC: {chef_email}"
        print(to_line)
        print(f"Subject: {subject}")
        print()
        print(body)
        print("=" * 62)

        if not preview_only:
            send_email(
                to_email=contact_email,
                cc_email=chef_email,
                subject=subject,
                body=body,
                filename_hint=wo_id_label,
            )
            try:
                s.get_table("Weekly Orders").update(wo_record["id"], {"Status": "Sent"})
                s.log.info(f"Marked '{wo_id_label}' as Sent.")
            except Exception as e:
                s.log.error(f"Failed to mark '{wo_id_label}' as Sent: {e}")
        else:
            s.log.info(f"[PREVIEW] Would send to {contact_email}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send caterer order emails")
    parser.add_argument("--preview", action="store_true",
                        help="Preview emails without sending or marking as Sent")
    args = parser.parse_args()
    process_orders(preview_only=args.preview)
