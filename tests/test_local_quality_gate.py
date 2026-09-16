from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LocalQualityGateTests(unittest.TestCase):
    def test_hook_and_installer_use_the_fast_local_gate(self):
        hook = (ROOT / ".githooks" / "pre-commit").read_text(encoding="utf-8")
        installer = (ROOT / "scripts" / "install-git-hooks.ps1").read_text(encoding="utf-8")
        self.assertIn("fast-local-gate.ps1", hook)
        self.assertIn("core.hooksPath", installer)

    def test_fast_gate_checks_a_python_change_without_running_full_ci(self):
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", "scripts/fast-local-gate.ps1", "-Paths", "scripts/secret-scan.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("FAST_LOCAL_GATE=PASS", result.stdout)

