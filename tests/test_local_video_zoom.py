"""Local-video zoom contract; disposable storage only."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config, timeline


class LocalVideoZoomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_default_and_saved_flag_survive_stale_progress_writer(self):
        settings = config.Settings()
        self.assertIs(getattr(settings, "montage_local_video_zoom", None), False)
        config.save_settings(settings)
        stale = config.load_settings()
        with patch.object(bridge, "snapshot", return_value={}):
            bridge.save_montage_settings({"localVideoZoom": True})
        stale.montage_task_statuses = {"1": {"status": "Рендер"}}
        config.save_settings(stale)
        self.assertTrue(config.load_settings().montage_local_video_zoom)
        with patch.object(bridge, "snapshot", return_value={}), self.assertRaises(ValueError):
            bridge.save_montage_settings({"localVideoZoom": "false"})

    def test_project_roundtrip_and_legacy_default(self):
        project = timeline.TimelineProject("Legacy")
        self.assertIs(getattr(project, "local_video_zoom", None), False)
        path = self.root / "saved.newsflow"
        project.local_video_zoom = True
        project.save(path)
        self.assertTrue(timeline.TimelineProject.load(path).local_video_zoom)

    def test_disabled_proxy_key_is_unchanged_enabled_has_separate_cache(self):
        path = self.root / "source.mp4"
        path.write_bytes(b"key fixture")
        clip = timeline.TimelineClip(str(path), "", "", duration=2.4)
        stat = path.stat()
        legacy = (f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|0.000000000|"
                  "2.400000000|1920x1080|30fps|crf20|proxy-v3-loop-short-source|"
                  "bounded-frame-grid-v2|None")
        original = hashlib.sha256(legacy.encode()).hexdigest()
        self.assertEqual(timeline._proxy_key(clip, 1920, 1080), original)
        self.assertNotEqual(timeline._proxy_key(clip, 1920, 1080, local_video_zoom=True), original)

    def test_gpu_filter_applies_only_to_local_not_intro_or_stock(self):
        path = self.root / "source.mp4"
        path.write_bytes(b"gpu command fixture")
        clips = [timeline.TimelineClip(str(path), "", "", duration=2.4, source=source)
                 for source in ("local", "intro", "pexels")]
        script = self.root / "gpu.ffscript"
        with patch.object(timeline, "probe_video_duration", return_value=6), \
             patch.object(timeline, "gpu_timeline_encoder_args", return_value=["-c:v", "h264_nvenc"]):
            timeline._gpu_timeline_chunk_command("ffmpeg", clips, self.root / "out.mp4", script,
                1920, 1080, local_video_zoom=True)
        filters = script.read_text(encoding="utf-8").split(";\n")
        self.assertIn("zoompan=", filters[0])
        self.assertIn("d=1", filters[0], "Never duplicate or slow down input frames")
        self.assertNotIn("zoompan=", filters[1])
        self.assertNotIn("zoompan=", filters[2])

    def test_remotion_manifest_has_local_only_zoom_with_no_timing_changes(self):
        project = timeline.TimelineProject("Test")
        project.local_video_zoom = True
        project.clips = [timeline.TimelineClip("local.mp4", "Voice", "", 2.4, source="local"),
                         timeline.TimelineClip("stock.mp4", "Voice 2", "", 3.2, source="pexels")]
        result = timeline.remotion_payload(project)
        self.assertTrue(result["sequences"][0].get("localVideoZoom"))
        self.assertFalse(result["sequences"][1].get("localVideoZoom"))
        self.assertEqual([s["durationInFrames"] for s in result["sequences"]], [72, 96])
        self.assertEqual(result["durationInFrames"], 168)

    def test_decorated_legacy_local_source_zooms_but_continuity_and_stock_do_not(self):
        for source, provenance, continuity, expected in (
            ("local · RELAXED_SEMANTIC", {}, {}, True),
            ("local · fallback", {}, {}, True),
            ("local", {"provider": "pexels"}, {}, False),
            ("local", {}, {"kind": "hold"}, False),
            ("local-file-remote", {}, {}, False),
        ):
            with self.subTest(source=source, provenance=provenance, continuity=continuity):
                clip = timeline.TimelineClip("unused.mp4", "", "", source=source,
                    stock_provenance=provenance, continuity=continuity)
                self.assertEqual(timeline._local_clip_zoom(clip, True), expected)


if __name__ == "__main__":
    unittest.main()
