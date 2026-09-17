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

    def test_windows_lane_is_separate_from_hosted_release_packaging(self):
        workflow = (ROOT / ".github" / "workflows" / "windows-native.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("pnpm build:web", workflow)
        self.assertNotIn("package:release", workflow)
