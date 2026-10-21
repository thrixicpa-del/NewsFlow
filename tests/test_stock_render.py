"""Synthetic technical acceptance through real stock preparation and rendering.

Provider discovery and CLIP/screen models are fake; media preparation, probing,
VoiceMap scene timing, source selection and FFmpeg rendering use production code.
This proves routing/audio/timing, not real-world visual relevance.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.config import Settings, app_data_root, save_settings
from scriptor.core import ScenarioRequest
from scriptor.footage import FootageItem
from scriptor.runner import Job, RunState
from scriptor.session import save_session
from scriptor.stock_sources import StockCandidate
from scriptor.timeline import (
    TimelineClip,
    TimelineProject,
    ffmpeg_executable,
    probe_media_duration,
    render_project,
)


class StockRenderTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1", "Use tests/run_isolated.py")
        outer = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.temporary = tempfile.TemporaryDirectory(prefix="stock-render-", dir=outer)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(outer))
        self.ffmpeg = ffmpeg_executable()
        self.ffprobe = shutil.which("ffprobe")
        self.assertTrue(self.ffprobe, "Technical acceptance requires real FFprobe")
        repository = Path(__file__).resolve().parents[1]
        evidence_parent = (repository / ".superpowers" / "stock-sources" / "render").resolve()
        self.evidence = evidence_parent / uuid.uuid4().hex
        self.assertTrue(self.evidence.resolve().is_relative_to(evidence_parent))
        self.assertTrue(evidence_parent.is_relative_to(repository))
        self.evidence.mkdir(parents=True)
        self.receipt = {"scope": "synthetic routing/audio/timing; fake provider and models",
                        "expected_cases": 6, "cases": []}
        self.addCleanup(self.write_receipt)

    def write_receipt(self):
        self.receipt["all_expected_passed"] = (
            len(self.receipt["cases"]) == self.receipt["expected_cases"]
            and all(case["status"] == "PASS" for case in self.receipt["cases"]))
        (self.evidence / "receipt.json").write_text(
            json.dumps(self.receipt, indent=2, ensure_ascii=False), encoding="utf-8")

    def run_media(self, command):
        result = subprocess.run(command, capture_output=True, timeout=120, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr[-4000:])
        return result.stdout

    def make_video(self, path, color, size='320x180'):
        self.run_media([
            self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
            f"color=c={color}:s={size}:r=30:d=4", "-f", "lavfi", "-i",
            "sine=frequency=880:sample_rate=48000:duration=4", "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ])

    def probe(self, path):
        return json.loads(self.run_media([
            self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
        ]))

    def pcm(self, path):
        raw = self.run_media([
            self.ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0", "-vn",
            "-ac", "1", "-ar", "48000", "-f", "f32le", "-",
        ])
        return np.frombuffer(raw, dtype="<f4")

    @staticmethod
    def magnitude(samples, frequency):
        window = np.hanning(len(samples))
        positions = np.arange(len(samples)) / 48000
        return float(abs(np.sum(samples * window * np.exp(-2j * np.pi * frequency * positions)))
                     / max(1, np.sum(window)))

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def exercise(self, mode, aspect, case):
        profile = self.root / f"{mode}-{aspect.replace(':', 'x')}"
        profile.mkdir()
        local, stock, voice = (profile / name for name in ("cargo-local.mp4", "cargo-stock.mp4", "voice.wav"))
        self.make_video(local, "red")
        # Keep the native HD gate enabled: the positive stock fixture must be
        # actual720p rather than a360p/180p source later upscaled by the renderer.
        self.make_video(stock, "blue", size='1280x720')
        self.run_media([self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=2", str(voice)])
        originals = {str(path): self.digest(path) for path in (local, stock, voice)}
        queries, scored = [], []
        trim = aspect == "9:16"
        scene = {"narration": "Грузовой поезд", "visual_query_en": "cargo train",
                 "duration": 2.0, "minimum_footage_duration": 2.0,
                 "voice_segment_id": 17, "voice_segment_ids": [17],
                 "narration_start": 0.0, "narration_end": 2.0}
        candidate = StockCandidate("pexels", "synthetic-1", "Cargo train",
            "https://videos.pexels.com/test.mp4", "https://www.pexels.com/video/1/",
            "Pexels License", "https://www.pexels.com/license/", "Synthetic test", local_path=stock)

        class Index:
            model_name = "synthetic-no-model"
            def __init__(self, *_args, **_kwargs):
                pass
            def count(self, *_args):
                return 1
            def screen_text_stats(self):
                return {"safe": 1, "blocked": 0, "unchecked": 0}
            def search_many(self, values, **_kwargs):
                score = .9 if mode == "local" else .01
                return [[SearchHit(FootageItem(str(local), "Cargo train"), score, 4.0)] for _ in values]
            def cached_media_duration(self, _path):
                return None  # Production native probe must inspect the actual file.
            def score_file(self, path, query):
                scored.append((Path(path), query))
                return .8

        class Service:
            def __init__(self, _root, *, enabled, **_kwargs):
                self.enabled = enabled
            def cached(self, *_args, **_kwargs):
                return []
            def search(self, query, *, kind="video", **_kwargs):
                queries.append(query)
                return [candidate] if kind == "video" else []
            def fetch(self, value):
                if value.provider not in self.enabled or mode == "local":
                    raise AssertionError("Unpermitted stock source")
                return stock

        with ExitStack() as contexts:
            contexts.enter_context(patch.dict(os.environ, {
                "NEWSFLOW_TEST_ROOT": str(profile), "LOCALAPPDATA": str(profile / "local-appdata"),
                "APPDATA": str(profile / "roaming"), "TEMP": str(profile), "TMP": str(profile),
                "NEWSFLOW_RENDER_TEMP_ROOT": str(profile / "render-work"),
            }))
            self.assertTrue(app_data_root().resolve().is_relative_to(profile))
            settings = Settings(montage_renderer="ffmpeg", montage_source_mode=mode,
                montage_aspect_ratio=aspect, montage_stock_sources=["pexels"], montage_stock_trim=trim,
                footage_folders=[str(profile)], voice_scenario_outputs={"1": str(voice)},
                montage_project_folder=str(profile / "projects"), montage_output_folder=str(profile / "outputs"),
                footage_download_folder=str(profile / "downloads"), montage_export_davinci_xml=False,
                montage_intro_enabled=False, montage_overlay_enabled=False)
            save_settings(settings)
            save_session(["Logistics"], [Job(ScenarioRequest(0, "Logistics", "", "synthetic-stock-render"),
                state=RunState.DONE, result=scene["narration"])])
            for context in (
                patch.object(bridge, "ClipIndex", Index), patch.object(bridge, "StockService", Service),
                patch.object(bridge, "_ensure_voice_map_for_scenario", return_value=SimpleNamespace(state="ready")),
                patch.object(bridge, "_voice_map_scenes", return_value=(
                    [copy.deepcopy(scene)], {"productionItemId": "synthetic-stock-render", "audioDuration": 2.0})),
                patch.object(bridge, "_montage_screen_text_safe", return_value=True),
            ):
                contexts.enter_context(context)
            prepared = bridge.prepare_montage({"scenarioIndex": 0})
            project_path = Path(prepared["preparedProject"]["path"])
            self.assertTrue(project_path.resolve().is_relative_to(profile))
            project = TimelineProject.load(project_path)
            self.assertFalse(project.manual_replacements)
            self.assertEqual(project.source_policy["mode"], mode)
            self.assertEqual(len(project.clips), 1)
            clip = project.clips[0]
            self.assertEqual(clip.voice_segment_ids, [17])
            self.assertEqual((clip.narration_start, clip.narration_end, clip.duration), (0.0, 2.0, 2.0))
            if mode == "local":
                self.assertEqual(Path(clip.path), local)
                self.assertFalse(queries)
                self.assertFalse(scored)
            else:
                self.assertTrue(queries)
                self.assertTrue(scored)
                for checked, query in scored:
                    self.assertNotEqual(checked, stock)
                    self.assertAlmostEqual(probe_media_duration(checked), 2.0, delta=.04)
                    self.assertEqual(query, "cargo train")
                if trim:
                    self.assertNotEqual(Path(clip.path), stock)
                    self.assertEqual([s["codec_type"] for s in self.probe(Path(clip.path))["streams"]], ["video"])
                    self.assertAlmostEqual(probe_media_duration(Path(clip.path)), 2.0, delta=.04)
                else:
                    self.assertEqual(Path(clip.path), stock)
                    self.assertAlmostEqual(probe_media_duration(Path(clip.path)), 4.0, delta=.04)
            output = profile / "outputs" / "acceptance.mp4"
            render_project(project, output, renderer="ffmpeg")
            metadata = self.probe(output)
            video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
            audio = next(stream for stream in metadata["streams"] if stream["codec_type"] == "audio")
            dimensions = (1920, 1080) if aspect == "16:9" else (1080, 1920)
            self.assertEqual((video["width"], video["height"]), dimensions)
            self.assertEqual(video["avg_frame_rate"], "30/1")
            self.assertAlmostEqual(float(audio["duration"]), 2.0, delta=.05)
            self.assertAlmostEqual(float(metadata["format"]["duration"]), 2.0, delta=.1)
            pcm = self.pcm(output)
            self.assertGreaterEqual(len(pcm) / 48000, 1.99)
            middle = pcm[12000:84000]
            voice_level = self.magnitude(middle, 440)
            stock_level = self.magnitude(middle, 880)
            self.assertGreater(voice_level, .025)
            self.assertLess(stock_level, voice_level * .02, "Original stock audio leaked into output")
            self.assertGreater(self.magnitude(pcm[int(1.85 * 48000):int(1.98 * 48000)], 440), .025,
                               "Final narration tone was cropped")
            original_tone = self.pcm(stock)
            self.assertGreater(self.magnitude(original_tone[12000:84000], 880), .025,
                               "Contamination fixture must contain audible stock audio")
            rgb = self.run_media([self.ffmpeg, "-v", "error", "-ss", "1", "-i", str(output),
                "-frames:v", "1", "-vf", "scale=16:16", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
            red, blue = sum(rgb[0::3]), sum(rgb[2::3])
            self.assertGreater(red if mode == "local" else blue, (blue if mode == "local" else red) * 4)
            self.assertEqual({str(path): self.digest(path) for path in (local, stock, voice)}, originals)
            exported = self.evidence / f"{mode}-{aspect.replace(':', 'x')}-trim-{str(trim).lower()}.mp4"
            self.assertTrue(output.resolve().is_relative_to(profile))
            shutil.copyfile(output, exported)
            case.update(status="PASS", output=exported.name, sha256=self.digest(exported),
                trim=trim, dimensions=list(dimensions), audio_duration=float(audio["duration"]),
                voice_440_magnitude=voice_level, stock_880_magnitude=stock_level,
                originals_sha256=originals, selected_source="local" if mode == "local" else "stock",
                checked_windows=len(scored))

    def test_six_mode_and_aspect_renders_preserve_voice_and_mute_stock(self):
        for mode in ("local", "hybrid", "stock"):
            for aspect in ("16:9", "9:16"):
                case = {"mode": mode, "aspect": aspect, "status": "NOT_COMPLETED"}
                self.receipt["cases"].append(case)
                with self.subTest(mode=mode, aspect=aspect):
                    self.exercise(mode, aspect, case)

    def test_fractional_scene_boundaries_preserve_final_voice(self):
        """Five non-frame-aligned beats must not accumulate a cropped voice tail."""
        durations = [1.113, 1.601, 1.223, 1.4, 1.8]
        voice = self.root / "fractional-voice.wav"
        self.run_media([self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
            "sine=frequency=440:sample_rate=48000:duration=7.137", str(voice)])
        clips, cursor = [], 0.0
        for index, (length, color) in enumerate(zip(durations, ["red", "blue", "green", "yellow", "purple"])):
            source = self.root / f"stock-{index}.mp4"
            self.make_video(source, color)
            clips.append(TimelineClip(str(source), f"Beat {index}", "synthetic stock", duration=length,
                source="wikimedia", source_family=self.digest(source), voice_segment_ids=[index],
                narration_start=cursor, narration_end=cursor + length))
            cursor += length
        project = TimelineProject("Fractional stock beats", clips=clips, voiceover_path=str(voice),
            source_policy={"mode": "stock", "uniquePercent": 100, "trim": False})
        saved = self.root / "fractional.json"
        project.save(saved)
        loaded = TimelineProject.load(saved)
        self.assertEqual([(c.voice_segment_ids, c.narration_start, c.narration_end, c.duration) for c in loaded.clips],
                         [(c.voice_segment_ids, c.narration_start, c.narration_end, c.duration) for c in clips])
        self.assertEqual(len({c.source_family for c in loaded.clips}), 5)
        output = self.evidence / "fractional-five-beats.mp4"
        render_project(loaded, output, renderer="ffmpeg")
        metadata = self.probe(output)
        audio = next(s for s in metadata["streams"] if s["codec_type"] == "audio")
        self.assertAlmostEqual(float(audio["duration"]), 7.137, delta=1/30)
        self.assertAlmostEqual(float(metadata["format"]["duration"]), 7.137, delta=1/30)
        samples = self.pcm(output)
        self.assertGreaterEqual(len(samples)/48000, 7.13)
        self.assertGreater(self.magnitude(samples[int(7.08*48000):int(7.13*48000)], 440), .025)
        self.assertLess(self.magnitude(samples[12000:84000], 880), .001)
        self.receipt.update(scope="synthetic fractional scene timing", expected_cases=1,
            cases=[{"status": "PASS", "output": output.name, "sha256": self.digest(output),
                    "scene_durations": durations, "audio_duration": float(audio["duration"])}])

    def test_mp3_narration_keeps_video_through_terminal_hold(self):
        """AAC/MP3 packet timing must not remove the final video frames."""
        from scriptor.stock_media import prepare_continuity_media
        voice = self.root / 'three-second-voice.mp3'
        self.run_media([self.ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=3', '-c:a', 'libmp3lame', str(voice)])
        source = prepare_continuity_media(None, self.root / 'hold', duration=3.05)
        project = TimelineProject('MP3 terminal hold', clips=[TimelineClip(str(source), 'Voice', 'Q',
            duration=3.05, continuity={'mode': 'background'})], voiceover_path=str(voice))
        output = self.evidence / 'mp3-terminal-hold.mp4'
        render_project(project, output, renderer='ffmpeg')
        metadata = self.probe(output)
        video = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
        self.assertGreaterEqual(int(video['nb_frames']), 90)
        self.assertEqual(int(video['nb_frames']), int(np.ceil(probe_media_duration(voice) * 30 - 1e-9)))
        self.assertGreaterEqual(float(video['duration']), 3.0)
        self.assertGreaterEqual(len(self.pcm(output)), 3 * 48000)
        frames = json.loads(self.run_media([self.ffprobe, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(output)]))['frames']
        timestamps = np.asarray([float(frame['best_effort_timestamp_time']) for frame in frames])
        self.assertLess(float(np.max(np.abs(np.diff(timestamps) - 1 / 30))), .000002)

    def test_gpu_voice_mux_preserves_explicit_limit_with_and_without_intro(self):
        from scriptor import timeline as timeline_module
        source, voice, intro = (self.root / name for name in ('source.mp4', 'voice.mp3', 'intro.mp4'))
        for path in (source, voice, intro):
            path.write_bytes(b'isolated command contract fixture')
        for with_intro in (False, True):
            with self.subTest(with_intro=with_intro):
                commands = []
                def run(command, captured=commands, **_kwargs):
                    captured.append(command)
                    Path(command[-1]).write_bytes(b'x' * 2048)
                project = TimelineProject('GPU mux', clips=[TimelineClip(str(source), 'N', 'Q', duration=3.05,
                    continuity={'mode': 'background'})],
                    voiceover_path=str(voice), intro_path=str(intro) if with_intro else '',
                    intro_duration=1 if with_intro else 0)
                with patch.object(timeline_module, '_run', side_effect=run), \
                     patch.object(timeline_module, 'probe_media_duration',
                                  side_effect=lambda path: 3.05 if Path(path) == voice else 10), \
                     patch.object(timeline_module, 'probe_video_duration', return_value=10), \
                     patch.object(timeline_module, 'gpu_timeline_encoder_args', return_value=['-c:v', 'h264_nvenc']), \
                     patch.object(timeline_module, 'render_workspace_root', return_value=self.root):
                    timeline_module._render_project_gpu_timeline(project, self.root / f'gpu-{with_intro}.mp4')
                mux = commands[-1]
                self.assertNotIn('-shortest', mux)
                self.assertEqual(float(mux[mux.index('-t') + 1]), 4.05 if with_intro else 3.05)
                self.assertEqual(int(mux[mux.index('-frames:v') + 1]), 122 if with_intro else 92)
                self.assertIn('[audio]' if with_intro else '1:a:0', mux)

    def test_normal_continuity_mux_retries_failed_nvenc_once_with_cpu(self):
        from scriptor import timeline as timeline_module
        from scriptor.media_health import MediaHealth
        source, voice = (self.root / name for name in ('source.mp4', 'voice.mp3'))
        source.write_bytes(b'isolated video fixture')
        voice.write_bytes(b'isolated voice fixture')
        mux_commands = []
        def run(command, **_kwargs):
            if '1:a:0' in command:
                mux_commands.append(command)
                if 'h264_nvenc' in command:
                    raise RuntimeError('NVENC session limit reached')
            Path(command[-1]).write_bytes(b'x' * 2048)
        project = TimelineProject('CPU retry', clips=[TimelineClip(str(source), 'N', 'Q', duration=3.05,
            continuity={'mode': 'background'})], voiceover_path=str(voice))
        # 3.05 seconds occupies 92 frames at 30fps; use the real health
        # contract and the exact frame budget, without the old .15s padding.
        health = SimpleNamespace(check=lambda _path: MediaHealth('valid', duration=92 / 30))
        with patch.object(timeline_module, '_run', side_effect=run), \
             patch.object(timeline_module, 'ffmpeg_executable', return_value='ffmpeg'), \
             patch.object(timeline_module, 'gpu_timeline_capability', return_value={'available': True}), \
             patch.object(timeline_module, 'video_encoder_args', return_value=[
                 '-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '20', '-b:v', '0']), \
             patch.object(timeline_module, 'render_source_for_proxy', side_effect=lambda path, *_args: path), \
             patch.object(timeline_module, 'probe_video_duration', return_value=10), \
             patch.object(timeline_module, 'probe_media_duration',
                          side_effect=lambda path: 3.05 if Path(path) == voice else 10), \
             patch.object(timeline_module, 'default_health_store', return_value=health), \
             patch.object(timeline_module, 'proxy_cache_root', return_value=self.root / 'proxies'), \
             patch.object(timeline_module, 'render_workspace_root', return_value=self.root), \
             patch.dict(timeline_module._ENCODER_CACHE, {}, clear=True):
            render_project(project, self.root / 'retry.mp4', renderer='ffmpeg')
            self.assertIn('libx264', timeline_module._ENCODER_CACHE['ffmpeg'])
        self.assertEqual(len(mux_commands), 2)
        self.assertIn('h264_nvenc', mux_commands[0])
        self.assertIn('libx264', mux_commands[1])
        self.assertNotIn('h264_nvenc', mux_commands[1])
        self.assertEqual(mux_commands[1][mux_commands[1].index('-fps_mode') + 1], 'cfr')

    def test_mixed_stream_parameters_keep_continuous_cfr_through_holds(self):
        from scriptor.stock_media import prepare_continuity_media
        voice, moving = self.root / 'mixed-voice.mp3', self.root / 'bt709.mp4'
        self.run_media([self.ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=30', '-c:a', 'libmp3lame', str(voice)])
        self.run_media([self.ffmpeg, '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'color=c=blue:s=640x360:r=30:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709', str(moving)])
        hold = prepare_continuity_media(None, self.root / 'mixed-hold', duration=6.05)
        clips = [TimelineClip(str(hold if i % 2 == 0 else moving), str(i), 'Q',
            duration=6.05 if i == 4 else 6.0,
            continuity={'mode': 'background'} if i % 2 == 0 else {}) for i in range(5)]
        project = TimelineProject('Mixed parameters', clips=clips, voiceover_path=str(voice))
        output = self.evidence / 'mixed-parameters.mp4'
        render_project(project, output, renderer='ffmpeg')
        video = next(stream for stream in self.probe(output)['streams'] if stream['codec_type'] == 'video')
        self.assertEqual(video['avg_frame_rate'], '30/1')
        frames = json.loads(self.run_media([self.ffprobe, '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(output)]))['frames']
        timestamps = np.asarray([float(frame['best_effort_timestamp_time']) for frame in frames])
        self.assertEqual(len(timestamps), int(np.ceil(probe_media_duration(voice) * 30 - 1e-9)))
        self.assertLess(float(np.max(np.abs(np.diff(timestamps) - 1 / 30))), .000002)
        self.assertGreaterEqual(len(self.pcm(output)), 30 * 48000)
        boundaries = self.run_media([self.ffmpeg, '-v', 'error', '-i', str(output), '-an',
            '-vf', "select='eq(n,179)+eq(n,180)+eq(n,359)+eq(n,360)+eq(n,539)+eq(n,540)+eq(n,719)+eq(n,720)',scale=1:1",
            '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
        self.assertEqual(len(boundaries), 8 * 3)
        self.assertEqual([boundaries[i + 2] > 150 for i in range(0, len(boundaries), 3)],
                         [False, True, True, False, False, True, True, False])


if __name__ == "__main__":
    unittest.main()
