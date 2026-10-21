"""External recovery must retain local safety gates; no network or models."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scriptor import bridge
from scriptor.config import Settings
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject


class ExternalFallbackSafetyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.settings = Settings(footage_folders=[str(self.root)], montage_auto_web=True,
                                 footage_download_folder=str(self.root / "downloads"),
                                 cutter_output_folder=str(self.root / "cuts"))
        self.scene = {"visual_query_en": "seaport cargo cranes ships", "narration": "В порту грузят контейнеры.", "duration": 6}
        self.index = SimpleNamespace(search_many=lambda *_a, **_k: [[]],
                                     montage_story_context=self.scene["narration"], add_item=Mock())
        self.clip = TimelineClip(str(self.root / "missing.mp4"), self.scene["narration"], self.scene["visual_query_en"], 6)
        self.raw = {"title": "Seaport cargo cranes", "url": "https://example.test/cached.mp4"}
        self.addCleanup(patch.stopall)
        self.search = patch.object(bridge, "search_wikimedia_videos", return_value=[self.raw]).start()
        self.download = patch.object(bridge, "download_footage", side_effect=AssertionError("network forbidden")).start()
        self.cut = patch.object(bridge, "cut_single_clip", side_effect=AssertionError("FFmpeg forbidden")).start()
        patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {}, clear=True).start()
        patch.dict(bridge._EXTERNAL_FOOTAGE_SOURCE_LOCKS, {}, clear=True).start()

    def item(self, name, relation="direct", start=0, duration=6):
        path = self.root / name
        path.write_bytes(b"test-owned-contract-source")
        item = FootageItem(str(path), name, tags=["port-logistics"])
        def assess(_query, requested_start, requested_duration, **kwargs):
            if kwargs.get("allow_alternatives"):
                requested_start = start
            valid = start <= requested_start and requested_start + requested_duration <= start + duration
            return {"relation": relation if valid else "contradiction", "dominant_kind": "port" if relation == "direct" else "map",
                    "source_start": requested_start, "duration": requested_duration, "source": "curated-interval"}
        item._visual_assessor = Mock(side_effect=assess)
        return item

    def test_cached_blocked_text_is_skipped_and_later_allowed_cache_is_returned(self):
        bad, good = self.item("blocked_port.mp4"), self.item("clean_port.mp4")
        other = {**self.raw, "url": "https://example.test/clean.mp4"}
        bridge._EXTERNAL_FOOTAGE_CACHE.update({self.raw["url"]: bad, other["url"]: good})
        self.search.return_value = [self.raw, other]
        with patch.object(bridge, "_montage_screen_text_safe", side_effect=lambda _i, item, **_k: item is good) as screen:
            self.assertIs(bridge._download_scene_fallback(self.scene, self.settings, self.index), good)
        self.assertEqual([bad, good], [call.args[1] for call in screen.call_args_list])
        self.download.assert_not_called()

    def test_cache_populated_while_waiting_for_source_lock_is_also_screened(self):
        bad = self.item("blocked_port.mp4")
        class ArrivingCache(dict):
            calls = 0
            def get(cache, key, default=None):
                cache.calls += 1
                return None if cache.calls == 1 else bad
        with patch.object(bridge, "_EXTERNAL_FOOTAGE_CACHE", ArrivingCache()), \
             patch.object(bridge, "_montage_screen_text_safe", return_value=False) as screen:
            self.assertIsNone(bridge._download_scene_fallback(self.scene, self.settings, self.index))
        screen.assert_called_once_with(self.index, bad)
        self.download.assert_not_called()

    def test_new_blocked_download_is_never_published_to_reusable_cache(self):
        original = self.item("download.mp4")
        cut = self.item("cut.mp4")
        final = self.root / "published-cuts"
        final.mkdir()
        (final / "cut.mp4").write_bytes(b"test-owned-published-cut")
        self.download.side_effect = None
        self.download.return_value = original
        self.cut.side_effect = None
        self.cut.return_value = Path(cut.path)
        with patch.object(bridge, "_production_staging_folder", side_effect=lambda folder, *_: Path(folder) / "staging"), \
             patch.object(bridge, "_publish_staged_paths", return_value=[self.root / "published-download", final]), \
             patch.object(bridge, "_montage_screen_text_safe", return_value=False):
            self.assertIsNone(bridge._download_scene_fallback(self.scene, self.settings, self.index))
        self.assertNotIn(self.raw["url"], bridge._EXTERNAL_FOOTAGE_CACHE)
        self.index.add_item.assert_called_once()

    def test_replacement_boundary_rechecks_blocked_download_without_trusting_provider(self):
        bad = self.item("blocked_port.mp4")
        with patch.object(bridge, "_download_scene_fallback", return_value=bad), \
             patch.object(bridge, "_montage_screen_text_safe", return_value=False) as screen:
            self.assertEqual(bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings), [])
        screen.assert_called()

    def test_cached_blocked_text_never_repairs_a_missing_slot(self):
        bad = self.item("blocked_port.mp4")
        bridge._EXTERNAL_FOOTAGE_CACHE[self.raw["url"]] = bad
        project = TimelineProject("Порт", clips=[self.clip])
        with patch.object(bridge, "_montage_screen_text_safe", return_value=False), \
             patch.object(bridge, "_validated_montage_clip_duration", side_effect=lambda path: 6 if path.is_file() else 0):
            candidates = bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings)
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: candidates, index=self.index), 0)
        self.assertEqual(self.clip.path, project.clips[0].path)

    def test_downloaded_wrong_visual_window_cannot_replace_port_scene(self):
        wrong = self.item("map_leisure.mp4", relation="contradiction")
        with patch.object(bridge, "_download_scene_fallback", return_value=wrong), \
             patch.object(bridge, "_montage_screen_text_safe", return_value=True):
            self.assertEqual(bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings), [])

    def test_compatible_download_keeps_exact_curated_window_and_shorter_policy(self):
        good = self.item("curated_port.mp4", start=9, duration=4)
        stat = Path(good.path).stat()
        good.visual_evidence = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                "observations": [{"start": 9, "end": 13, "kind": "port", "source": "manual"}]}
        with patch.object(bridge, "_download_scene_fallback", return_value=good), \
             patch.object(bridge, "_montage_screen_text_safe", return_value=True):
            self.assertEqual(bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings), [])
            self.assertEqual(bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings, allow_shorter=True), [good])
        self.assertTrue(any(call.args[1:3] == (9, 4) for call in good._visual_assessor.call_args_list))

    def test_allowed_cached_repair_keeps_story_duration_and_source_start(self):
        good = self.item("clean_port.mp4", start=2, duration=6)
        bridge._EXTERNAL_FOOTAGE_CACHE[self.raw["url"]] = good
        project = TimelineProject("Порт", clips=[self.clip])
        with patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
             patch.object(bridge, "_validated_montage_clip_duration", side_effect=lambda path: 8 if path.is_file() else 0):
            candidates = bridge._replacement_candidates_for_clip(self.index, self.clip, self.settings)
            self.assertEqual(candidates, [good])
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: candidates, index=self.index), 1)
        self.assertEqual((good.path, 2, 6, self.clip.narration),
                         (project.clips[0].path, project.clips[0].source_start, project.clips[0].duration, project.clips[0].narration))
        self.download.assert_not_called()

    def test_cached_story_and_current_candidate_filter_remain_hard_guards(self):
        good = self.item("clean_port.mp4")
        iran = self.item("Iran_port.mp4")
        for item, predicate in ((iran, lambda _item: True), (good, lambda candidate: candidate is not good)):
            with self.subTest(name=item.name), \
                 patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {self.raw["url"]: item}, clear=True), \
                 patch.object(bridge, "_montage_screen_text_safe", return_value=True):
                self.index.candidate_filter = predicate
                self.assertIsNone(bridge._download_scene_fallback(self.scene, self.settings, self.index))
        self.download.assert_not_called()
