"""Decoded GPU-path timing regressions with synthetic media and a CPU encoder.

Only the unavailable NVENC encoder is substituted. The actual GPU input trims,
filtergraph, chunks, concat and narration mux run through FFmpeg unchanged.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import imageio_ffmpeg
import numpy as np

from scriptor import timeline


class GpuTimelineTimingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1", "use tests/run_isolated.py")
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ffmpeg = timeline.ffmpeg_executable()
        self.ffprobe = shutil.which("ffprobe")
        self.assertTrue(self.ffprobe, "ffprobe is required for the decoded-frame gate")
        encoder = patch.object(timeline, "gpu_timeline_encoder_args", return_value=[
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
            "-bf", "2", "-threads", "2", "-s", "160x90",
        ])
        encoder.start()
        self.addCleanup(encoder.stop)

    def run_media(self, *arguments):
        result = subprocess.run(arguments, capture_output=True, check=False, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-3000:])
        return result.stdout

    def source(self, name, color, *, marker_at=None):
        source = self.root / f"{name}.mp4"
        graph = f"color={color}:s=160x90:r=30:d=2"
        if marker_at is not None:
            graph += f",drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='gte(t,{marker_at})'"
        self.run_media(self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", graph,
                       "-an", "-c:v", "libx264", "-preset", "ultrafast", str(source))
        return source

    def frames(self, output):
        metadata = json.loads(self.run_media(self.ffprobe, "-v", "error", "-select_streams", "v:0",
                                            "-show_frames", "-of", "json", str(output)))
        raw = self.run_media(self.ffmpeg, "-v", "error", "-i", str(output),
                             "-f", "rawvideo", "-pix_fmt", "rgb24", "-")
        frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 90, 160, 3)
        self.assertEqual(len(frames), len(metadata["frames"]))
        for index, frame in enumerate(metadata["frames"]):
            self.assertAlmostEqual(float(frame["best_effort_timestamp_time"]), index / 30, delta=.00001)
        return frames

    def assert_color(self, frames, number, channel):
        mean = frames[number, 20:70, 40:120].mean(axis=(0, 1))
        self.assertEqual(int(mean.argmax()), channel, f"wrong source at frame {number}: {mean}")

    def test_each_scene_stops_at_its_verified_window_with_zoom_on_or_off(self):
        source = self.source("bounded-red", "red", marker_at=1)
        clips = [timeline.TimelineClip(str(source), "verified red", "", 1.0) for _ in range(3)]
        for zoom in (False, True):
            with self.subTest(zoom=zoom):
                output = self.root / f"bounded-{zoom}.mp4"
                command = timeline._gpu_timeline_chunk_command(
                    self.ffmpeg, clips, output, self.root / f"bounded-{zoom}.ffscript", 160, 90,
                    local_video_zoom=zoom,
                )
                self.run_media(*command)
                frames = self.frames(output)
                self.assertEqual(len(frames), 90)
                self.assertTrue(np.all(frames[:, 45, 80, 0].astype(int) > frames[:, 45, 80, 2].astype(int) + 100),
                                "GPU rendering borrowed unverified blue frames after source time 1.0")

    def test_fractional_scenes_share_the_same_frame_grid_across_chunks(self):
        red, green, blue = [self.source(color, color) for color in ("red", "lime", "blue")]
        clips = [timeline.TimelineClip(str(path), "", "", .45, source_start=.5)
                 for path in (red, green, blue, red)]
        for chunk_size in (1, 3):
            with self.subTest(chunk_size=chunk_size):
                project = timeline.TimelineProject("fractional cuts", clips=clips)
                output = self.root / f"fractional-{chunk_size}.mp4"
                timeline._render_project_gpu_timeline(project, output, chunk_size=chunk_size)
                frames = self.frames(output)
                self.assertEqual(len(frames), 54)
                for number, channel in [(13, 0), (14, 1), (26, 1), (27, 2), (40, 2), (41, 0), (53, 0)]:
                    self.assert_color(frames, number, channel)

    def test_narrated_tail_keeps_its_verified_window_and_full_audio(self):
        source = self.source("tail-red", "red", marker_at=1)
        voice = self.root / "voice.wav"
        self.run_media(self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                       "sine=frequency=440:sample_rate=48000:duration=1", str(voice))
        clip = timeline.TimelineClip(str(source), "verified red", "", 1.0)
        project = timeline.TimelineProject("voice tail", clips=[clip], voiceover_path=str(voice))
        self.assertEqual(timeline._gpu_timeline_render_clips(project)[0].duration, 1.0)
        output = self.root / "voice.mp4"
        timeline._render_project_gpu_timeline(project, output)
        frames = self.frames(output)
        self.assertEqual(len(frames), 30)
        self.assert_color(frames, 29, 0)
        raw = self.run_media(self.ffmpeg, "-v", "error", "-i", str(output), "-map", "0:a:0",
                             "-ac", "1", "-ar", "48000", "-f", "f32le", "-")
        audio = np.frombuffer(raw, dtype="<f4")
        self.assertGreaterEqual(len(audio), 48000)
        self.assertGreater(float(np.sqrt(np.mean(audio[47000:47900] ** 2))), .04)


class BundledFfmpegGpuTimelineTimingTests(GpuTimelineTimingTests):
    """Exercise the locked FFmpeg runtime as well as the production resolver.

    System FFmpeg 6 can preserve concat timing that FFmpeg 7 changes unless the
    output frame rate is explicit. Keep the same decoded-frame/audio assertions.
    """

    def setUp(self):
        with patch.dict(os.environ, {"IMAGEIO_FFMPEG_EXE": ""}):
            bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        package = Path(imageio_ffmpeg.__file__).resolve().parent
        self.assertTrue(Path(bundled_ffmpeg).resolve().is_relative_to(package),
                        "the locked imageio-ffmpeg bundled runtime is required")
        executable = patch.object(timeline, "ffmpeg_executable", return_value=bundled_ffmpeg)
        executable.start()
        self.addCleanup(executable.stop)
        super().setUp()


class RemotionTimingContractTests(unittest.TestCase):
    def test_fractional_scenes_share_the_ffmpeg_cumulative_frame_grid(self):
        project = timeline.TimelineProject("fractional", clips=[
            timeline.TimelineClip(f"scene-{index}.mp4", "", "", .45) for index in range(4)
        ])
        payload = timeline.remotion_payload(project)
        self.assertEqual(payload["durationInFrames"], 54)
        self.assertEqual([row["from"] for row in payload["sequences"]], [0, 14, 27, 41])
        self.assertEqual([row["durationInFrames"] for row in payload["sequences"]], [14, 13, 14, 13])


if __name__ == "__main__":
    unittest.main()
