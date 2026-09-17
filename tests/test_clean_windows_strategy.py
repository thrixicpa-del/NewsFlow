from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CleanWindowsStrategyTests(unittest.TestCase):
    def test_clean_windows_strategy_protects_production_data_and_credentials(self):
        document = (ROOT / "docs" / "obsidian" / "NewsFlow" / "01 - Architecture" / "Clean Windows Smoke.md").read_text(encoding="utf-8")
        for fragment in ("NEWSFLOW_TEST_ROOT", "production", "credentials", "NewsFlowCore.exe", "FFmpeg", "Cyrillic", "uninstall"):
            self.assertIn(fragment, document)

