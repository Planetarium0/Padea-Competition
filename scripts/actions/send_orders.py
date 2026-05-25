"""
send_orders.py — Format and queue caterer order emails for next week.

Reads all Weekly Orders whose Week Start is >= today, aggregates the
per-session Orders records linked to each into per-item counts, formats a
caterer email, and creates a record in the 'Scheduled Emails' Airtable table
with Status='Queued'. Airtable automations watch that table to trigger actual
sending.

Usage:
  python scripts/send_orders.py [--preview]
"""

import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import support as s


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def subtract_minutes(time_str, minutes=10):
    """Parse a time string, subtract minutes, return a formatted string.

    Handles common formats like '6:30 PM', '18:30', '6:30pm'.
    Returns the original string unchanged if parsing fails.
    """
    if not time_str or time_str == "?":
        return time_str
    for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p"):
        try:
            t = datetime.strptime(time_str.strip().upper(), fmt.upper())
            t -= timedelta(minutes=minutes)
            return t.strftime("%-I:%M %p")
        except ValueError:
            continue
    return time_str


# ---------------------------------------------------------------------------
# Schedule email — writes to Airtable 'Scheduled Emails' table
# ---------------------------------------------------------------------------

def schedule_email(to_email, cc_email, subject, body, email_id, immediate=False,
                   weekly_order_id=None, caterer_switch_proposal_id=None):
    """Create a Queued record in the Scheduled Emails table.

    Exactly one of weekly_order_id or caterer_switch_proposal_id should be
    provided so the email is traceable back to its source record.
    """
    fields = {
        "Email ID": email_id,
        "To": to_email,
        "Subject": subject,
        "Body": body,
        "Status": "Send Immediately" if immediate else "Queued",
        "Send Date": None, # set when actually sent by automation
    }
    if cc_email:
        fields["CC"] = cc_email
    if weekly_order_id:
        fields["Weekly Order"] = [weekly_order_id]
    if caterer_switch_proposal_id:
        fields["Caterer Switch Proposal"] = [caterer_switch_proposal_id]
    s.airtable_post("Scheduled Emails", [{"fields": fields}])
    s.log.info(f"[QUEUED] Email record created: {email_id}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_pending_orders():
    orders = s.airtable_get("Weekly Orders", filter_formula="{Week Start} >= TODAY()")
    s.log.info(f"Found {len(orders)} Weekly Orders")
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

    # Fetch Orders for this week by date range, then filter by record ID
    # client-side. ARRAYJOIN({Weekly Order}) returns primary-field values, not
    # record IDs, so we can't use it to search for wo_id directly.
    week_start = wo_fields.get("Week Start", "")
    if week_start:
        monday = datetime.strptime(week_start, "%Y-%m-%d").date()
        friday = (monday + timedelta(days=4)).isoformat()
        all_orders = s.airtable_get(
            "Orders",
            filter_formula=f"AND({{Date}} >= '{week_start}', {{Date}} <= '{friday}')"
        )
    else:
        all_orders = s.airtable_get("Orders")
    individual_orders = [
        o for o in all_orders
        if wo_id in (o["fields"].get("Weekly Order") or [])
    ]
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
# Email formatting — Markdown (Airtable-supported subset, no tables)
# ---------------------------------------------------------------------------


def format_email_body(wo_fields, caterer_fields, line_items):
    """Return a Markdown email body using only Airtable-supported formatting."""
    week_start  = wo_fields.get("Week Start", "?")
    total_meals = wo_fields.get("Total Meals", 0)

    caterer_name  = caterer_fields.get("Caterer Name", "?")
    contact_name  = caterer_fields.get("Contact Name", "there") or "there"
    first_name    = contact_name.split()[0]
    delivery_fee  = caterer_fields.get("Delivery Fee", 0) or 0
    fee_structure = caterer_fields.get("Delivery Fee Structure", "Per trip")

    try:
        week_display = datetime.strptime(week_start, "%Y-%m-%d").strftime("%-d %B %Y")
    except (ValueError, TypeError):
        week_display = week_start

    by_session = defaultdict(list)
    for li in line_items:
        by_session[li["session"].get("Session ID", "unknown")].append(li)

    num_deliveries = 0
    blocks = []

    for sess_key in sorted(by_session):
        items = by_session[sess_key]
        sess  = items[0]["session"]

        day            = sess.get("Day", "?")
        school_name    = sess.get("_school_name", "?")
        dinner_time    = sess.get("Dinner Time", "?")
        building       = sess.get("Building", "")
        manager_name   = sess.get("_manager_name", "")
        manager_mobile = sess.get("_manager_mobile", "")

        deliver_by = subtract_minutes(dinner_time)

        block = [f"## {day} — {school_name}"]
        block.append(f"**Deliver by:** {deliver_by}")
        if building:
            block.append(f"**Building:** {building}")
        if manager_name:
            mgr = manager_name
            if manager_mobile:
                mgr += f" ({manager_mobile})"
            block.append(f"**On-site manager:** {mgr}")

        block.append("")
        session_total = 0
        for li in sorted(items, key=lambda x: -x["quantity"]):
            item_name = li["menu_item"].get("Menu Item Name", "?")
            qty       = li["quantity"]
            session_total += qty
            block.append(f"- {item_name} ×{qty}")

        block.append("")
        block.append(f"**Subtotal: {session_total} meals**")

        blocks.append("\n".join(block))
        num_deliveries += 1

    if fee_structure == "Per school per trip":
        total_delivery = delivery_fee * num_deliveries
        fee_note = f"{num_deliveries} deliveries × ${delivery_fee:.2f}"
    else:
        total_delivery = delivery_fee
        fee_note = f"${delivery_fee:.2f} per trip"

    sections = "\n\n".join(blocks)

    return (
        f"Hi {first_name},\n\n"
        f"Here is the meal order for **{caterer_name}** for the week of **{week_display}**:\n\n"
        f"{sections}\n\n"
        f"---\n\n"
        f"**Grand total: {total_meals} meals**\n"
        f"**Delivery fee:** ${total_delivery:.2f} ({fee_note})\n\n"
        f"Thanks,\n"
        f"Padea"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_orders(preview_only=False):
    pending_orders = load_pending_orders()
    if not pending_orders:
        s.log.info("No pending orders to process.")
        return

    for wo_record in pending_orders:
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

        # Don't preview email
        # print(f"\n{'='*62}")
        # print(f"To:      {contact_email}")
        # if chef_email:
        #     print(f"CC:      {chef_email}")
        # print(f"Subject: {subject}")
        # print()
        # print(body)
        # print("=" * 62)

        if not preview_only:
            email_id  = f"EMAIL-{week_start}-{wo_record['id'][:8]}"
            schedule_email(
                to_email=contact_email,
                cc_email=chef_email,
                subject=subject,
                body=body,
                email_id=email_id,
                weekly_order_id=wo_record["id"],
            )
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
