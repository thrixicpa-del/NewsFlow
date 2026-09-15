import tempfile
import unittest
from pathlib import Path

import numpy as np

from scriptor.ai_index import ClipIndex, SEMANTIC_TAG_LABELS


class FakeImageEmbedding:
    def embed(self, images, **_):
        for image in images:
            yield np.array([1.0, 0.0], dtype=np.float32) if image == "red" else np.array([0.0, 1.0], dtype=np.float32)


class FakeTextEmbedding:
    def query_embed(self, query, **_):
        yield np.array([1.0, 0.0], dtype=np.float32) if "red" in query else np.array([0.0, 1.0], dtype=np.float32)


class FakeClipIndex(ClipIndex):
    @staticmethod
    def _sample_frames(path, samples=3):
        color = "red" if "red" in path.name else "blue"
        return [color] * samples, 6.0, 1920, 1080


class ClipIndexTests(unittest.TestCase):
    def test_indexes_incrementally_and_searches_by_visual_meaning(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            (clips / "random_red.mp4").write_bytes(b"red")
            (clips / "random_blue.mp4").write_bytes(b"blue")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            first = index.index_folders([str(clips)], batch_clips=2)
            second = index.index_folders([str(clips)], batch_clips=2)
            self.assertEqual(first.indexed, 2)
            self.assertEqual(second.skipped, 2)
            self.assertEqual(Path(index.search("red object")[0].item.path).name, "random_red.mp4")
            self.assertEqual(Path(index.search("blue object")[0].item.path).name, "random_blue.mp4")

    def test_excludes_already_selected_clip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            first = clips / "red_one.mp4"
            second = clips / "red_two.mp4"
            first.write_bytes(b"1")
            second.write_bytes(b"2")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(clips)])
            hit = index.search("red", exclude={str(first.resolve())})[0]
            self.assertEqual(Path(hit.item.path).name, "red_two.mp4")

    def test_searches_multiple_scene_queries_from_one_index_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            (clips / "red_scene.mp4").write_bytes(b"red")
            (clips / "blue_scene.mp4").write_bytes(b"blue")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(clips)])
            matches = index.search_many(["red explosion", "blue sea"], limit=2)
            self.assertEqual(Path(matches[0][0].item.path).name, "red_scene.mp4")
            self.assertEqual(Path(matches[1][0].item.path).name, "blue_scene.mp4")

    def test_reuses_results_for_repeated_scene_query(self):
        class CountingTextEmbedding(FakeTextEmbedding):
            def __init__(self):
                self.calls = []

            def query_embed(self, query, **kwargs):
                self.calls.append(query)
                yield from super().query_embed(query, **kwargs)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            (clips / "red_scene.mp4").write_bytes(b"red")
            text = CountingTextEmbedding()
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), text))
            index.index_folders([str(clips)])
            matches = index.search_many(["red explosion", "red explosion", "red explosion"], limit=1)
            self.assertEqual(len(matches), 3)
            self.assertEqual(len(text.calls), 1)

    def test_search_uses_local_metadata_when_text_model_is_not_cached(self):
        """A ready index must remain searchable without a network model download."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            (clips / "fire_engine_smoke.mp4").write_bytes(b"red")
            (clips / "cargo_ship_port.mp4").write_bytes(b"blue")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(clips)])
            # The indexed vectors already exist, but a fresh portable profile
            # has no downloaded text model. Search must remain local and pick
            # the file whose persisted name/tags match the requested scene.
            index.embedder_factory = None
            index._image_embedder = None
            index._text_embedder = None
            hit = index.search("cargo ship port", limit=1)[0]
            self.assertEqual(Path(hit.item.path).name, "cargo_ship_port.mp4")

    def test_english_screen_text_check_skips_missing_text_model(self):
        """A new portable profile must not wait for a model download before planning."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "news_clip.mp4"
            clip.write_bytes(b"video")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            index.embedder_factory = None
            index._text_embedder = None

            def fail_if_called(_prompts):
                raise AssertionError("The missing text model must not be started")

            index._query_vectors = fail_if_called
            result = index.classify_english_screen_text()
            self.assertEqual(result["checked"], 0)

    def test_feedback_boosts_and_reject_disables_clip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            first = clips / "red_one.mp4"
            second = clips / "red_two.mp4"
            first.write_bytes(b"1")
            second.write_bytes(b"2")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(clips)])
            index.rate(str(second.resolve()), 1)
            self.assertEqual(Path(index.search("red")[0].item.path).name, "red_two.mp4")
            index.rate(str(second.resolve()), -10)
            self.assertEqual(Path(index.search("red")[0].item.path).name, "red_one.mp4")

    def test_scores_unindexed_preview_by_visual_meaning(self):
        with tempfile.TemporaryDirectory() as folder:
            index = FakeClipIndex(Path(folder) / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            self.assertGreater(index.score_file(Path(folder) / "red_preview.mp4", "red object"), 0.9)
            self.assertLess(index.score_file(Path(folder) / "blue_preview.mp4", "red object"), 0.1)

    def test_semantic_labels_are_incremental_and_not_recomputed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            (clips / "red_scene.mp4").write_bytes(b"red")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(clips)])
            first = index.enrich_semantic_tags()
            second = index.enrich_semantic_tags()
            self.assertEqual(first.indexed, 1)
            self.assertEqual(second.processed, 0)
            self.assertEqual(second.total, 0)
            self.assertTrue(set(index.all_items()[0].tags) & SEMANTIC_TAG_LABELS)


if __name__ == "__main__":
    unittest.main()
