"""Real decoded-frame timing regressions; synthetic media proves no semantics.

Run with tests/run_isolated.py. Encoder size/preset are reduced for test cost;
the real input trims, FPS filter, cache, concat, and audio mux remain active.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor import timeline


class FootageQualityTimingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1", "use tests/run_isolated.py")
        self.assertTrue(os.environ.get("NEWSFLOW_TEST_ROOT"), "disposable test storage is required")
        self.temporary = tempfile.TemporaryDirectory(prefix="newsflow-timing-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ffmpeg = timeline.ffmpeg_executable()
        self.ffprobe = shutil.which("ffprobe")
        if not self.ffprobe:
            self.fail("ffprobe is required for the rendered timing gate")
        encoder = patch.object(timeline, "video_encoder_args", return_value=[
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-bf", "2", "-threads", "2", "-s", "160x90",
        ])
        encoder.start()
        self.addCleanup(encoder.stop)
        cache = patch.object(timeline, "proxy_cache_root", return_value=self.root / "proxies")
        cache.start()
        self.addCleanup(cache.stop)

    def run_media(self, *arguments):
        result = subprocess.run(arguments, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-2000:])
        return result.stdout

    def source(self, name, color, duration=7, marker_at=None, marker_color="blue"):
        path = self.root / f"{name}.mp4"
        # A moving test pattern in the corner makes frozen output detectable;
        # the central field identifies the source independently of compression.
        graph = "[0:v][1:v]overlay=x=0:y=0:shortest=1"
        if marker_at is not None:
            graph += f",drawbox=x=40:y=0:w=280:h=180:color={marker_color}:t=fill:enable='gte(t,{marker_at})'"
        self.run_media(self.ffmpeg, "-y", "-f", "lavfi", "-i",
                       f"color=c={color}:s=320x180:r=30:d={duration}",
                       "-f", "lavfi", "-i", f"testsrc2=s=40x40:r=30:d={duration}",
                       "-filter_complex", graph, "-an", "-c:v", "libx264",
                       "-preset", "ultrafast", str(path))
        return path

    def render(self, clips, voice_duration=None):
        voice = ""
        if voice_duration is not None:
            voice = str(self.root / "voice.wav")
            self.run_media(self.ffmpeg, "-y", "-f", "lavfi", "-i",
                           f"sine=frequency=440:sample_rate=48000:duration={voice_duration}", voice)
        project = timeline.TimelineProject("timing", clips=clips, voiceover_path=voice,
                                            transition_style="cut", transition_frames=0)
        output = self.root / "output.mp4"
        timeline.render_project(project, output, renderer="ffmpeg")
        probe = json.loads(self.run_media(self.ffprobe, "-v", "error", "-select_streams", "v:0",
                                         "-show_frames", "-show_streams", "-of", "json", str(output)))
        raw = self.run_media(self.ffmpeg, "-v", "error", "-i", str(output),
                             "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
        frames = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160, 3)
        pts = [float(frame["best_effort_timestamp_time"]) for frame in probe["frames"]]
        self.assertEqual(len(frames), len(pts))
        for number, timestamp in enumerate(pts):
            self.assertAlmostEqual(timestamp, number / 30, delta=0.00001)
        return output, frames, pts

    def assert_color(self, frame, channel, message):
        rgb = frame[40:80, 60:140].mean(axis=(0, 1))
        self.assertEqual(int(rgb.argmax()), channel, f"{message}: central RGB={rgb}")

    def test_six_second_cuts_have_no_cumulative_extra_frames_and_keep_fractional_audio_tail(self):
        red = self.source("red", "red", marker_at=6.5)
        green = self.source("green", "lime", marker_at=6.5)
        blue = self.source("blue", "blue", duration=2)
        output, frames, pts = self.render([
            timeline.TimelineClip(str(red), "one", "red", 6, source_start=.5),
            timeline.TimelineClip(str(green), "two", "green", 6, source_start=.5),
            timeline.TimelineClip(str(blue), "tail", "blue", .47, source_start=.5),
        ], voice_duration=12.47)
        for number, channel in [(179, 0), (180, 1), (359, 1), (360, 2), (374, 2)]:
            self.assert_color(frames[number], channel, f"wrong source at PTS {pts[number]:.6f}")
        self.assertEqual(len(frames), 375)
        streams = json.loads(self.run_media(self.ffprobe, "-v", "error", "-show_streams",
                                           "-of", "json", str(output)))["streams"]
        audio = next(stream for stream in streams if stream["codec_type"] == "audio")
        self.assertAlmostEqual(float(audio["start_time"]), 0, delta=.001)
        self.assertAlmostEqual(float(audio["duration"]), 12.47, delta=.022)
        self.assertGreaterEqual(pts[-1] + 1 / 30, 12.47)
        self.assertGreater(np.abs(frames[-1, :20, :20].astype(float)
                                  - frames[-2, :20, :20].astype(float)).mean(), .2)

    def test_fractional_cuts_share_one_frame_grid_even_when_reusing_one_proxy_source(self):
        red = self.source("red", "red", duration=2)
        green = self.source("green", "lime", duration=2)
        _, frames, pts = self.render([
            timeline.TimelineClip(str(red), "one", "red", .45, source_start=.5),
            timeline.TimelineClip(str(green), "two", "green", .45, source_start=.5),
            timeline.TimelineClip(str(red), "three", "red", .45, source_start=.5),
            timeline.TimelineClip(str(red), "four", "red", .45, source_start=.5),
        ])
        self.assertEqual(len(frames), 54)
        for number, channel in [(13, 0), (14, 1), (26, 1), (27, 0), (40, 0), (41, 0), (53, 0)]:
            self.assert_color(frames[number], channel, f"wrong fractional cut at {pts[number]:.6f}")

    def test_renderer_never_borrows_unverified_frames_after_selected_source_window(self):
        source = self.source("window", "red", duration=2, marker_at=.53)
        _, frames, _ = self.render([
            timeline.TimelineClip(str(source), "verified red window", "red", .03, source_start=.5),
        ], voice_duration=.03)
        self.assertEqual(len(frames), 1)
        for number, frame in enumerate(frames):
            self.assert_color(frame, 0, f"frame {number} escaped source interval [.5, .53)")
        # Inspect the real cached proxy too: a final -shortest mux can hide
        # unverified source overread, but that proxy is reused on other cuts.
        proxy = next((self.root / "proxies").glob("*.mp4"))
        raw = self.run_media(self.ffmpeg, "-v", "error", "-i", str(proxy),
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
        proxy_frames = np.frombuffer(raw, np.uint8).reshape(-1, 90, 160, 3)
        for number, frame in enumerate(proxy_frames):
            self.assert_color(frame, 0, f"cached frame {number} escaped source interval [.5, .53)")
        self.assertEqual(len(proxy_frames), 1)
        # Decode all audio too, so a valid video-only file cannot satisfy this gate.
        audio = self.run_media(self.ffmpeg, "-v", "error", "-i", str(self.root / "output.mp4"),
                               "-map", "0:a:0", "-f", "f32le", "-")
        self.assertGreater(len(audio), 0)

    def test_short_prewarmed_proxy_never_loops_before_selected_source_start(self):
        source = self.source("source-eof", "blue", duration=2, marker_at=.5, marker_color="red")
        # The source before .5 is an explicit negative. An old prewarm can be
        # one frame short and activate whole-file looping at its EOF.
        proxy, _ = timeline.warm_source_proxy(source, 1920, 1080)
        # Persist the actual old-cache condition explicitly so the regression
        # also runs on FFmpeg versions whose warm encoder retains all frames.
        self.run_media(self.ffmpeg, "-y", "-i", str(source), "-vf", "fps=30,trim=end_frame=59",
                       "-frames:v", "59", "-an", "-c:v", "libx264", "-preset", "ultrafast", str(proxy))
        _, frames, _ = self.render([
            timeline.TimelineClip(str(source), "verified red EOF window", "red", 1.5, source_start=.5),
        ])
        self.assertEqual(len(frames), 45)
        for number, frame in enumerate(frames):
            self.assert_color(frame, 0, f"frame {number} escaped verified source interval [.5, 2)")
