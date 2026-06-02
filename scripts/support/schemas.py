"""Pydantic validation schemas for the Padea Catering Management System."""

from __future__ import annotations

from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field

# Enum-like Literals from records.py
Region = Literal["Redlands", "South Brisbane", "West Brisbane", "Central Brisbane"]
DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DeliveryFeeStructure = Literal["Per trip", "Per school per trip"]
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
ProposalStatus = Literal["Pending", "Approved", "Rejected", "Executed"]
YearLevel = Literal["All", "12", "11", "10", "9", "8", "7", "6"]


class School(BaseModel):
    school_name: str = Field(alias="School Name")
    region: Optional[Region] = Field(default=None, alias="Region")

    class Config:
        populate_by_name = True


class OnSiteManager(BaseModel):
    manager_name: str = Field(alias="Manager Name")
    mobile: Optional[str] = Field(default=None, alias="Mobile")
    email: Optional[str] = Field(default=None, alias="Email")

    class Config:
        populate_by_name = True


class Caterer(BaseModel):
    caterer_name: str = Field(alias="Caterer Name")
    region: Optional[Region] = Field(default=None, alias="Region")
    min_qty_4_items: Optional[int] = Field(default=None, alias="Min Qty 4 Items")
    min_qty_5_items: Optional[int] = Field(default=None, alias="Min Qty 5 Items")
    min_qty_6_items: Optional[int] = Field(default=None, alias="Min Qty 6 Items")
    price_per_item: Optional[float] = Field(default=None, alias="Price per Item")
    contact_name: Optional[str] = Field(default=None, alias="Contact Name")
    contact_email: Optional[str] = Field(default=None, alias="Contact Email")
    chef_name: Optional[str] = Field(default=None, alias="Chef Name")
    chef_email: Optional[str] = Field(default=None, alias="Chef Email")
    chef_wants_cc: bool = Field(default=False, alias="Chef Wants CC")
    delivery_fee: Optional[float] = Field(default=None, alias="Delivery Fee")
    delivery_fee_structure: Optional[DeliveryFeeStructure] = Field(default="Per trip", alias="Delivery Fee Structure")
    notes: Optional[str] = Field(default=None, alias="Notes")
    able_to_serve_schools: List[str] = Field(default_factory=list, alias="Able to Serve Schools")
    dietary_legend_tags: List[str] = Field(default_factory=list, alias="Dietary Legend Tags")

    class Config:
        populate_by_name = True


class MenuItem(BaseModel):
    menu_item_name: str = Field(alias="Menu Item Name")
    caterer: List[str] = Field(default_factory=list, alias="Caterer")
    dietary_tags: List[str] = Field(default_factory=list, alias="Dietary Tags")
    is_variant: bool = Field(default=False, alias="Is Variant")
    variant_of: List[str] = Field(default_factory=list, alias="Variant Of")
    notes: Optional[str] = Field(default=None, alias="Notes")

    class Config:
        populate_by_name = True


class DietaryRestriction(BaseModel):
    restriction_name: str = Field(alias="Restriction Name")
    supersets: List[str] = Field(default_factory=list, alias="Supersets")
    subsets: List[str] = Field(default_factory=list, alias="Subsets")

    class Config:
        populate_by_name = True


class Student(BaseModel):
    student_name: str = Field(alias="Student Name")
    year_level: Optional[int] = Field(default=None, alias="Year Level")
    subjects: Optional[str] = Field(default=None, alias="Subjects")
    dietary_requirements: List[str] = Field(default_factory=list, alias="Dietary Requirements")
    student_email: Optional[str] = Field(default=None, alias="Student Email")
    parent_name: Optional[str] = Field(default=None, alias="Parent Name")
    parent_email: Optional[str] = Field(default=None, alias="Parent Email")
    parent_mobile: Optional[str] = Field(default=None, alias="Parent Mobile")
    sessions: List[str] = Field(default_factory=list, alias="Sessions")
    meal_preference: List[str] = Field(default_factory=list, alias="Meal Preference")
    last_submitted: Optional[str] = Field(default=None, alias="Last Submitted")

    class Config:
        populate_by_name = True


class Session(BaseModel):
    session_id: str = Field(alias="Session ID")
    school: List[str] = Field(default_factory=list, alias="School")
    caterer: List[str] = Field(default_factory=list, alias="Caterer")
    date: Optional[str] = Field(default=None, alias="Date")
    day: Optional[DayName] = Field(default=None, alias="Day")
    on_site_manager: List[str] = Field(default_factory=list, alias="On-Site Manager")
    start_time: Optional[str] = Field(default=None, alias="Start Time")
    end_time: Optional[str] = Field(default=None, alias="End Time")
    dinner_time: Optional[str] = Field(default=None, alias="Dinner Time")
    year_levels: List[YearLevel] = Field(default_factory=list, alias="Year Levels")
    building: Optional[str] = Field(default=None, alias="Building")
    incoming_caterer: List[str] = Field(default_factory=list, alias="Incoming Caterer")

    class Config:
        populate_by_name = True


