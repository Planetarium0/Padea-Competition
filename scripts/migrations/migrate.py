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

import sys
from pathlib import Path

# Allow sibling modules to be imported by short name.
sys.path.insert(0, str(Path(__file__).parent))

import absences  # noqa: E402
import caterer_contacts  # noqa: E402
import caterer_menus  # noqa: E402
import caterers  # noqa: E402
import dietary_restrictions  # noqa: E402
import exclusions  # noqa: E402
import schools  # noqa: E402
import sessions  # noqa: E402
import students  # noqa: E402

from support import Database  # noqa: E402

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


def run(db: Database | None = None) -> None:
    db = db or Database.from_env()
    for mod in PIPELINE:
        mod.run(db)


if __name__ == "__main__":
    run()
