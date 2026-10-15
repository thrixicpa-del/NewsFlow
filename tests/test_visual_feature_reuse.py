"""Taxonomy upgrades reuse versioned, exact-window vectors without decoding."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import IMAGE_MODEL, TEXT_MODEL, ClipIndex
from scriptor.footage import FootageItem
from scriptor.visual_evidence import TAXONOMY, TAXONOMY_VERSION


class VisualFeatureReuseTests(unittest.TestCase):
    def test_repeated_zero_budget_raw_miss_avoids_feature_selects_within_session(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            index, clip = self.fixture(Path(temporary))
            feature_selects = []
            with index.read_session():
                index._read_session_connection.set_trace_callback(
                    lambda statement: feature_selects.append(statement)
                    if statement.startswith("SELECT ") and "FROM visual_window_features" in statement else None
                )
                try:
                    for _ in range(3):
                        value, state = index._visual_window_features(clip, 17., 6.)
                        self.assertIsNone(value)
                        self.assertEqual("cold-window-budget-exhausted", state)
                finally:
                    index._read_session_connection.set_trace_callback(None)
            self.assertEqual(2, len(feature_selects), feature_selects)
            self.assertEqual(2, index._visual_raw_miss_hits)
            self.assertEqual(1, index._visual_raw_miss_misses)

    def test_raw_miss_expires_with_session_and_budget_change(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            index, clip = self.fixture(Path(temporary))
            selects = []
            with index.read_session():
                index._read_session_connection.set_trace_callback(
                    lambda sql: selects.append(sql) if "FROM visual_window_features" in sql else None)
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                self.assertEqual(2, len(selects))
                index.visual_window_budget = 1
                index._loaded_model_revision = index._local_model_revision()
                with (patch.object(index, "_models", return_value=(object(), object())),
                      patch.object(index, "_sample_visual_window", side_effect=ValueError("synthetic decode stop"))):
                    self.assertEqual("window-assessment-unavailable:ValueError",
                                     index._visual_window_features(clip, 17., 6.)[1])
                self.assertEqual(1, index._visual_cold_windows)
                self.assertEqual(4, len(selects))
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                self.assertEqual(6, len(selects))
                index._visual_cold_windows = 0
                with (patch.object(index, "_models", return_value=(object(), object())),
                      patch.object(index, "_sample_visual_window", side_effect=ValueError("synthetic decode stop"))):
                    self.assertEqual("window-assessment-unavailable:ValueError",
                                     index._visual_window_features(clip, 17., 6.)[1])
                self.assertEqual(8, len(selects))
                index._read_session_connection.set_trace_callback(None)
            index.visual_window_budget = 0
            index._visual_cold_windows = 0
            with index.read_session():
                index._read_session_connection.set_trace_callback(
                    lambda sql: selects.append(sql) if "FROM visual_window_features" in sql else None)
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                index._read_session_connection.set_trace_callback(None)
            self.assertEqual(10, len(selects))

    def test_raw_miss_identity_includes_source_window_model_and_taxonomy(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            index, clip = self.fixture(Path(temporary))
            other = clip.with_name("other.mp4")
            other.write_bytes(clip.read_bytes())
            text_ref = index.model_cache / ("models--" + TEXT_MODEL.replace("/", "--")) / "refs" / "main"
            selects = []
            with index.read_session():
                index._read_session_connection.set_trace_callback(
                    lambda sql: selects.append(sql) if "FROM visual_window_features" in sql else None)
                for source, start in ((clip, 17.), (clip, 18.), (other, 17.)):
                    self.assertEqual("cold-window-budget-exhausted",
                                     index._visual_window_features(source, start, 6.)[1])
                clip.write_bytes(b"new synthetic source identity")
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                text_ref.write_text("local-revision-B", encoding="utf-8")
                self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                with patch("scriptor.visual_evidence.TAXONOMY_VERSION", TAXONOMY_VERSION + 1):
                    self.assertEqual("cold-window-budget-exhausted", index._visual_window_features(clip, 17., 6.)[1])
                index._read_session_connection.set_trace_callback(None)
            self.assertEqual(12, len(selects))

    def test_external_old_taxonomy_vectors_win_after_raw_miss(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            reader, clip = self.fixture(Path(temporary))
            writer = ClipIndex(reader.db_path)
            with reader.read_session():
                self.assertEqual("cold-window-budget-exhausted", reader._visual_window_features(clip, 17., 6.)[1])
                with writer._connect() as connection:
                    connection.execute(
                        "UPDATE visual_window_features SET source_start=?,sample_times=? WHERE cache_key=?",
                        (17., json.dumps([17.5, 20., 22.5]), "older-taxonomy"),
                    )
                reader._text_embedder = self.text_model()
                reader._loaded_model_revision = reader._local_model_revision()
                with patch.object(reader, "_sample_visual_window", side_effect=AssertionError("decoded image")):
                    value, state = reader._visual_window_features(clip, 17., 6.)
            self.assertEqual("sqlite-vectors-rescored", state)
            self.assertEqual([17.5, 20., 22.5], value["sample_times"])

    def test_external_insert_between_select_and_memo_stamp_is_seen_on_next_call(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            reader, clip = self.fixture(Path(temporary))
            writer = ClipIndex(reader.db_path)
            scores = [{"port": .8, "leisure": .1}] * 3
            inserted = False

            def insert_after_feature_selects(sql):
                nonlocal inserted
                if not inserted and "FROM clips WHERE path=" in sql:
                    inserted = True
                    self.insert_exact_scores(writer, clip, 17., 6., scores)

            with reader.read_session():
                reader._read_session_connection.set_trace_callback(insert_after_feature_selects)
                try:
                    self.assertEqual("cold-window-budget-exhausted", reader._visual_window_features(clip, 17., 6.)[1])
                finally:
                    reader._read_session_connection.set_trace_callback(None)
                self.assertTrue(inserted)
                self.assertFalse(reader._visual_raw_misses)
                self.assertEqual(1, reader._visual_raw_miss_invalidations)
                value, state = reader._visual_window_features(clip, 17., 6.)
            self.assertEqual("sqlite", state)
            self.assertEqual(scores, value["per_frame_scores"])

    def test_global_feature_memory_wins_after_raw_miss(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            reader, clip = self.fixture(Path(temporary))
            writer = ClipIndex(reader.db_path)
            scores = [{"port": .8, "leisure": .1}] * 3
            with reader.read_session():
                self.assertEqual("cold-window-budget-exhausted", reader._visual_window_features(clip, 17., 6.)[1])
                self.insert_exact_scores(writer, clip, 17., 6., scores)
                self.assertEqual("sqlite", writer._visual_window_features(clip, 17., 6.)[1])
                value, state = reader._visual_window_features(clip, 17., 6.)
            self.assertEqual("memory", state)
            self.assertEqual(scores, value["per_frame_scores"])

    def test_curated_annotation_update_wins_after_raw_miss(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-miss-") as temporary:
            reader, clip = self.fixture(Path(temporary))
            writer = ClipIndex(reader.db_path)
            stat = clip.stat()
            with writer._connect() as connection:
                connection.execute("INSERT INTO clips(path,name,size,mtime_ns,duration) VALUES(?,?,?,?,?)",
                                   (str(clip.resolve()), clip.name, stat.st_size, stat.st_mtime_ns, 30.))
            reader._visual_models_available = lambda: True
            with reader.read_session():
                self.assertEqual("cold-window-budget-exhausted",
                                 reader.assess_visual_window("seaport cargo", clip, 17., 6.)["reason"])
                writer.set_visual_evidence(str(clip),
                                           [{"kind": "port", "start": 17., "end": 23., "source": "manual"}])
                result = reader.assess_visual_window("seaport cargo", clip, 17., 6.)
            self.assertEqual("direct", result["relation"])
            self.assertEqual("curated-interval", result["source"])

    @staticmethod
    def insert_exact_scores(index, clip, start, duration, scores):
        stat = clip.stat()
        revision = json.dumps(index._local_model_revision(), sort_keys=True)
        key = (str(clip.resolve()).casefold(), stat.st_size, stat.st_mtime_ns,
               start.hex(), duration.hex(), IMAGE_MODEL, TEXT_MODEL, revision, TAXONOMY_VERSION)
        cache_key = hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()
        with index._connect() as connection:
            connection.execute(
                "INSERT INTO visual_window_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cache_key, str(clip.resolve()), stat.st_size, stat.st_mtime_ns,
                 start, duration, IMAGE_MODEL, TEXT_MODEL, TAXONOMY_VERSION,
                 b"", json.dumps(scores), json.dumps([start + 1., start + 3., start + 5.]), revision),
            )

    def test_zero_budget_feature_misses_reuse_read_session_connection(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-reader-") as temporary:
            index, clip = self.fixture(Path(temporary))
            with index.read_session(), patch("sqlite3.connect", wraps=sqlite3.connect) as opens:
                for start in range(40):
                    value, state = index._visual_window_features(clip, float(start + 100), 6.)
                    self.assertIsNone(value)
                    self.assertEqual("cold-window-budget-exhausted", state)
                self.assertEqual(0, opens.call_count)

    def test_feature_reader_sees_external_cache_insert_during_read_session(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-feature-reader-") as temporary:
            reader, clip = self.fixture(Path(temporary))
            writer = ClipIndex(reader.db_path)
            start, duration = 17., 6.
            stat = clip.stat()
            revision = json.dumps(reader._local_model_revision(), sort_keys=True)
            key = (str(clip.resolve()).casefold(), stat.st_size, stat.st_mtime_ns,
                   start.hex(), duration.hex(), IMAGE_MODEL, TEXT_MODEL, revision, TAXONOMY_VERSION)
            cache_key = hashlib.sha256(json.dumps(key).encode("utf-8")).hexdigest()
            scores = [{"port": .8, "leisure": .1}] * 3
            with reader.read_session():
                self.assertEqual("cold-window-budget-exhausted",
                                 reader._visual_window_features(clip, start, duration)[1])
                with writer._connect() as connection:
                    connection.execute(
                        "INSERT INTO visual_window_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (cache_key, str(clip.resolve()), stat.st_size, stat.st_mtime_ns,
                         start, duration, IMAGE_MODEL, TEXT_MODEL, TAXONOMY_VERSION,
                         b"", json.dumps(scores), json.dumps([18., 20., 22.]), revision),
                    )
                value, state = reader._visual_window_features(clip, start, duration)
                self.assertEqual("sqlite", state)
                self.assertEqual(scores, value["per_frame_scores"])

    def test_fresh_add_item_placeholder_duration_cannot_reject_valid_later_window(self):
        import cv2
        with tempfile.TemporaryDirectory(prefix='newsflow-placeholder-duration-') as temporary:
            root = Path(temporary)
            clip = root / 'twenty-seconds.avi'
            writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*'MJPG'), 5, (32, 24))
            self.assertTrue(writer.isOpened())
            try:
                for _ in range(100):
                    writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
            finally:
                writer.release()
            index = ClipIndex(root / 'index.sqlite3')
            index.add_item(FootageItem(str(clip), clip.name))
            index._visual_models_available = lambda: True
            vector = np.zeros(512, dtype=np.float32)
            vector[:3] = [.35, .10, .05]
            vector[-1] = np.sqrt(1 - float(vector @ vector))

            class Image:
                def embed(self, images, **_kwargs):
                    yield from [vector] * len(images)

            index._image_embedder, index._text_embedder = Image(), self.text_model()
            index._loaded_model_revision = index._local_model_revision()
            with patch.object(index, '_sample_visual_window', wraps=index._sample_visual_window) as decode:
                result = index.assess_visual_window('seaport cargo cranes ships', clip, 6, 6)
            self.assertEqual('direct', result['relation'])
            self.assertEqual(1, decode.call_count)
            self.assertEqual(3, len(result['sample_times']))
            self.assertTrue(all(6 <= time < 12 for time in result['sample_times']))

    def test_repeated_outside_source_window_spends_no_cold_budget_or_model_work(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-short-window-") as temporary:
            index, clip = self.fixture(Path(temporary))
            index.visual_window_budget = 96
            index._loaded_model_revision = index._local_model_revision()
            signature = clip.stat()
            with index._connect() as connection:
                connection.execute('INSERT INTO clips(path,name,size,mtime_ns,duration,width,height,fps,embedding,model,indexed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                   (str(clip.resolve()), clip.name, signature.st_size, signature.st_mtime_ns, 3., 32, 24, 0., bytes(2048), IMAGE_MODEL, 1.))
            with (patch.object(index, '_models', return_value=(object(), object())) as models,
                  patch.object(index, '_sample_visual_window', side_effect=ValueError('window-outside-source')) as decode,
                  index.read_session()):
                for _ in range(2):
                    value, state = index._visual_window_features(clip, 0., 6.)
                    self.assertIsNone(value)
                    self.assertEqual('window-outside-source', state)
            self.assertEqual(0, index._visual_cold_windows)
            self.assertEqual(0, models.call_count)
            self.assertEqual(0, decode.call_count)

    def test_valid_shorter_window_stays_exact_and_changed_source_ignores_stale_duration(self):
        for changed_source in (False, True):
            with self.subTest(changed_source=changed_source), tempfile.TemporaryDirectory(prefix="newsflow-short-window-") as temporary:
                index, clip = self.fixture(Path(temporary))
                index.visual_window_budget = 96
                signature = clip.stat()
                with index._connect() as connection:
                    connection.execute('INSERT INTO clips(path,name,size,mtime_ns,duration,width,height,fps,embedding,model,indexed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                       (str(clip.resolve()), clip.name, signature.st_size, signature.st_mtime_ns, 3., 32, 24, 0., bytes(2048), IMAGE_MODEL, 1.))
                if changed_source:
                    clip.write_bytes(b'changed source with a different signature and fresh native bounds')
                requested = 6. if changed_source else 3.
                vector = np.zeros(512, dtype=np.float32)
                vector[:3] = [.35, .10, .05]
                vector[-1] = np.sqrt(1 - float(vector @ vector))

                class Image:
                    def embed(self, images, **_kwargs):
                        yield from images

                index._image_embedder, index._text_embedder = Image(), self.text_model()
                index._loaded_model_revision = index._local_model_revision()
                with patch.object(index, '_sample_visual_window', return_value=([vector] * 3, [.25, requested / 2, requested - .25])) as decode:
                    result = index.assess_visual_window('seaport cargo cranes ships', clip, 0, requested)
                self.assertEqual('direct', result['relation'])
                self.assertEqual(requested, result['duration'])
                self.assertEqual(0, result['source_start'])
                self.assertEqual(1, decode.call_count)
                self.assertEqual(1, index._visual_cold_windows)

    def fixture(self, root):
        clip = root / "disposable.mp4"
        clip.write_bytes(b"synthetic-media-no-decoding")
        index = ClipIndex(root / "index.sqlite3")
        for model in (IMAGE_MODEL, TEXT_MODEL):
            reference = index.model_cache / ("models--" + model.replace("/", "--")) / "refs" / "main"
            reference.parent.mkdir(parents=True, exist_ok=True)
            reference.write_text("local-revision-A", encoding="utf-8")
        vector = np.zeros(512, dtype=np.float32)
        vector[:3] = [.232, .297, .05]
        vector[-1] = np.sqrt(1 - float(vector @ vector))
        signature = clip.stat()
        with index._connect() as connection:
            connection.execute(
                "INSERT INTO visual_window_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("older-taxonomy", str(clip.resolve()), signature.st_size, signature.st_mtime_ns,
                 5., 6., IMAGE_MODEL, TEXT_MODEL, TAXONOMY_VERSION - 1,
                 np.asarray([vector] * 3, dtype=np.float32).tobytes(),
                 json.dumps([{"port": .34, "leisure": .10}] * 3), json.dumps([5.5, 8., 10.5]),
                 json.dumps(index._local_model_revision(), sort_keys=True)),
            )
        index._visual_models_available = lambda: True
        index.visual_window_budget = 0
        index._visual_memory_clear()
        return index, clip

    @staticmethod
    def text_model():
        class Text:
            def query_embed(self, queries):
                for query in ([queries] if isinstance(queries, str) else queries):
                    vector = np.zeros(512, dtype=np.float32)
                    kind = next(kind for kind, prompts in TAXONOMY.items() if query in prompts)
                    vector[{"port": 0, "leisure": 1}.get(kind, 2)] = 1
                    yield vector
        return Text()

    def test_taxonomy_upgrade_rescores_exact_vectors_with_text_only_and_zero_cold_budget(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            with (patch("fastembed.ImageEmbedding", side_effect=AssertionError("image model constructed")),
                  patch("fastembed.TextEmbedding", return_value=self.text_model()) as text,
                  patch.object(index, "_sample_visual_window", side_effect=AssertionError("frames decoded")),
                  index.read_session()):
                result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            self.assertEqual("contradiction", result["relation"])
            self.assertEqual("leisure", result["dominant_kind"])
            self.assertEqual("sqlite-vectors-rescored", result["feature_cache"])
            self.assertEqual([5.5, 8., 10.5], result["sample_times"])
            self.assertEqual(TAXONOMY_VERSION, result["taxonomy_version"])
            self.assertEqual(0, index._visual_cold_windows)
            self.assertIsNone(index._image_embedder)
            self.assertTrue(text.call_args.kwargs["local_files_only"])
            self.assertEqual(1, text.call_count)
            with index._connect() as connection:
                rows = connection.execute("SELECT rules_version,scores,model_revision FROM visual_window_features").fetchall()
            self.assertEqual(2, len(rows))
            current = next(row for row in rows if row["rules_version"] == TAXONOMY_VERSION)
            self.assertAlmostEqual(.297, json.loads(current["scores"])[0]["leisure"], places=5)
            self.assertEqual(result["model_revision"], json.loads(current["model_revision"]))
            index._visual_memory_clear()
            warm = ClipIndex(index.db_path)
            warm._visual_models_available = lambda: True
            warm.visual_window_budget = 0
            with (patch("fastembed.TextEmbedding", side_effect=AssertionError("warm text construction")),
                  patch.object(warm, "_sample_visual_window", side_effect=AssertionError("warm decode"))):
                again = warm.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            self.assertEqual("sqlite", again["feature_cache"])
            self.assertEqual(result["per_frame_scores"], again["per_frame_scores"])

    def test_reuse_requires_source_window_model_and_revision_match(self):
        mismatches = {
            "size": 1, "mtime_ns": 1, "source_start": 4., "duration": 7.,
            "image_model": "different-image", "text_model": "different-text",
            "model_revision": "{}", "path": "different-path.mp4",
        }
        for column, value in mismatches.items():
            with self.subTest(column=column), tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
                index, clip = self.fixture(Path(temporary))
                with index._connect() as connection:
                    connection.execute(f"UPDATE visual_window_features SET {column}=?", (value,))
                with (patch("fastembed.TextEmbedding", side_effect=AssertionError("mismatched vectors reused")),
                      patch.object(index, "_sample_visual_window", side_effect=AssertionError("budget bypass"))):
                    result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
                self.assertEqual("unknown", result["relation"])
                self.assertEqual("cold-window-budget-exhausted", result["reason"])
                self.assertEqual(0, index._visual_cold_windows)

    def test_changed_model_revision_cannot_reuse_older_taxonomy_vectors(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            reference = index.model_cache / ("models--" + TEXT_MODEL.replace("/", "--")) / "refs" / "main"
            reference.write_text("local-revision-B", encoding="utf-8")
            with patch("fastembed.TextEmbedding", side_effect=AssertionError("wrong revision reused")):
                result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            self.assertEqual("cold-window-budget-exhausted", result["reason"])

    def test_text_only_load_is_reused_by_full_models_without_relabeling_live_revision(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            with (patch("fastembed.ImageEmbedding", return_value=object()) as image,
                  patch("fastembed.TextEmbedding", return_value=self.text_model()) as text):
                result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
                self.assertEqual("contradiction", result["relation"])
                self.assertEqual(0, image.call_count)
                captured_text = index._text_embedder
                full = index._models(local_files_only=True)
                self.assertIs(captured_text, full[1])
                self.assertEqual(1, image.call_count)
                self.assertEqual(1, text.call_count)
                reference = index.model_cache / ("models--" + TEXT_MODEL.replace("/", "--")) / "refs" / "main"
                reference.write_text("local-revision-B", encoding="utf-8")
                self.assertEqual(full, index._models(local_files_only=True))
                self.assertEqual(result["model_revision"], index._loaded_model_revision)

    def test_partial_text_model_cannot_be_combined_with_new_image_revision(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            with patch("fastembed.TextEmbedding", return_value=self.text_model()):
                index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            reference = index.model_cache / ("models--" + IMAGE_MODEL.replace("/", "--")) / "refs" / "main"
            reference.write_text("local-revision-B", encoding="utf-8")
            with (patch("fastembed.ImageEmbedding", side_effect=AssertionError("revision mismatch reached image load")),
                  self.assertRaisesRegex(RuntimeError, "model-cache-changed-after-text-load")):
                index._models(local_files_only=True)

    def test_changed_source_during_rescore_is_not_persisted(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            model = self.text_model()
            embed = model.query_embed

            def changed(queries):
                clip.write_bytes(b"changed while computing text scores")
                yield from embed(queries)

            model.query_embed = changed
            with patch("fastembed.TextEmbedding", return_value=model):
                result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            self.assertEqual("source-changed-during-assessment", result["reason"])
            with index._connect() as connection:
                self.assertEqual(1, connection.execute("SELECT count(*) FROM visual_window_features").fetchone()[0])

    def test_corrupt_cached_vectors_do_not_trigger_unbounded_decode(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-vector-reuse-") as temporary:
            index, clip = self.fixture(Path(temporary))
            with index._connect() as connection:
                connection.execute("UPDATE visual_window_features SET vectors=?", (b"invalid",))
            with patch.object(index, "_sample_visual_window", side_effect=AssertionError("corrupt cache decode")):
                result = index.assess_visual_window("seaport cargo cranes ships", clip, 5, 6)
            self.assertEqual("unknown", result["relation"])
            self.assertEqual("window-assessment-unavailable:ValueError", result["reason"])
            self.assertEqual(0, index._visual_cold_windows)


if __name__ == "__main__":
    unittest.main()
