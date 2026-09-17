"""Contract for the compact deterministic NewsFlow golden dataset."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class GoldenDatasetTests(unittest.TestCase):
    def test_materialized_dataset_contains_the_safe_cross_pipeline_fixture(self):
        from tests.golden_dataset import materialize_golden_dataset

        test_root = Path(os.environ["NEWSFLOW_TEST_ROOT"])
        with tempfile.TemporaryDirectory(dir=test_root, prefix="golden-dataset-") as temporary:
            dataset = materialize_golden_dataset(Path(temporary))

            manifest = json.loads((dataset.root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["format"])
            self.assertEqual("golden-topic-ormuz", manifest["topics"][0]["id"])
            self.assertEqual("golden-production-ormuz", manifest["expectedMappings"]["topicToProduction"]["golden-topic-ormuz"])
            self.assertEqual("golden-channel-news", manifest["publication"]["jobs"][0]["channelId"])
            self.assertEqual(["footage/tanker.mp4"], manifest["expectedTimeline"]["clips"])
            self.assertTrue((dataset.root / "audio" / "voice.mp3").is_file())
            self.assertTrue((dataset.root / "faces" / "iranian-official.png").is_file())
            self.assertTrue((dataset.root / "covers" / "ormuz-cover.png").is_file())
            self.assertTrue((dataset.root / "footage" / "tanker.mp4").is_file())

    def test_materialization_is_repeatable_and_rejects_non_test_roots(self):
        from tests.golden_dataset import GoldenDatasetError, materialize_golden_dataset

        test_root = Path(os.environ["NEWSFLOW_TEST_ROOT"])
        with tempfile.TemporaryDirectory(dir=test_root, prefix="golden-dataset-") as temporary:
            root = Path(temporary)
            first = materialize_golden_dataset(root / "first")
            second = materialize_golden_dataset(root / "second")
            self.assertEqual(
                (first.root / "manifest.json").read_bytes(),
                (second.root / "manifest.json").read_bytes(),
            )
            self.assertEqual(
                (first.root / "faces" / "iranian-official.png").read_bytes(),
                (second.root / "faces" / "iranian-official.png").read_bytes(),
            )

        with self.assertRaises(GoldenDatasetError):
            materialize_golden_dataset(test_root.parent / "not-a-newsflow-test-root")


if __name__ == "__main__":
    unittest.main()
