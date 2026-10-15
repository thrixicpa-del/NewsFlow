"""Opt-in owner-authorized ready speech; originals remain read-only.

Existing approximate timing remains approximate; no speech-alignment claim.
"""
import cProfile
import hashlib
import json
import os
import re
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
from scriptor.voice_map import (
    VoiceMapContext,
    audio_sha256,
    inspect_voice_map,
    script_sha256,
    voice_map_path,
)


def _validate_ready_probe(probe, duration):
    if abs(float(probe['format']['duration']) - duration) > .25:
        raise ValueError('ready speech container duration mismatch')
    if not {'audio', 'video'} <= {s['codec_type'] for s in probe['streams']}:
        raise ValueError('ready speech requires audio and video')
    endpoints = {}
    for kind in ('audio', 'video'):
        stream = next(s for s in probe['streams'] if s['codec_type'] == kind)
        try:
            endpoint = float(stream.get('start_time', 0)) + float(stream['duration'])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f'{kind} duration is unverified') from error
        if not duration - .25 <= endpoint <= duration + .25:
            raise ValueError(f'{kind} endpoint does not preserve ready speech: {endpoint}')
        endpoints[kind] = endpoint
    return endpoints


def _validate_ready_results(results):
    if len(results) != 2 or not any(row['status'] == 'RENDERED' for row in results):
        raise ValueError('expected two ready voices and at least one verified rendered output')
    if any(row['status'] not in {'RENDERED', 'INCOMPLETE'} for row in results):
        raise ValueError('unexpected ready speech outcome')


def _controlled_ready_shortage(error, stage, projects):
    if stage != 'prepare':
        return False
    if isinstance(error, bridge.MontageSelectionFailure):
        return True
    match = re.fullmatch(
        r'Нет допустимого тематического футажа для сцены (\d+)\. '
        r'Неполный черновик сохранён: ([^\r\n]+\.newsflow\.partial)', str(error))
    if not match or Path(match[2]).name != match[2]:
        return False
    draft = projects / match[2]
    if not draft.is_file():
        return False
    payload = json.loads(draft.read_text(encoding='utf-8'))
    return len(payload.get('clips', [])) == int(match[1]) - 1


