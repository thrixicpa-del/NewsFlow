from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseLintTests(unittest.TestCase):
    def test_release_lint_defaults_to_the_full_phase_zero_baseline_sha(self):
        script = (ROOT / "scripts" / "release-lint.ps1").read_text(encoding="utf-8")

        self.assertIn(
            "[string]$BaseRef = '654bdadc9ce673c072991298ad410687fdd6213b'",
            script,
        )

    def test_release_lint_checks_only_the_explicit_candidate_python_files(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/release-lint.ps1",
                "-Files",
                "tests/test_release_gate.py",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("RELEASE_LINT=PASS", result.stdout)

    def test_release_lint_uses_the_phase_zero_baseline_for_a_candidate_diff(self):
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/release-lint.ps1",
                "-BaseRef",
                "654bdad",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("RELEASE_LINT=PASS candidate additions", result.stdout)
