import subprocess
import tempfile
import unittest
from pathlib import Path

from scriptor.timeline import (
    TimelineClip,
    TimelineProject,
    ffmpeg_executable,
    probe_media_duration,
    render_project,
)


class FastReuseRenderTests(unittest.TestCase):
    """A real FFmpeg render, not a mocked montage-plan check.

    The clips deliberately reuse two source files in alternating speech scenes.
    This verifies that the quick montage mode can render a complete 30 FPS MP4
    with narration, rather than ending on a frozen final frame.
    """

    def _run(self, *args: str) -> None:
        subprocess.run([ffmpeg_executable(), "-y", *args], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _probe(self, output: Path) -> str:
        result = subprocess.run(
            [ffmpeg_executable(), "-hide_banner", "-i", str(output)],
            capture_output=True, text=True,
        )
        return result.stderr

    def test_short_source_proxy_uses_the_loop_aware_cache_generation(self):
        """A proxy made before short-source looping must never mask the new render behavior."""
        timeline = (Path(__file__).resolve().parents[1] / "scriptor" / "timeline.py").read_text(encoding="utf-8")

        self.assertIn("proxy-v3-loop-short-source", timeline)

    def test_rotated_sources_render_as_complete_thirty_fps_video(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-fast-reuse-") as temporary:
            root = Path(temporary)
            clip_a = root / "battlefield-a.mp4"
            clip_b = root / "battlefield-b.mp4"
            voice = root / "voice.wav"
            output = root / "result.mp4"
            self._run("-f", "lavfi", "-i", "color=c=red:s=320x180:r=30:d=4", "-an", "-c:v", "libx264", str(clip_a))
            self._run("-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=4", "-an", "-c:v", "libx264", str(clip_b))
            self._run("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=12", "-c:a", "pcm_s16le", str(voice))
            project = TimelineProject(
                title="Smoke: quick rotating montage",
                voiceover_path=str(voice),
                clips=[
                    TimelineClip(str(clip_a), "scene 1", "battlefield", duration=2.0),
                    TimelineClip(str(clip_b), "scene 2", "battlefield", duration=2.0),
                    TimelineClip(str(clip_a), "scene 3", "battlefield", duration=2.0),
                    TimelineClip(str(clip_b), "scene 4", "battlefield", duration=2.0),
                    TimelineClip(str(clip_a), "scene 5", "battlefield", duration=2.0),
                    TimelineClip(str(clip_b), "scene 6", "battlefield", duration=2.0),
                ],
            )
            render_project(project, output, renderer="ffmpeg")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 10_000)
            probe = self._probe(output)
            self.assertIn("30 fps", probe)
            self.assertIn("Audio:", probe)
            self.assertAlmostEqual(probe_media_duration(output), 12.0, delta=0.2)

    def test_short_source_is_looped_as_motion_not_a_frozen_voice_tail(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-short-source-") as temporary:
            root = Path(temporary)
            source = root / "short-moving-source.mp4"
            voice = root / "voice.wav"
            output = root / "result.mp4"
            self._run("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=1", "-an", "-c:v", "libx264", str(source))
            self._run("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000:duration=4", "-c:a", "pcm_s16le", str(voice))
            project = TimelineProject(
                title="Smoke: short source",
                voiceover_path=str(voice),
                clips=[TimelineClip(str(source), "one long narration beat", "test pattern", duration=4.0)],
            )
            render_project(project, output, renderer="ffmpeg")
            self.assertTrue(output.is_file())
            self.assertIn("30 fps", self._probe(output))
            self.assertAlmostEqual(probe_media_duration(output), 4.0, delta=0.2)
