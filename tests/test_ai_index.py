import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import (
    _SCREEN_TEXT_NEGATIVE_QUERIES,
    _SCREEN_TEXT_POSITIVE_QUERIES,
    SCREEN_TEXT_CLASSIFIER_VERSION,
    SEMANTIC_INDEX_VERSION,
    SEMANTIC_TAG_LABELS,
    ClipIndex,
    _SearchCorpus,
    discover_video_paths,
    source_family_identity,
    source_family_identity_text,
)
from scriptor.footage import FootageItem
from scriptor.timeline import ffmpeg_executable


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
    def test_deep_taxonomy_covers_required_news_visual_families(self):
        required = {
            "frontline-combat", "artillery-fire", "military-drone", "emergency-aftermath",
            "protest-crowd", "diplomatic-negotiations", "parliament-government",
            "oil-tanker-port", "markets-trading", "factory-industry", "cargo-warehouse",
            "aviation-airport", "rail-metro", "city-urban", "migrant-border",
            "agriculture-farming", "healthcare-hospital", "weather-disaster",
            "technology-datacenter", "documentary-neutral",
            "us-government-washington", "ukraine-government-kyiv", "eu-institutions",
            "russia-government-moscow", "iran-government-tehran",
            "armenia-government-yerevan", "azerbaijan-government-baku",
            "nato-alliance", "cybersecurity-network", "economic-sanctions",
        }
        self.assertTrue(required <= SEMANTIC_TAG_LABELS)

    def test_screen_text_gate_keeps_obvious_interstitial_queries_but_uses_v6_storage(self):
        queries = " ".join(_SCREEN_TEXT_POSITIVE_QUERIES).casefold()
        self.assertGreaterEqual(SCREEN_TEXT_CLASSIFIER_VERSION, 6)
        self.assertIn("cyrillic", queries)
        self.assertIn("title card", queries)
        self.assertIn("interstitial", queries)

    def test_neutral_filenames_retrieve_by_visual_meaning_after_deep_enrichment(self):
        class CategoryImageEmbedding:
            vectors: ClassVar[dict[str, np.ndarray]] = {
                "tanker": np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
                "protest": np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
                "diplomacy": np.asarray([0.0, 0.0, 1.0], dtype=np.float32),
            }

            def embed(self, images, **_):
                for image in images:
                    yield self.vectors[image]

        class CategoryTextEmbedding:
            def query_embed(self, queries, **_):
                values = queries if isinstance(queries, list) else [queries]
                for query in values:
                    text = str(query).casefold()
                    if any(word in text for word in ("tanker", "port", "oil")):
                        yield np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
                    elif any(word in text for word in ("protest", "crowd", "rally")):
                        yield np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
                    elif any(word in text for word in ("diplomatic", "negotiation", "summit")):
                        yield np.asarray([0.0, 0.0, 1.0], dtype=np.float32)
                    else:
                        yield np.asarray([0.33, 0.33, 0.33], dtype=np.float32)

        class NeutralNameIndex(ClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                category = path.read_text(encoding="utf-8")
                return [category] * samples, 6.0, 1920, 1080, 30.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            expected = {
                "oil tanker at port": "clip001.mp4",
                "street protest crowd": "clip002.mp4",
                "diplomatic negotiations": "clip003.mp4",
            }
            for name, category in zip(expected.values(), ("tanker", "protest", "diplomacy")):
                (root / name).write_text(category, encoding="utf-8")
            index = NeutralNameIndex(
                root / "index.sqlite3",
                embedder_factory=lambda: (CategoryImageEmbedding(), CategoryTextEmbedding()),
            )
            index.index_folders([str(root)])
            deep = index.enrich_semantic_tags(batch_clips=1)
            results = index.search_many(expected.keys(), limit=1)

            self.assertEqual(deep.indexed, 3)
            self.assertEqual([Path(hits[0].item.path).name for hits in results], list(expected.values()))
            for hits in results:
                self.assertGreater(hits[0].semantic_confidence, 0.0)
            self.assertEqual(index.semantic_status(), {
                "version": SEMANTIC_INDEX_VERSION, "current": 3, "outdated": 0,
            })

    def test_interrupted_deep_enrichment_resumes_from_versioned_rows_without_decoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(3):
                (root / f"clip{number:03d}.mp4").write_bytes(b"red")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            index._sample_frames = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("deep enrichment decoded source video")
            )
            cancel = threading.Event()

            def interrupt(state):
                if state.processed == 1:
                    cancel.set()

            partial = index.enrich_semantic_tags(progress=interrupt, cancel=cancel, batch_clips=1)
            status = index.semantic_status()
            resumed = index.enrich_semantic_tags(batch_clips=1)

            self.assertEqual(partial.stage, "cancelled")
            self.assertEqual((status["current"], status["outdated"]), (1, 2))
            self.assertEqual((resumed.indexed, index.semantic_status()["outdated"]), (2, 0))

    def test_incremental_lifecycle_refreshes_metadata_and_removes_stale_paths(self):
        class LifecycleIndex(FakeClipIndex):
            probes = 0

            @staticmethod
            def _sample_frames(path, samples=3):
                LifecycleIndex.probes += 1
                payload = path.read_bytes()
                if payload == b"corrupt":
                    raise ValueError("unreadable")
                return ["red"] * samples, float(len(payload)), 640 + len(payload), 360, 30.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            current = clips / "family_cut_001.mp4"
            current.write_bytes(b"one")
            index = LifecycleIndex(root / "index.sqlite3",
                                   embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))

            first = index.index_folders([str(clips)])
            unchanged = index.index_folders([str(clips)])
            with index._connect() as connection:
                connection.execute("UPDATE clips SET english_text=1 WHERE path=?", (str(current.resolve()),))
            time.sleep(0.002)
            current.write_bytes(b"replacement")
            modified = index.index_folders([str(clips)])
            metadata = index.metadata(current)
            renamed = clips / "family_cut_002.mp4"
            current.rename(renamed)
            moved = index.index_folders([str(clips)])
            renamed.unlink()
            deleted = index.index_folders([str(clips)])

            self.assertEqual((first.indexed, unchanged.indexed, modified.indexed), (1, 0, 1))
            self.assertEqual(LifecycleIndex.probes, 3)
            self.assertEqual((metadata.duration, metadata.width, metadata.height, metadata.fps),
                             (11.0, 651, 360, 30.0))
            self.assertEqual(metadata.english_text, 0)
            self.assertEqual(moved.removed, 1)
            self.assertEqual(deleted.removed, 1)
            self.assertEqual(index.count(), 0)
            self.assertEqual(index.search_many(["red"]), [[]])

    def test_discovery_deduplicates_overlapping_unicode_roots_and_failed_media_is_truthful(self):
        class ExplicitFailureIndex(FakeClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                if path.stat().st_size == 0:
                    raise ValueError("zero-byte video")
                return ["red"] * samples, 2.0, 320, 180, 25.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            nested = root / "Кириллица" / "вложенная"
            nested.mkdir(parents=True)
            good = nested / "сюжет.MP4"
            bad = nested / "повреждённый.mov"
            good.write_bytes(b"video")
            bad.touch()
            (nested / "notes.txt").write_text("not media", encoding="utf-8")

            discovered = discover_video_paths([str(root), str(nested), str(root)])
            index = ExplicitFailureIndex(root / "index.sqlite3",
                                         embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            result = index.index_folders([str(root), str(nested)])

            self.assertEqual(discovered, sorted([good.resolve(), bad.resolve()], key=lambda value: str(value).casefold()))
            self.assertEqual((result.total, result.processed, result.indexed, result.failed), (2, 2, 1, 1))
            self.assertEqual([Path(item.path).name for item in index.all_items()], [good.name])

    def test_one_permission_read_failure_does_not_destroy_the_rest_of_the_batch(self):
        class PermissionFailureIndex(FakeClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                if "denied" in path.name:
                    raise PermissionError("synthetic access denied")
                return ["red"] * samples, 3.0, 640, 360, 30.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "good.mp4").write_bytes(b"good")
            (root / "denied.mp4").write_bytes(b"not-readable-in-fixture")
            index = PermissionFailureIndex(
                root / "index.sqlite3",
                embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()),
            )
            result = index.index_folders([str(root)])

            self.assertEqual((result.indexed, result.failed, index.count()), (1, 1, 1))

    def test_concurrent_reader_sees_committed_snapshot_while_incremental_probe_is_running(self):
        entered = threading.Event()
        release = threading.Event()

        class SlowIncrementalIndex(FakeClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                if path.name == "red_second.mp4":
                    entered.set()
                    release.wait(timeout=3)
                return ["red"] * samples, 4.0, 640, 360, 30.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / "red_first.mp4"
            first.write_bytes(b"first")
            database = root / "index.sqlite3"
            writer = SlowIncrementalIndex(
                database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding())
            )
            writer.index_folders([str(root)])
            (root / "red_second.mp4").write_bytes(b"second")
            worker = threading.Thread(target=writer.index_folders, args=([str(root)],))
            worker.start()
            self.assertTrue(entered.wait(timeout=2))

            reader = SlowIncrementalIndex(
                database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding())
            )
            self.assertEqual(Path(reader.search("red", limit=1)[0].item.path).name, first.name)
            release.set()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(reader.count(), 2)

    def test_search_and_all_items_never_return_a_path_deleted_after_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "aaa_red_scene.mp4"
            healthy = root / "zzz_red_current.mp4"
            clip.write_bytes(b"red")
            healthy.write_bytes(b"red")
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            clip.unlink()

            results = index.search_many(["red scene", "red scene"], limit=2)
            self.assertTrue(all([Path(hit.item.path).name for hit in hits] == [healthy.name] for hits in results))
            self.assertEqual([item.name for item in index.all_items(limit=1)], [healthy.name])

    def test_source_family_identity_hot_path_is_string_only(self):
        with patch("scriptor.ai_index.Path", side_effect=AssertionError("Path must not be used")):
            self.assertEqual(
                source_family_identity_text("D:/library/one/one_0001.mp4"),
                "path::d:/library/one",
            )
            self.assertEqual(
                source_family_identity("D:/library/one/one_0001.mp4"),
                "path::d:/library/one",
            )

    def test_source_family_identity_is_stable_and_distinguishes_unrelated_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            slices = root / "original_slices"
            slices.mkdir()
            first = slices / "clip_original_000001.mp4"
            second = slices / "clip_original_000002.mp4"
            other = root / "other_source.mp4"
            neutral_one = root / "clip_001.mp4"
            neutral_two = root / "clip_002.mp4"
            for path in (first, second, other, neutral_one, neutral_two):
                path.write_bytes(path.name.encode("utf-8"))
            database = root / "index.sqlite3"
            index = FakeClipIndex(database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            families = {Path(item.path).name: index.metadata(item.path).source_family for item in index.all_items()}
            reopened = ClipIndex(database)
            reopened_families = {
                Path(item.path).name: reopened.metadata(item.path).source_family for item in reopened.all_items()
            }

            self.assertEqual(families[first.name], families[second.name])
            self.assertNotEqual(families[first.name], families[other.name])
            self.assertNotEqual(families[neutral_one.name], families[neutral_two.name])
            self.assertEqual(families, reopened_families)
            self.assertTrue(all(families.values()))

    def test_cutter_numbered_outputs_share_family_without_collapsing_plain_year_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "evening_report"
            source.mkdir()
            first = source / "evening_report_0001.mp4"
            second = source / "evening_report_0002.mp4"
            random_cut_first = source / "clip_qcsfjt_204.mp4"
            random_cut_second = source / "clip_5yf7qx_488.mp4"
            plain_report = root / "report_2024.mp4"
            another_report = root / "report_2025.mp4"
            ordinary_clip = root / "clip_editorial_2024.mp4"
            for path in (
                first,
                second,
                random_cut_first,
                random_cut_second,
                plain_report,
                another_report,
                ordinary_clip,
            ):
                path.write_bytes(path.name.encode("utf-8"))
            database = root / "index.sqlite3"
            index = FakeClipIndex(
                database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding())
            )
            index.index_folders([str(root)])
            families = {Path(item.path).name: index.metadata(item.path).source_family
                        for item in index.all_items()}
            reopened = ClipIndex(database)
            reopened_families = {Path(item.path).name: reopened.metadata(item.path).source_family
                                 for item in reopened.all_items()}

            self.assertEqual(families[first.name], families[second.name])
            self.assertEqual(families[random_cut_first.name], families[random_cut_second.name])
            self.assertEqual(families[first.name], families[random_cut_first.name])
            self.assertNotEqual(families[plain_report.name], families[another_report.name])
            self.assertNotEqual(families[random_cut_first.name], families[ordinary_clip.name])
            self.assertEqual(families, reopened_families)
            self.assertEqual(
                source_family_identity(first, "https://example.test/watch?v=Original"),
                "url::https://example.test/watch?v=original",
            )

    def test_large_corpus_search_validates_only_shared_bounded_candidates(self):
        total = 20_000
        items = tuple(
            FootageItem(f"C:/fake/clip_{number:05d}.mp4", f"clip_{number:05d}.mp4", tags=[])
            for number in range(total)
        )
        corpus = _SearchCorpus(
            fingerprint=((1, 1),),
            items=items,
            vectors=np.column_stack((np.linspace(1.0, 0.0, total), np.zeros(total))).astype(np.float32),
            path_keys=tuple(item.path.casefold() for item in items),
            durations=(6.0,) * total,
            widths=(1920,) * total,
            heights=(1080,) * total,
            semantic_confidences=(0.0,) * total,
            source_families=tuple(f"family-{number}" for number in range(total)),
            used_counts=np.zeros(total, dtype=np.float32),
            ratings=np.zeros(total, dtype=np.float32),
        )
        checks: list[str] = []

        def fake_is_file(candidate: Path) -> bool:
            checks.append(str(candidate))
            return candidate.name not in {"clip_00000.mp4", "clip_00001.mp4"}

        with tempfile.TemporaryDirectory() as folder:
            index = ClipIndex(
                Path(folder) / "index.sqlite3",
                embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()),
            )
            with patch.object(index, "_search_corpus", return_value=corpus), \
                 patch("pathlib.Path.is_file", autospec=True, side_effect=fake_is_file):
                results = index.search_many(["red first", "red second"], limit=3)

        expected = ["clip_00002.mp4", "clip_00003.mp4", "clip_00004.mp4"]
        self.assertEqual([[Path(hit.item.path).name for hit in hits] for hits in results], [expected, expected])
        self.assertEqual(len(checks), len(set(checks)))
        self.assertLessEqual(len(checks), 8)

    def test_concurrent_indexing_and_search_keep_one_row_per_physical_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / "clips"
            clips.mkdir()
            for number in range(12):
                (clips / f"red_{number:02d}.mp4").write_bytes(f"clip-{number}".encode())
            database = root / "index.sqlite3"
            first = FakeClipIndex(database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            second = FakeClipIndex(database, embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            barrier = threading.Barrier(2)
            errors = []

            def run(index):
                try:
                    barrier.wait(timeout=2)
                    index.index_folders([str(clips)], batch_clips=2)
                except Exception as exc:  # noqa: BLE001  # pragma: no cover - asserted below
                    errors.append(exc)

            workers = [threading.Thread(target=run, args=(index,)) for index in (first, second)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=5)

            self.assertEqual(errors, [])
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(first.count(), 12)
            self.assertEqual(len(first.search_many(["red"])[0]), 12)

    def test_search_many_is_one_bounded_corpus_pass_without_discovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("red_one.mp4", "blue_two.mp4"):
                (root / name).write_bytes(name.encode())
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            with patch("scriptor.ai_index.discover_video_paths", side_effect=AssertionError("filesystem rescan")), \
                 patch.object(index, "_search_corpus", wraps=index._search_corpus) as corpus:
                result = index.search_many(["red", "blue", "red"], limit=2)

            self.assertEqual(len(result), 3)
            self.assertEqual(corpus.call_count, 1)
            self.assertEqual(
                [hit.item.path for hit in result[0]],
                [hit.item.path for hit in index.search_many(["red"], limit=2)[0]],
            )

    def test_real_synthetic_metadata_matches_media_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "known_2997fps.mp4"
            made = subprocess.run(
                [ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
                 "testsrc2=size=426x240:rate=30000/1001:duration=1.6",
                 "-an", "-c:v", "libx264", str(clip)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=False,
            )
            self.assertEqual(made.returncode, 0, made.stderr[-1000:])
            index = ClipIndex(root / "index.sqlite3",
                              embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            indexed = index.index_folders([str(root)])
            metadata = index.metadata(clip)

            self.assertEqual(indexed.indexed, 1)
            self.assertIsNotNone(metadata)
            self.assertEqual((metadata.width, metadata.height), (426, 240))
            self.assertAlmostEqual(metadata.fps, 30000 / 1001, delta=0.05)
            self.assertAlmostEqual(metadata.duration, 1.6, delta=0.12)
            stat = clip.stat()
            self.assertEqual((metadata.size, metadata.mtime_ns), (stat.st_size, stat.st_mtime_ns))

    def test_replaced_file_invalidates_screen_text_but_preserves_three_states(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            blocked = root / "blocked.mp4"
            safe = root / "safe.mp4"
            unchecked = root / "unchecked.mp4"
            for path in (blocked, safe, unchecked):
                path.write_bytes(path.name.encode())
            index = FakeClipIndex(root / "index.sqlite3",
                                  embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            index.index_folders([str(root)])
            with index._connect() as connection:
                connection.execute(
                    "UPDATE clips SET english_text=1,english_text_version=? WHERE path=?",
                    (SCREEN_TEXT_CLASSIFIER_VERSION, str(blocked.resolve())),
                )
                connection.execute(
                    "UPDATE clips SET english_text=-1,english_text_version=? WHERE path=?",
                    (SCREEN_TEXT_CLASSIFIER_VERSION, str(safe.resolve())),
                )

            self.assertEqual(index.screen_text_stats(), {"blocked": 1, "safe": 1, "unchecked": 1})
            self.assertEqual(
                {item.name for item in index.all_items(exclude_english_text=True)},
                {safe.name, unchecked.name},
            )
            time.sleep(0.002)
            blocked.write_bytes(b"changed blocked media")
            index.index_folders([str(root)])
            self.assertEqual(index.metadata(blocked).english_text, 0)
            self.assertEqual(
                {item.name for item in index.all_items(exclude_english_text=True)},
                {blocked.name, safe.name, unchecked.name},
            )

    def test_indexing_obvious_text_sets_current_classifier_version_without_second_decode(self):
        class TextImageEmbedding:
            def embed(self, images, **_):
                for image in images:
                    yield (
                        np.asarray([1.0, 0.0], dtype=np.float32)
                        if image == "text"
                        else np.asarray([0.0, 1.0], dtype=np.float32)
                    )

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / "headline.mp4"
            clip.write_bytes(b"video")
            index = ClipIndex(root / "index.sqlite3")
            query_vectors = np.asarray(
                [[1.0, 0.0]] * len(_SCREEN_TEXT_POSITIVE_QUERIES)
                + [[0.0, 1.0]] * len(_SCREEN_TEXT_NEGATIVE_QUERIES),
                dtype=np.float32,
            )
            with patch.object(index, "_models", return_value=(TextImageEmbedding(), object())), \
                 patch.object(index, "_text_model_is_cached", return_value=True), \
                 patch.object(index, "_query_vectors", return_value=query_vectors), \
                 patch.object(index, "_sample_frames",
                              return_value=(["clean", "text", "clean"], 6.0, 1920, 1080, 30.0)):
                result = index.index_folders([str(root)])

            self.assertEqual(result.indexed, 1)
            with index._connect() as connection:
                row = connection.execute(
                    "SELECT english_text,english_text_version FROM clips WHERE path=?",
                    (str(clip.resolve()),),
                ).fetchone()
            self.assertEqual(
                (int(row["english_text"]), int(row["english_text_version"])),
                (1, SCREEN_TEXT_CLASSIFIER_VERSION),
            )

    def test_frame_level_screen_text_blocks_one_text_frame_and_caches_safe_result(self):
        class TextImageEmbedding:
            def embed(self, images, **_):
                for image in images:
                    yield (np.asarray([1.0, 0.0], dtype=np.float32)
                           if image == "text" else np.asarray([0.0, 1.0], dtype=np.float32))

        class TextQueryEmbedding:
            def query_embed(self, queries, **_):
                values = queries if isinstance(queries, list) else [queries]
                positive = {value.casefold() for value in _SCREEN_TEXT_POSITIVE_QUERIES}
                negative = {value.casefold() for value in _SCREEN_TEXT_NEGATIVE_QUERIES}
                for query in values:
                    value = str(query).casefold()
                    if value in positive:
                        yield np.asarray([1.0, 0.0], dtype=np.float32)
                    elif value in negative:
                        yield np.asarray([0.0, 1.0], dtype=np.float32)
                    else:
                        raise AssertionError(f"Unexpected screen-text query: {query!r}")

        class TextFrameIndex(ClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                frames = ["clean", "text", "clean", "clean", "clean"] if "blocked" in path.name else ["clean"] * 5
                return frames[:samples], 6.0, 1920, 1080, 30.0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            blocked = root / "blocked.mp4"
            safe = root / "safe.mp4"
            blocked.write_bytes(b"blocked")
            safe.write_bytes(b"safe")
            index = TextFrameIndex(
                root / "index.sqlite3",
                embedder_factory=lambda: (TextImageEmbedding(), TextQueryEmbedding()),
            )
            index.index_folders([str(root)])

            self.assertFalse(index.screen_text_safe(blocked))
            self.assertTrue(index.screen_text_safe(safe))
            with index._connect() as connection:
                rows = {
                    Path(row["path"]).name: (int(row["english_text"]), int(row["english_text_version"]))
                    for row in connection.execute(
                        "SELECT path,english_text,english_text_version FROM clips"
                    )
                }
            self.assertEqual(rows["blocked.mp4"], (1, SCREEN_TEXT_CLASSIFIER_VERSION))
            self.assertEqual(rows["safe.mp4"], (-1, SCREEN_TEXT_CLASSIFIER_VERSION))

    def test_batch_screen_classifier_uses_persisted_clip_embedding_without_redecoding(self):
        """The 2.1.136-style maintenance pass must not reopen source videos."""
        class TextEmbedding:
            def query_embed(self, queries, **_):
                values = queries if isinstance(queries, list) else [queries]
                for query in values:
                    text = str(query).casefold()
                    if "prominent english words" in text:
                        yield np.asarray([1.0, 0.0], dtype=np.float32)
                    elif "no readable writing" in text:
                        yield np.asarray([0.0, 1.0], dtype=np.float32)
                    else:
                        yield np.asarray([0.0, 1.0], dtype=np.float32)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            blocked = root / "blocked.mp4"
            safe = root / "safe.mp4"
            blocked.write_bytes(b"blocked")
            safe.write_bytes(b"safe")
            index = ClipIndex(
                root / "index.sqlite3",
                embedder_factory=lambda: (FakeImageEmbedding(), TextEmbedding()),
            )
            with index._connect() as connection:
                connection.executemany(
                    """INSERT INTO clips(
                           path,name,size,mtime_ns,duration,width,height,fps,source_family,
                           tags,embedding,model,indexed_at,english_text,english_text_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            str(blocked.resolve()), blocked.name, blocked.stat().st_size,
                            blocked.stat().st_mtime_ns, 6.0, 1920, 1080, 30.0, "blocked",
                            "[]", np.asarray([1.0, 0.0], dtype=np.float32).tobytes(),
                            "test", time.time(), 0, 0,
                        ),
                        (
                            str(safe.resolve()), safe.name, safe.stat().st_size,
                            safe.stat().st_mtime_ns, 6.0, 1920, 1080, 30.0, "safe",
                            "[]", np.asarray([0.0, 1.0], dtype=np.float32).tobytes(),
                            "test", time.time(), 0, 0,
                        ),
                    ],
                )
            index._sample_frames = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("batch screen classifier reopened source media")
            )
            result = index.classify_english_screen_text()

            self.assertEqual(result, {"checked": 2, "blocked": 1, "safe": 1, "uncertain": 0})
            self.assertEqual(index.screen_text_stats(), {"blocked": 1, "safe": 1, "unchecked": 0})

    def test_failed_embedding_transaction_is_recoverable_without_partial_rows(self):
        class FailingImageEmbedding:
            def embed(self, _images, **_):
                raise RuntimeError("synthetic embedding failure")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for number in range(3):
                (root / f"red_{number}.mp4").write_bytes(str(number).encode())
            database = root / "index.sqlite3"
            failing = FakeClipIndex(database,
                                    embedder_factory=lambda: (FailingImageEmbedding(), FakeTextEmbedding()))
            with self.assertRaisesRegex(RuntimeError, "synthetic embedding failure"):
                failing.index_folders([str(root)])
            self.assertEqual(failing.count(), 0)

            recovered = FakeClipIndex(database,
                                      embedder_factory=lambda: (FakeImageEmbedding(), FakeTextEmbedding()))
            result = recovered.index_folders([str(root)])
            self.assertEqual((result.indexed, recovered.count()), (3, 3))

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
