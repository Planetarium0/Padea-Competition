"""
Shared test fixtures for Padea action-script tests.

Call the factory functions to get fresh Record instances per test.
All IDs are stable constants so error messages stay readable.
"""
from __future__ import annotations

from support import Record
from support.compatibility import DietaryHierarchy, build_hierarchy

# ---------------------------------------------------------------------------
# ID constants
# ---------------------------------------------------------------------------

# Dietary restrictions
DIET_VEG_ID    = "rVeg0001"
DIET_VEGAN_ID  = "rVegan01"
DIET_OPT_ID    = "rOptOut1"
DIET_NOBEEF_ID = "rNoBeef1"

# Schools
SCHOOL_A_ID = "sAlpha001"
SCHOOL_B_ID = "sBeta0001"

# Caterers
CATERER_A_ID    = "cAlpha001"
CATERER_B_ID    = "cBeta0001"
CATERER_MEAT_ID = "cMeat0001"

# Menu items — Caterer A
ITEM_CHICKEN_RICE_ID = "iChkRice"
ITEM_BEEF_BURGER_ID  = "iBeefBgr"
ITEM_VEG_PASTA_ID    = "iVegPsta"
ITEM_VEGAN_BOWL_ID   = "iVgnBowl"

# Menu items — Caterer B
ITEM_B_GRILLED_CHICKEN_ID = "iBGrCh01"
ITEM_B_VEG_CURRY_ID       = "iBVCurr1"

# Menu items — meat-only caterer
ITEM_MEAT_CHICKEN_ID = "iMeat001"
ITEM_MEAT_BEEF_ID    = "iMeat002"

# Sessions
SESSION_MON_ID = "sessMon1"
SESSION_WED_ID = "sessWed1"

# Students
STU_NORMAL_ID  = "stuNorm1"
STU_VEG_ID     = "stuVeg01"
STU_VEGAN_ID   = "stuVgan1"
STU_OPT_ID     = "stuOpt01"
STU_NOBEEF_ID  = "stuNoBf1"

# Managers
MANAGER_A_ID = "mgrAlph1"
MANAGER_B_ID = "mgrBeta1"

# Manager substitutions
SUB_MON_ID = "subMon01"


# ---------------------------------------------------------------------------
# Dietary restrictions
# ---------------------------------------------------------------------------

def dietary_records() -> list[Record]:
    """Standard set of dietary restriction Records for tests."""
    return [
        Record(id=DIET_VEG_ID,    fields={"name": "Vegetarian",            "superset_ids": []}),
        Record(id=DIET_VEGAN_ID,  fields={"name": "Vegan",                 "superset_ids": [DIET_VEG_ID]}),
        Record(id=DIET_OPT_ID,    fields={"name": "Opted out of Catering", "superset_ids": []}),
        Record(id=DIET_NOBEEF_ID, fields={"name": "No Beef",               "superset_ids": []}),
    ]


def test_hierarchy() -> DietaryHierarchy:
    """Pre-built DietaryHierarchy from the standard test dietary records."""
    return build_hierarchy(dietary_records())


# Dietary IDs that are compatible with each caterer's menu (for coverage tests)
VEGAN_ONLY_IDS = [DIET_VEGAN_ID]  # only Vegan Bowl in caterer A
VEG_IDS        = [DIET_VEG_ID]    # Veg Pasta + Vegan Bowl in caterer A
OPT_OUT_IDS    = [DIET_OPT_ID]


# ---------------------------------------------------------------------------
# Menu items
# ---------------------------------------------------------------------------

