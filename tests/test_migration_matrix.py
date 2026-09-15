"""Disposable compatibility matrix for supported NewsFlow settings schemas."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import config
from scriptor.config import app_data_root, load_settings

FIXTURES = Path(__file__).with_name("migration-fixtures")


class MigrationCompatibilityMatrixTests(unittest.TestCase):
    def _run_fixture(self, filename: str) -> tuple[dict, dict]:
        root = Path(os.environ["NEWSFLOW_TEST_ROOT"]) / f"migration-{filename}"
        root.mkdir(parents=True, exist_ok=True)
        original = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
        with patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1",
            "NEWSFLOW_TEST_ROOT": str(root),
            "LOCALAPPDATA": str(root),
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root.parent / "production-local-appdata"),
        }, clear=False):
            path = app_data_root() / "settings.json"
            path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
            config.seal_current_runtime_storage()
            upgraded = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_settings()
        return upgraded, {"ideas": loaded.idea_results, "covers": loaded.cover_queue}

    def test_schema_three_snapshot_is_sealed_without_losing_or_resurrecting_records(self):
        upgraded, projection = self._run_fixture("schema-3-current.json")

        self.assertEqual(4, upgraded["schema_version"])
        self.assertEqual(["Current topic"], upgraded["idea_results"])
        self.assertEqual(["legacy-cover:historical"], upgraded["cover_queue_tombstones"])
        self.assertEqual(["Current topic"], projection["ideas"])
        self.assertEqual(["current-cover-1"], [item["production_item_id"] for item in projection["covers"]])

    def test_schema_zero_snapshot_seals_to_current_without_auto_importing_legacy_business_state(self):
        upgraded, projection = self._run_fixture("schema-0-empty.json")

        self.assertEqual(4, upgraded["schema_version"])
        self.assertEqual([], projection["ideas"])
        self.assertEqual([], projection["covers"])


if __name__ == "__main__":
    unittest.main()
