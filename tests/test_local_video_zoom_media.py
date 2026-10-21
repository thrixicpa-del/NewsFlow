"""Real synthetic MP4 acceptance: zoom, timing, audio and immutable originals."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path

import numpy as np

from scriptor.timeline import (
    TimelineClip,
    TimelineProject,
    ffmpeg_executable,
    render_project,
)


class LocalVideoZoomMediaTests(unittest.TestCase):
    def test_both_aspects_zoom_only_when_enabled_and_preserve_voice(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        ffmpeg, ffprobe = ffmpeg_executable(), shutil.which("ffprobe")
        renderer = os.environ.get("NEWSFLOW_LOCAL_ZOOM_RENDERER", "ffmpeg")
        self.assertTrue(ffprobe)
        evidence = Path(__file__).resolve().parents[1] / ".superpowers/local-video-zoom/media" / uuid.uuid4().hex
        evidence.mkdir(parents=True)
        receipt = []

        def run(args):
            result = subprocess.run(args, capture_output=True, timeout=120, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.assertEqual(result.returncode, 0, result.stderr[-3000:])
            return result.stdout

        def frame(path, second, width, height):
            raw = run([ffmpeg, "-v", "error", "-ss", str(second), "-i", str(path),
                "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
            pixels = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))
            red = (pixels[:, :, 0] > 150) & (pixels[:, :, 1] < 60) & (pixels[:, :, 2] < 60)
            _ys, xs = np.where(red)
            self.assertGreater(len(xs), 100)
            return int(xs.max()-xs.min()+1), float(pixels[height//2, width//3, 1])

        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as temporary:
            root = Path(temporary)
            voice = root / "voice.wav"
            run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                 "sine=frequency=440:sample_rate=48000:duration=2.4", str(voice)])
            for aspect, source_size, output_size in [("16:9", "320x180", (1920, 1080)), ("9:16", "180x320", (1080, 1920))]:
                source = root / f"local-{aspect.replace(':','x')}.mp4"
                width, height = output_size
                run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={source_size}:r=30:d=1.2",
                    "-f", "lavfi", "-i", f"color=0x004000:s={source_size}:r=30:d=2.8",
                    "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=4",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,drawbox=x=iw*0.6:y=ih*0.2:w=iw*0.12:h=ih*0.6:color=red:t=fill[v]",
                    "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)])
                original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
                for enabled in (False, True):
                    with self.subTest(aspect=aspect, enabled=enabled):
                        clip = TimelineClip(str(source), "Synthetic voice", "", 2.4, source="local")
                        project = TimelineProject("Local zoom", aspect_ratio=aspect, clips=[clip],
                            voiceover_path=str(voice), local_video_zoom=enabled)
                        output = evidence / f"{aspect.replace(':','x')}-zoom-{enabled}.mp4"
                        render_project(project, output, renderer=renderer, remotion_concurrency=1)
                        probe = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]))
                        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
                        audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
                        self.assertEqual((video["width"], video["height"]), output_size)
                        self.assertEqual(video["avg_frame_rate"], "30/1")
                        self.assertEqual(int(video["nb_frames"]), 72)
                        self.assertAlmostEqual(float(video["duration"]), 2.4, delta=1/30)
                        # Remotion's AAC encoder appends up to three silent
                        # packets; the exact video frame count and voiced tail
                        # below distinguish padding from slowed/truncated audio.
                        self.assertAlmostEqual(float(audio["duration"]), 2.4, delta=3*1024/48000)
                        first, first_green = frame(output, 0, width, height)
                        last, last_green = frame(output, 2.3, width, height)
                        self.assertGreater(last_green, first_green + 30, "Source motion/time must advance")
                        if enabled:
                            self.assertGreater(last/first, 1.055)
                            self.assertLess(last/first, 1.095)
                        elif renderer == "remotion":
                            # OFF preserves Remotion's existing slight zoom-out.
                            self.assertGreater(last/first, .92)
                            self.assertLess(last/first, .96)
                        else:
                            # Chroma subsampling/encoding moves the thresholded
                            # edge by one pixel per side on hosted CPU encoders.
                            # Two pixels are well below the ON growth (>=7px).
                            self.assertLessEqual(abs(last-first), 2)
                        raw = run([ffmpeg, "-v", "error", "-i", str(output), "-map", "0:a:0", "-ac", "1", "-ar", "48000", "-f", "f32le", "-"])
                        samples = np.frombuffer(raw, dtype="<f4")
                        self.assertGreaterEqual(len(samples)/48000, 2.39)
                        def magnitude(part, frequency):
                            window = np.hanning(len(part))
                            return abs(np.sum(part*window*np.exp(-2j*np.pi*frequency*np.arange(len(part))/48000)))/np.sum(window)
                        self.assertGreater(magnitude(samples[int(2.32*48000):int(2.38*48000)], 440), .025)
                        self.assertLess(magnitude(samples[12000:84000], 880), .001)
                        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), original_hash)
                        receipt.append({"aspect":aspect, "renderer":renderer, "enabled":enabled, "status":"PASS", "output":output.name,
                                        "red_width_first":first, "red_width_last":last, "audio_duration":audio["duration"]})
        (evidence / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"LOCAL_ZOOM_MEDIA_EVIDENCE={evidence}", flush=True)
