"""Actual renderer modes must feed the same overlay finishing stage."""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor import timeline

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "test-data/overlay-404/acceptance"


class OverlayRendererModes(unittest.TestCase):
    def test_actual_gpu_and_remotion_both_layouts(self):
        self.assertTrue(
            (EVIDENCE / "16x9.newsflow").exists(), "Run overlay media acceptance first"
        )
        ffmpeg = timeline.ffmpeg_executable()
        node = shutil.which("node")
        report = []
        for renderer in ["gpu-timeline", "remotion"]:
            if (
                renderer == "gpu-timeline"
                and not timeline.gpu_timeline_capability()["available"]
            ):
                report.append(
                    {
                        "renderer": renderer,
                        "status": "BLOCKED",
                        "reason": timeline.gpu_timeline_capability()["reason"],
                    }
                )
                continue
            self.assertTrue(node)
            with patch.dict(
                os.environ,
                {
                    "NEWSFLOW_REMOTION_NODE": node,
                    "NEWSFLOW_REMOTION_RUNNER": str(
                        ROOT / "studio-ui-remotion-verify/remotion/render.mjs"
                    ),
                },
            ):
                for ratio, w, h in [("16:9", 1920, 1080), ("9:16", 1080, 1920)]:
                    project = timeline.TimelineProject.load(
                        EVIDENCE / (ratio.replace(":", "x") + ".newsflow")
                    )
                    output = EVIDENCE / (
                        ratio.replace(":", "x") + "-" + renderer + ".mp4"
                    )
                    timeline.render_project(
                        project, output, renderer=renderer, remotion_concurrency=1
                    )
                    info = subprocess.run(
                        [
                            shutil.which("ffprobe"),
                            "-v",
                            "error",
                            "-show_streams",
                            "-show_format",
                            "-of",
                            "json",
                            str(output),
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    meta = json.loads(info.stdout)
                    video = next(
                        s for s in meta["streams"] if s["codec_type"] == "video"
                    )
                    self.assertEqual((video["width"], video["height"]), (w, h))
                    self.assertAlmostEqual(
                        float(meta["format"]["duration"]), 7, delta=0.1
                    )

                    def decode(*args, output=output):
                        return subprocess.run(
                            [ffmpeg, "-v", "error", "-i", str(output), *map(str, args)],
                            capture_output=True,
                            check=True,
                            timeout=60,
                        ).stdout

                    audio = np.frombuffer(
                        decode(
                            "-map", "0:a:0", "-ac", 1, "-ar", 48000, "-f", "f32le", "-"
                        ),
                        dtype=np.float32,
                    )
                    self.assertGreater(len(audio), int(6.9 * 48000))
                    self.assertGreater(
                        float(
                            np.sqrt(
                                np.mean(
                                    audio[int(6.65 * 48000) : int(6.9 * 48000)] ** 2
                                )
                            )
                        ),
                        0.02,
                    )

                    def pixel(when, x, y, output=output):
                        raw = subprocess.run(
                            [
                                ffmpeg,
                                "-v",
                                "error",
                                "-ss",
                                str(when),
                                "-i",
                                str(output),
                                "-frames:v",
                                "1",
                                "-vf",
                                f"crop=2:2:{x}:{y},format=rgb24",
                                "-f",
                                "rawvideo",
                                "-",
                            ],
                            capture_output=True,
                            check=True,
                        ).stdout
                        return tuple(raw[:3])

                    p = pixel(2.85, 240, 100)
                    self.assertGreater(p[0], 200)
                    self.assertLess(p[1], 35)
                    p = pixel(2.85, 204, 64)
                    self.assertLess(p[1], 30)
                    self.assertGreater(p[2], 200)
                    p = pixel(6.7, 420, 120)
                    self.assertGreater(p[0], 200)
                    self.assertGreater(p[2], 200)
                    decode("-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")
                    report.append(
                        {
                            "renderer": renderer,
                            "aspect": ratio,
                            "path": str(output),
                            "status": "PASS",
                            "full_decode": True,
                            "voice_tail": True,
                            "chroma_repeat_end_pixels": True,
                        }
                    )
        (EVIDENCE / "renderer-modes.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
