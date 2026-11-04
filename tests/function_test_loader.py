"""Expose simple test_* functions to unittest discovery without requiring pytest."""

from __future__ import annotations

import inspect
import unittest


def load_function_tests(module) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for name, function in sorted(vars(module).items()):
        if name.startswith("test_") and inspect.isfunction(function) and not inspect.signature(function).parameters:
            suite.addTest(unittest.FunctionTestCase(function, description=name))
    return suite
