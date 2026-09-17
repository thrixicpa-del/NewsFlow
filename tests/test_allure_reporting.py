from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTING_MODULE = ROOT / "scripts" / "allure_reporting.py"


def load_reporting_module():
    specification = importlib.util.spec_from_file_location("newsflow_allure_reporting", REPORTING_MODULE)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


class AllureReportingTests(unittest.TestCase):
    def test_failed_suite_result_includes_error_log_and_screenshot_attachment(self):
        reporting = load_reporting_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screenshot = root / "electron-e2e.png"
            screenshot.write_bytes(b"png-fixture")

            result_path = reporting.write_suite_result(
                results_root=root / "results",
                suite="E2E",
                name="source-e2e",
                status="failed",
                started_at=1_700_000_000_000,
                stopped_at=1_700_000_000_123,
                stdout="test output",
                stderr="traceback output",
                screenshots=[screenshot],
            )
            result = json.loads(result_path.read_text(encoding="utf-8"))

            self.assertEqual("failed", result["status"])
            self.assertEqual("E2E", next(label["value"] for label in result["labels"] if label["name"] == "suite"))
            self.assertIn("traceback output", result["statusDetails"]["message"])
            attachment_names = {attachment["name"] for attachment in result["attachments"]}
            self.assertTrue({"stdout", "stderr", "electron-e2e.png"}.issubset(attachment_names))
            for attachment in result["attachments"]:
                self.assertTrue((result_path.parent / attachment["source"]).is_file())

    def test_report_runner_dry_run_lists_python_frontend_and_optional_smoke_suites(self):
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/run-allure-report.ps1", "-DryRun"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        plan = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(["python", "frontend", "integration", "source-e2e", "packaged-smoke"], plan["suites"])
        self.assertTrue(plan["testOnly"])

    def test_frontend_suite_uses_the_platform_pnpm_executable(self):
        reporting = load_reporting_module()
        frontend = next(suite for suite in reporting.suite_plan(False, "") if suite.key == "frontend")

        self.assertEqual("pnpm.cmd" if os.name == "nt" else "pnpm", frontend.command[0])


if __name__ == "__main__":
    unittest.main()
