"""Pydantic validation schemas for the Padea Supabase database.

All non-aggregate fields are ``Optional`` so the same model can validate both
full reads and partial-payload updates. Postgres ``NOT NULL`` constraints
still enforce presence at insert time; Pydantic's role here is type/enum
validation, not field-presence checking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Region = Literal["Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"]
DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DeliveryFeeStructure = Literal["Per trip", "Per school per trip"]
ClarificationStatus = Literal["Open", "Resolved", "Escalated", "Cancelled"]
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
ProposalStatus = Literal["Pending", "Approved", "Rejected", "Executed"]
YearLevel = Literal["All", "12", "11", "10", "9", "8", "7", "6"]


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class School(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    region: Optional[Region] = None


class OnSiteManager(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None


class Caterer(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    region: Optional[Region] = None
    min_qty_4_items: Optional[int] = None
    min_qty_5_items: Optional[int] = None
    min_qty_6_items: Optional[int] = None
    price_per_item: Optional[float] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    chef_name: Optional[str] = None
    chef_email: Optional[str] = None
    chef_wants_cc: Optional[bool] = None
    delivery_fee: Optional[float] = None
    delivery_fee_structure: Optional[DeliveryFeeStructure] = None
    notes: Optional[str] = None
    # View-aggregated
    legend_tag_ids: List[str] = Field(default_factory=list)
    able_to_serve_school_ids: List[str] = Field(default_factory=list)


class MenuItem(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    caterer_id: Optional[str] = None
    is_variant: Optional[bool] = None
    variant_of_id: Optional[str] = None
    notes: Optional[str] = None
    # View-aggregated
    dietary_tag_ids: List[str] = Field(default_factory=list)


class DietaryRestriction(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    # View-aggregated
    superset_ids: List[str] = Field(default_factory=list)
    subset_ids: List[str] = Field(default_factory=list)


class Student(_Base):
    id: Optional[str] = None
    name: Optional[str] = None
    year_level: Optional[int] = None
    subjects: Optional[str] = None
    email: Optional[str] = None
    parent_name: Optional[str] = None
    parent_email: Optional[str] = None
    parent_mobile: Optional[str] = None
    meal_preference_id: Optional[str] = None
    last_submitted: Optional[str] = None
    # View-aggregated
    dietary_requirement_ids: List[str] = Field(default_factory=list)
    session_ids: List[str] = Field(default_factory=list)


class Session(_Base):
    id: Optional[str] = None
    session_code: Optional[str] = None
    school_id: Optional[str] = None
    caterer_id: Optional[str] = None
    incoming_caterer_id: Optional[str] = None
    on_site_manager_id: Optional[str] = None
    day: Optional[DayName] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    dinner_time: Optional[str] = None
    building: Optional[str] = None
    # View-aggregated
    year_levels: List[YearLevel] = Field(default_factory=list)


class Absence(_Base):
    id: Optional[str] = None
    absence_code: Optional[str] = None
    student_id: Optional[str] = None
    session_id: Optional[str] = None
    date: Optional[str] = None
    reason: Optional[str] = None


class Exclusion(_Base):
    id: Optional[str] = None
    exclusion_code: Optional[str] = None
    school_id: Optional[str] = None
    date: Optional[str] = None
    reason: Optional[str] = None
    # View-aggregated
    year_levels: List[YearLevel] = Field(default_factory=list)


class CatererFeedback(_Base):
    id: Optional[str] = None
    feedback_code: Optional[str] = None
    student_id: Optional[str] = None
    session_id: Optional[str] = None
    caterer_id: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    session_date: Optional[str] = None


class WeeklyOrder(_Base):
    id: Optional[str] = None
    order_code: Optional[str] = None
    caterer_id: Optional[str] = None
    week_start: Optional[str] = None
    total_meals: Optional[int] = None
    total_cost: Optional[float] = None
    notes: Optional[str] = None


class Order(_Base):
    id: Optional[str] = None
    order_code: Optional[str] = None
    weekly_order_id: Optional[str] = None
    menu_item_id: Optional[str] = None
    session_id: Optional[str] = None
    date: Optional[str] = None
    quantity: Optional[int] = None
    # View-aggregated
    student_ids: List[str] = Field(default_factory=list)


class ScheduledEmail(_Base):
    id: Optional[str] = None
    email_code: Optional[str] = None
    to_address: Optional[str] = None
    cc_address: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    status: Optional[EmailStatus] = None
    weekly_order_id: Optional[str] = None
    caterer_switch_proposal_id: Optional[str] = None
    send_date: Optional[str] = None
    sent_at: Optional[str] = None


class ManagerSubstitution(_Base):
    id: Optional[str] = None
    substitution_code: Optional[str] = None
    session_id: Optional[str] = None
    date: Optional[str] = None
    substitute_manager_id: Optional[str] = None


class CatererSwitchProposal(_Base):
    id: Optional[str] = None
    proposal_code: Optional[str] = None
    session_id: Optional[str] = None
    outgoing_caterer_id: Optional[str] = None
    incoming_caterer_id: Optional[str] = None
    avg_rating: Optional[float] = None
    sessions_sampled: Optional[int] = None
    unique_raters: Optional[int] = None
    proposed_on: Optional[str] = None
    effective_week: Optional[str] = None
    status: Optional[ProposalStatus] = None
    notes: Optional[str] = None


class DietaryClarificationRequest(_Base):
    id: Optional[str] = None
    request_code: Optional[str] = None
    caterer_id: Optional[str] = None
    school_id: Optional[str] = None
    sent_at: Optional[str] = None
    responded_at: Optional[str] = None
    status: Optional[ClarificationStatus] = None
    question_set: List[Dict[str, str]] = Field(default_factory=list)
    notes: Optional[str] = None


# Maps Postgres table names to their Pydantic validation models.
MODEL_MAP = {
    "schools":                  School,
    "on_site_managers":         OnSiteManager,
    "caterers":                 Caterer,
    "menu_items":               MenuItem,
    "dietary_restrictions":     DietaryRestriction,
    "students":                 Student,
    "sessions":                 Session,
    "absences":                 Absence,
    "exclusions":               Exclusion,
    "caterer_feedback":         CatererFeedback,
    "weekly_orders":            WeeklyOrder,
    "orders":                   Order,
    "scheduled_emails":         ScheduledEmail,
    "manager_substitutions":    ManagerSubstitution,
    "caterer_switch_proposals": CatererSwitchProposal,
    "dietary_clarification_requests": DietaryClarificationRequest,
}
