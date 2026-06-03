"""Pydantic validation schemas for the Padea Supabase database."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Region = Literal["Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"]
DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DeliveryFeeStructure = Literal["Per trip", "Per school per trip"]
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
ProposalStatus = Literal["Pending", "Approved", "Rejected", "Executed"]
YearLevel = Literal["All", "12", "11", "10", "9", "8", "7", "6"]


class _Base(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")


class School(_Base):
    id: str
    name: str
    region: Optional[Region] = None


class OnSiteManager(_Base):
    id: str
    name: str
    mobile: Optional[str] = None
    email: Optional[str] = None


class Caterer(_Base):
    id: str
    name: str
    region: Optional[Region] = None
    min_qty_4_items: Optional[int] = None
    min_qty_5_items: Optional[int] = None
    min_qty_6_items: Optional[int] = None
    price_per_item: Optional[float] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    chef_name: Optional[str] = None
    chef_email: Optional[str] = None
    chef_wants_cc: bool = False
    delivery_fee: Optional[float] = None
    delivery_fee_structure: Optional[DeliveryFeeStructure] = None
    notes: Optional[str] = None
    # View-aggregated
    legend_tag_ids: List[str] = Field(default_factory=list)
    able_to_serve_school_ids: List[str] = Field(default_factory=list)


class MenuItem(_Base):
    id: str
    name: str
    caterer_id: str
    is_variant: bool = False
    variant_of_id: Optional[str] = None
    notes: Optional[str] = None
    # View-aggregated
    dietary_tag_ids: List[str] = Field(default_factory=list)


class DietaryRestriction(_Base):
    id: str
    name: str
    # View-aggregated
    superset_ids: List[str] = Field(default_factory=list)
    subset_ids: List[str] = Field(default_factory=list)


class Student(_Base):
    id: str
    name: str
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
    id: str
    session_code: str
    school_id: str
    caterer_id: str
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
    id: str
    absence_code: Optional[str] = None
    student_id: str
    session_id: str
    date: str
    reason: Optional[str] = None


class Exclusion(_Base):
    id: str
    exclusion_code: Optional[str] = None
    school_id: str
    date: str
    reason: Optional[str] = None
    # View-aggregated
    year_levels: List[YearLevel] = Field(default_factory=list)


class CatererFeedback(_Base):
    id: str
    feedback_code: Optional[str] = None
    student_id: str
    session_id: str
    caterer_id: str
    rating: int
    comment: Optional[str] = None
    session_date: str


class WeeklyOrder(_Base):
    id: str
    order_code: Optional[str] = None
    caterer_id: str
    week_start: str
    total_meals: Optional[int] = None
    total_cost: Optional[float] = None
    notes: Optional[str] = None


class Order(_Base):
    id: str
    order_code: Optional[str] = None
    weekly_order_id: str
    menu_item_id: str
    session_id: str
    date: str
    quantity: int
    # View-aggregated
    student_ids: List[str] = Field(default_factory=list)


class ScheduledEmail(_Base):
    id: str
    email_code: Optional[str] = None
    to_address: str
    cc_address: Optional[str] = None
    subject: str
    body: str
    status: EmailStatus = "Queued"
    weekly_order_id: Optional[str] = None
    caterer_switch_proposal_id: Optional[str] = None
    send_date: Optional[str] = None
    sent_at: Optional[str] = None


class ManagerSubstitution(_Base):
    id: str
    substitution_code: Optional[str] = None
    session_id: str
    date: str
    substitute_manager_id: str


class CatererSwitchProposal(_Base):
    id: str
    proposal_code: Optional[str] = None
    session_id: str
    outgoing_caterer_id: str
    incoming_caterer_id: str
    avg_rating: Optional[float] = None
    sessions_sampled: Optional[int] = None
    unique_raters: Optional[int] = None
    proposed_on: Optional[str] = None
    effective_week: Optional[str] = None
    status: ProposalStatus = "Pending"
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
}
