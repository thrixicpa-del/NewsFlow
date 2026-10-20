"""Source preparation uses the current VoiceMap, not another scene planner."""
import copy
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.config import Settings, save_settings
from scriptor.core import ScenarioRequest
from scriptor.footage import FootageItem
from scriptor.runner import Job, RunState
from scriptor.session import save_session
from scriptor.stock_sources import StockCandidate
from scriptor.timeline import TimelineProject


class StockPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root), "NEWSFLOW_TEST_ROOT": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        self.voice = self.root / "voice.wav"
        self.voice.write_bytes(b"voice-fixture")
        self.local = self.root / "cargo-local.mp4"
        self.local.write_bytes(b"local-fixture")
        self.stock = self.root / "cargo-stock.mp4"
        self.stock.write_bytes(b"stock-fixture")
        self.queries = []
        self.scenes = [{"narration": "Грузовой поезд", "visual_query_en": "cargo train",
                        "duration": 3.0, "minimum_footage_duration": 3.0,
                        "voice_segment_id": 17, "voice_segment_ids": [17],
                        "narration_start": 0.0, "narration_end": 3.0}]

    def prepare(self, mode, *, local_score=.9, empty=False, fast_reuse=False):
        settings = Settings(montage_renderer="ffmpeg", montage_source_mode=mode,
            montage_stock_sources=["pexels"], montage_stock_trim=False,
            footage_folders=[str(self.root)], voice_scenario_outputs={"1": str(self.voice)},
            montage_project_folder=str(self.root / "projects"), montage_output_folder=str(self.root / "outputs"),
            footage_download_folder=str(self.root / "downloads"), montage_export_davinci_xml=False)
        settings.montage_fast_reuse_enabled = fast_reuse
        settings.montage_unique_footage_percent = 40
        save_settings(settings)
        save_session(["Logistics"], [Job(ScenarioRequest(0, "Logistics", "", "product-1"), state=RunState.DONE, result="Грузовой поезд")])
        parent = self
        class Index:
            def __init__(self, *_args, **_kwargs):
                pass
            def count(self, *_args):
                return 1
            def screen_text_stats(self):
                return {"safe": 1, "blocked": 0, "unchecked": 0}
            def search_many(self, queries, **_kwargs):
                return [[SearchHit(FootageItem(str(parent.local), "Cargo train"), local_score, 10.0)] for _ in queries]
            def score_file(self, *_args):
                return .8
            def media_duration(self, *_args):
                return 10.0

        candidate = StockCandidate("pexels", "1", "Cargo train", "https://videos.pexels.com/1.mp4",
            "https://www.pexels.com/video/1/", "Pexels License", "https://www.pexels.com/license/", "Test",
            local_path=self.stock)
        class Service:
            def __init__(self, *_args, **_kwargs):
                self.enabled = ["pexels"]
            def cached(self, *_args, **_kwargs):
                return []
            def search(self, query, **_kwargs):
                parent.queries.append(query)
                return [] if empty else [candidate]
            def fetch(self, _candidate):
                return parent.stock

        patches = [patch.object(bridge, "ClipIndex", Index),
            patch.object(bridge, "StockService", Service, create=True),
            patch.object(bridge, "_ensure_voice_map_for_scenario", return_value=SimpleNamespace(state="ready")),
            patch.object(bridge, "_voice_map_scenes", return_value=(copy.deepcopy(self.scenes), {"productionItemId": "product-1"})),
            patch.object(bridge, "probe_media_duration", return_value=3.0),
            patch.object(bridge, "_cached_or_probed_montage_duration", return_value=10.0),
            patch.object(bridge, "_montage_screen_text_safe", return_value=True),
            patch.object(bridge, "_semantic_clip_ok", return_value=True),
            patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source)]
        for context in patches:
            context.start()
            self.addCleanup(context.stop)
        result = bridge.prepare_montage({"scenarioIndex": 0})
        self.project_path = result["preparedProject"]["path"]
        return TimelineProject.load(Path(result["preparedProject"]["path"]))

    def test_stock_only_ignores_local_and_preserves_existing_voice_scene(self):
        project = self.prepare("stock")
        self.assertEqual(project.clips[0].path, str(self.stock))
        self.assertEqual(project.clips[0].voice_segment_ids, [17])
        self.assertEqual(project.clips[0].narration_end, 3.0)
        self.assertEqual(project.clips[0].stock_provenance["provider"], "pexels")
        self.assertEqual(project.source_policy["mode"], "stock")

    def test_local_and_hybrid_exact_never_request_stock(self):
        project = self.prepare("local")
        self.assertEqual(project.clips[0].path, str(self.local))
        self.assertEqual(self.queries, [])

    def test_hybrid_downloads_when_local_is_below_threshold(self):
        project = self.prepare("hybrid", local_score=.01)
        self.assertEqual(project.clips[0].path, str(self.stock))

    def test_exhausted_stock_scene_is_saved_for_manual_replacement(self):
        project = self.prepare("stock", empty=True)
        self.assertEqual(project.manual_replacements[0]["voiceSegmentIds"], [17])
        self.assertEqual(project.manual_replacements[0]["sceneIndex"], 0)
        self.assertFalse(project.clips)
        with self.assertRaisesRegex(ValueError, "ручн"):
            bridge.render_montage({"projectPath": self.project_path})
