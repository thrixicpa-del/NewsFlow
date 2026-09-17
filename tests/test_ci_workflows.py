from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CiWorkflowTests(unittest.TestCase):
    def test_primary_ci_declares_required_quality_jobs(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for fragment in (
            "pnpm install --frozen-lockfile",
            "scripts/release-lint.ps1",
            "pnpm typecheck",
            "tests/run_isolated.py",
            "pnpm test:ui",
            "verify:security",
            "pnpm build",
        ):
            self.assertIn(fragment, workflow)
        self.assertNotIn("ruff check scripts tests", workflow)

    def test_hosted_python_lane_has_an_explicit_disposable_production_boundary(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("LOCALAPPDATA: ${{ runner.temp }}/newsflow-production-boundary", workflow)

    def test_codeql_is_documented_as_optional_when_private_code_scanning_is_unavailable(self):
        workflow = (ROOT / ".github" / "workflows" / "codeql.yml").read_text(encoding="utf-8")
        security_docs = (ROOT / "docs" / "obsidian" / "NewsFlow" / "01 - Architecture" / "Security Gates.md").read_text(encoding="utf-8")

        self.assertIn("vars.NEWSFLOW_CODE_SCANNING_ENABLED == 'true'", workflow)
        self.assertIn("CodeQL", security_docs)
        self.assertIn("local security gates remain required", security_docs)

    def test_windows_lane_is_separate_from_hosted_release_packaging(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-native.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("pnpm build:web", workflow)
        self.assertNotIn("package:release", workflow)
