TABLES_SCHEMA = {
    "Schools": {
        "primary": {"name": "School Name", "type": "singleLineText"},
        "fields": [
            {
                "name": "Region",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Redlands"},
                        {"name": "South Brisbane"},
                        {"name": "West Brisbane"},
                        {"name": "Central Brisbane"}
                    ]
                }
            }
            # Back-links (Sessions, Serves Schools, Able to Serve Schools, Exclusions)
            # are auto-created by Airtable when the owning side creates the link.
        ]
    },
    "On-Site Managers": {
        "primary": {"name": "Manager Name", "type": "singleLineText"},
        "fields": [
            {"name": "Mobile", "type": "phoneNumber"},
            {"name": "Email",  "type": "email"}
            # Sessions back-link is auto-created by Sessions.'On-Site Manager'
        ]
    },
    "Caterers": {
        "primary": {"name": "Caterer Name", "type": "singleLineText"},
        "fields": [
            {
                "name": "Region",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Redlands"},
                        {"name": "South Brisbane"},
                        {"name": "West Brisbane"},
                        {"name": "Central Brisbane"}
                    ]
                }
            },
            {"name": "Min Qty 4 Items", "type": "number", "options": {"precision": 0}},
            {"name": "Min Qty 5 Items", "type": "number", "options": {"precision": 0}},
            {"name": "Min Qty 6 Items", "type": "number", "options": {"precision": 0}},
            {"name": "Price per Item", "type": "currency", "options": {"precision": 2, "symbol": "$"}},
            {"name": "Contact Name", "type": "singleLineText"},
            {"name": "Contact Email", "type": "email"},
            {"name": "Chef Name", "type": "singleLineText"},
            {"name": "Chef Email", "type": "email"},
            {"name": "Chef Wants CC", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
            {"name": "Delivery Fee", "type": "currency", "options": {"precision": 2, "symbol": "$"}},
            {
                "name": "Delivery Fee Structure",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Per trip"},
                        {"name": "Per school per trip"}
                    ]
                }
            },
            {"name": "Price Includes GST", "type": "checkbox", "options": {"icon": "check", "color": "greenBright"}},
            {"name": "Notes", "type": "multilineText"},
            {
                "name": "Serves Schools",
                "type": "multipleRecordLinks",
                "link_target": "Schools"
            },
            {
                "name": "Able to Serve Schools",
                "type": "multipleRecordLinks",
                "link_target": "Schools"
            }
            # Menu Items back-link is auto-created by Menu Items.'Caterer'
        ]
    },
    "Menu Items": {
        "primary": {"name": "Menu Item Name", "type": "singleLineText"},
        "fields": [
            {
                "name": "Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {
                "name": "Dietary Tags",
                "type": "multipleRecordLinks",
                "link_target": "Dietary Restrictions"
            },
            {"name": "Notes", "type": "multilineText"}
        ]
    },
    "Dietary Restrictions": {
        "primary": {"name": "Restriction Name", "type": "singleLineText"},
        "fields": [
            # Supersets = less-restrictive parents. (e.g. Vegetarian's supersets
            # include No Red Meat — a Vegetarian item satisfies a "No Red Meat"
            # constraint.) `inverse_name` renames Airtable's auto-created
            # back-link from "From field: Supersets" to the friendlier "Subsets".
            {
                "name": "Supersets",
                "type": "multipleRecordLinks",
                "link_target": "Dietary Restrictions",
                "inverse_name": "Subsets",
            }
        ]
    },
    "Students": {
        "primary": {"name": "Student Name", "type": "singleLineText"},
        "fields": [
            {"name": "Year Level", "type": "number", "options": {"precision": 0}},
            {"name": "Subjects", "type": "singleLineText"},
            {
                "name": "Dietary Requirements",
                "type": "multipleRecordLinks",
                "link_target": "Dietary Restrictions"
            },
            {"name": "Student Email", "type": "email"},
            {"name": "Parent Name", "type": "singleLineText"},
            {"name": "Parent Email", "type": "email"},
            {"name": "Parent Mobile", "type": "phoneNumber"},
            {
                "name": "Sessions",
                "type": "multipleRecordLinks",
                "link_target": "Sessions"
            },
            # Current preference for next week's meal. The webapp upserts this
            # field directly; the weekly cron snapshots it into the Orders table.
            {
                "name": "Meal Preference",
                "type": "multipleRecordLinks",
                "link_target": "Menu Items"
            }
        ]
    },
    "Sessions": {
        "primary": {"name": "Session ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "School",
                "type": "multipleRecordLinks",
                "link_target": "Schools"
            },
            {
                "name": "Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {
                # The meaning of this option is as-yet unclear.
                # Try not to mess with this value too much.
                "name": "Date",
                "type": "date",
                "options": {"dateFormat": {"name": "iso"}}
            },
            {
                "name": "Day",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Monday"},
                        {"name": "Tuesday"},
                        {"name": "Wednesday"},
                        {"name": "Thursday"},
                        {"name": "Friday"}
                    ]
                }
            },
            {
                "name": "On-Site Manager",
                "type": "multipleRecordLinks",
                "link_target": "On-Site Managers"
            },
            {"name": "Start Time", "type": "singleLineText"},
            {"name": "End Time", "type": "singleLineText"},
            {"name": "Dinner Time", "type": "singleLineText"},
            {"name": "Year Levels", "type": "singleLineText"},
            {"name": "Building", "type": "singleLineText"},
            {
                # Set when a caterer switch is approved but not yet live.
                # The webapp uses this to show the incoming caterer's menu for
                # preference selection while still rating the current caterer.
                # register_orders.py flips Caterer = Incoming Caterer at run time.
                "name": "Incoming Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            }
        ]
    },
    "Absences": {
        "primary": {"name": "Absence ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "Student",
                "type": "multipleRecordLinks",
                "link_target": "Students"
            },
            {
                "name": "Session",
                "type": "multipleRecordLinks",
                "link_target": "Sessions"
            },
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Reason", "type": "singleLineText"}
        ]
    },
    "Exclusions": {
        "primary": {"name": "Exclusion ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "School",
                "type": "multipleRecordLinks",
                "link_target": "Schools"
            },
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {
                "name": "Affected Year Levels",
                "type": "multipleSelects",
                "options": {
                    "choices": [
                        {"name": "All"},
                        {"name": "12"},
                        {"name": "11"},
                        {"name": "10"},
                        {"name": "9"},
                        {"name": "8"},
                        {"name": "7"},
                        {"name": "6"}
                    ]
                }
            },
            {"name": "Reason", "type": "singleLineText"}
        ]
    },
    "Caterer Feedback": {
        "primary": {"name": "Feedback ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "Student",
                "type": "multipleRecordLinks",
                "link_target": "Students"
            },
            {
                "name": "Session",
                "type": "multipleRecordLinks",
                "link_target": "Sessions"
            },
            {
                "name": "Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {"name": "Rating", "type": "number", "options": {"precision": 0}},
            {"name": "Comment", "type": "multilineText"},
            # Set by the webapp to the actual date feedback was submitted.
            # Used by evaluate_caterers.py for the rolling-window calculation.
            {"name": "Session Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}}
        ]
    },
    "Weekly Orders": {
        "primary": {"name": "Order ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {"name": "Week Start", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Total Meals", "type": "number", "options": {"precision": 0}},
            {"name": "Total Cost", "type": "currency", "options": {"precision": 2, "symbol": "$"}},
            {"name": "Notes", "type": "multilineText"}
        ]
    },
    "Orders": {
        # Per-session-per-item quantity record. One row per unique (Session,
        # Menu Item) pair for a given week; Quantity holds the total portions
        # to order. Rolled up from student preferences by register_orders.py.
        "primary": {"name": "Order ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "Weekly Order",
                "type": "multipleRecordLinks",
                "link_target": "Weekly Orders"
            },
            {
                "name": "Menu Item",
                "type": "multipleRecordLinks",
                "link_target": "Menu Items"
            },
            {
                "name": "Session",
                "type": "multipleRecordLinks",
                "link_target": "Sessions"
            },
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Quantity", "type": "number", "options": {"precision": 0}}
        ]
    },
    "Scheduled Emails": {
        # One record per outbound email queued by send_orders.py.
        # Airtable automations watch Status='Queued' to trigger actual sending.
        "primary": {"name": "Email ID", "type": "singleLineText"},
        "fields": [
            {"name": "To", "type": "email"},
            {"name": "CC", "type": "email"},
            {"name": "Subject", "type": "singleLineText"},
            {"name": "Body", "type": "multilineText"},
            {
                "name": "Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Queued"},
                        {"name": "Sent"},
                        {"name": "Failed"}
                    ]
                }
            },
            {
                # Optional — set for order emails; null for switch-proposal emails.
                "name": "Weekly Order",
                "type": "multipleRecordLinks",
                "link_target": "Weekly Orders"
            },
            {
                # Optional — set for caterer-switch proposal emails; null for order emails.
                # Airtable doesn't support polymorphic links, so both live as
                # separate optional fields on this table.
                "name": "Caterer Switch Proposal",
                "type": "multipleRecordLinks",
                "link_target": "Caterer Switch Proposals"
            },
            {"name": "Send Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}}
        ]
    },
    "Caterer Switch Proposals": {
        # One record per automated switch proposal generated by evaluate_caterers.py.
        # Coordinator sets Status='Approved' to trigger execute_caterer_switch.py.
        "primary": {"name": "Proposal ID", "type": "singleLineText"},
        "fields": [
            {
                "name": "School",
                "type": "multipleRecordLinks",
                "link_target": "Schools"
            },
            {
                "name": "Outgoing Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {
                "name": "Incoming Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {"name": "Avg Rating",       "type": "number", "options": {"precision": 2}},
            {"name": "Sessions Sampled", "type": "number", "options": {"precision": 0}},
            {"name": "Unique Raters",    "type": "number", "options": {"precision": 0}},
            {"name": "Proposed On",      "type": "date",   "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Effective Week",   "type": "date",   "options": {"dateFormat": {"name": "iso"}}},
            {
                "name": "Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Pending"},
                        {"name": "Approved"},
                        {"name": "Rejected"},
                        {"name": "Executed"}
                    ]
                }
            },
            {"name": "Notes", "type": "multilineText"}
        ]
    }
}
