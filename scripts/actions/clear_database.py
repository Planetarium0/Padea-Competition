"""
clear_database.py — Delete every record from every table in the Airtable base.

Prompts for confirmation before proceeding. Intended for dev/test resets only.

Usage:
  python scripts/clear_database.py [--yes]
"""

from __future__ import annotations

import argparse
import sys

from data.schema import TABLES_SCHEMA
from support import Database, log


def clear_database(yes: bool = False) -> None:
    try:
        db = Database.from_env()
    except RuntimeError as e:
        log.error(f"{e}. Exiting.")
        sys.exit(1)

    if not yes:
        print("This will permanently delete ALL records from the following tables:")
        for name in TABLES_SCHEMA:
            print(f"  • {name}")
        answer = input("\nType 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            sys.exit(0)

    for name in TABLES_SCHEMA:
        table = db._table(name)
        log.info(f"Clearing {name}...")
        table.clear()

    log.info("Database cleared.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clear all records from the Airtable base.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    args = parser.parse_args()
    clear_database(yes=args.yes)
