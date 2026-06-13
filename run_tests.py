#!/usr/bin/env python3
"""Run repo-intel tests (stdlib unittest)."""

import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
