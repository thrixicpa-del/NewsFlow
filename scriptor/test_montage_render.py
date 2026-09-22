"""End-to-end local render checks for the NewsFlow montage core.

The fixture runs the same FFmpeg route used by the desktop queue: footage is
normalised to 30 FPS, a longer voice is preserved, and the final MP4 gets an
audio stream.  It is intentionally independent from API keys and the UI.
"""
from __future__ import annotations

# Existing media smoke commands intentionally inspect return codes/output.
# Keep that established style while this file is touched for stale-path truth.
# ruff: noqa: PLW1510, SIM117
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from . import bridge
from . import config as config_module
from . import timeline as timeline_module
from .ai_index import (
    _SCREEN_TEXT_POSITIVE_QUERIES,
    SCREEN_ELIGIBILITY_BLOCKED,
    SCREEN_ELIGIBILITY_SAFE,
    SCREEN_ELIGIBILITY_UNCERTAIN,
    SCREEN_TEXT_CLASSIFIER_VERSION,
    ClipIndex,
)
from .bridge import _semantic_clip_ok
from .config import Settings, _exclusive_settings_write
from .cutter import cut_single_clip
from .footage import FootageItem
from .timeline import (
    TimelineClip,
    TimelineProject,
    _proxy_lock,
    align_timeline_to_audio,
    fallback_scene_plan,
    ffmpeg_executable,
    probe_media_duration,
    render_project,
    title_only_scene_plan,
    validate_rendered_montage,
)


