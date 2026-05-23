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
            {"name": "Mobile", "type": "phoneNumber"}
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
            {"name": "Price", "type": "currency", "options": {"precision": 2, "symbol": "$"}},
            {
                "name": "Dietary Tags",
                "type": "multipleSelects",
                "options": {
                    "choices": [
                        {"name": "Gluten Free"},
                        {"name": "Dairy Free"},
                        {"name": "Nut Free"},
                        {"name": "Vegetarian"},
                        {"name": "Halal"}
                    ]
                }
            },
            {"name": "Notes", "type": "multilineText"}
        ]
    },
    "Students": {
        "primary": {"name": "Student Name", "type": "singleLineText"},
        "fields": [
            {"name": "Year Level", "type": "number", "options": {"precision": 0}},
            {"name": "Subjects", "type": "singleLineText"},
            {
                "name": "Dietary Requirements",
                "type": "multipleSelects",
                "options": {
                    "choices": [
                        {"name": "Dairy Free"},
                        {"name": "Gluten Free"},
                        {"name": "Nut Free"},
                        {"name": "Vegetarian"},
                        {"name": "Halal"},
                        {"name": "No Beef"},
                        {"name": "No Pork"},
                        {"name": "No Seafood"},
                        {"name": "No Shellfish"},
                        {"name": "No Fish"},
                        {"name": "No Red Meat"},
                        {"name": "Opted out of Catering"}
                    ]
                }
            },
            {"name": "Student Email", "type": "email"},
            {"name": "Parent Name", "type": "singleLineText"},
            {"name": "Parent Email", "type": "email"},
            {"name": "Parent Mobile", "type": "phoneNumber"},
            {
                "name": "Sessions",
                "type": "multipleRecordLinks",
                "link_target": "Sessions"
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
            {
                "name": "Caterer",
                "type": "multipleRecordLinks",
                "link_target": "Caterers"
            },
            {"name": "Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
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
            {"name": "Building", "type": "singleLineText"}
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
            {"name": "Affected Year Levels", "type": "singleLineText"},
            {"name": "Reason", "type": "singleLineText"}
        ]
    },
    "Meal Feedback": {
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
                "name": "Menu Item",
                "type": "multipleRecordLinks",
                "link_target": "Menu Items"
            },
            {"name": "Rating", "type": "number", "options": {"precision": 0}},
            {"name": "Comment", "type": "multilineText"}
        ]
    },
    "Meal Selections": {
        "primary": {"name": "Selection ID", "type": "singleLineText"},
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
                "name": "Menu Item",
                "type": "multipleRecordLinks",
                "link_target": "Menu Items"
            },
            {"name": "Selection Date", "type": "date", "options": {"dateFormat": {"name": "iso"}}}
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
            {
                "name": "Round",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Round 1 (Mon–Wed)"},
                        {"name": "Round 2 (Thu–Fri)"}
                    ]
                }
            },
            {"name": "Week Start", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
            {"name": "Total Meals", "type": "number", "options": {"precision": 0}},
            {"name": "Total Cost", "type": "currency", "options": {"precision": 2, "symbol": "$"}},
            {
                "name": "Status",
                "type": "singleSelect",
                "options": {
                    "choices": [
                        {"name": "Draft"},
                        {"name": "Sent"},
                        {"name": "Confirmed"}
                    ]
                }
            },
            {"name": "Notes", "type": "multilineText"}
        ]
    },
    "Order Line Items": {
        "primary": {"name": "Line Item ID", "type": "singleLineText"},
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
            {"name": "Quantity", "type": "number", "options": {"precision": 0}}
        ]
    }
}
