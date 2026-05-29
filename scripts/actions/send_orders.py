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

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from support import (
    CatererFields,
    Database,
    MenuItemFields,
    OnSiteManagerFields,
    Record,
    SchoolFields,
    SessionFields,
    WeeklyOrderFields,
    load_substitutions,
    log,
    resolve_manager_id,
)


# ---------------------------------------------------------------------------
# Per-line data carried into the email template
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionContext:
    """Session fields enriched with the school + on-site manager details
    needed by the email template."""

    fields:            SessionFields
    school_name:       str
    manager_name:      str | None
    manager_mobile:    str | None
    manager_email:     str | None
    manager_is_sub:    bool = False


@dataclass(frozen=True)
class LineItem:
    quantity:  int
    session:   SessionContext
    menu_item: MenuItemFields


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def subtract_minutes(time_str: str | None, minutes: int = 10) -> str:
    """Parse a time string, subtract minutes, return a formatted string.

    Handles common formats like '6:30 PM', '18:30', '6:30pm'.
    Returns the original string unchanged if parsing fails.
    """
    if not time_str or time_str == "?":
        return time_str or "?"
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

def schedule_email(
    db:                          Database,
    to_email:                    str,
    cc_email:                    list[str] | None,
    subject:                     str,
    body:                        str,
    email_id:                    str,
    immediate:                   bool = False,
    weekly_order_id:             str | None = None,
    caterer_switch_proposal_id:  str | None = None,
) -> None:
    """Create a Queued record in the Scheduled Emails table.

    Exactly one of ``weekly_order_id`` or ``caterer_switch_proposal_id`` should
    be provided so the email is traceable back to its source record.
    """
    fields: dict[str, object] = {
        "Email ID":  email_id,
        "To":        to_email,
        "Subject":   subject,
        "Body":      body,
        "Status":    "Send Immediately" if immediate else "Queued",
        "Send Date": None,  # set when actually sent by automation
    }
    if cc_email:
        fields["CC"] = ", ".join(cc_email)
    if weekly_order_id:
        fields["Weekly Order"] = [weekly_order_id]
    if caterer_switch_proposal_id:
        fields["Caterer Switch Proposal"] = [caterer_switch_proposal_id]
    db.ScheduledEmails.create([fields])
    log.info(f"[QUEUED] Email record created: {email_id}")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_pending_orders(db: Database) -> list[Record[WeeklyOrderFields]]:
    orders = db.WeeklyOrders.all(formula="{Week Start} >= TODAY()")
    log.info(f"Found {len(orders)} Weekly Orders")
    return orders


def load_order_details(
    db:                    Database,
    weekly_order_record:   Record[WeeklyOrderFields],
) -> tuple[CatererFields, list[LineItem]]:
    """Aggregate individual Orders records for a Weekly Order into line items."""
    wo_id     = weekly_order_record.id
    wo_fields = weekly_order_record.fields

    caterer_id     = (wo_fields.get("Caterer") or [None])[0]
    caterer_fields: CatererFields = {}
    if caterer_id:
        rec = db.Caterers.get(caterer_id)
        if rec:
            caterer_fields = rec.fields

    # Fetch Orders for this week by date range, then filter by record ID
    # client-side. ARRAYJOIN({Weekly Order}) returns primary-field values, not
    # record IDs, so we can't use it to search for wo_id directly.
    week_start = wo_fields.get("Week Start", "")
    if week_start:
        monday = datetime.strptime(week_start, "%Y-%m-%d").date()
        friday = (monday + timedelta(days=4)).isoformat()
        all_orders = db.Orders.all(
            formula=f"AND({{Date}} >= '{week_start}', {{Date}} <= '{friday}')",
        )
    else:
        all_orders = db.Orders.all()
    individual_orders = [
        o for o in all_orders
        if wo_id in (o.fields.get("Weekly Order") or [])
    ]
    log.info(f"  Found {len(individual_orders)} individual order records")

    # Load any substitutions covering the order week in one round-trip.
    substitutions = load_substitutions(db, week_start, friday) if week_start else {}

    # Aggregate: session_id → item_id → count; also capture a date per session.
    session_item_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    session_dates: dict[str, str] = {}
    all_session_ids: set[str] = set()
    all_item_ids: set[str] = set()

    for order in individual_orders:
        sess_id  = (order.fields.get("Session")   or [None])[0]
        item_id  = (order.fields.get("Menu Item") or [None])[0]
        quantity = order.fields.get("Quantity", 1)
        if sess_id and item_id:
            session_item_counts[sess_id][item_id] += quantity
            all_session_ids.add(sess_id)
            all_item_ids.add(item_id)
            if sess_id not in session_dates and order.fields.get("Date"):
                session_dates[sess_id] = order.fields["Date"]

    session_map: dict[str, SessionContext] = {}
    for sid in all_session_ids:
        rec = db.Sessions.get(sid)
        if not rec:
            continue
        sf = rec.fields
        school_name = "?"
        manager_name: str | None = None
        manager_mobile: str | None = None
        manager_email: str | None = None

        school_links = sf.get("School") or []
        if school_links:
            s_rec: Record[SchoolFields] | None = db.Schools.get(school_links[0])
            if s_rec:
                school_name = s_rec.fields.get("School Name", "?")

        mgr_id, is_sub = resolve_manager_id(sid, sf, session_dates.get(sid), substitutions)
        if mgr_id:
            m_rec: Record[OnSiteManagerFields] | None = db.OnSiteManagers.get(mgr_id)
            if m_rec:
                manager_name   = m_rec.fields.get("Manager Name")
                manager_mobile = m_rec.fields.get("Mobile")
                manager_email  = m_rec.fields.get("Email")

        session_map[sid] = SessionContext(
            fields=sf,
            school_name=school_name,
            manager_name=manager_name,
            manager_mobile=manager_mobile,
            manager_email=manager_email,
            manager_is_sub=is_sub,
        )

    item_map: dict[str, MenuItemFields] = {}
    for mid in all_item_ids:
        rec = db.MenuItems.get(mid)
        if rec:
            item_map[mid] = rec.fields

    line_items: list[LineItem] = []
    for sess_id, item_counts in session_item_counts.items():
        sess_ctx = session_map.get(sess_id)
        if sess_ctx is None:
            continue
        for item_id, count in item_counts.items():
            menu = item_map.get(item_id)
            if menu is None:
                continue
            line_items.append(LineItem(quantity=count, session=sess_ctx, menu_item=menu))

    return caterer_fields, line_items


