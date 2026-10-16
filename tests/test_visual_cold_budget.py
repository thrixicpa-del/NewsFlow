"""Job-local cold feature admission uses disposable media and SQLite only."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import IMAGE_MODEL, TEXT_MODEL, ClipIndex
from scriptor.visual_evidence import TAXONOMY, TAXONOMY_VERSION


class VisualColdBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="newsflow-cold-credit-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.clip = root / "synthetic.mp4"
        self.clip.write_bytes(b"synthetic media; no decoder is run")
        self.index = ClipIndex(root / "index.sqlite3")
        self.index._visual_memory_clear()
        self.index._loaded_model_revision = self.index._local_model_revision()

    def fail_decode(self, start, duration):
        with (patch.object(self.index, "_models", return_value=(object(), object())),
              patch.object(self.index, "_sample_visual_window", side_effect=ValueError("synthetic decode stop"))):
            return self.index._visual_window_features(self.clip, start, duration)[1]

    def insert_exact_scores(self, start, duration):
        stat = self.clip.stat()
        revision = json.dumps(self.index._local_model_revision(), sort_keys=True)
        key = (str(self.clip.resolve()).casefold(), stat.st_size, stat.st_mtime_ns,
               start.hex(), duration.hex(), IMAGE_MODEL, TEXT_MODEL, revision, TAXONOMY_VERSION)
        cache_key = hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()
        with self.index._connect() as connection:
            connection.execute(
                "INSERT INTO visual_window_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cache_key, str(self.clip.resolve()), stat.st_size, stat.st_mtime_ns,
                 start, duration, IMAGE_MODEL, TEXT_MODEL, TAXONOMY_VERSION,
                 b"", json.dumps([{"port": .8}] * 3),
                 json.dumps([start + .5, start + 2., start + duration - .5]), revision),
            )

    def test_ordinary_release_carries_and_one_grant_cannot_fund_other_windows(self):
        index = self.index
        self.assertTrue(hasattr(index, "begin_visual_scene_admission"), "scene admission is required")
        index.begin_visual_scene_admission(1, 50)
        self.assertEqual("scene-cold-credit-deferred", self.fail_decode(0., 6.))
        with index.visual_cold_window_grant(self.clip, 0., 6.):
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(1., 6.))
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(0., 6.398))
            self.assertEqual("window-assessment-unavailable:ValueError", self.fail_decode(0., 6.))
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(0., 6.))
        self.assertEqual(1, index._visual_cold_windows)
        index.begin_visual_scene_admission(2, 50)
        for start in (2., 3., 4.):
            with index.visual_cold_window_grant(self.clip, start, 6.):
                self.assertEqual("window-assessment-unavailable:ValueError", self.fail_decode(start, 6.))
        self.assertEqual(4, index._visual_cold_windows)
        with index.visual_cold_window_grant(self.clip, 5., 6.):
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(5., 6.))
        self.assertEqual(4, index._visual_cold_windows)

    def test_emergency_debt_has_three_charge_limit_and_aggregate_tail_reserve(self):
        index = self.index
        self.assertTrue(hasattr(index, "begin_visual_scene_admission"), "scene admission is required")
        index.begin_visual_scene_admission(1, 50)
        for start in (0., 1.):
            with index.visual_cold_window_grant(self.clip, start, 6.):
                self.assertEqual("window-assessment-unavailable:ValueError", self.fail_decode(start, 6.))
        for start in (2., 3., 4.):
            with index.visual_cold_window_grant(self.clip, start, 6., emergency=True):
                self.assertEqual("window-assessment-unavailable:ValueError", self.fail_decode(start, 6.))
        with index.visual_cold_window_grant(self.clip, 5., 6., emergency=True):
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(5., 6.))
        self.assertEqual(5, index._visual_cold_windows)
        index.begin_visual_scene_admission(2, 50)
        with index.visual_cold_window_grant(self.clip, 6., 6.):
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(6., 6.))
        index._visual_cold_windows = 48
        with index.visual_cold_window_grant(self.clip, 7., 6., emergency=True):
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(7., 6.))

    def test_deferred_miss_does_not_hide_external_exact_features(self):
        index = self.index
        index.begin_visual_scene_admission(1, 50)
        with index.read_session():
            self.assertEqual("scene-cold-credit-deferred", index._visual_window_features(self.clip, 17., 6.)[1])
            self.assertFalse(index._visual_raw_misses)
            self.insert_exact_scores(17., 6.)
            value, source = index._visual_window_features(self.clip, 17., 6.)
        self.assertEqual("sqlite", source)
        self.assertEqual(.8, value["per_frame_scores"][0]["port"])
        self.assertEqual(0, index._visual_cold_windows)

    def test_curated_evidence_and_hard_budget_survive_scene_gate(self):
        index = self.index
        stat = self.clip.stat()
        with index._connect() as connection:
            connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                               (str(self.clip.resolve()), self.clip.name, stat.st_size, stat.st_mtime_ns, 30.))
        index._visual_models_available = lambda: True
        index.set_visual_evidence(str(self.clip),
                                  [{"kind": "port", "start": 17., "end": 23., "source": "manual"}])
        index.begin_visual_scene_admission(1, 50)
        index._visual_cold_windows = 96
        result = index.assess_visual_window("seaport cargo", self.clip, 17., 6.)
        self.assertEqual("direct", result["relation"])
        self.assertEqual("curated-interval", result["source"])
        with index.visual_cold_window_grant(self.clip, 0., 6.):
            self.assertEqual("cold-window-budget-exhausted", self.fail_decode(0., 6.))
        self.assertEqual(96, index._visual_cold_windows)

    def test_legacy_clipindex_use_is_unrestricted_by_scene_admission(self):
        with self.index.visual_cold_window_grant(self.clip, 0., 6.):
            self.assertEqual("window-assessment-unavailable:ValueError", self.fail_decode(0., 6.))
        self.assertEqual(1, self.index._visual_cold_windows)

    def test_grant_expires_when_source_or_model_identity_changes(self):
        index = self.index
        index.begin_visual_scene_admission(1, 50)
        with index.visual_cold_window_grant(self.clip, 0., 6.):
            self.clip.write_bytes(b"a different synthetic source signature")
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(0., 6.))
        with index.visual_cold_window_grant(self.clip, 0., 6.):
            index._loaded_model_revision = {"image": "changed", "text": "changed"}
            self.assertEqual("scene-cold-credit-deferred", self.fail_decode(0., 6.))
        self.assertEqual(0, index._visual_cold_windows)

    def test_exact_old_taxonomy_vectors_rescore_without_scene_credit(self):
        index = self.index
        stat = self.clip.stat()
        revision = json.dumps(index._local_model_revision(), sort_keys=True)
        with index._connect() as connection:
            connection.execute(
                "INSERT INTO visual_window_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("old-taxonomy", str(self.clip.resolve()), stat.st_size, stat.st_mtime_ns,
                 5., 6.398, IMAGE_MODEL, TEXT_MODEL, TAXONOMY_VERSION - 1,
                 np.zeros((3, 512), dtype=np.float32).tobytes(),
                 json.dumps([{"port": .1}] * 3), json.dumps([5.5, 8., 10.5]), revision),
            )
        index.begin_visual_scene_admission(1, 50)
        shape = sum(len(queries) for queries in TAXONOMY.values()), 512
        with (patch.object(index, "_cached_text_model", return_value=object()),
              patch.object(index, "_query_vectors", return_value=np.zeros(shape, dtype=np.float32)),
              patch.object(index, "_sample_visual_window", side_effect=AssertionError("decoded image"))):
            value, source = index._visual_window_features(self.clip, 5., 6.398)
        self.assertEqual("sqlite-vectors-rescored", source)
        self.assertEqual([5.5, 8., 10.5], value["sample_times"])
        self.assertEqual(0, index._visual_cold_windows)


if __name__ == "__main__":
    unittest.main()
