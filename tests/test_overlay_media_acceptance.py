"""Actual 1080p/vertical MP4 overlay acceptance with disposable generated media."""

import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from scriptor import timeline

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg")


@unittest.skipUnless(
    FFMPEG, "A genuine system FFmpeg is required (checkout asset is LFS pointer)"
)
class OverlayOutputAcceptance(unittest.TestCase):
    def run_media(self, *args):
        return subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
            check=True,
            capture_output=True,
            timeout=120,
        ).stdout

    def pixel(self, source, time, x, y):
        data = self.run_media(
            "-ss",
            time,
            "-i",
            source,
            "-frames:v",
            1,
            "-vf",
            f"crop=2:2:{x}:{y},format=rgb24",
            "-f",
            "rawvideo",
            "-",
        )
        return np.frombuffer(data, dtype=np.uint8)[:3].astype(float)

    def test_saved_projects_both_formats_exact_layers_clock_and_narration(self):
        out = ROOT / "test-data/overlay-404/acceptance"
        out.mkdir(parents=True, exist_ok=True)
        blue, intro, voice, insert = [
            out / name
            for name in ("blue.mp4", "intro.mp4", "voice.wav", "subscribe.mp4")
        ]
        self.run_media(
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=320x240:r=30:d=6.2",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            blue,
        )
        self.run_media(
            "-f",
            "lavfi",
            "-i",
            "color=black:s=320x240:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            1,
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            intro,
        )
        self.run_media(
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=437:sample_rate=48000:duration=5.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=997:sample_rate=48000:duration=0.5",
            "-filter_complex",
            "[0:a][1:a]concat=n=2:v=0:a=1[a]",
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            voice,
        )
        self.run_media(
            "-f",
            "lavfi",
            "-i",
            "color=0x00FF00:s=64x64:r=30:d=1,drawbox=x=16:y=16:w=32:h=32:color=red:t=fill:enable='lt(t,0.4)',drawbox=x=16:y=16:w=32:h=32:color=yellow:t=fill:enable='gte(t,0.4)'",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1711:sample_rate=48000:duration=1",
            "-c:v",
            "libx264",
            "-crf",
            10,
            "-c:a",
            "aac",
            insert,
        )
        image = Image.new("RGBA", (24, 24), (255, 0, 0, 255))
        for x in range(8):
            for y in range(24):
                image.putpixel((x, y), (255, 0, 0, 0))
        png = out / "transparent.png"
        image.save(png)
        jpg = out / "yellow.jpg"
        Image.new("RGB", (24, 24), (255, 255, 0)).save(jpg)
        tail = out / "tail.png"
        Image.new("RGBA", (24, 24), (255, 0, 255, 255)).save(tail)

        until = out / "until-end.png"
        Image.new("RGBA", (24, 24), (0, 255, 255, 255)).save(until)

        def layer(identifier, path, **kw):
            return dict(
                {
                    "id": identifier,
                    "name": identifier,
                    "enabled": True,
                    "path": str(path),
                    "kind": "image",
                    "x": 20,
                    "y": 30,
                    "width": 96,
                    "height": 96,
                    "keepAspect": False,
                    "opacity": 1,
                    "start": 0,
                    "duration": 7,
                    "mode": "once",
                    "repeatEvery": 2,
                    "endOffset": 0.6,
                    "chromaEnabled": False,
                    "chromaColor": "#00FF00",
                    "chromaSimilarity": 0.12,
                    "chromaBlend": 0.08,
                    "audioEnabled": False,
                },
                **kw,
            )

        rows = [
            layer("alpha", png),
            layer("top", jpg, x=80, y=90, start=1, duration=0.3),
            layer(
                "anim",
                insert,
                kind="video",
                x=200,
                y=60,
                start=0.75,
                duration=0.6,
                mode="repeat",
                chromaEnabled=True,
            ),
            layer("end", tail, x=400, y=100, duration=4, mode="end"),
            layer(
                "until-end",
                until,
                x=600,
                y=100,
                start=6,
                duration=0.1,
                mode="until-end",
            ),
            layer("manual-ranges", tail, x=750, y=100, width=64, height=64, mode="intervals",
                  ranges=[{"start": .8, "end": 1.1}, {"start": 3.2, "end": 3.6}, {"start": 6.5, "end": 9}]),
            layer("count", jpg, x=850, y=100, width=64, height=64, mode="count",
                  start=1, duration=.3, repeatCount=4, rangeEnd=6.8),
            layer("loop-to-end", insert, kind="video", x=950, y=100, width=64, height=64,
                  mode="until-end", start=4.2, chromaEnabled=True),
            layer("animated-ranges", insert, kind="video", x=750, y=220, width=64, height=64,
                  mode="intervals", ranges=[{"start": .5, "end": 1.3}, {"start": 3, "end": 3.8}, {"start": 5.8, "end": 7.8}], chromaEnabled=True),
            layer("animated-count", insert, kind="video", x=850, y=220, width=64, height=64,
                  mode="count", start=.5, duration=.8, repeatCount=3, rangeEnd=6.7, chromaEnabled=True),
        ]
        rows[0]["opacity"] = 0.5
        results = []
        with patch.object(timeline, "ffmpeg_executable", return_value=FFMPEG):
            for ratio, width, height in [("16:9", 1920, 1080), ("9:16", 1080, 1920)]:
                project = timeline.TimelineProject(
                    "Overlay acceptance " + ratio,
                    aspect_ratio=ratio,
                    clips=[
                        timeline.TimelineClip(
                            str(blue), "Generated narration", "test", duration=6
                        )
                    ],
                    voiceover_path=str(voice),
                    intro_path=str(intro),
                    intro_duration=1,
                    transition_style="cut",
                    transition_frames=0,
                )
                reference = out / (ratio.replace(":", "x") + "-reference.mp4")
                timeline.render_project(project, reference)
                project.overlay_template = {
                    "version": 1,
                    "layouts": {
                        "16:9": copy.deepcopy(rows),
                        "9:16": copy.deepcopy(rows),
                    },
                }
                saved = out / (ratio.replace(":", "x") + ".newsflow")
                project.save(saved)
                restored = timeline.TimelineProject.load(saved)
                self.assertEqual(restored.overlay_template, project.overlay_template)
                output = out / (ratio.replace(":", "x") + "-overlays.mp4")
                timeline.render_project(restored, output)
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
                metadata = json.loads(info.stdout)
                for x, red_times, yellow_times in [(780, (.6, 3.1, 5.9, 6.9), (1.1, 3.6, 6.4)),
                                                    (880, (.6, 3.3, 6), (1.1, 3.8, 6.5))]:
                    for when in red_times:
                        color = self.pixel(output, when, x, 250)
                        self.assertGreater(color[0], 200, (ratio, x, when, color))
                        self.assertLess(color[1], 35, (ratio, x, when, color))
                    for when in yellow_times:
                        color = self.pixel(output, when, x, 250)
                        self.assertGreater(color[0], 200, (ratio, x, when, color))
                        self.assertGreater(color[1], 200, (ratio, x, when, color))
                video = next(
                    s for s in metadata["streams"] if s["codec_type"] == "video"
                )
                self.assertEqual((video["width"], video["height"]), (width, height))
                self.assertAlmostEqual(
                    float(metadata["format"]["duration"]), 7, delta=0.08
                )
                for time in (.9, 3.3, 6.8):
                    color = self.pixel(output, time, 780, 130)
                    self.assertGreater(color[0], 180)
                    self.assertGreater(color[2], 180)
                for time in (1.3, 3.8, 6.2):
                    self.assertLess(self.pixel(output, time, 780, 130)[0], 40)
                for time in (1.1, 2.95, 4.8, 6.6):
                    color = self.pixel(output, time, 880, 130)
                    self.assertGreater(color[0], 180)
                    self.assertGreater(color[1], 180)
                for time in (1.5, 3.3, 5.1):
                    self.assertLess(self.pixel(output, time, 880, 130)[0], 40)
                for time in (4.3, 5.3, 6.3):
                    color = self.pixel(output, time, 980, 130)
                    self.assertGreater(color[0], 180)
                    self.assertLess(color[1], 80)
                for time in (4.8, 5.8, 6.8):
                    color = self.pixel(output, time, 980, 130)
                    self.assertGreater(color[0], 180)
                    self.assertGreater(color[1], 150)
                self.assertLess(
                    self.pixel(output, 1.7, 24, 50)[0], 20
                )  # transparent PNG hole
                mixed = self.pixel(output, 1.7, 70, 50)
                self.assertGreater(mixed[0], 100)
                self.assertGreater(mixed[2], 100)
                self.assertLess(mixed[1], 20)
                top = self.pixel(output, 1.1, 90, 100)
                self.assertGreater(top[0], 210)
                self.assertGreater(top[1], 210)
                self.assertLess(top[2], 25)
                for when in (0.85, 2.85, 4.85, 6.85):
                    red = self.pixel(output, when, 240, 100)
                    self.assertGreater(red[0], 200)
                    self.assertLess(red[1], 35, (ratio, when, red))
                keyed = self.pixel(output, 2.85, 204, 64)
                self.assertLess(keyed[1], 30)
                self.assertGreater(keyed[2], 200)
                off = self.pixel(output, 2, 240, 100)
                self.assertGreater(off[2], 200)
                before = self.pixel(output, 6.2, 420, 120)
                self.assertLess(before[0], 30)
                end = self.pixel(output, 6.7, 420, 120)
                self.assertGreater(end[0], 200)
                self.assertGreater(end[2], 200)
                self.assertLess(self.pixel(output, 5.8, 620, 120)[1], 30)
                for when in (6.2, 6.8):
                    full = self.pixel(output, when, 620, 120)
                    self.assertGreater(full[1], 200)
                    self.assertGreater(full[2], 200)
                    self.assertLess(full[0], 30)

                def pcm(path):
                    return self.run_media(
                        "-i",
                        path,
                        "-map",
                        "0:a:0",
                        "-ac",
                        1,
                        "-ar",
                        48000,
                        "-f",
                        "f32le",
                        "-",
                    )

                baseline = pcm(reference)
                actual = pcm(output)
                self.assertEqual(
                    actual,
                    baseline,
                    "Muted overlays must preserve the exact encoded narration",
                )
                samples = np.frombuffer(actual, dtype=np.float32)
                tail_samples = samples[int(6.6 * 48000) : int(6.9 * 48000)]
                self.assertGreater(float(np.sqrt(np.mean(tail_samples**2))), 0.02)
                self.run_media(
                    "-i", output, "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"
                )
                results.append(
                    {
                        "aspect": ratio,
                        "path": str(output),
                        "width": width,
                        "height": height,
                        "duration": float(metadata["format"]["duration"]),
                        "pcm_exact": True,
                        "full_decode": True,
                    }
                )
        (out / "acceptance.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )
