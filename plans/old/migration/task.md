# Task Checklist - Padea Data Migration

- [x] Create `scripts/__init__.py` and the shared helper library `scripts/support.py`
- [x] Create `scripts/schema.py` containing the schema specification
- [x] Create `scripts/update_schema.py` to programmatically update the Airtable database schema
- [x] Run `python3 scripts/update_schema.py` to build the Airtable schema
- [x] Implement and run migration for `caterers` (`migrations/caterers.py`)
- [x] Implement and run migration for `caterer_contacts` (`migrations/caterer_contacts.py`)
- [x] Implement and run migration for `caterer_menus` (`migrations/caterer_menus.py`)
- [x] Implement and run migration for `sessions` (`migrations/sessions.py`)
- [x] Implement and run migration for `students` (`migrations/students.py`)
- [x] Implement and run migration for `absences` (`migrations/absences.py`)
- [x] Implement and run migration for `exclusions` (`migrations/exclusions.py`)
- [x] Create and run `scripts/verify_migration.py` to validate record counts and relations
- [x] Complete the migration walkthrough report (`walkthrough.md`)
