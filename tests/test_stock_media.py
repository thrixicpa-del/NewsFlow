"""Real, synthetic-only stock media preparation checks."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scriptor.stock_media import prepare_stock_media
from scriptor.timeline import ffmpeg_executable


class StockMediaTests(unittest.TestCase):
    def setUp(self):
        test_root = os.environ.get("NEWSFLOW_TEST_ROOT")
        self.assertTrue(test_root, "Run through tests/run_isolated.py")
        self.temporary = tempfile.TemporaryDirectory(dir=test_root)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.out = self.root / "cache"
        self.ffmpeg = ffmpeg_executable()
        self.ffprobe = shutil.which("ffprobe")
        self.assertTrue(self.ffprobe, "Real media checks require ffprobe")
        self.source = self.root / "synthetic source.mp4"
        self.run_media([
            self.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
            "color=red:s=160x90:r=30:d=1", "-f", "lavfi", "-i",
            "color=blue:s=160x90:r=30:d=1", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=2", "-filter_complex",
            "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(self.source),
        ])
        self.original = self.source.read_bytes()
        self.original_stat = self.source.stat().st_mtime_ns

    def tearDown(self):
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.source.stat().st_mtime_ns, self.original_stat)

    def run_media(self, command):
        result = subprocess.run(command, capture_output=True, timeout=60, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr[-3000:])
        return result.stdout

    def probe(self, path):
        return json.loads(self.run_media([
            self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
        ]))

    def assert_silent(self, path, duration, dimensions=None):
        data = self.probe(path)
        self.assertEqual([s["codec_type"] for s in data["streams"]], ["video"])
        video = data["streams"][0]
        self.assertEqual(video["avg_frame_rate"], "30/1")
        self.assertAlmostEqual(float(data["format"]["duration"]), duration, delta=1 / 30 + .002)
        if dimensions:
            self.assertEqual((video["width"], video["height"]), dimensions)

    def frame(self, path, start=0):
        return self.run_media([
            self.ffmpeg, "-v", "error", "-ss", str(start), "-i", str(path),
            "-frames:v", "1", "-vf", "scale=16:16", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
        ])

    def image(self):
        path = self.root / "synthetic image.png"
        image = Image.new("RGB", (180, 120))
        image.putdata([(x % 256, y * 2, (x + y) % 256) for y in range(120) for x in range(180)])
        image.save(path)
        return path

    def test_video_interval_is_silent_and_preserves_original(self):
        result = prepare_stock_media(self.source, self.out, duration=.6, source_start=1.2)
        self.assertNotEqual(result, self.source)
        self.assert_silent(result, .6, (160, 90))
        rgb = self.frame(result)
        self.assertGreater(sum(rgb[2::3]), sum(rgb[0::3]) * 4, "Must select the blue second half")

    def test_trim_false_returns_original_without_preparation(self):
        with patch("scriptor.stock_media.cut_single_clip", side_effect=AssertionError("pretrim")):
            result = prepare_stock_media(self.source, self.out, duration=.7, source_start=.5, trim=False)
        self.assertEqual(result, self.source)
        self.assertFalse(self.out.exists())
        self.assertIn("audio", [s["codec_type"] for s in self.probe(result)["streams"]])

    def test_cache_reuses_bytes_and_separates_interval_and_aspect(self):
        result = prepare_stock_media(self.source, self.out, duration=.4)
        stamp = result.stat().st_mtime_ns
        with patch("scriptor.stock_media.cut_single_clip", side_effect=AssertionError("cache miss")):
            self.assertEqual(prepare_stock_media(self.source, self.out, duration=.4), result)
        self.assertEqual(result.stat().st_mtime_ns, stamp)
        alternate = prepare_stock_media(self.source, self.out, duration=.6, source_start=1)
        aspect = prepare_stock_media(self.source, self.out, duration=.4, aspect_ratio="9:16")
        self.assertEqual(len({result, alternate, aspect}), 3)
        self.assert_silent(alternate, .6)

    def test_corrupt_or_wrong_length_cache_is_rebuilt(self):
        result = prepare_stock_media(self.source, self.out, duration=.4)
        result.write_bytes(b"broken")
        self.assertEqual(prepare_stock_media(self.source, self.out, duration=.4), result)
        self.assert_silent(result, .4)
        other = prepare_stock_media(self.source, self.out, duration=1.2)
        shutil.copyfile(other, result)
        prepare_stock_media(self.source, self.out, duration=.4)
        self.assert_silent(result, .4)

    def test_image_panzoom_is_silent_cfr_and_matches_aspect(self):
        source = self.image()
        original = hashlib.sha256(source.read_bytes()).digest()
        result = prepare_stock_media(source, self.out, duration=.6, kind="image", aspect_ratio="9:16")
        self.assert_silent(result, .6, (1080, 1920))
        self.assertNotEqual(self.frame(result), self.frame(result, .5), "Pan/zoom must move")
        self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)
        square = prepare_stock_media(source, self.out, duration=.4, kind="image", aspect_ratio="1:1", trim=False)
        self.assert_silent(square, .4, (1080, 1080))

    def test_content_change_changes_cache_key(self):
        source = self.image()
        first = prepare_stock_media(source, self.out, duration=.2, kind="image")
        Image.new("RGB", (180, 120), "green").save(source)
        second = prepare_stock_media(source, self.out, duration=.2, kind="image")
        self.assertNotEqual(first, second)

    def test_portrait_image_keeps_head_and_lower_content_in_landscape(self):
        source = self.root / "portrait.png"
        portrait = Image.new("RGB", (180, 320), "green")
        portrait.paste("red", (40, 32, 140, 64))
        portrait.paste("blue", (40, 256, 140, 288))
        portrait.save(source)
        result = prepare_stock_media(source, self.out, duration=.6, kind="image", aspect_ratio="16:9")
        for start in (0, .5):
            raw = self.run_media([self.ffmpeg, "-v", "error", "-ss", str(start), "-i", str(result),
                "-frames:v", "1", "-vf", "scale=96:54", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
            pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
            self.assertGreater(sum(r > 100 and r > 2*g and r > 2*b for r,g,b in pixels), 30,
                               "Top portrait content was cropped")
            self.assertGreater(sum(b > 100 and b > 2*g and b > 2*r for r,g,b in pixels), 30,
                               "Lower portrait content was cropped")

    def test_rejects_invalid_parameters_and_short_source(self):
        for options in ({"duration": 0}, {"duration": float("nan")}, {"duration": float("inf")},
                        {"duration": True}, {"duration": .4, "source_start": -1},
                        {"duration": .4, "source_start": float("inf")},
                        {"duration": .4, "aspect_ratio": "16:9;bad"},
                        {"duration": .4, "kind": "audio"}, {"duration": .4, "trim": "false"}):
            with self.subTest(options=options), self.assertRaises((ValueError, TypeError)):
                prepare_stock_media(self.source, self.out, **options)
        with self.assertRaises(ValueError):
            prepare_stock_media(self.source, self.out, duration=1, source_start=1.8)
        self.assertEqual(list(self.out.rglob("*.mp4")) if self.out.exists() else [], [])

    def test_two_processes_publish_one_valid_derivative(self):
        code = ("from pathlib import Path; from scriptor.stock_media import prepare_stock_media; "
                "import sys; print(prepare_stock_media(Path(sys.argv[1]), Path(sys.argv[2]), duration=.4))")
        command = [sys.executable, "-B", "-c", code, str(self.source), str(self.out)]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                     for _ in range(2)]
        outputs = []
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=60)
                self.assertEqual(process.returncode, 0, stderr)
                outputs.append(stdout.decode().strip())
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
        self.assertEqual(outputs[0], outputs[1])
        self.assert_silent(Path(outputs[0]), .4)
        self.assertEqual(len(list(self.out.rglob("*.mp4"))), 1)


if __name__ == "__main__":
    unittest.main()
