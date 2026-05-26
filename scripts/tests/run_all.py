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

import test_api
import test_evaluate_caterers
import test_execute_caterer_switch
import test_register_orders
import test_send_orders


def suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    s = unittest.TestSuite()
    for module in (
        test_api,
        test_register_orders,
        test_send_orders,
        test_evaluate_caterers,
        test_execute_caterer_switch,
    ):
        s.addTests(loader.loadTestsFromModule(module))
    return s


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)
