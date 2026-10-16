"""Opt-in read-only owner-authorized media smoke; no visual PASS assertions.

Run with NEWSFLOW_REAL_FOOTAGE_MANIFEST pointing at a local source manifest.
Labels for evaluation must live outside the retrieval database.
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

from scriptor import ai_index, bridge
from scriptor.ai_index import ClipIndex
from scriptor.config import Settings, app_data_root, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import save_session
from scriptor.timeline import TimelineProject, ffmpeg_executable


@unittest.skipUnless(os.environ.get("NEWSFLOW_REAL_FOOTAGE_MANIFEST"), "requires authorized local media manifest")
class RealFootageAcceptance(unittest.TestCase):
    def test_readonly_real_model_and_source_pipeline(self):
        manifest = Path(os.environ["NEWSFLOW_REAL_FOOTAGE_MANIFEST"]).resolve()
        output = manifest.parent
        sources = json.loads(manifest.read_text(encoding="utf-8"))
        paths = [Path(row["path"]).resolve() for row in sources]
        self.assertTrue(all(path.is_file() for path in paths))
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        models = Path(os.environ["NEWSFLOW_REAL_MODEL_COPY"]).resolve()
        shutil.copytree(models, app_data_root() / "models", dirs_exist_ok=True)
        index = ClipIndex(app_data_root() / "footage-index.sqlite3")
        index.allowed_roots = list(dict.fromkeys(str(path.parent) for path in paths))
        started = time.perf_counter()
        # Only enumeration is restricted. Images, CLIP vectors, rankings and
        # screen-text verdicts use the actual production implementation.
        with patch.object(ai_index, "discover_video_paths", return_value=paths):
            indexed = index.index_folders(index.allowed_roots)
        index_seconds = time.perf_counter() - started
        self.assertEqual(indexed.failed, 0)
        index.enrich_semantic_tags()
        index.classify_english_screen_text()
        queries = [
            "peaceful civilian protest crowd placards street rally march",
            "workers labor strike picket line union protest factory gate",
            "peaceful farmers protest tractors placards",
            "Vladimir Putin press conference statement journalists cameras",
            "Volodymyr Zelensky press conference statement journalists cameras",
            "diplomatic negotiations delegations meeting",
            "frontline trenches soldiers battlefield military action",
        ]
        retrieval = []
        for query, hits in zip(queries, index.search_many(queries, limit=8)):
            retrieval.append({"query": query, "candidates": [{
                "id": next(row["id"] for row in sources if Path(row["path"]).resolve() == Path(hit.item.path)),
                "score": hit.score, "tags": hit.item.tags,
                "semantic_ok": bridge._semantic_clip_ok(query, hit.item),
                "screen_eligibility": index.screen_text_eligibility(hit.item.path, deep=True),
            } for hit in hits]})
        scripts = [
            "На фронте продолжаются бои. Делегации встретились для обсуждения соглашения.",
            "Заявление Путина прокомментировал Зеленский. Путин выступил с заявлением.",
            "Наступление не началось. Обстрел продолжился.",
            "Пашинян выступил с заявлением. Делегации провели встречу.",
            "На фронте продолжаются бои. Жители собрались на мирный митинг. Представители властей начали переговоры. Рабочие объявили забастовку. В порту возобновилась погрузка.",
            "На митинге не было столкновений. Митинг отменили. Делегации встретились. Фермеры протестуют у здания правительства.",
        ]
        settings = Settings(footage_folders=index.allowed_roots, montage_project_folder=str(output / "projects"),
            montage_output_folder=str(output / "outputs"), montage_renderer="ffmpeg", montage_export_davinci_xml=False,
            montage_auto_web=False, montage_scene_planner="local", montage_intro_enabled=False,
            montage_overlay_enabled=False, montage_transition_style="cut", montage_transition_frames=0,
            montage_fast_reuse_enabled=True, montage_unique_footage_percent=50)
        titles = [f"PR403 real {i + 1}" for i in range(len(scripts))]
        for i, text in enumerate(scripts):
            voice = output / f"voice-{i + 1}.wav"
            duration = len(text.split('. ')) * 6
            subprocess.run([ffmpeg_executable(), '-y', '-f', 'lavfi', '-i',
                            f'sine=frequency=440:sample_rate=48000:duration={duration}', str(voice)],
                           capture_output=True, check=True)
            settings.voice_scenario_outputs[str(i + 1)] = str(voice)
        save_settings(settings)
        save_session(titles, [Job(ScenarioRequest(i, title, ""), RunState.DONE, text, "")
                              for i, (title, text) in enumerate(zip(titles, scripts))])
        records = []
        for i, text in enumerate(scripts):
            started = time.perf_counter()
            try:
                prepared = bridge.prepare_montage({"scenarioIndex": i})["preparedProject"]
                preparation = time.perf_counter() - started
                project = TimelineProject.load(Path(prepared["path"]))
                started = time.perf_counter()
                bridge.render_montage({"projectPath": prepared["path"]})
                elapsed = time.perf_counter() - started
                target = output / "outputs" / f"{titles[i]}.mp4"
                probe = json.loads(subprocess.check_output([
                    shutil.which('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(target)], text=True))
                video_end = float(next(s['duration'] for s in probe['streams'] if s['codec_type'] == 'video'))
                audio_end = float(next(s['duration'] for s in probe['streams'] if s['codec_type'] == 'audio'))
                self.assertAlmostEqual(audio_end, len(text.split('. ')) * 6, delta=.05)
                self.assertGreaterEqual(video_end, audio_end - .25)
                subprocess.run([ffmpeg_executable(), '-v', 'error', '-i', str(target), '-f', 'null', '-'],
                                         capture_output=True, check=True)
                rows = []
                cursor = 0
                for position, clip in enumerate(project.clips):
                    frames = []
                    for label, moment in [('start', cursor + .05), ('middle', cursor + clip.duration / 2),
                                          ('end', cursor + clip.duration - .12)]:
                        moment = min(moment, max(0, video_end - 2/30))
                        frame = output / f'video-{i+1}-scene-{position+1}-{label}.png'
                        subprocess.run([ffmpeg_executable(), '-v', 'error', '-y', '-ss', str(moment), '-i', str(target),
                                        '-frames:v', '1', str(frame)], check=True, capture_output=True)
                        self.assertTrue(frame.is_file(), f'No decoded boundary frame at {moment}')
                        frames.append(frame.name)
                    rows.append({'text': clip.narration, 'query': clip.visual_query_en, 'time': cursor,
                        'source_id': next(row['id'] for row in sources if Path(row['path']).resolve() == Path(clip.path)),
                        'source_start': clip.source_start, 'duration': clip.duration, 'level': clip.fallback_level,
                        'diagnostics': clip.selection_diagnostics, 'frames': frames})
                    cursor += clip.duration
                records.append({'script': text, 'status': 'RENDERED', 'output': target.name,
                                'prepare_seconds': preparation, 'render_seconds': elapsed, 'video_duration': video_end,
                                'audio_duration': audio_end, 'scenes': rows})
            except (ValueError, RuntimeError, bridge.MontageSelectionFailure) as error:
                records.append({'script': text, 'status': 'INCOMPLETE', 'reason': str(error),
                                'elapsed': time.perf_counter() - started})
        self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
        report = {'scope': 'actual CLIP and permitted original files; labels NOT injected; tone audio',
                  'runtime': {'python': platform.python_version(), 'platform': platform.platform(),
                              'ffmpeg_sha256': hashlib.sha256(Path(ffmpeg_executable()).read_bytes()).hexdigest(),
                              'source_sha256': {name: hashlib.sha256(Path(__import__(f'scriptor.{name}', fromlist=['__file__']).__file__).read_bytes()).hexdigest()
                                                for name in ('scene_intent', 'timeline', 'bridge', 'ai_index')}},
                  'index_seconds': index_seconds, 'count': index.count(), 'retrieval': retrieval, 'outputs': records,
                  'source_hashes': 'UNCHANGED', 'REAL_MEDIA_SEMANTICS': 'AWAITING_INDEPENDENT_REVIEW',
                  'PERSON_MATCH': 'NOT_VERIFIED', 'PROTEST_REAL_MEDIA': 'AWAITING_INDEPENDENT_REVIEW'}
        (output / 'model-pipeline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('real model outputs', [(row['status'], row.get('output', '')) for row in records])
