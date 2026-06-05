"""
Full migration orchestrator. Runs all migrations in dependency order:

  dietary_restrictions  (no deps)
  schools               (no deps — seeded from sessions.xlsx)
  caterers              (no deps)
  caterer_contacts      (← caterers, schools)
  caterer_menus         (← caterers, dietary_restrictions)
  sessions              (← schools, caterers)
  students              (← sessions, schools, dietary_restrictions)
  absences              (← students, sessions)
  exclusions            (← schools)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow sibling modules to be imported by short name.
sys.path.insert(0, str(Path(__file__).parent))

import absences
import caterer_contacts
import caterer_menus
import caterers
import dietary_restrictions
import exclusions
import schools
import sessions
import students

from support import Database, log

PIPELINE = [
    dietary_restrictions,
    schools,
    caterers,
    caterer_contacts,
    caterer_menus,
    sessions,
    students,
    absences,
    exclusions,
]

# Junction tables have no `id` column; map them to a known NOT NULL FK column
# so we can issue a "delete all" via a not.is.null filter.
_JUNCTION_CLEAR: dict[str, str] = {
    "student_dietary_restrictions": "student_id",
    "student_sessions":             "student_id",
    "session_year_levels":          "session_id",
    "caterer_legend_tags":          "caterer_id",
    "caterer_schools":              "caterer_id",
    "menu_item_dietary_tags":       "menu_item_id",
    "dietary_restriction_supersets": "restriction_id",
    "order_students":               "order_id",
    "exclusion_year_levels":        "exclusion_id",
}

# Main tables in reverse dependency order (safe to clear after junctions are gone).
_MAIN_WIPE_ORDER = [
    "scheduled_emails",
    "caterer_switch_proposals",
    "dietary_clarification_requests",
    "dietary_inbound_messages",
    "support_cases",
    "support_inbound_messages",
    "exclusions",
    "absences",
    "manager_substitutions",
    "orders",
    "weekly_orders",
    "caterer_feedback",
    "students",
    "sessions",
    "menu_items",
    "on_site_managers",
    "caterers",
    "schools",
    "dietary_restrictions",
]


def _wipe(db: Database) -> None:
    log.info("Wiping all tables...")
    for table_name, fk_col in _JUNCTION_CLEAR.items():
        db._client.table(table_name).delete().filter(fk_col, "not.is", "null").execute()
        log.info(f"Cleared junction table {table_name}")
    for table_name in _MAIN_WIPE_ORDER:
        db._table(table_name).clear()
    log.info("All tables cleared.")


def run(db: Database | None = None, wipe: bool = False) -> None:
    db = db or Database.from_env()
    if wipe:
        _wipe(db)
    for mod in PIPELINE:
        mod.run(db)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all migrations in dependency order.")
    parser.add_argument("--wipe", action="store_true", help="Clear all tables before migrating.")
    parser.add_argument("--yes", action="store_true", help="Skip the wipe confirmation prompt.")
    args = parser.parse_args()

    if args.wipe and not args.yes:
        print("WARNING: This will permanently delete ALL records from ALL tables.")
        answer = input("Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    run(wipe=args.wipe)
