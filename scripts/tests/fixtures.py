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


# ---------------------------------------------------------------------------
# Dietary restrictions
# ---------------------------------------------------------------------------

def dietary_records() -> list[Record]:
    """Standard set of dietary restriction Records for tests."""
    return [
        Record(id=DIET_VEG_ID,    fields={"Restriction Name": "Vegetarian",            "Supersets": []}),
        Record(id=DIET_VEGAN_ID,  fields={"Restriction Name": "Vegan",                 "Supersets": [DIET_VEG_ID]}),
        Record(id=DIET_OPT_ID,    fields={"Restriction Name": "Opted out of Catering", "Supersets": []}),
        Record(id=DIET_NOBEEF_ID, fields={"Restriction Name": "No Beef",               "Supersets": []}),
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
            "Menu Item Name": "Chicken Fried Rice",
            "Caterer": [CATERER_A_ID],
            "Dietary Tags": [],
        }),
        Record(id=ITEM_BEEF_BURGER_ID, fields={
            "Menu Item Name": "Beef Burger",
            "Caterer": [CATERER_A_ID],
            "Dietary Tags": [],
        }),
        Record(id=ITEM_VEG_PASTA_ID, fields={
            "Menu Item Name": "Vegetarian Pasta",
            "Caterer": [CATERER_A_ID],
            "Dietary Tags": [DIET_VEG_ID],
        }),
        Record(id=ITEM_VEGAN_BOWL_ID, fields={
            "Menu Item Name": "Vegan Bowl",
            "Caterer": [CATERER_A_ID],
            "Dietary Tags": [DIET_VEGAN_ID],
        }),
    ]


def menu_items_caterer_b() -> list[Record]:
    """Two items for Caterer B: one meat, one vegan-tagged."""
    return [
        Record(id=ITEM_B_GRILLED_CHICKEN_ID, fields={
            "Menu Item Name": "Grilled Chicken",
            "Caterer": [CATERER_B_ID],
            "Dietary Tags": [],
        }),
        Record(id=ITEM_B_VEG_CURRY_ID, fields={
            "Menu Item Name": "Vegetable Curry",
            "Caterer": [CATERER_B_ID],
            "Dietary Tags": [DIET_VEGAN_ID],
        }),
    ]


def menu_items_meat_only() -> list[Record]:
    """Meat-only caterer — cannot cover Vegan students.

    "Chicken Burger" triggers "chicken" keyword for Vegan/Vegetarian.
    "Beef Steak" triggers "beef" for Vegan/Vegetarian/No Beef.
    """
    return [
        Record(id=ITEM_MEAT_CHICKEN_ID, fields={
            "Menu Item Name": "Chicken Burger",
            "Caterer": [CATERER_MEAT_ID],
            "Dietary Tags": [],
        }),
        Record(id=ITEM_MEAT_BEEF_ID, fields={
            "Menu Item Name": "Beef Steak",
            "Caterer": [CATERER_MEAT_ID],
            "Dietary Tags": [],
        }),
    ]


# ---------------------------------------------------------------------------
# Schools
# ---------------------------------------------------------------------------

def school_alpha() -> Record:
    return Record(id=SCHOOL_A_ID, fields={"School Name": "Alpha Academy", "Region": "Redlands"})


def school_beta() -> Record:
    return Record(id=SCHOOL_B_ID, fields={"School Name": "Beta College", "Region": "South Brisbane"})


# ---------------------------------------------------------------------------
# Caterers
# ---------------------------------------------------------------------------

def caterer_a() -> Record:
    return Record(id=CATERER_A_ID, fields={
        "Caterer Name":          "Café Deluxe",
        "Serves Schools":        [SCHOOL_A_ID],
        "Able to Serve Schools": [],
        "Contact Email":         "cafe@deluxe.com",
        "Contact Name":          "Alice Smith",
        "Price per Item":        12.0,
        "Delivery Fee":          20.0,
        "Delivery Fee Structure": "Per trip",
        "Min Qty 4 Items":       3,
    })


