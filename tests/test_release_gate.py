from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseGateTests(unittest.TestCase):
    def test_dry_run_lists_the_complete_fail_closed_release_sequence(self):
        result = subprocess.run(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/release-gate.ps1",
                "-DryRun",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plan = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(
            [
                "repo-state",
                "toolchain",
                "production-integrity-capture",
                "dependencies",
                "lint",
                "frontend-typecheck",
                "python-suite",
                "frontend-suite",
                "visual-regression",
                "security",
                "performance",
                "core-runtime",
                "immutable-package",
                "artifact-manifest",
                "packaged-smoke",
                "production-integrity-verify",
            ],
            plan["steps"],
        )
        self.assertTrue(plan["requiresPackage"])
