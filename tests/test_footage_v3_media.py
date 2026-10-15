"""Opt-in source prepare/render smoke with readable synthetic motion media.

Synthetic metadata/embeddings and tone audio test plumbing, never visual
semantics, recognition, speech alignment, or a provider. Outputs stay local.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor import bridge
from scriptor.ai_index import SCREEN_TEXT_CLASSIFIER_VERSION, ClipIndex
from scriptor.config import Settings, app_data_root, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import save_session
from scriptor.timeline import TimelineProject, ffmpeg_executable


class SyntheticText:
    def query_embed(self, queries):
        for _ in [queries] if isinstance(queries, str) else queries:
            yield np.ones(8, dtype=np.float32)


class SyntheticIndex(ClipIndex):
    def __init__(self, db_path, **kwargs):
        super().__init__(db_path, embedder_factory=lambda: (object(), SyntheticText()), **kwargs)


def run_media(command):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise AssertionError(result.stderr[-1500:])
    return result.stdout


@unittest.skipUnless(os.environ.get("NEWSFLOW_FOOTAGE_MEDIA_OUTPUT"), "opt-in local MP4 engineering smoke")
class FootageV3MediaSmoke(unittest.TestCase):
    def test_four_complete_source_montages(self):
        output = Path(os.environ["NEWSFLOW_FOOTAGE_MEDIA_OUTPUT"]).resolve()
        output.mkdir(parents=True, exist_ok=True)
        library = output / "synthetic-library"
        library.mkdir(exist_ok=True)
        ffmpeg = ffmpeg_executable()
        # Archive checkouts can resolve a different binary from PATH. Persist
        # identity so equal-source comparisons cannot hide that confounder.
        runtime = {
            "python": platform.python_version(), "platform": platform.platform(),
            "ffmpeg_version": run_media([ffmpeg, "-version"]).splitlines()[0],
            "ffmpeg_sha256": hashlib.sha256(Path(ffmpeg).read_bytes()).hexdigest(),
            "ffprobe_version": run_media([shutil.which("ffprobe"), "-version"]).splitlines()[0],
        }
        categories = [
            ("parliament-government", "government building exterior"),
            ("diplomatic-negotiations", "diplomatic negotiations delegations"),
            ("military-vehicles", "frontline tanks armored vehicles"),
            ("markets-trading", "economy finance markets"),
            ("oil-tanker-port", "oil tanker cargo ship port"),
            ("technology-datacenter", "data center servers computer network"),
            ("agriculture-farming", "agriculture farming harvest"),
            ("protest-crowd", "protest crowd placards"),
        ]
        index = SyntheticIndex(app_data_root() / "footage-index.sqlite3")
        before_hashes = {}
        for number, (tag, words) in enumerate(categories):
            path = library / f"clip_{number:03}.mp4"
            run_media([ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=7",
                       "-vf", f"hue=h={number * 36}", "-an", "-c:v", "libx264", str(path)])
            before_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            stat = path.stat()
            with index._connect() as connection:
                connection.execute(
                    "INSERT INTO clips(path,name,size,mtime_ns,embedding,tags,duration,width,height,fps,"
                    "english_text,english_text_version) VALUES(?,?,?,?,?,?,7,320,180,30,-1,?)",
                    (str(path), path.name, stat.st_size, stat.st_mtime_ns,
                     np.full(8, 1 / np.sqrt(8), dtype=np.float32).tobytes(),
                     json.dumps([tag, words]), SCREEN_TEXT_CLASSIFIER_VERSION),
                )
        scripts = [
            "Путин выступил с заявлением. Зеленский ответил журналистам. Трамп провёл переговоры.",
            "Санкции ударили по экономике. Танкер прибыл в порт. Поезд перевозит зерно к порту.",
            ("Стороны ведут переговоры. Начался артиллерийский обстрел. Санкции ударили по экономике. "
             "Зеленский выступил с обращением. Кибератака нарушила работу серверов. Фермеры собирают урожай."),
            "Пашинян выступил с заявлением. На НПЗ произошёл пожар. Нарушена работа дата-центра.",
        ]
        titles = [f"Footage V3 engineering {i + 1}" for i in range(4)]
        settings = Settings(
            footage_folders=[str(library)], montage_project_folder=str(output / "projects"),
            montage_output_folder=str(output / "outputs"), montage_renderer="ffmpeg",
            montage_export_davinci_xml=False, montage_auto_web=False, montage_scene_planner="local",
            montage_intro_enabled=False, montage_overlay_enabled=False, montage_transition_style="cut",
            montage_transition_frames=0, montage_fast_reuse_enabled=False,
        )
        jobs = []
        for number, script in enumerate(scripts):
            duration = len(script.split(". ")) * 6
            voice = output / f"voice-{number + 1}.wav"
            run_media([ffmpeg, "-y", "-f", "lavfi", "-i",
                       f"sine=frequency={440 + number * 80}:sample_rate=48000:duration={duration}", str(voice)])
            settings.voice_scenario_outputs[str(number + 1)] = str(voice)
            jobs.append(Job(ScenarioRequest(number, titles[number], ""), RunState.DONE, script, ""))
        save_settings(settings)
        save_session(titles, jobs)
        self.assertEqual(bridge.load_settings().footage_folders, [str(library)])
        index.allowed_roots = [str(library)]
        self.assertTrue(index.search("Vladimir Putin press conference"))
        records = []
        with patch.object(bridge, "ClipIndex", SyntheticIndex):
            for number in range(4):
                started = time.perf_counter()
                prepared = bridge.prepare_montage({"scenarioIndex": number,
                    "_progress": lambda stage, detail: print(stage, detail)})["preparedProject"]
                preparation_seconds = time.perf_counter() - started
                project_path = Path(prepared["path"])
                project = TimelineProject.load(project_path)
                frozen_plan = [(clip.path, clip.source_start, clip.duration) for clip in project.clips]
                started = time.perf_counter()
                bridge.render_montage({"projectPath": str(project_path)})
                render_seconds = time.perf_counter() - started
                restored = TimelineProject.load(project_path)
                self.assertEqual(frozen_plan, [(clip.path, clip.source_start, clip.duration) for clip in restored.clips])
                mp4 = output / "outputs" / f"{titles[number]}.mp4"
                probe = json.loads(run_media([shutil.which("ffprobe"), "-v", "error", "-show_streams",
                                             "-show_format", "-of", "json", str(mp4)]))
                self.assertTrue({"audio", "video"} <= {s["codec_type"] for s in probe["streams"]})
                run_media([ffmpeg, "-v", "error", "-i", str(mp4), "-f", "null", "-"])
                expected = len(scripts[number].split(". ")) * 6
                self.assertAlmostEqual(float(probe["format"]["duration"]), expected, delta=.25)
                rows = []
                cursor = 0.
                for position, clip in enumerate(project.clips):
                    frame = output / f"frame-{number + 1}-{position + 1}.jpg"
                    run_media([ffmpeg, "-y", "-ss", str(min(cursor + clip.duration / 2, expected - .05)),
                               "-i", str(mp4), "-frames:v", "1", str(frame)])
                    rows.append({"time": round(cursor, 3), "text": clip.narration,
                                 "frame": frame.name, "source": Path(clip.path).name,
                                 "query": clip.visual_query_en, "level": clip.fallback_level,
                                 "person": getattr(clip, "selection_diagnostics", {}).get("person", {})})
                    cursor += clip.duration
                records.append({"output": mp4.name, "duration": float(probe["format"]["duration"]),
                                "preparation_seconds": preparation_seconds, "render_seconds": render_seconds,
                                "preparation_metrics_ms": project.preparation_metrics_ms,
                                "storyboard": rows, "summary": project.selection_summary})
        self.assertEqual(before_hashes, {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                        for path in library.glob("*.mp4")})
        (output / "manifest.json").write_text(json.dumps({
            "scope": "source prepare/persist/render/decode engineering only",
            "runtime": runtime,
            "limitations": ["synthetic motion patterns, metadata, embeddings and tone audio",
                             "no actual person imagery, speech alignment or semantic visual acceptance"],
            "PERSON_MATCH": "NOT VERIFIED", "VISUAL_SEMANTICS": "NOT VERIFIED", "outputs": records,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