class MontageRenderTests(unittest.TestCase):
    def test_explicit_remotion_never_silently_falls_back_to_ffmpeg(self):
        """Composition mode must fail diagnostically if its canonical runner is absent."""
        project = TimelineProject(
            title="Remotion contract",
            clips=[TimelineClip("missing.mp4", "n", "q", duration=1.0)],
        )
        with patch.object(timeline_module, "_remotion_runner", return_value=None), \
             patch.object(timeline_module, "ffmpeg_executable", side_effect=AssertionError("legacy fallback")):
            with self.assertRaisesRegex(RuntimeError, "Remotion не найден"):
                render_project(project, Path("result.mp4"), renderer="remotion")

    def test_montage_counter_uses_all_existing_task_outputs_not_stale_legacy_paths(self):
        """The dashboard must count every real completed MP4 after a legacy list fell behind."""
        with tempfile.TemporaryDirectory(prefix="newsflow-montage-counter-") as temporary:
            root = Path(temporary)
            outputs = []
            for index in range(3):
                output = root / f"{index + 1:04d}.mp4"
                output.write_bytes(b"\x00\x00\x00\x18ftypisom" + (b"\x00" * 1024))
                outputs.append(output)
            settings = Settings(
                pipeline_montage_outputs=[str(outputs[0])],
                montage_task_statuses={
                    str(index): {"status": "Готово", "outputPath": str(output)}
                    for index, output in enumerate(outputs)
                },
            )

            self.assertEqual(bridge.montage_ready_count(settings), 3)

    def test_external_source_is_cut_to_silent_h264_30fps_clip(self):
        """The automatic web route never lets source audio/FPS into a timeline.

        This matches the production behaviour for downloaded stock/news clips:
        source media can be any common FPS and have an audio track, while the
        saved footage-library item must be a short, silent H.264 30 FPS MP4.
        """
        with tempfile.TemporaryDirectory(prefix="newsflow-external-cut-") as temporary:
            root = Path(temporary)
            source = root / "external-source.mp4"
            output_root = root / "normalized"
            ffmpeg = ffmpeg_executable()
            made_source = subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(made_source.returncode, 0, made_source.stderr[-1000:])
            clip = cut_single_clip(source, output_root, duration=0.75, fps=30, bitrate="1M", start=0.4)
            self.assertTrue(clip.is_file())
            inspected = subprocess.run([
                ffmpeg, "-hide_banner", "-i", str(clip),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            details = inspected.stderr
            self.assertIn("Video: h264", details)
            self.assertIn("30 fps", details)
            self.assertNotIn("Audio:", details)
            self.assertGreaterEqual(probe_media_duration(clip), 0.70)

    def test_web_download_is_normalized_and_indexed_before_montage(self):
        """The UI download action stores only the safe short clip in the library.

        Network fetching itself is replaced by a generated source here.  The
        rest of the route is production code: the result is cut, stripped of
        audio, registered in the persistent index and added as a footage root.
        """
        with tempfile.TemporaryDirectory(prefix="newsflow-web-ingest-") as temporary:
            root = Path(temporary)
            ffmpeg = ffmpeg_executable()
            source = root / "raw-web-source.mp4"
            made_source = subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2",
                "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=2",
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(source),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(made_source.returncode, 0, made_source.stderr[-1000:])
            settings = Settings(
                footage_download_folder=str(root / "downloads"),
                cutter_output_folder=str(root / "cuts"),
                footage_folders=[],
            )
            source_item = FootageItem(str(source), source.name, "wikimedia", "https://example.test/source",
                                      "CC BY", ["test", "source"])
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings") as saved, \
                 patch.object(bridge, "download_footage", return_value=source_item), \
                 patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "snapshot", return_value={}):
                result = bridge.download_web_footage({
                    "result": {"title": "Test source", "source": "wikimedia", "download_url": "https://example.test/raw.mp4"},
                    "duration": 0.8,
                })
                # The immediate ingest row intentionally has metadata first;
                # visual embedding is picked up by the incremental indexer.
                # A montage can still use it through its metadata fallback.
                indexed_count = ClipIndex(root / "footage-index.sqlite3").count()
            normalized = Path(result["downloadedFootage"]["path"])
            self.assertTrue(normalized.is_file())
            self.assertIn(str(root / "cuts"), str(normalized))
            details = subprocess.run([ffmpeg, "-hide_banner", "-i", str(normalized)], capture_output=True,
                                     text=True, encoding="utf-8", errors="replace").stderr
            self.assertIn("30 fps", details)
            self.assertNotIn("Audio:", details)
            self.assertIn(str(root / "cuts" / "Внешние для монтажа"), settings.footage_folders)
            self.assertTrue(indexed_count)
            saved.assert_called_once_with(settings)

    def test_settings_lock_serialises_two_bridge_processes(self):
        """Status updates and a UI save cannot replace settings.json together."""
        with tempfile.TemporaryDirectory(prefix="newsflow-settings-process-") as temporary:
            settings_path = Path(temporary) / "settings.json"
            code = (
                "from pathlib import Path\n"
                "import time\n"
                "from scriptor.config import _exclusive_settings_write\n"
                f"target = Path(r'''{settings_path}''')\n"
                "with _exclusive_settings_write(target):\n"
                "    print('locked', flush=True)\n"
                "    time.sleep(0.9)\n"
            )
            worker = subprocess.Popen(
                [sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parents[1]),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            )
            try:
                self.assertEqual(worker.stdout.readline().strip(), "locked")
                started = time.monotonic()
                with _exclusive_settings_write(settings_path):
                    waited = time.monotonic() - started
                self.assertGreaterEqual(waited, 0.45)
            finally:
                worker.wait(timeout=5)
                error_output = worker.stderr.read()
                worker.stdout.close()
                worker.stderr.close()
                if worker.returncode:
                    self.fail(error_output)

    def test_proxy_lock_serialises_two_bridge_processes(self):
        """Two Electron bridge processes cannot publish the same proxy together."""
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-process-") as temporary:
            target = Path(temporary) / "shared.mp4"
            code = (
                "from pathlib import Path\n"
                "import sys, time\n"
                "from scriptor.timeline import _proxy_lock\n"
                f"target = Path(r'''{target}''')\n"
                "with _proxy_lock(target):\n"
                "    print('locked', flush=True)\n"
                "    time.sleep(0.9)\n"
            )
            worker = subprocess.Popen(
                [sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parents[1]),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
            )
            try:
                self.assertEqual(worker.stdout.readline().strip(), "locked")
                started = time.monotonic()
                with _proxy_lock(target):
                    waited = time.monotonic() - started
                self.assertGreaterEqual(waited, 0.45)
            finally:
                worker.wait(timeout=5)
                error_output = worker.stderr.read()
                worker.stdout.close()
                worker.stderr.close()
                if worker.returncode:
                    self.fail(error_output)

    def test_settings_save_retries_a_transient_windows_file_lock(self):
        """A momentary WinError 5/32 cannot discard a user's settings change."""
        with tempfile.TemporaryDirectory(prefix="newsflow-settings-lock-") as temporary:
            root = Path(temporary)
            destination = root / "settings.json"
            real_replace = config_module.os.replace
            attempts = {"count": 0}

            def briefly_locked(source, target):
                attempts["count"] += 1
                if attempts["count"] == 1:
                    raise PermissionError(5, "Access is denied", str(target))
                return real_replace(source, target)

            with patch.object(config_module, "config_path", return_value=destination), \
                 patch.object(config_module.os, "replace", side_effect=briefly_locked), \
                 patch.object(config_module.time, "sleep", return_value=None):
                config_module.save_settings(Settings(montage_output_folder=str(root / "output")))
            self.assertGreaterEqual(attempts["count"], 2)
            self.assertTrue(destination.is_file())

    def test_snapshot_survives_an_unavailable_footage_database(self):
        """A locked/corrupt index must be reported in UI data, not crash Electron."""
        with tempfile.TemporaryDirectory(prefix="newsflow-snapshot-") as temporary:
            root = Path(temporary)
            settings = Settings(
                montage_project_folder=str(root / "projects"),
                montage_output_folder=str(root / "output"),
                media_output_folder=str(root / "media"),
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([], [])), \
                 patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_recover_interrupted_montage_tasks", return_value=False), \
                 patch.object(bridge, "_migrate_legacy_cover_texts", return_value=False), \
                 patch.object(bridge, "_read_footage_index_status", return_value={"active": False}), \
                 patch.object(bridge, "ClipIndex", side_effect=sqlite3.OperationalError("database is locked")):
                data = bridge.snapshot()
            self.assertEqual(data["footageIndex"]["total"], 0)
            self.assertIn("временно недоступна", data["footageIndex"]["error"])

    def test_snapshot_survives_a_database_lock_after_opening(self):
        """A transaction starting between schema read and counters must also be non-fatal."""
        with tempfile.TemporaryDirectory(prefix="newsflow-snapshot-lock-") as temporary:
            root = Path(temporary)
            settings = Settings(
                montage_project_folder=str(root / "projects"),
                montage_output_folder=str(root / "output"),
                media_output_folder=str(root / "media"),
            )

            class BusyIndex:
                def count(self, *_args):
                    raise sqlite3.OperationalError("database is locked")

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=([], [])), \
                 patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_recover_interrupted_montage_tasks", return_value=False), \
                 patch.object(bridge, "_migrate_legacy_cover_texts", return_value=False), \
                 patch.object(bridge, "_read_footage_index_status", return_value={"active": False}), \
                 patch.object(bridge, "ClipIndex", return_value=BusyIndex()):
                data = bridge.snapshot()
            self.assertEqual(data["footageIndex"]["indexed"], 0)
            self.assertIn("временно занята", data["footageIndex"]["error"])

    def test_local_scene_planner_keeps_title_context_for_pronoun_sentences(self):
        """A short sentence without nouns must still search within its news topic."""
        plan = fallback_scene_plan(
            "Это может изменить ситуацию уже в ближайшие часы.",
            "Иран — Ормузский пролив и нефтяные танкеры",
        )
        self.assertEqual(len(plan), 1)
        query = plan[0]["visual_query_en"].casefold()
        self.assertIn("hormuz", query)
        self.assertIn("oil tanker", query)
        self.assertNotIn("ukraine", query)

    def test_topic_guard_rejects_explicitly_contradictory_footage(self):
        """A Ukraine-labelled file must not fill an Ormuz scene just for being war footage."""
        ukraine_clip = FootageItem(
            path=r"D:\footage\Ukraine\Zelensky Kyiv military factory.mp4",
            name="Ukraine Kyiv military factory.mp4",
            tags=["ukraine", "kyiv", "zelensky", "war"],
        )
        self.assertFalse(_semantic_clip_ok("Strait of Hormuz oil tanker Persian Gulf", ukraine_clip))

    def test_topic_guard_rejects_sevastopol_footage_for_washington(self):
        """A named Russian location cannot stand in for a Washington government scene."""
        sevastopol_clip = FootageItem(
            path=r"D:\footage\Задержания\Севастополе вскрыта агентурная сеть\clip.mp4",
            name="clip.mp4",
            tags=["sevastopol", "press-conference", "military-drone"],
        )
        self.assertFalse(_semantic_clip_ok(
            "Washington DC White House US government officials", sevastopol_clip,
        ))

    def test_topic_guard_rejects_druzhkivka_footage_for_kyiv_government(self):
        """A named frontline city is not neutral Kyiv-government B-roll."""
        druzhkivka_clip = FootageItem(
            path=r"D:\footage\Украина\Дружковка Краматорск FPV дроны\clip.mp4",
            name="clip.mp4",
            tags=["ukraine-government-kyiv", "emergency-aftermath", "druzhkivka", "kramatorsk"],
        )
        self.assertFalse(_semantic_clip_ok("Kyiv Ukraine government city", druzhkivka_clip))

    def test_fast_title_only_planner_uses_mp3_timing_and_topic(self):
        plan = title_only_scene_plan("Иран — Ормузский пролив и нефтяные танкеры", 10.0)
        self.assertGreaterEqual(len(plan), 2)
        self.assertAlmostEqual(sum(item["duration"] for item in plan), 10.0, places=1)
        self.assertTrue(all("hormuz" in item["visual_query_en"].casefold() for item in plan))

    def test_screen_v4_restores_english_only_contract_and_blocks_interstitials(self):
        """Russian text is allowed; English and full-screen slates are blocked."""
        class DummyImageEmbedder:
            def embed(self, images, **_):
                for image in images:
                    if image in {"english", "interstitial"}:
                        yield np.asarray([1.0, 0.0], dtype=np.float32)
                    elif image == "uncertain":
                        yield np.asarray([1.0, 1.0], dtype=np.float32)
                    else:
                        # clean and ordinary Cyrillic footage both align with
                        # the allowed/no-English side of the classifier.
                        yield np.asarray([0.0, 1.0], dtype=np.float32)

        class DummyTextEmbedder:
            def query_embed(self, value, **_):
                queries = value if isinstance(value, list) else [value]
                positive = {item.casefold() for item in _SCREEN_TEXT_POSITIVE_QUERIES}
                for query in queries:
                    if str(query).casefold() in positive:
                        yield np.asarray([1.0, 0.0], dtype=np.float32)
                    else:
                        yield np.asarray([0.0, 1.0], dtype=np.float32)

        class FrameIndex(ClipIndex):
            @staticmethod
            def _sample_frames(path, samples=3):
                name = path.name
                if "english-caption" in name:
                    frames = ["clean", "clean", "clean", "english", "clean"]
                elif "russian-caption" in name:
                    frames = ["cyrillic"] * max(11, samples)
                elif "title-card" in name:
                    frames = ["clean", "interstitial", "interstitial", "clean", "clean"]
                elif "uncertain" in name:
                    frames = ["uncertain"] * max(11, samples)
                else:
                    frames = ["clean"] * max(11, samples)
                return frames[:samples], 6.0, 1920, 1080, 30.0

        with tempfile.TemporaryDirectory(prefix="newsflow-screen-v4-") as temporary:
            root = Path(temporary)
            english_path = root / "english-caption.mp4"
            russian_path = root / "russian-caption.mp4"
            interstitial_path = root / "title-card.mp4"
            uncertain_path = root / "uncertain.mp4"
            for path in (english_path, russian_path, interstitial_path, uncertain_path):
                path.touch()
            index = FrameIndex(
                root / "clips.sqlite3",
                embedder_factory=lambda: (DummyImageEmbedder(), DummyTextEmbedder()),
            )
            indexed = index.index_folders([str(root)])
            self.assertEqual(indexed.indexed, 4)
            self.assertEqual(index.screen_text_stats(), {"blocked": 0, "safe": 0, "unchecked": 4})

            labeled = index.classify_english_screen_text()
            self.assertEqual(labeled["checked"], 4)
            self.assertEqual(labeled["blocked"], 2)
            self.assertEqual(labeled["safe"], 1)
            self.assertEqual(labeled["uncertain"], 1)
            self.assertEqual(index.screen_text_eligibility(english_path), SCREEN_ELIGIBILITY_BLOCKED)
            self.assertEqual(index.screen_text_eligibility(interstitial_path), SCREEN_ELIGIBILITY_BLOCKED)
            self.assertEqual(index.screen_text_eligibility(russian_path), SCREEN_ELIGIBILITY_SAFE)
            self.assertEqual(index.screen_text_eligibility(uncertain_path), SCREEN_ELIGIBILITY_UNCERTAIN)
            self.assertEqual(index.screen_text_eligibility(uncertain_path, deep=True), SCREEN_ELIGIBILITY_UNCERTAIN)

            names = {item.name for item in index.all_items(exclude_english_text=True)}
            self.assertEqual(names, {"russian-caption.mp4", "uncertain.mp4"})

    def test_stale_v3_blocks_reenter_search_as_uncertain_under_v4(self):
        """Old all-language v3 blocks must not permanently trash the library."""
        with tempfile.TemporaryDirectory(prefix="newsflow-screen-v3-migration-") as temporary:
            root = Path(temporary)
            path = root / "russian-news.mp4"
            path.touch()
            index = ClipIndex(root / "clips.sqlite3")
            index.add_item(FootageItem(str(path), path.name))
            with index._connect() as connection:
                connection.execute(
                    "UPDATE clips SET english_text=1,english_text_version=? WHERE path=?",
                    (SCREEN_TEXT_CLASSIFIER_VERSION - 1, str(path)),
                )
            self.assertEqual([item.name for item in index.all_items(exclude_english_text=True)], [path.name])
            self.assertEqual(index.screen_text_stats(), {"blocked": 0, "safe": 0, "unchecked": 1})

    def test_ffmpeg_render_is_30fps_has_audio_and_does_not_crop_voice(self):
        source_root = Path(__file__).resolve().parents[1] / "work" / "smoke-clips"
        red, blue = source_root / "red.mp4", source_root / "blue.mp4"
        self.assertTrue(red.is_file() and blue.is_file(), "Smoke fixtures missing")
        with tempfile.TemporaryDirectory(prefix="newsflow-render-test-") as temporary:
            root = Path(temporary)
            voice = root / "voice.wav"
            ffmpeg = ffmpeg_executable()
            make_voice = subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2.0",
                str(voice),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(make_voice.returncode, 0, make_voice.stderr[-1000:])
            project = TimelineProject(
                title="FFmpeg smoke",
                voiceover_path=str(voice),
                clips=[
                    TimelineClip(path=str(red), narration="Первая сцена", visual_query_en="red", duration=1.0),
                    TimelineClip(path=str(blue), narration="Вторая сцена", visual_query_en="blue", duration=1.0),
                ],
            )
            output = root / "result.mp4"
            with patch.object(timeline_module, "proxy_cache_root", return_value=root / "RenderProxy"):
                render_project(project, output, renderer="ffmpeg")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertGreaterEqual(probe_media_duration(output), 1.9)
            self.assertGreaterEqual(validate_rendered_montage(output, expected_duration=2.0), 1.9)
            inspect = subprocess.run([ffmpeg, "-hide_banner", "-i", str(output)], capture_output=True, text=True,
                                     encoding="utf-8", errors="replace")
            details = inspect.stderr
            self.assertIn("30 fps", details)
            self.assertIn("Audio:", details)

    def test_ffmpeg_intro_keeps_insert_audio_and_delays_voiceover(self):
        """The first news insert is a real audible insert, not a silent cropped frame."""
        source_root = Path(__file__).resolve().parents[1] / "work" / "smoke-clips"
        footage = source_root / "red.mp4"
        self.assertTrue(footage.is_file(), "Smoke fixture missing")
        with tempfile.TemporaryDirectory(prefix="newsflow-intro-test-") as temporary:
            root = Path(temporary)
            ffmpeg = ffmpeg_executable()
            intro = root / "intro.mp4"
            voice = root / "voice.wav"
            made_intro = subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=640x360:r=30:d=1.6",
                "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=1.6",
                "-shortest", "-c:v", "libx264", "-c:a", "aac", str(intro),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(made_intro.returncode, 0, made_intro.stderr[-1000:])
            made_voice = subprocess.run([
                ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=2",
                str(voice),
            ], capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(made_voice.returncode, 0, made_voice.stderr[-1000:])
            project = TimelineProject(
                title="Заставка", voiceover_path=str(voice), intro_path=str(intro), intro_duration=1.6,
                clips=[TimelineClip(path=str(footage), narration="Сцена", visual_query_en="news", duration=2.0)],
            )
            output = root / "intro-result.mp4"
            with patch.object(timeline_module, "proxy_cache_root", return_value=root / "RenderProxy"):
                render_project(project, output, renderer="ffmpeg")
            self.assertTrue(output.is_file())
            # Voice starts only after the complete 1.6-second insert.  A
            # legacy six/one-second trim would make this test shorter.
            self.assertGreaterEqual(probe_media_duration(output), 3.5)
            inspect = subprocess.run([ffmpeg, "-hide_banner", "-i", str(output)], capture_output=True, text=True,
                                     encoding="utf-8", errors="replace")
            self.assertIn("Audio:", inspect.stderr)

    def test_tail_completion_keeps_existing_full_clips_and_trims_only_final_clip(self):
        """A recoverable tail never shortens earlier footage beats."""
        project = TimelineProject(
            title="Хвост", clips=[
                TimelineClip("a.mp4", "a", "a", duration=1.0),
                TimelineClip("b.mp4", "b", "b", duration=1.0),
            ],
        )
        durations = {"a.mp4": 6.0, "b.mp4": 6.04, "c.mp4": 5.96}
        added = align_timeline_to_audio(
            project, 14.3,
            [TimelineClip("c.mp4", "tail", "tail", duration=1.0)],
            duration_probe=lambda path: durations[path.name],
        )
        self.assertEqual([round(clip.duration, 2) for clip in project.clips], [6.0, 6.04, 2.26])
        self.assertEqual([clip.path for clip in added], ["c.mp4"])

    def test_tail_completion_adds_full_sources_before_final_trim(self):
        """Any shortage can need multiple real sources, not a hard-coded six seconds."""
        project = TimelineProject(title="Длинный хвост")
        durations = {"a.mp4": 6.0, "b.mp4": 5.96, "c.mp4": 6.04}
        align_timeline_to_audio(
            project, 13.4,
            [TimelineClip("a.mp4", "a", "a"), TimelineClip("b.mp4", "b", "b"), TimelineClip("c.mp4", "c", "c")],
            duration_probe=lambda path: durations[path.name],
        )
        self.assertEqual([round(clip.duration, 2) for clip in project.clips], [6.0, 5.96, 1.44])

    def test_tail_completion_does_not_append_when_timeline_already_covers_audio(self):
        project = TimelineProject(title="Без хвоста", clips=[TimelineClip("a.mp4", "a", "a")])
        added = align_timeline_to_audio(
            project, 5.8, [TimelineClip("b.mp4", "b", "b")],
            duration_probe=lambda _path: 6.0,
        )
        self.assertEqual([round(clip.duration, 2) for clip in project.clips], [5.8])
        self.assertEqual(added, [])

    def test_failed_retry_never_overwrites_previous_published_mp4(self):
        """Force-retry renders into a partial file, preserving the last good output."""
        with tempfile.TemporaryDirectory(prefix="newsflow-atomic-retry-") as temporary:
            root = Path(temporary)
            output = root / "published.mp4"
            output.write_bytes(b"previous-good-video")
            project = TimelineProject(
                title="Повтор",
                clips=[TimelineClip(str(root / "missing.mp4"), "n", "q", duration=1.0)],
            )
            with self.assertRaises(FileNotFoundError):
                render_project(project, output, renderer="ffmpeg")
            self.assertEqual(output.read_bytes(), b"previous-good-video")


if __name__ == "__main__":
    unittest.main()
