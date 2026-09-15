from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class PytestArchitectureTests(unittest.TestCase):
    def test_direct_pytest_refuses_to_start_without_an_isolated_root(self):
        repository = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment.pop("NEWSFLOW_TEST_MODE", None)
        environment.pop("NEWSFLOW_TEST_ROOT", None)
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_ranges.py", "-q"],
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests/run_isolated.py --pytest", result.stdout + result.stderr)
