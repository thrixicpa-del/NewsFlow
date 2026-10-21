import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor.cutter import build_cut_command, cut_single_clip, cut_sources


class CutterTests(unittest.TestCase):
    @patch("scriptor.cutter.ffmpeg_executable", return_value="ffmpeg.exe")
    @patch("scriptor.cutter.subprocess.run")
    def test_unknown_container_extension_reaches_ffmpeg(self, run, _ffmpeg):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "camera.recording"
            source.write_bytes(b"media")
            def normalize(command, **_kwargs):
                Path(command[-1].replace("%04d", "0000")).write_bytes(b"video")
                return SimpleNamespace(returncode=0, stderr="", stdout="")
            run.side_effect = normalize
            self.assertEqual(len(cut_sources([str(source)], root / "batch")), 1)
            self.assertEqual(cut_single_clip(source, root / "single").read_bytes(), b"video")

    @patch("scriptor.cutter.ffmpeg_executable", return_value="ffmpeg.exe")
    @patch("scriptor.cutter.subprocess.run")
    def test_wikimedia_ogv_reaches_normalizer(self, run, _ffmpeg):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "Ocean surface waves.OGV"
            source.write_bytes(b"downloaded-media")
            def normalize(command, **_kwargs):
                self.assertEqual(command[command.index("-i") + 1], str(source))
                Path(command[-1].replace("%04d", "0000")).write_bytes(b"normalized")
                return SimpleNamespace(returncode=0, stderr="", stdout="")
            run.side_effect = normalize
            result = cut_sources([str(source)], root / "cuts")
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].read_bytes(), b"normalized")

    @patch("scriptor.cutter.ffmpeg_executable", return_value="ffmpeg.exe")
    def test_builds_silent_normalized_six_second_segments(self, _ffmpeg):
        command = build_cut_command(Path("source.mp4"), Path("out_%04d.mp4"), 6, 30, "4M")
        self.assertIn("-an", command)
        self.assertIn("fps=30", command)
        self.assertIn("-segment_time", command)
        self.assertIn("6", command)
        self.assertEqual(command[-1], "out_%04d.mp4")

    def test_rejects_invalid_duration(self):
        with self.assertRaises(ValueError):
            build_cut_command(Path("source.mp4"), Path("out.mp4"), 0)

    @patch("scriptor.cutter.ffmpeg_executable", return_value="ffmpeg.exe")
    @patch("scriptor.cutter.subprocess.run")
    def test_external_single_clip_reads_only_requested_interval(self, run, _ffmpeg):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "long.webm"
            source.write_bytes(b"source")
            def fake_run(command, **_kwargs):
                Path(command[-1]).write_bytes(b"clip")
                return SimpleNamespace(returncode=0, stderr="", stdout="")
            run.side_effect = fake_run
            result = cut_single_clip(source, root / "out", duration=6, fps=30, bitrate="4M", start=12)
            command = run.call_args.args[0]
            self.assertEqual(result.name, "long_short.mp4")
            self.assertIn("-ss", command)
            self.assertIn("12.000", command)
            self.assertIn("-t", command)
            self.assertIn("6.000", command)
            self.assertNotIn("-f", command)
            self.assertNotIn("segment", command)
