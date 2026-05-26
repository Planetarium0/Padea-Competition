"""
Typed record models for the Padea Airtable base.

For every table in `data/schema.py` we expose:
  - ``<Name>Fields`` — a ``TypedDict`` describing the optional shape that
    Airtable returns inside ``record["fields"]``. Optional because Airtable
    omits keys whose value is empty.
  - ``<Name>Record`` — alias for ``Record[<Name>Fields]``, the full record
    envelope that ``Table.all()`` / ``Table.get()`` produce.

The functional ``TypedDict(...)`` syntax is used because most Airtable field
names contain spaces and can't appear as Python identifiers.
"""

from __future__ import annotations

from typing import Literal, TypedDict


# ---------------------------------------------------------------------------
# Enum-like literals for the small set of singleSelect fields
# ---------------------------------------------------------------------------

Region = Literal[
    "Redlands",
    "South Brisbane",
    "West Brisbane",
    "Central Brisbane",
]
DayName = Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DeliveryFeeStructure = Literal["Per trip", "Per school per trip"]
EmailStatus = Literal["Queued", "Send Immediately", "Sent", "Failed"]
ProposalStatus = Literal["Pending", "Approved", "Rejected", "Executed"]
YearLevel = Literal["All", "12", "11", "10", "9", "8", "7", "6"]


# ---------------------------------------------------------------------------
# Per-table field shapes
# ---------------------------------------------------------------------------

SchoolFields = TypedDict(
    "SchoolFields",
    {
        "School Name": str,
        "Region": Region,
    },
    total=False,
)

OnSiteManagerFields = TypedDict(
    "OnSiteManagerFields",
    {
        "Manager Name": str,
        "Mobile": str,
        "Email": str,
    },
    total=False,
)

CatererFields = TypedDict(
    "CatererFields",
    {
        "Caterer Name": str,
        "Region": Region,
        "Min Qty 4 Items": int,
        "Min Qty 5 Items": int,
        "Min Qty 6 Items": int,
        "Price per Item": float,
        "Contact Name": str,
        "Contact Email": str,
        "Chef Name": str,
        "Chef Email": str,
        "Chef Wants CC": bool,
        "Delivery Fee": float,
        "Delivery Fee Structure": DeliveryFeeStructure,
        "Notes": str,
        "Able to Serve Schools": list[str],
    },
    total=False,
)

MenuItemFields = TypedDict(
    "MenuItemFields",
    {
        "Menu Item Name": str,
        "Caterer": list[str],
        "Dietary Tags": list[str],
        "Is Variant": bool,
        "Variant Of": list[str],
        "Notes": str,
    },
    total=False,
)

DietaryRestrictionFields = TypedDict(
    "DietaryRestrictionFields",
    {
        "Restriction Name": str,
        "Supersets": list[str],
        "Subsets": list[str],
    },
    total=False,
)

StudentFields = TypedDict(
    "StudentFields",
    {
        "Student Name": str,
        "Year Level": int,
        "Subjects": str,
        "Dietary Requirements": list[str],
        "Student Email": str,
        "Parent Name": str,
        "Parent Email": str,
        "Parent Mobile": str,
        "Sessions": list[str],
        "Meal Preference": list[str],
    },
    total=False,
)

SessionFields = TypedDict(
    "SessionFields",
    {
        "Session ID": str,
        "School": list[str],
        "Caterer": list[str],
        "Date": str,
        "Day": DayName,
        "On-Site Manager": list[str],
        "Start Time": str,
        "End Time": str,
        "Dinner Time": str,
        "Year Levels": list[YearLevel],
        "Building": str,
        "Incoming Caterer": list[str],
    },
    total=False,
)

AbsenceFields = TypedDict(
    "AbsenceFields",
    {
        "Absence ID": str,
        "Student": list[str],
        "Session": list[str],
        "Date": str,
        "Reason": str,
    },
    total=False,
)

ExclusionFields = TypedDict(
    "ExclusionFields",
    {
        "Exclusion ID": str,
        "School": list[str],
        "Date": str,
        "Affected Year Levels": list[YearLevel],
        "Reason": str,
    },
    total=False,
)

CatererFeedbackFields = TypedDict(
    "CatererFeedbackFields",
    {
        "Feedback ID": str,
        "Student": list[str],
        "Session": list[str],
        "Caterer": list[str],
        "Rating": int,
        "Comment": str,
        "Session Date": str,
    },
    total=False,
)

WeeklyOrderFields = TypedDict(
    "WeeklyOrderFields",
    {
        "Order ID": str,
        "Caterer": list[str],
        "Week Start": str,
        "Total Meals": int,
        "Total Cost": float,
        "Notes": str,
    },
    total=False,
)

OrderFields = TypedDict(
    "OrderFields",
    {
        "Order ID": str,
        "Weekly Order": list[str],
        "Menu Item": list[str],
        "Session": list[str],
        "Date": str,
        "Quantity": int,
    },
    total=False,
)

ScheduledEmailFields = TypedDict(
    "ScheduledEmailFields",
    {
        "Email ID": str,
        "To": str,
        "CC": str,
        "Subject": str,
        "Body": str,
        "Status": EmailStatus,
        "Weekly Order": list[str],
        "Caterer Switch Proposal": list[str],
        "Send Date": str | None,
    },
    total=False,
)

CatererSwitchProposalFields = TypedDict(
    "CatererSwitchProposalFields",
    {
        "Proposal ID": str,
        "Session": list[str],
        "Outgoing Caterer": list[str],
        "Incoming Caterer": list[str],
        "Avg Rating": float,
        "Sessions Sampled": int,
        "Unique Raters": int,
        "Proposed On": str,
        "Effective Week": str,
        "Status": ProposalStatus,
        "Notes": str,
    },
    total=False,
)


__all__ = [
    "Region",
    "DayName",
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
    "CatererSwitchProposalFields",
]
