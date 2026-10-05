"""Regression checks for NewsFlow's editable DaVinci handoff.

Run from ``work/NewsFlow``:
``python -m unittest scriptor.test_davinci -v``.
The tests do not require DaVinci Resolve, network access or a user profile.
"""
from __future__ import annotations

import subprocess
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from . import bridge, davinci
from .config import Settings
from .footage import FootageItem
from .timeline import (
    TimelineClip,
    TimelineProject,
    export_fcpxml,
    ffmpeg_executable,
    probe_media_duration,
    remotion_payload,
)


class DaVinciHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="newsflow-davinci-")
        self.root = Path(self.tempdir.name)
        # XML references media; it does not decode the fixture, so a tiny file
        # keeps this deterministic and independent of FFmpeg.
        self.media = self.root / "clip.mp4"
        self.media.write_bytes(b"fixture")

    def tearDown(self):
        self.tempdir.cleanup()

    def project(self) -> TimelineProject:
        return TimelineProject(
            title="Проверка DaVinci",
            voiceover_path=str(self.media),
            clips=[
                TimelineClip(path=str(self.media), narration="Первая сцена", visual_query_en="news", duration=2.0),
                TimelineClip(path=str(self.media), narration="Вторая сцена", visual_query_en="news", duration=2.0),
            ],
        )

    def test_xml_has_video_voice_and_editable_sequence(self):
        output = self.root / "timeline.fcpxml"
        project = self.project()
        export_fcpxml(project, output)
        root = ET.parse(output).getroot()
        self.assertEqual(root.tag, "fcpxml")
        self.assertEqual(root.attrib["version"], "1.10")
        sequence = root.find(".//sequence")
        self.assertIsNotNone(sequence)
        clips = root.findall(".//asset-clip")
        self.assertEqual(len(clips), 3)
        self.assertEqual(len([item for item in clips if item.attrib.get("lane") == "1"]), 1)
        self.assertEqual(project.davinci_xml_path, str(output))
        self.assertIn("file:///", output.read_text(encoding="utf-8"))

    def test_bridge_exports_xml_without_rendering_mp4(self):
        plan = self.root / "plan.newsflow"
        self.project().save(plan)
        settings = Settings()
        settings.montage_project_folder = str(self.root)
        old_load, old_snapshot = bridge.load_settings, bridge.snapshot
        try:
            bridge.load_settings = lambda: settings
            bridge.snapshot = lambda: {"snapshot": True}
            result = bridge.export_davinci_xml({"projectPath": str(plan)})
        finally:
            bridge.load_settings, bridge.snapshot = old_load, old_snapshot
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertTrue(plan.with_suffix(".fcpxml").is_file())
        self.assertFalse(plan.with_suffix(".mp4").exists())

    def test_full_intro_duration_ignores_legacy_clip_setting(self):
        """A selected intro must keep its full source duration, not six seconds."""
        ffmpeg = ffmpeg_executable()
        intro = self.root / "full-intro.mp4"
        created = subprocess.run([
            ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x180:r=30:d=2.4",
            "-f", "lavfi", "-i", "sine=frequency=250:sample_rate=48000:duration=2.4",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(intro),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        self.assertEqual(created.returncode, 0, created.stderr[-1000:])
        self.assertGreater(bridge._full_intro_duration(str(intro), fallback=6.0), 2.2)

    def test_import_uses_public_resolve_api(self):
        xml = self.root / "timeline.fcpxml"
        export_fcpxml(self.project(), xml)
        calls = []

        class Timeline:
            def SetName(self, name):
                calls.append(("SetName", name))

        class MediaPool:
            def ImportTimelineFromFile(self, path, options):
                calls.append(("ImportTimelineFromFile", path, options))
                return Timeline()

        class Project:
            def GetMediaPool(self):
                return MediaPool()

            def SetCurrentTimeline(self, timeline):
                calls.append(("SetCurrentTimeline", bool(timeline)))

        class Resolve:
            def GetProjectManager(self):
                return types.SimpleNamespace(GetCurrentProject=lambda: Project())

        module = types.SimpleNamespace(scriptapp=lambda _: Resolve())
        old_load = davinci._load_module
        try:
            davinci._load_module = lambda paths=None: module
            result = davinci.import_fcpxml(xml, "Мой таймлайн")
        finally:
            davinci._load_module = old_load
        self.assertEqual(result["timeline"], "Мой таймлайн")
        self.assertEqual(calls[0][0], "ImportTimelineFromFile")
        self.assertEqual(calls[0][2], {})
        self.assertIn(("SetName", "Мой таймлайн"), calls)

    def test_status_explains_incomplete_resolve_installation(self):
        """A leftover API shim must not look like a working Resolve install."""
        old_paths, old_library = davinci._module_paths, davinci._configure_native_library
        try:
            davinci._module_paths = lambda: [self.root]
            davinci._configure_native_library = lambda: None
            status = davinci.resolve_status()
        finally:
            davinci._module_paths, davinci._configure_native_library = old_paths, old_library
        self.assertFalse(status["available"])
        self.assertFalse(status["connected"])
        self.assertIn("fusionscript.dll", status["message"])

    def test_optional_auto_import_never_turns_render_into_failure(self):
        """MP4/XML remain usable even when Resolve is currently unavailable."""
        plan = self.root / "plan.newsflow"
        project = self.project()
        project.save(plan)
        settings = Settings()
        settings.montage_project_folder = str(self.root)
        settings.montage_output_folder = str(self.root / "out")
        settings.montage_export_davinci_xml = True
        settings.montage_davinci_auto_import = True
        rendered = Path(settings.montage_output_folder) / "Проверка DaVinci.mp4"
        rendered.parent.mkdir(parents=True)
        rendered.write_bytes(b"rendered")
        old_load, old_save, old_snapshot = bridge.load_settings, bridge.save_settings, bridge.snapshot
        old_render, old_import = bridge.render_project, bridge.import_fcpxml
        try:
            bridge.load_settings = lambda: settings
            bridge.save_settings = lambda _: None
            bridge.snapshot = lambda: {"snapshot": True}
            bridge.render_project = lambda *_args, **_kwargs: rendered
            bridge.import_fcpxml = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Resolve закрыт"))
            # This hand-off test deliberately uses a tiny non-media fixture;
            # source-duration decoding is covered by the real render tests.
            with patch.object(bridge, "probe_media_duration", return_value=4.0), \
                 patch.object(bridge, "validate_rendered_montage"):
                result = bridge.render_montage({"projectPath": str(plan)})
        finally:
            bridge.load_settings, bridge.save_settings, bridge.snapshot = old_load, old_save, old_snapshot
            bridge.render_project, bridge.import_fcpxml = old_render, old_import
        self.assertTrue(rendered.is_file())
        self.assertTrue(plan.with_suffix(".fcpxml").is_file())
        self.assertIn("не импортирован", result["operationResult"]["warning"])

    def test_remotion_payload_keeps_full_voice_duration(self):
        """The composition must not truncate a longer MP3 after the last clip."""
        project = self.project()
        old_probe = __import__("scriptor.timeline", fromlist=["probe_media_duration"]).probe_media_duration
        module = __import__("scriptor.timeline", fromlist=["probe_media_duration"])
        try:
            module.probe_media_duration = lambda _path: 11.0
            payload = remotion_payload(project, fps=30)
        finally:
            module.probe_media_duration = old_probe
        self.assertEqual(payload["visualDurationInFrames"], 120)
        self.assertEqual(payload["durationInFrames"], 330)

    def test_bridge_ffmpeg_render_creates_mp4_remotion_plan_and_xml(self):
        """Exercise the desktop render action, not only the lower FFmpeg helper."""
        clip = self.root / "red.mp4"
        voice = self.root / "voice.wav"
        ffmpeg = ffmpeg_executable()
        made_clip = subprocess.run([
            ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=640x360:r=30:d=2.5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        self.assertEqual(made_clip.returncode, 0, made_clip.stderr[-1000:])
        made_voice = subprocess.run([
            ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2.5",
            str(voice),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        self.assertEqual(made_voice.returncode, 0, made_voice.stderr[-1000:])
        settings = Settings()
        settings.montage_renderer = "ffmpeg"
        settings.montage_project_folder = str(self.root / "projects")
        settings.montage_output_folder = str(self.root / "outputs")
        settings.montage_export_davinci_xml = True
        project_path = Path(settings.montage_project_folder) / "desktop.newsflow"
        project_path.parent.mkdir(parents=True)
        TimelineProject(
            title="Desktop render",
            voiceover_path=str(voice),
            clips=[TimelineClip(path=str(clip), narration="Сцена", visual_query_en="news", duration=2.5)],
        ).save(project_path)
        old_load, old_save, old_snapshot = bridge.load_settings, bridge.save_settings, bridge.snapshot
        try:
            bridge.load_settings = lambda: settings
            bridge.save_settings = lambda _settings: None
            bridge.snapshot = lambda: {"snapshot": True}
            result = bridge.render_montage({"projectPath": str(project_path)})
        finally:
            bridge.load_settings, bridge.save_settings, bridge.snapshot = old_load, old_save, old_snapshot
        output = Path(settings.montage_output_folder) / "Desktop render.mp4"
        self.assertEqual(result["operationResult"]["kind"], "render")
        self.assertTrue(output.is_file())
        self.assertGreaterEqual(probe_media_duration(output), 2.4)
        self.assertTrue(project_path.with_suffix(".fcpxml").is_file())
        self.assertTrue(output.with_suffix(".remotion.json").is_file())

    def test_manual_mp3_preparation_has_a_safe_external_download_fallback(self):
        """"Use TXT сценария" may be off; manual prepare must not reference an undefined queue semaphore."""
        clip = self.root / "fallback.mp4"
        clip.write_bytes(b"fixture")
        voice = self.root / "manual.mp3"
        voice.write_bytes(b"fixture")
        settings = Settings()
        settings.montage_use_script_text = False
        settings.montage_project_folder = str(self.root / "projects")
        settings.montage_output_folder = str(self.root / "outputs")
        settings.voice_scenario_outputs = {"1": str(voice)}

        class Index:
            def count(self, *_args):
                return 1

            def search_many(self, queries, limit=96):
                return [[] for _ in queries]

        observed = {}

        def external(scene, _settings, _index, semaphore, **_kwargs):
            observed["semaphore"] = semaphore
            return FootageItem(str(clip), clip.name, "fixture", "", "", ["news"])

        single_scene = [{"duration": 1.0, "narration": "", "visual_query_en": "news"}]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(["Ручной MP3"], [])), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={"snapshot": True}), \
             patch.object(bridge, "ClipIndex", return_value=Index()), \
             patch.object(bridge, "probe_media_duration", return_value=1.0), \
             patch.object(bridge, "_cached_or_probed_montage_duration", return_value=1.0), \
             patch.object(bridge, "_complete_project_visual_tail", return_value=0), \
             patch.object(bridge, "title_only_scene_plan", return_value=single_scene), \
             patch.object(bridge, "_download_scene_fallback", side_effect=external):
            result = bridge.prepare_montage({"scenarioIndex": 0})
        self.assertIsNone(observed["semaphore"])
        self.assertEqual(result["preparedProject"]["clips"], 1)
        self.assertTrue((Path(settings.montage_project_folder) / "Ручной MP3.newsflow").is_file())

    def test_remove_project_keeps_original_media_and_rendered_mp4(self):
        """The Delete project button must never delete source footage or final MP4."""
        settings = Settings()
        settings.montage_project_folder = str(self.root / "projects")
        settings.montage_output_folder = str(self.root / "outputs")
        project_path = Path(settings.montage_project_folder) / "safe.newsflow"
        project_path.parent.mkdir(parents=True)
        self.project().save(project_path)
        export_fcpxml(self.project(), project_path.with_suffix(".fcpxml"))
        output = Path(settings.montage_output_folder) / "safe.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"final output")
        output.with_suffix(".remotion.json").write_text("{}", encoding="utf-8")
        old_load, old_snapshot = bridge.load_settings, bridge.snapshot
        try:
            bridge.load_settings = lambda: settings
            bridge.snapshot = lambda: {"snapshot": True}
            result = bridge.remove_montage_projects({"paths": [str(project_path)]})
        finally:
            bridge.load_settings, bridge.snapshot = old_load, old_snapshot
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertFalse(project_path.exists())
        self.assertFalse(project_path.with_suffix(".fcpxml").exists())
        self.assertFalse(output.with_suffix(".remotion.json").exists())
        self.assertTrue(output.exists())
        self.assertTrue(self.media.exists())


if __name__ == "__main__":
    unittest.main()
