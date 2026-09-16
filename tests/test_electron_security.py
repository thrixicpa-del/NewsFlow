"""Executable security baseline for the Electron desktop boundary."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


class ElectronSecurityGateTests(unittest.TestCase):
    def test_repository_has_reviewable_security_automation_configuration(self):
        expected = {
            ROOT / ".gitleaks.toml": "useDefault",
            ROOT / ".github" / "dependabot.yml": "version: 2",
            ROOT / ".github" / "workflows" / "codeql.yml": "github/codeql-action/init",
            ROOT / ".github" / "workflows" / "dependency-review.yml": "dependency-review-action",
            ROOT / "scripts" / "audit-python-dependencies.ps1": "pip_audit",
        }
        for file, expected_fragment in expected.items():
            self.assertTrue(file.is_file(), file)
            self.assertIn(expected_fragment, file.read_text(encoding="utf-8"), file)

    def test_security_gate_enforces_renderer_and_ipc_hardening(self):
        result = subprocess.run(
            ["node", "scripts/security-gate.mjs"],
            cwd=APP_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SECURITY_GATE=PASS", result.stdout)

    def test_release_scripts_run_the_security_gate(self):
        package = json.loads((APP_ROOT / "package.json").read_text(encoding="utf-8"))
        scripts = package["scripts"]
        self.assertIn("verify:security", scripts)
        self.assertIn("verify:secrets", scripts)
        self.assertIn("verify:dependencies", scripts)
        self.assertIn("verify:security", scripts["package:preview"])
        self.assertIn("verify:secrets", scripts["package:preview"])
        self.assertIn("verify:dependencies", scripts["package:preview"])
        self.assertIn("verify:security", scripts["package:release"])
        self.assertIn("verify:secrets", scripts["package:release"])
        self.assertIn("verify:dependencies", scripts["package:release"])

    def test_known_high_severity_transitive_dependencies_are_pinned_safe(self):
        workspace = (APP_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
        self.assertIn("js-yaml: 4.3.2", workspace)
        self.assertIn("fast-uri: 3.1.6", workspace)


if __name__ == "__main__":
    unittest.main()
