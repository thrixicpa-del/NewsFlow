"""Synthetic FAST NEWS MONTAGE baseline; it never reads production media."""

from __future__ import annotations

import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import timeline
from scriptor.timeline import TimelineClip, TimelineProject, ffmpeg_executable, probe_video_duration, render_project


class FastNewsMontageBenchmarkTests(unittest.TestCase):
    def test_default_renderer_uses_current_fast_news_ffmpeg_path(self):
        """An unparameterized current render must not fall back to Remotion."""
        with tempfile.TemporaryDirectory(prefix="newsflow-fast-news-default-") as temporary:
            root = Path(temporary)
            ffmpeg = ffmpeg_executable()
            source = root / "source.mp4"
            made = subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=green:s=320x180:r=30:d=1",
                 "-an", "-c:v", "libx264", str(source)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(made.returncode, 0, made.stderr[-1000:])

            output = root / "fast-news-default.mp4"
            workspace, proxy = root / "work", root / "proxy"
            workspace.mkdir()
            proxy.mkdir()
            project = TimelineProject(
                title="FAST NEWS default route",
                clips=[TimelineClip(str(source), "scene", "test", duration=1.0)],
            )
            with patch.object(timeline, "render_workspace_root", return_value=workspace), \
                 patch.object(timeline, "proxy_cache_root", return_value=proxy), \
                 patch.object(timeline, "_remotion_runner", side_effect=AssertionError("legacy compositor route")):
                render_project(project, output)

            self.assertTrue(output.is_file())
            self.assertGreater(probe_video_duration(output), 0.8)

    def test_ffmpeg_fast_news_fixture_is_valid_and_within_tolerance(self):
        """A small direct montage catches accidental slow-renderer regressions."""
        with tempfile.TemporaryDirectory(prefix="newsflow-fast-news-benchmark-") as temporary:
            root = Path(temporary)
            ffmpeg = ffmpeg_executable()
            source = root / "source.mp4"
            voice = root / "voice.wav"
            for command in (
                [ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=3", "-an", "-c:v", "libx264", str(source)],
                [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", str(voice)],
            ):
                made = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
                self.assertEqual(made.returncode, 0, made.stderr[-1000:])

            project = TimelineProject(
                title="FAST NEWS synthetic",
                voiceover_path=str(voice),
                clips=[
                    TimelineClip(str(source), "scene one", "test", duration=1.5),
                    TimelineClip(str(source), "scene two", "test", duration=1.5, source_start=1.5),
                ],
            )
            output = root / "fast-news.mp4"
            workspace, proxy = root / "work", root / "proxy"
            workspace.mkdir()
            proxy.mkdir()
            started = time.monotonic()
            with patch.object(timeline, "render_workspace_root", return_value=workspace), \
                 patch.object(timeline, "proxy_cache_root", return_value=proxy):
                render_project(project, output, renderer="ffmpeg")
            elapsed = time.monotonic() - started

            self.assertTrue(output.is_file())
            self.assertGreater(probe_video_duration(output), 2.8)
            # This is intentionally generous for shared CI disks; it detects
            # an accidental switch to the browser compositor, not CPU speed.
            self.assertLess(elapsed, 20.0, f"FAST NEWS synthetic render took {elapsed:.2f}s")
