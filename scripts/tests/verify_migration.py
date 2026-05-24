import support as s

def verify_migration():
    s.log.info("=== STARTING DATA MIGRATION VERIFICATION ===")
    
    tables_to_check = [
        "Schools",
        "On-Site Managers",
        "Caterers",
        "Menu Items",
        "Dietary Restrictions",
        "Students",
        "Sessions",
        "Absences",
        "Exclusions",
        "Meal Feedback",
        "Orders",
    ]

    counts = {}
    records_by_table = {}

    # 1. Check counts in all tables
    s.log.info("--- Retrieving Record Counts ---")
    for t_name in tables_to_check:
        try:
            records = s.airtable_get(t_name)
            counts[t_name] = len(records)
            records_by_table[t_name] = records
            s.log.info(f"Table '{t_name}': {len(records)} records")
        except Exception as e:
            s.log.error(f"Failed to read table '{t_name}': {e}")
            counts[t_name] = 0

    # 2. Detailed integrity checks
    s.log.info("--- Relational Integrity Audit ---")
    errors = 0
    warnings = 0

    # Audit Schools
    schools = records_by_table.get("Schools", [])
    if len(schools) != 6:
        s.log.error(f"Expected exactly 6 Schools, but found {len(schools)}.")
        errors += 1
    else:
        s.log.info("✓ Schools table populated correctly (6 schools).")

    # Audit On-Site Managers
    managers = records_by_table.get("On-Site Managers", [])
    if len(managers) == 0:
        s.log.error("On-Site Managers table is empty!")
        errors += 1
    else:
        s.log.info(f"✓ On-Site Managers table has {len(managers)} records.")

    # Audit Caterers
    caterers = records_by_table.get("Caterers", [])
    if len(caterers) != 4:
        s.log.error(f"Expected exactly 4 Caterers, but found {len(caterers)}.")
        errors += 1
    else:
        s.log.info("✓ Caterers table populated correctly (4 caterers).")
        for cat in caterers:
            fields = cat["fields"]
            name = fields.get("Caterer Name")
            # Check contacts
            if not fields.get("Contact Name") or not fields.get("Contact Email"):
                s.log.warning(f"Caterer '{name}' is missing contact name or email.")
                warnings += 1
            # Check linked schools
            if not fields.get("Serves Schools"):
                s.log.warning(f"Caterer '{name}' is not linked to any 'Serves Schools' records.")
                warnings += 1

    # Audit Menu Items
    menu_items = records_by_table.get("Menu Items", [])
    if len(menu_items) == 0:
        s.log.error("Menu Items table is empty!")
        errors += 1
    else:
        s.log.info(f"✓ Menu Items table populated with {len(menu_items)} items.")
        halal_count = sum(1 for item in menu_items if "Halal" in item["fields"].get("Dietary Tags", []))
        s.log.info(f"  └─ Halal tagged items: {halal_count} / {len(menu_items)}")

    # Audit Students
    students = records_by_table.get("Students", [])
    if len(students) == 0:
        s.log.error("Students table is empty!")
        errors += 1
    else:
        s.log.info(f"✓ Students table populated with {len(students)} students.")
        unlinked_students = sum(1 for std in students if not std["fields"].get("Sessions"))
        if unlinked_students > 0:
            s.log.warning(f"{unlinked_students} students are not linked to any active sessions.")
            warnings += 1

    # Audit Sessions
    sessions = records_by_table.get("Sessions", [])
    if len(sessions) == 0:
        s.log.error("Sessions table is empty!")
        errors += 1
    else:
        s.log.info(f"✓ Sessions table populated with {len(sessions)} records.")
        for sess in sessions:
            fields = sess["fields"]
            sess_id = fields.get("Session ID")
            if not fields.get("School"):
                s.log.error(f"Session '{sess_id}' is missing school link.")
                errors += 1
            if not fields.get("Caterer"):
                s.log.warning(f"Session '{sess_id}' is missing caterer link.")
                warnings += 1
            if not fields.get("On-Site Manager"):
                s.log.warning(f"Session '{sess_id}' is missing On-Site Manager link.")
                warnings += 1

    # Audit Absences
    absences = records_by_table.get("Absences", [])
    s.log.info(f"✓ Absences table has {len(absences)} records.")
    for abs_rec in absences:
        fields = abs_rec["fields"]
        if not fields.get("Student") or not fields.get("Session"):
            s.log.error(f"Absence record '{fields.get('Absence ID')}' is missing Student or Session links.")
            errors += 1

    # Audit Exclusions
    exclusions = records_by_table.get("Exclusions", [])
    s.log.info(f"✓ Exclusions table has {len(exclusions)} records.")
    for excl in exclusions:
        fields = excl["fields"]
        if not fields.get("School") or not fields.get("Date"):
            s.log.error(f"Exclusion record '{fields.get('Exclusion ID')}' is missing School link or Date.")
            errors += 1

    s.log.info("=== AUDIT SUMMARY ===")
    s.log.info(f"Errors found: {errors}")
    s.log.info(f"Warnings found: {warnings}")
    
    if errors == 0:
        s.log.info("🎉 SUCCESS: All database integrity audits passed cleanly!")
    else:
        s.log.error("❌ FAILED: Schema audit found structural errors. Review logs above.")

if __name__ == "__main__":
    verify_migration()
