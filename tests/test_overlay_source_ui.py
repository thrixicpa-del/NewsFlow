"""Exercise the actual source Electron main/preload/core in disposable storage."""

import copy
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from PIL import Image

from scriptor import config, session, timeline
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"
ELECTRON = APP / "node_modules/electron/dist/electron.exe"


@unittest.skipUnless(
    ELECTRON.exists()
    and (APP / "dist/index.html").exists()
    and (APP / "dist-electron/main.js").exists(),
    "Build source web/desktop and install Electron first",
)
class OverlaySourceUITest(unittest.TestCase):
    def test_real_main_preload_core_numeric_preview_persistence_and_selection(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        root = Path(os.environ["NEWSFLOW_TEST_ROOT"])
        image = root / "source-logo.png"
        Image.new("RGBA", (100, 50), (255, 0, 0, 180)).save(image)
        library = root / "overlay-library"
        library.mkdir()
        for number, color in enumerate(((255, 0, 0, 180), (0, 255, 0, 180), (0, 0, 255, 180))):
            Image.new("RGBA", (100, 50), color).save(library / f"image-{number}.png")
        projects = root / "overlay-projects"
        projects.mkdir()
        layer = {
            "id": "source-logo",
            "name": "Source logo",
            "enabled": True,
            "path": str(image),
            "kind": "image",
            "x": 20,
            "y": 30,
            "width": 100,
            "height": 50,
            "keepAspect": True,
            "opacity": 1,
            "start": 0,
            "duration": 10,
            "mode": "once",
            "repeatEvery": 30,
            "endOffset": 5,
            "chromaEnabled": False,
            "chromaColor": "#00FF00",
            "chromaSimilarity": 0.12,
            "chromaBlend": 0.08,
            "audioEnabled": False,
        }
        vertical = {**layer, "x": 11, "y": 22}
        template = {"version": 1, "layouts": {"16:9": [layer], "9:16": [vertical]}}
        fixtures = root / "fixtures"
        fixtures.mkdir()
        ffmpeg = shutil.which("ffmpeg") or timeline.ffmpeg_executable()

        def fixture(*args):
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                check=True,
                capture_output=True,
                timeout=30,
            )

        fixture(
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=320x240:r=30:d=6.2",
            "-c:v",
            "libx264",
            fixtures / "blue.mp4",
        )
        video_library = root / "overlay-videos"
        video_library.mkdir()
        for number in range(3):
            shutil.copy2(fixtures / "blue.mp4", video_library / f"video-{number}.mp4")
        fixture(
            "-f",
            "lavfi",
            "-i",
            "color=black:s=320x240:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            1,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            fixtures / "intro.mp4",
        )
        voice = fixtures / "voice.wav"
        fixture(
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=437:sample_rate=48000:duration=6",
            "-c:a",
            "pcm_s16le",
            voice,
        )
        project = timeline.TimelineProject(
            "Overlay source QA",
            clips=[
                timeline.TimelineClip(str(fixtures / "blue.mp4"), "Test", "test", 6)
            ],
            overlay_template=copy.deepcopy(template),
            voiceover_path=str(voice),
            intro_path=str(fixtures / "intro.mp4"),
            intro_duration=1,
            selection_summary={"source_ui_plan": "must remain unchanged", "scenes": 1},
        )
        projectfile = projects / "Overlay source QA.newsflow"
        project.save(projectfile)
        settings = config.load_settings()
        outputs = root / "outputs"
        outputs.mkdir()
        settings.montage_project_folder = str(projects)
        settings.montage_output_folder = str(outputs)
        settings.montage_renderer = "ffmpeg"
        settings.montage_renderer_explicit = True
        settings.montage_export_davinci_xml = True
        settings.montage_overlay_template = copy.deepcopy(template)
        settings.idea_production_items = [
            {"id": "source-qa-id", "title": "Overlay source QA", "manual": True}
        ]
        settings.idea_scenario_context = {
            "Overlay source QA": copy.deepcopy(settings.idea_production_items[0])
        }
        settings.montage_task_statuses = {
            "0": {
                "index": 0,
                "title": "Overlay source QA",
                "status": "Готов к монтажу",
                "phase": "Готов к монтажу",
                "projectPath": str(projectfile),
                "production_item_id": "source-qa-id",
                "overlayTemplate": copy.deepcopy(template),
            }
        }
        # Existing generated fixture is local test material only; no user's voices.

        settings.voice_scenario_outputs = {"1": str(voice)}
        config.save_settings(settings)
        session.save_session(
            ["Overlay source QA", "Overlay no MP3"],
            [
                Job(
                    ScenarioRequest(0, "Overlay source QA", "", "source-qa-id"),
                    RunState.DONE,
                    "Generated fixture narration",
                    "",
                )
            ],
        )
        evidence = ROOT / "test-data/overlay-404/source-ui"
        evidence.mkdir(parents=True, exist_ok=True)
        report = evidence / "result.json"
        env = {
            **os.environ,
            "NEWSFLOW_PYTHON": sys.executable,
            "NEWSFLOW_OVERLAY_UI_REPORT": str(report),
            "NEWSFLOW_OVERLAY_UI_SCREENSHOT": str(evidence / "screen.png"),
            "NEWSFLOW_OVERLAY_UI_LIBRARY": str(library),
            "NEWSFLOW_OVERLAY_UI_VIDEO_LIBRARY": str(video_library),
            "NEWSFLOW_OVERLAY_UI_CHOICES": str(evidence / "saved-choices.json"),
        }
        env.pop("ELECTRON_RUN_AS_NODE", None)
        result = subprocess.run(
            [str(ELECTRON), str(APP / "scripts/verify-overlay-source-ui.mjs")],
            cwd=APP,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        (evidence / "run.log").write_text(
            result.stdout + "\n" + result.stderr, encoding="utf-8"
        )
        self.assertEqual(result.returncode, 0, (result.stdout + result.stderr)[-18000:])
        self.assertEqual(json.loads(report.read_text())["status"], "PASS")
        stored = json.loads(projectfile.read_text(encoding="utf-8"))
        self.assertEqual(stored["overlay_template"]["layouts"]["16:9"][0]["x"], 41)
        self.assertEqual(stored["overlay_template"]["layouts"]["16:9"][0]["ranges"],
                         [{"start": .2, "end": .6}, {"start": 2, "end": 2.4}, {"start": 5.5, "end": 6.3}])
        self.assertEqual(next(row for row in stored["overlay_template"]["layouts"]["16:9"]
                              if row["name"] == "video-0.mp4")["repeatCount"], 3)
        self.assertEqual(
            config.load_settings().montage_overlay_template["layouts"]["9:16"][0]["x"],
            11,
        )
        self.assertEqual(
            stored["selection_summary"],
            {"source_ui_plan": "must remain unchanged", "scenes": 1},
        )
        self.assertEqual(len(stored["clips"]), 1)
        output = Path(stored["output_path"])
        self.assertTrue(output.is_file())
        self.assertFalse(stored["overlay_needs_render"])
        shutil.copy2(output, evidence / "source-ui-output.mp4")
        shutil.copy2(
            Path(stored["davinci_xml_path"]), evidence / "source-ui-output.fcpxml"
        )
        env["NEWSFLOW_OVERLAY_UI_STAGE"] = "restart"
        env["NEWSFLOW_OVERLAY_UI_REPORT"] = str(evidence / "restart-result.json")
        restart = subprocess.run(
            [str(ELECTRON), str(APP / "scripts/verify-overlay-source-ui.mjs")],
            cwd=APP,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        (evidence / "restart.log").write_text(
            restart.stdout + "\n" + restart.stderr, encoding="utf-8"
        )
        self.assertEqual(
            restart.returncode, 0, (restart.stdout + restart.stderr)[-12000:]
        )
        self.assertTrue(
            json.loads((evidence / "restart-result.json").read_text())[
                "fullProcessRestart"
            ]
        )