# ---------------------------------------------------------------------------
# Email formatting — Markdown (Airtable-supported subset, no tables)
# ---------------------------------------------------------------------------

def format_email_body(
    wo_fields:      WeeklyOrderFields,
    caterer_fields: CatererFields,
    line_items:     list[LineItem],
) -> str:
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

    by_session: dict[str, list[LineItem]] = defaultdict(list)
    for li in line_items:
        by_session[li.session.fields.get("Session ID", "unknown")].append(li)

    num_deliveries = 0
    blocks: list[str] = []

    for sess_key in sorted(by_session):
        items = by_session[sess_key]
        sess  = items[0].session

        day            = sess.fields.get("Day", "?")
        school_name    = sess.school_name
        dinner_time    = sess.fields.get("Dinner Time", "?")
        building       = sess.fields.get("Building", "")
        manager_name   = sess.manager_name or ""
        manager_mobile = sess.manager_mobile or ""

        deliver_by = subtract_minutes(dinner_time)

        manager_is_sub = sess.manager_is_sub

        block = [f"## {day} — {school_name}"]
        block.append(f"**Deliver by:** {deliver_by}")
        if building:
            block.append(f"**Building:** {building}")
        if manager_name:
            mgr = manager_name
            if manager_mobile:
                mgr += f" ({manager_mobile})"
            label = "On-site manager (substitute)" if manager_is_sub else "On-site manager"
            block.append(f"**{label}:** {mgr}")

        block.append("")
        session_total = 0
        for li in sorted(items, key=lambda x: -x.quantity):
            item_name = li.menu_item.get("Menu Item Name", "?")
            session_total += li.quantity
            block.append(f"- {item_name} ×{li.quantity}")

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

def process_orders(db: Database | None = None, preview_only: bool = False) -> None:
    db = db or Database.from_env()
    pending_orders = load_pending_orders(db)
    if not pending_orders:
        log.info("No pending orders to process.")
        return

    for wo_record in pending_orders:
        wo_fields   = wo_record.fields
        wo_id_label = wo_fields.get("Order ID", wo_record.id)
        log.info(f"\nProcessing: {wo_id_label}")

        caterer_fields, line_items = load_order_details(db, wo_record)

        if not line_items:
            log.warning(f"No order records found for '{wo_id_label}' — skipping.")
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
        # Do not cc chef if chef is main contact
        if chef_email == contact_email:
            chef_email = None

        # Collect unique on-site manager emails across all sessions in this order.
        seen: set[str] = set()
        cc_list: list[str] = []
        for addr in ([chef_email] if chef_email else []) + [
            li.session.manager_email
            for li in line_items
            if li.session.manager_email
        ]:
            if addr not in seen:
                seen.add(addr)
                cc_list.append(addr)

        subject = f"Padea Meal Order — Week of {week_display}"
        body    = format_email_body(wo_fields, caterer_fields, line_items)

        if not preview_only:
            email_id = f"EMAIL-{week_start}-{wo_record.id[:8]}"
            schedule_email(
                db,
                to_email=contact_email,
                cc_email=cc_list or None,
                subject=subject,
                body=body,
                email_id=email_id,
                weekly_order_id=wo_record.id,
            )
        else:
            log.info(f"[PREVIEW] Would send to {contact_email}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send caterer order emails")
    parser.add_argument(
        "--preview", action="store_true",
        help="Preview emails without sending or marking as Sent",
    )
    args = parser.parse_args()
    process_orders(preview_only=args.preview)
