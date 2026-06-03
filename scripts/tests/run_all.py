"""
Test runner for all Padea action-script unit tests.

Usage (from the project root):
    PYTHONPATH=$PWD:$PWD/scripts python scripts/tests/run_all.py

Or via the run script (if a test target is added there):
    ./run test
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure the tests directory itself is on sys.path so relative fixture
# imports work regardless of the caller's working directory.
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

import test_database
import test_email
import test_error_handler
import test_evaluate_caterers
import test_execute_caterer_switch
import test_register_orders
import test_send_meals_links
import test_send_orders
import test_send_qr_emails
import test_substitutions
import test_edge_cases


def suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    s = unittest.TestSuite()
    for module in (
        test_database,
        test_email,
        test_error_handler,
        test_register_orders,
        test_send_meals_links,
        test_send_orders,
        test_send_qr_emails,
        test_substitutions,
        test_evaluate_caterers,
        test_execute_caterer_switch,
        test_edge_cases,
    ):
        s.addTests(loader.loadTestsFromModule(module))
    return s


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)
