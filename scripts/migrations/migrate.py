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

import sys
from pathlib import Path

# Allow sibling modules to be imported by short name.
sys.path.insert(0, str(Path(__file__).parent))

import dietary_restrictions
import schools
import caterers
import caterer_contacts
import caterer_menus
import sessions
import students
import absences
import exclusions

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


def run():
    for mod in PIPELINE:
        mod.run()


if __name__ == "__main__":
    run()
