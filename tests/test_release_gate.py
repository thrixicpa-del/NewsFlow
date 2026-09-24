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

    def test_gate_hydrates_git_history_before_lfs_and_release_lint(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")
        history_script = (ROOT / "scripts" / "prepare-git-history.ps1").read_text(encoding="utf-8")

        hydrate_history = "Invoke-GateStep -Name 'git-history' -FilePath $powerShellExecutable"
        hydrate_lfs = "Invoke-GateStep -Name 'lfs-hydration' -FilePath $powerShellExecutable"
        lint = "Invoke-GateStep -Name 'lint'"

        self.assertIn(hydrate_history, script)
        self.assertIn("scripts/prepare-git-history.ps1", script)
        self.assertLess(script.index(hydrate_history), script.index(hydrate_lfs))
        self.assertLess(script.index(hydrate_history), script.index(lint))
        self.assertIn("fetch', '--unshallow', '--no-tags', 'origin'", history_script)
        self.assertIn("654bdadc9ce673c072991298ad410687fdd6213b", history_script)
        self.assertIn("merge-base', '--is-ancestor'", history_script)
        self.assertIn("GIT_HISTORY_VERIFY=PASS", history_script)

    def test_gate_hydrates_lfs_before_production_capture_and_test_suites(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")

        hydrate = "Invoke-GateStep -Name 'lfs-hydration' -FilePath $powerShellExecutable"
        capture = "Invoke-GateStep -Name 'production-integrity-capture'"
        python_suite = "Invoke-GateStep -Name 'python-suite'"
        visual_suite = "Invoke-GateStep -Name 'visual-regression'"

        self.assertIn(hydrate, script)
        self.assertIn("scripts/prepare-lfs-assets.ps1", script)
        self.assertLess(script.index(hydrate), script.index(capture))
        self.assertLess(script.index(hydrate), script.index(python_suite))
        self.assertLess(script.index(hydrate), script.index(visual_suite))

    def test_lfs_prepare_script_hydrates_fscks_and_hash_verifies_tracked_assets(self):
        script = (ROOT / "scripts" / "prepare-lfs-assets.ps1").read_text(encoding="utf-8")

        self.assertIn("Invoke-GitLfs -Arguments @('pull')", script)
        self.assertIn("Invoke-GitLfs -Arguments @('fsck')", script)
        self.assertIn("Invoke-GitLfs -Arguments @('ls-files', '--long')", script)
        self.assertIn("version https://git-lfs.github.com/spec/v1", script)
        self.assertIn("Get-FileHash -LiteralPath $path -Algorithm SHA256", script)
        self.assertIn("assets/ffmpeg.exe", script)
        self.assertIn("GIT_LFS_VERIFY=PASS", script)

    def test_gate_installs_locked_javascript_dependencies_before_audit_and_typecheck(self):
        script = (ROOT / "scripts" / "release-gate.ps1").read_text(encoding="utf-8")

        install = "Invoke-GateStep -Name 'dependencies-install' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'install', '--frozen-lockfile')"
        audit = "Invoke-GateStep -Name 'dependencies' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'verify:dependencies')"
        typecheck = "Invoke-GateStep -Name 'frontend-typecheck' -FilePath 'pnpm' -Arguments @('--dir', $appRoot, 'typecheck')"

        self.assertIn(install, script)
        self.assertIn(audit, script)
        self.assertIn(typecheck, script)
        self.assertLess(script.index(install), script.index(audit))
        self.assertLess(script.index(audit), script.index(typecheck))

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
                "git-history",
                "lfs-hydration",
                "production-integrity-capture",
                "dependencies-install",
                "dependencies",
                "dependencies-python",
                "lint",
                "frontend-typecheck",
                "python-suite",
                "frontend-suite",
                "visual-regression",
                "security",
                "security-secrets",
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