def menu_items_caterer_a() -> list[Record]:
    """Four items for Caterer A spanning the dietary range.

    Compatibility with keywords from dietary_keywords.json:
      - Chicken Fried Rice: "chicken" → blocked for Vegetarian/Vegan
      - Beef Burger:        "beef"    → blocked for Vegetarian/Vegan/No Beef
      - Vegetarian Pasta:  tagged Vegetarian → ok for Vegetarian; no
                            Vegan-tag match but keyword-safe for Vegan
      - Vegan Bowl:        tagged Vegan → ok for Vegan (and Vegetarian via closure)
    """
    return [
        Record(id=ITEM_CHICKEN_RICE_ID, fields={
            "name":            "Chicken Fried Rice",
            "caterer_id":      CATERER_A_ID,
            "dietary_tag_ids": [],
        }),
        Record(id=ITEM_BEEF_BURGER_ID, fields={
            "name":            "Beef Burger",
            "caterer_id":      CATERER_A_ID,
            "dietary_tag_ids": [],
        }),
        Record(id=ITEM_VEG_PASTA_ID, fields={
            "name":            "Vegetarian Pasta",
            "caterer_id":      CATERER_A_ID,
            "dietary_tag_ids": [DIET_VEG_ID],
        }),
        Record(id=ITEM_VEGAN_BOWL_ID, fields={
            "name":            "Vegan Bowl",
            "caterer_id":      CATERER_A_ID,
            "dietary_tag_ids": [DIET_VEGAN_ID],
        }),
    ]


def menu_items_caterer_b() -> list[Record]:
    """Two items for Caterer B: one meat, one vegan-tagged."""
    return [
        Record(id=ITEM_B_GRILLED_CHICKEN_ID, fields={
            "name":            "Grilled Chicken",
            "caterer_id":      CATERER_B_ID,
            "dietary_tag_ids": [],
        }),
        Record(id=ITEM_B_VEG_CURRY_ID, fields={
            "name":            "Vegetable Curry",
            "caterer_id":      CATERER_B_ID,
            "dietary_tag_ids": [DIET_VEGAN_ID],
        }),
    ]


def menu_items_meat_only() -> list[Record]:
    """Meat-only caterer — cannot cover Vegan students.

    "Chicken Burger" triggers "chicken" keyword for Vegan/Vegetarian.
    "Beef Steak" triggers "beef" for Vegan/Vegetarian/No Beef.
    """
    return [
        Record(id=ITEM_MEAT_CHICKEN_ID, fields={
            "name":            "Chicken Burger",
            "caterer_id":      CATERER_MEAT_ID,
            "dietary_tag_ids": [],
        }),
        Record(id=ITEM_MEAT_BEEF_ID, fields={
            "name":            "Beef Steak",
            "caterer_id":      CATERER_MEAT_ID,
            "dietary_tag_ids": [],
        }),
    ]


# ---------------------------------------------------------------------------
# Schools
# ---------------------------------------------------------------------------

def school_alpha() -> Record:
    return Record(id=SCHOOL_A_ID, fields={"name": "Alpha Academy", "region": "Redlands"})


def school_beta() -> Record:
    return Record(id=SCHOOL_B_ID, fields={"name": "Beta College", "region": "South Brisbane"})


# ---------------------------------------------------------------------------
# Caterers
# ---------------------------------------------------------------------------

def caterer_a() -> Record:
    return Record(id=CATERER_A_ID, fields={
        "name":                     "Café Deluxe",
        "able_to_serve_school_ids": [],
        "contact_email":            "cafe@deluxe.com",
        "contact_name":             "Alice Smith",
        "price_per_item":           12.0,
        "delivery_fee":             20.0,
        "delivery_fee_structure":   "Per trip",
        "min_qty_4_items":          3,
        "legend_tag_ids":           [],
    })


def caterer_b() -> Record:
    return Record(id=CATERER_B_ID, fields={
        "name":                     "Fresh Eats",
        "able_to_serve_school_ids": [SCHOOL_A_ID],
        "contact_email":            "info@fresh-eats.com",
        "contact_name":             "Bob Jones",
        "price_per_item":           10.0,
        "delivery_fee":             15.0,
        "delivery_fee_structure":   "Per trip",
        "legend_tag_ids":           [],
    })


