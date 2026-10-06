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

    def test_dependency_review_is_documented_as_optional_when_github_advanced_security_is_unavailable(self):
        workflow = (ROOT / ".github" / "workflows" / "dependency-review.yml").read_text(encoding="utf-8")
        security_docs = (ROOT / "docs" / "obsidian" / "NewsFlow" / "01 - Architecture" / "Security Gates.md").read_text(encoding="utf-8")

        self.assertIn("vars.NEWSFLOW_DEPENDENCY_REVIEW_ENABLED == 'true'", workflow)
        self.assertIn("GitHub Advanced Security", security_docs)
        self.assertIn("local dependency audits remain required", security_docs)

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
        immutable_wrapper = (APP_ROOT / "scripts" / "package-immutable-rc.mjs").read_text(encoding="utf-8")
        self.assertIn("verify:security", scripts)
        self.assertIn("verify:secrets", scripts)
        self.assertIn("verify:dependencies", scripts)
        self.assertIn("package-immutable-rc.mjs", scripts["package:preview"])
        self.assertIn("package-immutable-rc.mjs", scripts["package:release"])
        self.assertIn('run(pnpm, ["verify:security"])', immutable_wrapper)
        self.assertIn('run(pnpm, ["verify:secrets"])', immutable_wrapper)
        self.assertIn('run(pnpm, ["verify:dependencies"])', immutable_wrapper)

    def test_sandboxed_preload_uses_commonjs_bridge(self):
        """Sandboxed Electron renderers cannot load an ESM-import preload."""
        main = (APP_ROOT / "electron" / "main.ts").read_text(encoding="utf-8")
        preload = (APP_ROOT / "electron" / "preload.cts").read_text(encoding="utf-8")
        tsconfig = (APP_ROOT / "electron" / "tsconfig.json").read_text(encoding="utf-8")

        self.assertIn("sandbox: true", main)
        self.assertIn("preload.cjs", main)
        self.assertIn("require('electron')", preload)
        self.assertNotIn("from 'electron'", preload)
        self.assertIn('"*.cts"', tsconfig)

    def test_renderer_styles_do_not_require_remote_google_fonts_blocked_by_csp(self):
        """A secure packaged renderer must not depend on an external stylesheet for its base font."""
        styles = (APP_ROOT / "src" / "ui" / "styles.css").read_text(encoding="utf-8")
        index = (APP_ROOT / "index.html").read_text(encoding="utf-8")

        self.assertNotIn("fonts.googleapis.com", styles)
        self.assertIn("style-src 'self'", index)

    def test_known_high_severity_transitive_dependencies_are_pinned_safe(self):
        workspace = (APP_ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
        self.assertIn("js-yaml: 4.3.2", workspace)
        self.assertIn("fast-uri: 3.1.8", workspace)
        self.assertIn("postcss-selector-parser: 7.1.6", workspace)
        self.assertIn("source-map-js: 1.2.2", workspace)


if __name__ == "__main__":
    unittest.main()
