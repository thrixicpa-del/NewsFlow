from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseGateTests(unittest.TestCase):
    def test_gate_uses_an_explicit_powershell_host_for_nested_integrity_steps(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")

        self.assertIn("$powerShellExecutable", script)
        self.assertIn("WindowsPowerShell\\v1.0\\powershell.exe", script)
        self.assertNotIn("-FilePath 'powershell'", script)

    def test_gate_checks_native_exit_codes_without_treating_successful_stderr_as_a_failure(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")

        self.assertIn("$savedErrorActionPreference = $ErrorActionPreference", script)
        self.assertIn("$ErrorActionPreference = 'Continue'", script)
        self.assertIn("$ErrorActionPreference = $savedErrorActionPreference", script)

    def test_packaged_smoke_targets_the_unpacked_electron_runtime_not_the_portable_loader(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")

        self.assertIn("$packagedSmokeRoot = Join-Path $candidateRoot 'win-unpacked'", script)
        self.assertIn("Get-ChildItem -LiteralPath $packagedSmokeRoot", script)

    def test_ci_provisions_the_pinned_python_dependency_auditor_required_by_release(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        audit_script = (ROOT / "scripts" / "audit-python-dependencies.ps1").read_text(encoding="utf-8")

        self.assertIn("pip-audit==2.10.1", workflow)
        self.assertIn("-m pip_audit", audit_script)
        self.assertIn("--strict", audit_script)
        self.assertIn("audit-python-dependencies.ps1", workflow)

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