def caterer_b() -> Record:
    return Record(id=CATERER_B_ID, fields={
        "Caterer Name":          "Fresh Eats",
        "Serves Schools":        [],
        "Able to Serve Schools": [SCHOOL_A_ID],
        "Contact Email":         "info@fresh-eats.com",
        "Contact Name":          "Bob Jones",
        "Price per Item":        10.0,
        "Delivery Fee":          15.0,
        "Delivery Fee Structure": "Per trip",
    })


def caterer_meat_only() -> Record:
    return Record(id=CATERER_MEAT_ID, fields={
        "Caterer Name":          "Meat Masters",
        "Serves Schools":        [],
        "Able to Serve Schools": [SCHOOL_A_ID],
    })


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def session_monday() -> Record:
    return Record(id=SESSION_MON_ID, fields={
        "Session ID":      "Alpha Academy - Monday",
        "School":          [SCHOOL_A_ID],
        "Caterer":         [CATERER_A_ID],
        "Day":             "Monday",
        "Date":            "2026-02-02",
        "Dinner Time":     "6:30 PM",
        "Building":        "Block B",
        "On-Site Manager": [MANAGER_A_ID],
    })


def session_wednesday() -> Record:
    return Record(id=SESSION_WED_ID, fields={
        "Session ID":      "Alpha Academy - Wednesday",
        "School":          [SCHOOL_A_ID],
        "Caterer":         [CATERER_A_ID],
        "Day":             "Wednesday",
        "Date":            "2026-02-04",
        "Dinner Time":     "18:00",
        "Building":        "Block C",
        "On-Site Manager": [MANAGER_A_ID],
    })


# ---------------------------------------------------------------------------
# On-site managers
# ---------------------------------------------------------------------------

def manager_alpha() -> Record:
    return Record(id=MANAGER_A_ID, fields={
        "Manager Name": "Carol Manager",
        "Mobile":       "0412345678",
        "Email":        "carol@alpha.edu.au",
    })


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

def student_normal() -> Record:
    return Record(id=STU_NORMAL_ID, fields={
        "Student Name":        "Normal Student",
        "Year Level":          10,
        "Sessions":            [SESSION_MON_ID],
        "Dietary Requirements": [],
    })


def student_vegetarian() -> Record:
    return Record(id=STU_VEG_ID, fields={
        "Student Name":        "Veggie Student",
        "Year Level":          11,
        "Sessions":            [SESSION_MON_ID],
        "Dietary Requirements": [DIET_VEG_ID],
    })


def student_vegan() -> Record:
    return Record(id=STU_VEGAN_ID, fields={
        "Student Name":        "Vegan Student",
        "Year Level":          10,
        "Sessions":            [SESSION_MON_ID],
        "Dietary Requirements": [DIET_VEGAN_ID],
    })


def student_opted_out() -> Record:
    return Record(id=STU_OPT_ID, fields={
        "Student Name":        "No Meal Student",
        "Year Level":          9,
        "Sessions":            [SESSION_MON_ID],
        "Dietary Requirements": [DIET_OPT_ID],
    })


def student_no_beef() -> Record:
    return Record(id=STU_NOBEEF_ID, fields={
        "Student Name":        "No Beef Student",
        "Year Level":          10,
        "Sessions":            [SESSION_MON_ID],
        "Dietary Requirements": [DIET_NOBEEF_ID],
    })


# ---------------------------------------------------------------------------
# Helper: build n generic students with no dietary restrictions
# ---------------------------------------------------------------------------

def make_students(n: int, session_id: str = SESSION_MON_ID) -> list[Record]:
    return [
        Record(id=f"stu{i:04d}", fields={
            "Student Name":        f"Student {i}",
            "Year Level":          10,
            "Sessions":            [session_id],
            "Dietary Requirements": [],
        })
        for i in range(n)
    ]
