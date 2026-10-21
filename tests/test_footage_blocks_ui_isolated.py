"""Opt-in real Electron issue417 journey; technical fixtures, no providers/models.

Run through tests/run_isolated.py with NEWSFLOW_RUN_FOOTAGE_BLOCKS_UI=1.
The outer production-write guard remains active. Evidence is retained beneath
the repository's ignored .superpowers tree, never in user NewsFlow storage.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
APP = REPO / "studio-ui-remotion-verify"
_RESOURCE_JOB = None


def _bound_windows_resources():
    """Bound this test and all inherited Electron/Python/FFmpeg children."""
    global _RESOURCE_JOB
    if os.name != "nt":
        raise RuntimeError("This source acceptance journey requires Windows")
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetProcessAffinityMask.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    affinity, system = ctypes.c_size_t(), ctypes.c_size_t()
    if not kernel.GetProcessAffinityMask(
        kernel.GetCurrentProcess(), ctypes.byref(affinity), ctypes.byref(system)
    ):
        raise ctypes.WinError()
    mask = sum([1 << bit for bit in range(64) if affinity.value & (1 << bit)][:4])
    if not kernel.SetProcessAffinityMask(kernel.GetCurrentProcess(), mask):
        raise ctypes.WinError()

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class IO(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", IO),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _RESOURCE_JOB = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.BasicLimitInformation.LimitFlags = 0x200 | 0x2000
    limits.JobMemoryLimit = 4 * 1024**3
    if not (
        _RESOURCE_JOB
        and kernel.SetInformationJobObject(
            _RESOURCE_JOB, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        )
        and kernel.AssignProcessToJobObject(_RESOURCE_JOB, kernel.GetCurrentProcess())
    ):
        raise ctypes.WinError()
    return {
        "affinityMask": mask,
        "cpuCount": mask.bit_count(),
        "wholeJobMemoryBytes": limits.JobMemoryLimit,
    }


@unittest.skipUnless(
    os.environ.get("NEWSFLOW_RUN_FOOTAGE_BLOCKS_UI") == "1",
    "opt-in source Electron fixture",
)
class FootageBlocksIsolatedUiTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("NEWSFLOW_FOOTAGE_BLOCKS_REEXPORT_ROOT"),
        "requires an existing disposable UI profile",
    )
    def test_reexport_existing_saved_plans(self):
        self.assertEqual(
            os.environ.get("NEWSFLOW_TEST_MODE"), "1", "Use tests/run_isolated.py"
        )
        _bound_windows_resources()
        root = Path(os.environ["NEWSFLOW_FOOTAGE_BLOCKS_REEXPORT_ROOT"]).resolve()
        self.assertTrue(
            root.is_relative_to(
                (REPO / ".superpowers/footage-blocks/ui-runtime").resolve()
            )
        )
        environment = json.loads(
            (root / "environment.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            environment["NEWSFLOW_PRODUCTION_LOCALAPPDATA"],
            os.environ["NEWSFLOW_PRODUCTION_LOCALAPPDATA"],
        )
        for name in ("NEWSFLOW_TEST_ROOT", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
            self.assertTrue(Path(environment[name]).resolve().is_relative_to(root))
        preserved = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for name in ("landscape", "portrait")
            for path in (
                root / "artifacts" / f"{name}.newsflow",
                root / "artifacts" / f"{name}.mp4",
            )
        }
        process = subprocess.Popen(
            [
                str(APP / "node_modules/electron/dist/electron.exe"),
                str(APP / "scripts/verify-footage-blocks-ui.mjs"),
                "reexport",
            ],
            cwd=APP,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            stdout, stderr = process.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
            )
            stdout, stderr = process.communicate(timeout=15)
            raise
        artifacts = root / "artifacts/after-tail-fix"
        (artifacts / "stdout.log").write_text(stdout, encoding="utf-8")
        (artifacts / "stderr.log").write_text(stderr, encoding="utf-8")
        self.assertEqual(process.returncode, 0, stdout[-3000:] + stderr[-5000:])
        self.assertEqual(
            json.loads((artifacts / "reexport.json").read_text(encoding="utf-8"))[
                "status"
            ],
            "PASS",
        )
        for path, expected in preserved.items():
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(),
                expected,
                f"Original evidence changed: {path}",
            )
        for name in ("landscape", "portrait"):
            self.assertTrue((artifacts / f"{name}.mp4").is_file())
        print(f"SAVED_PLAN_REEXPORT_ARTIFACTS={artifacts}", flush=True)

    def test_real_ui_crud_import_manual_restart_and_queue(self):
        self.assertEqual(
            os.environ.get("NEWSFLOW_TEST_MODE"), "1", "Use tests/run_isolated.py"
        )
        self.assertTrue(os.environ.get("NEWSFLOW_TEST_ROOT"))
        resources = _bound_windows_resources()
        root = (
            REPO / ".superpowers" / "footage-blocks" / "ui-runtime" / uuid.uuid4().hex
        )
        for name in (
            "local-app-data",
            "roaming-app-data",
            "io",
            "inputs",
            "block-a",
            "block-b/nested",
            "unused",
            "unused-new",
            "projects",
            "outputs",
            "downloads",
            "artifacts",
        ):
            (root / name).mkdir(parents=True, exist_ok=True)
        production = os.environ["NEWSFLOW_PRODUCTION_LOCALAPPDATA"]
        environment = {
            **os.environ,
            "NEWSFLOW_TEST_MODE": "1",
            "NEWSFLOW_TEST_ROOT": str(root),
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": production,
            "LOCALAPPDATA": str(root / "local-app-data"),
            "APPDATA": str(root / "roaming-app-data"),
            "TEMP": str(root / "io"),
            "TMP": str(root / "io"),
            "TMPDIR": str(root / "io"),
            "NEWSFLOW_PYTHON": sys.executable,
            "NEWSFLOW_REPO_ROOT": str(REPO),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HUB_OFFLINE": "1",
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "4",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
        }
        environment.pop("ELECTRON_RUN_AS_NODE", None)
        with patch.dict(os.environ, environment):
            manifest = self._seed(root, resources)
        (root / "environment.json").write_text(
            json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"FOOTAGE_BLOCKS_UI_PROFILE={root}", flush=True)
        electron = APP / "node_modules/electron/dist/electron.exe"
        self.assertTrue(electron.is_file())
        self.assertTrue(
            (APP / "dist/index.html").is_file(),
            "Build current source web and desktop first",
        )
        for phase in ("configure", "restart-off", "restart-on-queue"):
            process = subprocess.Popen(
                [
                    str(electron),
                    str(APP / "scripts/verify-footage-blocks-ui.mjs"),
                    phase,
                ],
                cwd=APP,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            try:
                stdout, stderr = process.communicate(timeout=240)
            except subprocess.TimeoutExpired:
                subprocess.run(
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                stdout, stderr = process.communicate(timeout=15)
                (root / "artifacts" / f"{phase}-timeout.log").write_text(
                    stdout + stderr, encoding="utf-8"
                )
                raise
            (root / "artifacts" / f"{phase}-stdout.log").write_text(
                stdout, encoding="utf-8"
            )
            (root / "artifacts" / f"{phase}-stderr.log").write_text(
                stderr, encoding="utf-8"
            )
            self.assertEqual(
                process.returncode, 0, f"{phase}: {stdout[-3000:]} {stderr[-5000:]}"
            )
            evidence = json.loads(
                (root / "artifacts" / f"{phase}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(evidence["status"], "PASS", evidence)
        projects = list((root / "projects").glob("*.newsflow"))
        self.assertEqual(len(projects), 1)
        project = json.loads(projects[0].read_text(encoding="utf-8"))
        self.assertEqual(project["source_policy"]["mode"], "block")
        self.assertEqual(
            project["source_policy"]["productionItemId"], manifest["productionItemId"]
        )
        self.assertEqual(
            Path(project["source_policy"]["footageBlock"]["root"]).resolve(),
            (root / "block-b").resolve(),
        )
        for clip in project["clips"]:
            self.assertTrue(
                Path(clip["path"])
                .resolve()
                .is_relative_to((root / "block-b").resolve()),
                clip,
            )
        self.assertAlmostEqual(
            sum(clip["duration"] for clip in project["clips"]), 6, places=1
        )
        outputs = list((root / "outputs").rglob("*.mp4"))
        self.assertEqual(len(outputs), 1)
        from scriptor.timeline import probe_media_duration

        self.assertAlmostEqual(probe_media_duration(outputs[0]), 6, delta=0.2)
        receipt = {
            "status": "PASS",
            "profileRoot": str(root),
            "project": str(projects[0]),
            "mp4": str(outputs[0]),
            "fixture": manifest["fixture"],
            "resources": resources,
        }
        (root / "artifacts/final-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(receipt, ensure_ascii=False), flush=True)

    def _seed(self, root, resources):
        from scriptor import bridge
        from scriptor.ai_index import SCREEN_TEXT_CLASSIFIER_VERSION, ClipIndex
        from scriptor.config import Settings, app_data_root, save_settings
        from scriptor.core import ScenarioRequest
        from scriptor.footage import FootageItem
        from scriptor.runner import Job, RunState
        from scriptor.session import save_session
        from scriptor.timeline import ffmpeg_executable
        from scriptor.voice_map import AlignmentResult, TimedObservation

        executable = ffmpeg_executable()
        voice = root / "inputs/synthetic-sine-6s.wav"
        subprocess.run(
            [
                executable,
                "-nostdin",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=6",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "pcm_s16le",
                str(voice),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        paths = []
        for folder, color in (
            ("block-a", "red"),
            ("block-b", "green"),
            ("block-b/nested", "blue"),
            ("unused", "black"),
            ("unused-new", "white"),
        ):
            video = root / folder / f"technical-{color}.mp4"
            subprocess.run(
                [
                    executable,
                    "-nostdin",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:s=320x180:r=30:d=8",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-pix_fmt",
                    "yuv420p",
                    "-threads",
                    "1",
                    str(video),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            paths.append(video)
        identity = "qa-footage-blocks-" + uuid.uuid4().hex
        title = "Заявления Алиева о протестах"
        script = "Технический цветной кадр первый. Технический цветной кадр второй."
        settings = Settings(
            pipeline_target_count=137,
            cover_rate_auto_resume=False,
            montage_renderer="ffmpeg",
            montage_source_mode="local",
            montage_use_footage_blocks=False,
            idea_production_items=[{"id": identity, "title": title, "manual": True}],
            voice_scenario_outputs={"1": str(voice)},
            voice_task_statuses={
                "1": {"state": "done", "label": "Готово", "progress": 100}
            },
            montage_project_folder=str(root / "projects"),
            montage_output_folder=str(root / "outputs"),
            footage_download_folder=str(root / "downloads"),
            footage_folders=[],
            montage_intro_enabled=False,
            montage_overlay_enabled=False,
            montage_export_davinci_xml=False,
            montage_davinci_auto_import=False,
            montage_planning_workers=1,
            montage_download_workers=1,
            montage_render_workers=1,
            montage_scene_planner="local",
        )
        save_settings(settings)
        save_session(
            [title],
            [
                Job(
                    ScenarioRequest(0, title, "", identity),
                    state=RunState.DONE,
                    result=script,
                )
            ],
        )

        class SyntheticTimingEngine:
            name = "qa-synthetic-sine-two-segment-fixture-not-speech-alignment"

            def availability(self):
                return True, ""

            def align(self, context):
                assert (
                    context.production_item_id == identity and context.script == script
                )
                return AlignmentResult(
                    self.name,
                    [
                        TimedObservation(
                            "Технический цветной кадр первый.", 0, 3, 1, "segment"
                        ),
                        TimedObservation(
                            "Технический цветной кадр второй.", 3, 6, 1, "segment"
                        ),
                    ],
                    1,
                )

        status = bridge._ensure_voice_map_for_scenario(
            0, engine=SyntheticTimingEngine()
        )
        self.assertEqual(status.state, "ready")
        self.assertEqual(len(status.data["segments"]), 2)
        # Solid-color clips contain no writing by construction. Seed their
        # known fixture metadata, never execute CLIP or alter a user index.
        index = ClipIndex(app_data_root() / "footage-index.sqlite3")
        for video in paths:
            index.add_item(FootageItem(str(video.resolve()), video.stem))
            with index._connect() as connection:
                connection.execute(
                    "UPDATE clips SET english_text=-1,english_text_version=?,duration=8,width=320,height=180,fps=30 WHERE path=?",
                    (SCREEN_TEXT_CLASSIFIER_VERSION, str(video.resolve())),
                )
        text = "Заявления Алиева о протестах\r\n\r\nАлиев протесты\r\n\r\nПолитическая ситуация в Армении\r\n\r\nАрмения политика\r\n\r\nНовая история о протестах в Баку\r\n\r\nАлиев протесты\r\n"
        (root / "inputs/pairs.txt").write_bytes(("\ufeff" + text).encode("utf-8"))
        manifest = {
            "productionItemId": identity,
            "title": title,
            "fixture": "Technical solid-color MP4 and sine-wave WAV; synthetic segment timing. No semantic/planner/speech-quality evidence.",
            "voice": str(voice),
            "voiceMap": status.path,
            "resources": resources,
            "files": {
                str(video): hashlib.sha256(video.read_bytes()).hexdigest()
                for video in paths
            },
        }
        (root / "fixture.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return manifest
