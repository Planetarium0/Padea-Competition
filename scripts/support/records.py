"""
Typed record models for the Padea Supabase database.

For every table we expose:
  - ``<Name>Fields`` — a ``TypedDict`` describing the shape returned by
    ``Table.all()`` / ``Table.get()``. Fields match Postgres column names
    (snake_case). Linked fields that were multi-record arrays in Airtable
    are either scalar FKs (one-to-many) or UUID list fields aggregated by
    the corresponding *_view (many-to-many via junction tables).
  - ``<Name>Record`` — alias for ``Record[<Name>Fields]``.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


# ---------------------------------------------------------------------------
# Enum-like literals
# ---------------------------------------------------------------------------

Region = Literal[
    "Redlands",
    "South Brisbane",
    "West Brisbane",
    "Central Brisbane",
]
DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DeliveryFeeStructure = Literal["Per trip", "Per school per trip"]
ClarificationStatus = Literal["Open", "Clarifying", "Resolved", "Escalated", "Cancelled"]
SupportCaseStatus = Literal["Open", "Resolved", "Escalated"]
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
ProposalStatus = Literal["Pending", "Approved", "Rejected", "Executed"]
YearLevel = Literal["All", "12", "11", "10", "9", "8", "7", "6"]


# ---------------------------------------------------------------------------
# Per-table field shapes
# ---------------------------------------------------------------------------

SchoolFields = TypedDict(
    "SchoolFields",
    {
        "id": str,
        "name": str,
        "region": Region,
    },
    total=False,
)

OnSiteManagerFields = TypedDict(
    "OnSiteManagerFields",
    {
        "id": str,
        "name": str,
        "mobile": str,
        "email": str,
    },
    total=False,
)

CatererFields = TypedDict(
    "CatererFields",
    {
        "id": str,
        "name": str,
        "region": Region,
        "min_qty_4_items": int,
        "min_qty_5_items": int,
        "min_qty_6_items": int,
        "price_per_item": float,
        "contact_name": str,
        "contact_email": str,
        "chef_name": str,
        "chef_email": str,
        "chef_wants_cc": bool,
        "delivery_fee": float,
        "delivery_fee_structure": DeliveryFeeStructure,
        "notes": str,
        "pending_dietary_clarify": bool,
        # Aggregated by caterers_view
        "legend_tag_ids": list[str],
        "able_to_serve_school_ids": list[str],
    },
    total=False,
)

MenuItemFields = TypedDict(
    "MenuItemFields",
    {
        "id": str,
        "name": str,
        "caterer_id": str,
        "is_variant": bool,
        "variant_of_id": str,
        "notes": str,
        # Aggregated by menu_items_view
        "dietary_tag_ids": list[str],
        "unavailable_days": list[str],
    },
    total=False,
)

DietaryRestrictionFields = TypedDict(
    "DietaryRestrictionFields",
    {
        "id": str,
        "name": str,
        # Aggregated by dietary_restrictions_view
        "superset_ids": list[str],
        "subset_ids": list[str],
    },
    total=False,
)

StudentFields = TypedDict(
    "StudentFields",
    {
        "id": str,
        "name": str,
        "year_level": int,
        "subjects": str,
        "email": str,
        "parent_name": str,
        "parent_email": str,
        "parent_mobile": str,
        "meal_preference_id": str,
        "last_submitted": str,
        # Aggregated by students_view
        "dietary_requirement_ids": list[str],
        "session_ids": list[str],
    },
    total=False,
)

SessionFields = TypedDict(
    "SessionFields",
    {
        "id": str,
        "session_code": str,
        "school_id": str,
        "caterer_id": str,
        "incoming_caterer_id": str,
        "on_site_manager_id": str,
        "day": DayName,
        "start_time": str,
        "end_time": str,
        "dinner_time": str,
        "building": str,
        # Aggregated by sessions_view
        "year_levels": list[YearLevel],
    },
    total=False,
)

AbsenceFields = TypedDict(
    "AbsenceFields",
    {
        "id": str,
        "absence_code": str,
        "student_id": str,
        "session_id": str,
        "date": str,
        "reason": str,
    },
    total=False,
)

ExclusionFields = TypedDict(
    "ExclusionFields",
    {
        "id": str,
        "exclusion_code": str,
        "school_id": str,
        "date": str,
        "reason": str,
        # Aggregated by exclusions_view
        "year_levels": list[YearLevel],
    },
    total=False,
)

CatererFeedbackFields = TypedDict(
    "CatererFeedbackFields",
    {
        "id": str,
        "feedback_code": str,
        "student_id": str,
        "session_id": str,
        "caterer_id": str,
        "rating": int,
        "comment": str,
        "session_date": str,
    },
    total=False,
)

WeeklyOrderFields = TypedDict(
    "WeeklyOrderFields",
    {
        "id": str,
        "order_code": str,
        "caterer_id": str,
        "week_start": str,
        "total_meals": int,
        "total_cost": float,
        "notes": str,
    },
    total=False,
)

OrderFields = TypedDict(
    "OrderFields",
    {
        "id": str,
        "order_code": str,
        "weekly_order_id": str,
        "menu_item_id": str,
        "session_id": str,
        "date": str,
        "quantity": int,
        # Aggregated by orders_view
        "student_ids": list[str],
    },
    total=False,
)

ScheduledEmailFields = TypedDict(
    "ScheduledEmailFields",
    {
        "id": str,
        "email_code": str,
        "to_address": str,
        "cc_address": str,
        "subject": str,
        "body": str,
        "status": EmailStatus,
        "weekly_order_id": str,
        "caterer_switch_proposal_id": str,
        "send_date": str,
        "sent_at": str,
    },
    total=False,
)

ManagerSubstitutionFields = TypedDict(
    "ManagerSubstitutionFields",
    {
        "id": str,
        "substitution_code": str,
        "session_id": str,
        "date": str,
        "substitute_manager_id": str,
    },
    total=False,
)

CatererSwitchProposalFields = TypedDict(
    "CatererSwitchProposalFields",
    {
        "id": str,
        "proposal_code": str,
        "session_id": str,
        "outgoing_caterer_id": str,
        "incoming_caterer_id": str,
        "avg_rating": float,
        "sessions_sampled": int,
        "unique_raters": int,
        "proposed_on": str,
        "effective_week": str,
        "status": ProposalStatus,
        "notes": str,
    },
    total=False,
)


DietaryClarificationRequestFields = TypedDict(
    "DietaryClarificationRequestFields",
    {
        "id": str,
        "request_code": str,
        "caterer_id": str,
        "school_id": str,
        "sent_at": str,
        "responded_at": str,
        "clarification_rounds": int,
        "status": ClarificationStatus,
        "question_set": list[dict],   # [{menu_item_id, restriction_id, answer?, ...}]
        "messages": list[dict],       # [{direction, sent_at, message_id, body, ...}]
        "reply_to_address": str,
        "notes": str,
    },
    total=False,
)

DietaryInboundMessageFields = TypedDict(
    "DietaryInboundMessageFields",
    {
        "id": str,
        "received_at": str,
        "seen": bool,
        "from_address": str,
        "subject": str,
        "body_text": str,
        "message_id": str,
        "in_reply_to": str,
        "to_address": str,
        "raw_payload": dict,
    },
    total=False,
)

SupportInboundMessageFields = TypedDict(
    "SupportInboundMessageFields",
    {
        "id": str,
        "received_at": str,
        "seen": bool,
        "from_address": str,
        "subject": str,
        "body_text": str,
        "message_id": str,
        "in_reply_to": str,
        "to_address": str,
        "raw_payload": dict,
    },
    total=False,
)

SupportCaseFields = TypedDict(
    "SupportCaseFields",
    {
        "id": str,
        "case_code": str,
        "parent_email": str,
        "status": SupportCaseStatus,
        "opened_at": str,
        "resolved_at": str,
        "messages": list[dict],     # [{direction, sent_at, message_id, body, tool_calls}]
        "notes": str,
    },
    total=False,
)


SchoolTermFields = TypedDict(
    "SchoolTermFields",
    {
        "id": str,
        "term_code": str,
        "start_date": str,
        "end_date": str,
    },
    total=False,
)


class PendingChangeFields(TypedDict, total=False):
    id: str
    requested_at: str
    parent_email: str
    student_id: str
    field_name: str
    current_value: Any
    new_value: Any
    reason: str
    status: str  # 'Pending' | 'Approved' | 'Denied'
    notification_message_id: str
    resolved_at: str
    coordinator_message: str
    support_case_id: str


__all__ = [
    "Region",
    "DayName",
    "ClarificationStatus",
    "DeliveryFeeStructure",
    "EmailStatus",
    "ProposalStatus",
    "YearLevel",
    "SchoolFields",
    "OnSiteManagerFields",
    "CatererFields",
    "MenuItemFields",
    "DietaryRestrictionFields",
    "StudentFields",
    "SessionFields",
    "AbsenceFields",
    "ExclusionFields",
    "CatererFeedbackFields",
    "WeeklyOrderFields",
    "OrderFields",
    "ScheduledEmailFields",
    "ManagerSubstitutionFields",
    "CatererSwitchProposalFields",
    "DietaryClarificationRequestFields",
    "DietaryInboundMessageFields",
    "SupportCaseStatus",
    "SupportInboundMessageFields",
    "SupportCaseFields",
    "PendingChangeFields",
    "SchoolTermFields",
]