class ReadyVoiceEvidenceTests(unittest.TestCase):
    def test_only_prepare_shortage_with_matching_saved_draft_is_controlled(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT']) as folder:
            projects = Path(folder)
            expected = RuntimeError('Нет допустимого тематического футажа для сцены 2. '
                                    'Неполный черновик сохранён: test.newsflow.partial')
            self.assertFalse(_controlled_ready_shortage(expected, 'prepare', projects))
            (projects/'test.newsflow.partial').write_text(json.dumps({'clips': [{}]}), encoding='utf-8')
            self.assertTrue(_controlled_ready_shortage(expected, 'prepare', projects))
            self.assertFalse(_controlled_ready_shortage(expected, 'render', projects))
            self.assertFalse(_controlled_ready_shortage(RuntimeError('unexpected render failure'), 'prepare', projects))
    def test_short_audio_cannot_pass_with_long_video(self):
        with self.assertRaises(ValueError):
            _validate_ready_probe({'format': {'duration': '300'}, 'streams': [
                {'codec_type': 'video', 'duration': '300'},
                {'codec_type': 'audio', 'duration': '6'},
            ]}, 300)

    def test_missing_stream_duration_is_not_verified(self):
        with self.assertRaises(ValueError):
            _validate_ready_probe({'format': {'duration': '300'}, 'streams': [
                {'codec_type': 'video', 'duration': '300'}, {'codec_type': 'audio'},
            ]}, 300)

    def test_no_rendered_output_is_not_passing_coverage(self):
        for rows in ([], [{'status': 'INCOMPLETE'}] * 2, [{'status': 'RENDERED'}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                _validate_ready_results(rows)

    def test_controlled_shortage_and_one_verified_render_are_distinct(self):
        _validate_ready_results([{'status': 'INCOMPLETE'}, {'status': 'RENDERED'}])
        _validate_ready_probe({'format': {'duration': '300.1'}, 'streams': [
            {'codec_type': 'video', 'start_time': '0', 'duration': '300.1'},
            {'codec_type': 'audio', 'start_time': '0', 'duration': '300'},
        ]}, 300)


@unittest.skipUnless(os.environ.get('NEWSFLOW_READY_VOICE_MANIFEST'), 'owner-authorized local speech manifest required')
class ReadyVoiceMontage(unittest.TestCase):
    def test_two_five_minute_ready_voices(self):
        inputs = json.loads(Path(os.environ['NEWSFLOW_READY_VOICE_MANIFEST']).read_text(encoding='utf-8'))
        self.assertEqual(2, len(inputs), 'this acceptance requires exactly two ready voices')
        output = Path(os.environ['NEWSFLOW_READY_VOICE_OUTPUT']).resolve()
        output.mkdir(parents=True, exist_ok=True)
        sources = json.loads(Path(os.environ['NEWSFLOW_REAL_FOOTAGE_MANIFEST']).read_text(encoding='utf-8'))
        paths = [Path(row['path']).resolve() for row in sources]
        media_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        shutil.copytree(Path(os.environ['NEWSFLOW_REAL_MODEL_COPY']), app_data_root()/'models', dirs_exist_ok=True)
        index = ClipIndex(app_data_root()/'footage-index.sqlite3')
        roots = list(dict.fromkeys(str(path.parent) for path in paths))
        with patch.object(ai_index, 'discover_video_paths', return_value=paths):
            state = index.index_folders(roots)
        self.assertEqual(0, state.failed)
        index.enrich_semantic_tags()
        index.classify_english_screen_text()
        settings = Settings(footage_folders=roots, montage_project_folder=str(output/'projects'),
            montage_output_folder=str(output/'outputs'), montage_renderer='ffmpeg', montage_export_davinci_xml=False,
            montage_auto_web=False, montage_scene_planner='local', montage_intro_enabled=False,
            montage_overlay_enabled=False, montage_transition_style='cut', montage_transition_frames=0,
            montage_fast_reuse_enabled=True, montage_unique_footage_percent=50)
        jobs, titles, audio_hashes = [], [], {}
        for number, record in enumerate(inputs):
            original = Path(record['audio'])
            audio_hashes[str(original)] = hashlib.sha256(original.read_bytes()).hexdigest()
            voice = output/f'voice-{number+1}-300s.wav'
            subprocess.run([ffmpeg_executable(),'-v','error','-y','-i',str(original),'-t','300','-vn',
                            '-ac','1','-ar','48000','-c:a','pcm_s16le',str(voice)], capture_output=True,check=True)
            duration = float(subprocess.check_output([shutil.which('ffprobe'),'-v','error','-show_entries',
                'format=duration','-of','default=nw=1:nk=1',str(voice)],text=True))
            self.assertAlmostEqual(300,duration,delta=.05)
            old_map = json.loads(Path(record['map']).read_text(encoding='utf-8'))
            segments = []
            for segment in old_map['segments']:
                if float(segment['start']) >= duration:
                    break
                current = dict(segment)
                if float(current['end']) > duration:
                    ratio = (duration-float(current['start'])) / float(current['duration'])
                    words = current['text'].split()
                    current['text'] = ' '.join(words[:max(1,int(len(words)*ratio))])
                    current.update(end=duration,duration=duration-float(current['start']))
                segments.append(current)
            script = ' '.join(segment['text'].strip() for segment in segments)
            title = f'PR403 ready speech {number+1}'
            identity = f'test-pr403-ready-speech-{number+1}'
            context = VoiceMapContext(identity,number,title,script,voice,audio_duration=duration)
            payload = {**old_map,'productionItemId':identity,'scenarioIndex':number,'title':title,
                       'audioPath':str(voice),'audioDuration':duration,'scriptSha256':script_sha256(script),
                       'audioSha256':audio_sha256(voice),'segments':segments}
            # The saved maps are approximate. Keep their provenance, never
            # relabel proportional/cropped timing as measured word alignment.
            target = voice_map_path(context)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
            self.assertIn(inspect_voice_map(context).state,{'ready','approximate'})
            titles.append(title)
            jobs.append(Job(ScenarioRequest(number,title,'',identity),RunState.DONE,script,''))
            settings.voice_scenario_outputs[str(number+1)] = str(voice)
            settings.voice_task_statuses[str(number+1)] = {'durationSeconds':duration}
        save_settings(settings)
        save_session(titles,jobs)
        results = []
        for number,title in enumerate(titles):
            started=time.perf_counter()
            stage = 'prepare'
            try:
                profile=cProfile.Profile()
                try:
                    prepared=profile.runcall(bridge.prepare_montage,{'scenarioIndex':number})['preparedProject']
                finally:
                    profile.dump_stats(str(output/f'prepare-{number+1}.prof'))
                preparation=time.perf_counter()-started
                path=Path(prepared['path'])
                plan=TimelineProject.load(path)
                frozen=[(clip.path,clip.source_start,clip.duration) for clip in plan.clips]
                started=time.perf_counter()
                stage = 'render'
                profile=cProfile.Profile()
                try:
                    profile.runcall(bridge.render_montage,{'projectPath':str(path)})
                finally:
                    profile.dump_stats(str(output/f'render-{number+1}.prof'))
                elapsed=time.perf_counter()-started
                self.assertEqual(frozen,[(c.path,c.source_start,c.duration) for c in TimelineProject.load(path).clips])
                mp4=output/'outputs'/f'{title}.mp4'
                probe=json.loads(subprocess.check_output([shutil.which('ffprobe'),'-v','error',
                    '-show_streams','-show_format','-of','json',str(mp4)],text=True))
                endpoints = _validate_ready_probe(probe, duration)
                subprocess.run([ffmpeg_executable(),'-v','error','-i',str(mp4),'-f','null','-'],capture_output=True,check=True)
                rows=[]
                for position,clip in enumerate(plan.clips):
                    frame=output/f'video-{number+1}-scene-{position+1}.png'
                    moment=sum(c.duration for c in plan.clips[:position])+clip.duration/2
                    subprocess.run([ffmpeg_executable(),'-v','error','-y','-ss',str(min(moment,299.5)),
                        '-i',str(mp4),'-frames:v','1',str(frame)],capture_output=True,check=True)
                    self.assertTrue(frame.is_file())
                    rows.append({'time':moment,'text':clip.narration,'query':clip.visual_query_en,
                                 'source_id':next(r['id'] for r in sources if Path(r['path']).resolve()==Path(clip.path)),
                                 'source_start':clip.source_start,'duration':clip.duration,'level':clip.fallback_level,
                                 'frame':frame.name})
                results.append({'status':'RENDERED','output':mp4.name,'duration':300,'scenes':rows,
                                'preparation_seconds':preparation,'render_seconds':elapsed,
                                'timing':plan.voice_map_provenance,'metrics':plan.preparation_metrics_ms,
                                'stream_endpoints':endpoints})
            except (ValueError, RuntimeError) as error:
                if not _controlled_ready_shortage(error, stage, output/'projects'):
                    raise
                results.append({'status':'INCOMPLETE','reason':str(error),'elapsed':time.perf_counter()-started})
            (output/'manifest.json').write_text(json.dumps({'scope':'real owner speech trimmed to 300s test copies and real CLIP footage',
                'timing_limit':'source maps approximate; cropped last segment proportional; no measured speech alignment',
                'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
        self.assertEqual(audio_hashes,{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in audio_hashes})
        self.assertEqual(media_hashes,{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in media_hashes})
        _validate_ready_results(results)
        print('ready speech outcomes',[row['status'] for row in results])