def caterer_meat_only() -> Record:
    return Record(id=CATERER_MEAT_ID, fields={
        "name":                     "Meat Masters",
        "able_to_serve_school_ids": [SCHOOL_A_ID],
        "legend_tag_ids":           [],
    })


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def session_monday() -> Record:
    return Record(id=SESSION_MON_ID, fields={
        "session_code":       "Alpha Academy - Monday",
        "school_id":          SCHOOL_A_ID,
        "caterer_id":         CATERER_A_ID,
        "day":                "Monday",
        "dinner_time":        "6:30 PM",
        "building":           "Block B",
        "on_site_manager_id": MANAGER_A_ID,
    })


def session_wednesday() -> Record:
    return Record(id=SESSION_WED_ID, fields={
        "session_code":       "Alpha Academy - Wednesday",
        "school_id":          SCHOOL_A_ID,
        "caterer_id":         CATERER_A_ID,
        "day":                "Wednesday",
        "dinner_time":        "18:00",
        "building":           "Block C",
        "on_site_manager_id": MANAGER_A_ID,
    })


# ---------------------------------------------------------------------------
# On-site managers
# ---------------------------------------------------------------------------

def manager_alpha() -> Record:
    return Record(id=MANAGER_A_ID, fields={
        "name":   "Carol Manager",
        "mobile": "0412345678",
        "email":  "carol@alpha.edu.au",
    })


def manager_beta() -> Record:
    """Substitute manager used in substitution tests."""
    return Record(id=MANAGER_B_ID, fields={
        "name":   "Dave Substitute",
        "mobile": "0499999999",
        "email":  "dave@beta.edu.au",
    })


def substitution_monday(date_str: str = "2026-06-02") -> Record:
    """One-off substitution: Dave covers the Monday session on date_str."""
    return Record(id=SUB_MON_ID, fields={
        "substitution_code":     f"Alpha Academy - Monday - {date_str}",
        "session_id":            SESSION_MON_ID,
        "date":                  date_str,
        "substitute_manager_id": MANAGER_B_ID,
    })


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

def student_normal() -> Record:
    return Record(id=STU_NORMAL_ID, fields={
        "name":                    "Normal Student",
        "year_level":              10,
        "session_ids":             [SESSION_MON_ID],
        "dietary_requirement_ids": [],
    })


def student_vegetarian() -> Record:
    return Record(id=STU_VEG_ID, fields={
        "name":                    "Veggie Student",
        "year_level":              11,
        "session_ids":             [SESSION_MON_ID],
        "dietary_requirement_ids": [DIET_VEG_ID],
    })


def student_vegan() -> Record:
    return Record(id=STU_VEGAN_ID, fields={
        "name":                    "Vegan Student",
        "year_level":              10,
        "session_ids":             [SESSION_MON_ID],
        "dietary_requirement_ids": [DIET_VEGAN_ID],
    })


def student_opted_out() -> Record:
    return Record(id=STU_OPT_ID, fields={
        "name":                    "No Meal Student",
        "year_level":              9,
        "session_ids":             [SESSION_MON_ID],
        "dietary_requirement_ids": [DIET_OPT_ID],
    })


def student_no_beef() -> Record:
    return Record(id=STU_NOBEEF_ID, fields={
        "name":                    "No Beef Student",
        "year_level":              10,
        "session_ids":             [SESSION_MON_ID],
        "dietary_requirement_ids": [DIET_NOBEEF_ID],
    })


# ---------------------------------------------------------------------------
# Helper: build n generic students with no dietary restrictions
# ---------------------------------------------------------------------------

def make_students(n: int, session_id: str = SESSION_MON_ID) -> list[Record]:
    return [
        Record(id=f"stu{i:04d}", fields={
            "name":                    f"Student {i}",
            "year_level":              10,
            "session_ids":             [session_id],
            "dietary_requirement_ids": [],
        })
        for i in range(n)
    ]
