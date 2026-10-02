"""Offline report only; run through tests/run_isolated.py."""
import json
import unittest
from pathlib import Path

from tests.test_cover_quality_selection import replay_saved_responses


class ReplayReport(unittest.TestCase):
    def test_replay(self):
        results = replay_saved_responses()
        self.assertEqual(len(results), 17)
        destination = Path(__file__).resolve().parents[1] / "docs/evidence/issue-316-quality-offline"
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "replay.json").write_text(json.dumps({
            "type": "OFFLINE_REVALIDATION_ORIGINAL_CONTEXT", "paid_calls": 0,
            "responses": results,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