class Absence(BaseModel):
    absence_id: str = Field(alias="Absence ID")
    student: List[str] = Field(default_factory=list, alias="Student")
    session: List[str] = Field(default_factory=list, alias="Session")
    date: str = Field(alias="Date")
    reason: Optional[str] = Field(default=None, alias="Reason")

    class Config:
        populate_by_name = True


class Exclusion(BaseModel):
    exclusion_id: str = Field(alias="Exclusion ID")
    school: List[str] = Field(default_factory=list, alias="School")
    date: str = Field(alias="Date")
    affected_year_levels: List[YearLevel] = Field(default_factory=list, alias="Affected Year Levels")
    reason: Optional[str] = Field(default=None, alias="Reason")

    class Config:
        populate_by_name = True


class CatererFeedback(BaseModel):
    feedback_id: str = Field(alias="Feedback ID")
    student: List[str] = Field(default_factory=list, alias="Student")
    session: List[str] = Field(default_factory=list, alias="Session")
    caterer: List[str] = Field(default_factory=list, alias="Caterer")
    rating: int = Field(alias="Rating")
    comment: Optional[str] = Field(default=None, alias="Comment")
    session_date: str = Field(alias="Session Date")

    class Config:
        populate_by_name = True


class WeeklyOrder(BaseModel):
    order_id: str = Field(alias="Order ID")
    caterer: List[str] = Field(default_factory=list, alias="Caterer")
    week_start: str = Field(alias="Week Start")
    total_meals: int = Field(alias="Total Meals")
    total_cost: float = Field(alias="Total Cost")
    notes: Optional[str] = Field(default=None, alias="Notes")

    class Config:
        populate_by_name = True


class Order(BaseModel):
    order_id: str = Field(alias="Order ID")
    weekly_order: List[str] = Field(default_factory=list, alias="Weekly Order")
    menu_item: List[str] = Field(default_factory=list, alias="Menu Item")
    session: List[str] = Field(default_factory=list, alias="Session")
    student: List[str] = Field(default_factory=list, alias="Student")
    date: str = Field(alias="Date")
    quantity: int = Field(alias="Quantity")

    class Config:
        populate_by_name = True


class ScheduledEmail(BaseModel):
    email_id: str = Field(alias="Email ID")
    to: str = Field(alias="To")
    cc: Optional[str] = Field(default=None, alias="CC")
    subject: str = Field(alias="Subject")
    body: str = Field(alias="Body")
    status: EmailStatus = Field(default="Queued", alias="Status")
    weekly_order: List[str] = Field(default_factory=list, alias="Weekly Order")
    caterer_switch_proposal: List[str] = Field(default_factory=list, alias="Caterer Switch Proposal")
    send_date: Optional[str] = Field(default=None, alias="Send Date")

    class Config:
        populate_by_name = True


class ManagerSubstitution(BaseModel):
    substitution_id: str = Field(alias="Substitution ID")
    session: List[str] = Field(default_factory=list, alias="Session")
    date: str = Field(alias="Date")
    substitute_manager: List[str] = Field(default_factory=list, alias="Substitute Manager")

    class Config:
        populate_by_name = True


class CatererSwitchProposal(BaseModel):
    proposal_id: str = Field(alias="Proposal ID")
    session: List[str] = Field(default_factory=list, alias="Session")
    outgoing_caterer: List[str] = Field(default_factory=list, alias="Outgoing Caterer")
    incoming_caterer: List[str] = Field(default_factory=list, alias="Incoming Caterer")
    avg_rating: float = Field(alias="Avg Rating")
    sessions_sampled: int = Field(alias="Sessions Sampled")
    unique_raters: int = Field(alias="Unique Raters")
    proposed_on: str = Field(alias="Proposed On")
    effective_week: str = Field(alias="Effective Week")
    status: ProposalStatus = Field(default="Pending", alias="Status")
    notes: Optional[str] = Field(default=None, alias="Notes")

    class Config:
        populate_by_name = True


# Mapping of table names to their respective Pydantic validation models
MODEL_MAP = {
    "Schools": School,
    "On-Site Managers": OnSiteManager,
    "Caterers": Caterer,
    "Menu Items": MenuItem,
    "Dietary Restrictions": DietaryRestriction,
    "Students": Student,
    "Sessions": Session,
    "Absences": Absence,
    "Exclusions": Exclusion,
    "Caterer Feedback": CatererFeedback,
    "Weekly Orders": WeeklyOrder,
    "Orders": Order,
    "Scheduled Emails": ScheduledEmail,
    "Manager Substitutions": ManagerSubstitution,
    "Caterer Switch Proposals": CatererSwitchProposal,
}
