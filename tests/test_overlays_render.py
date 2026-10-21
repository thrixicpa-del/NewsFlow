"""Overlay contracts and real FFmpeg pixels, using disposable media only."""
import importlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import timeline


def template(*layers, layout="16:9"):
    return {"version": 1, "layouts": {layout: list(layers)}}


def layer(**values):
    return {"id": "layer", "path": "local.png", "kind": "image", **values}


def png(path, color):
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    data = b"\x00" + bytes(color) * 4
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 4, 4, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(data * 4)) + chunk(b"IEND", b""))


class OverlaySchemaTests(unittest.TestCase):
    def setUp(self):
        self.overlays = importlib.import_module("scriptor.overlays")

    def test_empty_defaults_and_layouts_are_independent(self):
        normalize = self.overlays.normalize_overlay_template
        empty = {"version": 1, "layouts": {"16:9": [], "9:16": []}}
        self.assertEqual(normalize(None), empty)
        self.assertEqual(normalize({}), empty)
        result = normalize(template(layer(x=17)))
        self.assertEqual(result["layouts"]["9:16"], [])
        row = result["layouts"]["16:9"][0]
        self.assertEqual((row["x"], row["width"], row["height"]), (17, 1920, 1080))
        self.assertFalse(row["audioEnabled"])
        result["layouts"]["16:9"][0]["x"] = 99
        self.assertEqual(normalize(template(layer(x=17)))["layouts"]["16:9"][0]["x"], 17)

    def test_filter_file_option_supports_ffmpeg_six_seven_and_nine(self):
        for version, option in (("6.1.1", "-filter_complex_script"), ("7.1", "-/filter_complex"),
                                ("9.0.1", "-/filter_complex"), ("N-114234-gcustom", "-filter_complex")):
            with self.subTest(version=version), patch.object(self.overlays.subprocess, "run",
                    return_value=SimpleNamespace(stdout=f"ffmpeg version {version} Copyright", stderr="")) as probe:
                self.assertEqual(self.overlays._filter_graph_option(f"test-ffmpeg-{version}"), option)
                self.assertEqual(self.overlays._filter_graph_option(f"test-ffmpeg-{version}"), option)
                self.assertEqual(probe.call_count, 1)

    def test_rejects_invalid_bounded_values_and_network_sources(self):
        for values in ({"opacity": float("nan")}, {"x": float("inf")}, {"width": 0},
                       {"duration": -1}, {"repeatEvery": 0}, {"enabled": "false"},
                       {"chromaColor": "red;movie=bad"}, {"path": "https://example.com/a.mp4"},
                       {"kind": "script"}, {"mode": "forever"}, {"x": 100000}, {"audioEnabled": 1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.overlays.normalize_overlay_template(template(layer(**values)))
        with self.assertRaises(ValueError):
            self.overlays.normalize_overlay_template(template(layer(), layer()))

    def test_file_validation_is_explicit_and_ignores_disabled_missing_layers(self):
        value = template(layer(path="does-not-exist.png"))
        self.overlays.normalize_overlay_template(value)
        with self.assertRaisesRegex(ValueError, "does-not-exist"):
            self.overlays.normalize_overlay_template(value, check_files=True)
        self.overlays.normalize_overlay_template(template(layer(path="", enabled=False)), check_files=True)

    def test_schedule_clips_repeat_and_end_to_whole_final_duration(self):
        intervals = self.overlays.overlay_intervals
        self.assertEqual(intervals(layer(start=2, duration=3, mode="repeat", repeatEvery=4), 11),
                         [(2, 5), (6, 9), (10, 11)])
        self.assertEqual(intervals(layer(duration=4, mode="end", endOffset=2), 11), [(9, 11)])
        self.assertEqual(intervals(layer(duration=3, mode="end", endOffset=12), 11), [(0, 2)])
        self.assertEqual(intervals(layer(start=12, duration=3), 11), [])
        with self.assertRaises(ValueError):
            intervals(layer(duration=1, mode="repeat", repeatEvery=.001), 1000)

    def test_until_end_uses_start_on_final_clock_and_ignores_manual_duration(self):
        row = self.overlays.normalize_overlay_template(template(layer(mode="until-end", start=6, duration=.1)))["layouts"]["16:9"][0]
        self.assertEqual(self.overlays.overlay_intervals(row, 20), [(6, 20)])
        self.assertEqual(self.overlays.overlay_intervals(row, 5), [])
        self.assertEqual(self.overlays.overlay_intervals(row, 6), [])
        self.assertEqual(self.overlays.overlay_intervals(layer(mode="once", start=6, duration=.1), 20), [(6, 6.1)])

    def test_project_and_remotion_manifest_retain_template(self):
        value = self.overlays.normalize_overlay_template(template(layer(path="saved.png", x=39)))
        project = timeline.TimelineProject("saved", overlay_template=value)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "project.json"
            project.save(path)
            restored = timeline.TimelineProject.load(path)
        self.assertEqual(restored.overlay_template, value)
        payload = timeline.remotion_payload(restored)
        self.assertEqual(payload["overlayTemplate"], value)
        self.assertTrue(payload["requiresOverlayFinishing"])

    def test_fcpxml_and_direct_remotion_refuse_silent_overlay_loss(self):
        project = timeline.TimelineProject("export", clips=[timeline.TimelineClip("a.mp4", "", "")],
                                           overlay_template=template(layer()))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "[Нн]алож|[Oo]verlay"):
                timeline.export_fcpxml(project, Path(temporary) / "out.xml")
            with self.assertRaisesRegex(ValueError, "[Нн]алож|[Oo]verlay"):
                timeline._render_project_remotion(project, Path(temporary) / "out.mp4")

    def test_fcpxml_with_overlays_references_published_baked_master_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged, published, output = root / "staged.mp4", root / "published.mp4", root / "out.fcpxml"
            staged.write_bytes(b"staged rendered master")
            project = timeline.TimelineProject("master", voiceover_path="voice.wav",
                                               clips=[timeline.TimelineClip("footage.mp4", "", "", 4)],
                                               overlay_template=template(layer()))
            with patch.object(timeline, "probe_media_duration", return_value=4):
                timeline.export_fcpxml(project, output, baked_source=staged, baked_reference=published)
            xml = ET.fromstring(output.read_text(encoding="utf-8"))
            assets = xml.findall(".//asset")
            self.assertEqual(len(assets), 1)
            self.assertEqual(assets[0].attrib["src"], published.resolve().as_uri())
            self.assertEqual(assets[0].attrib["hasAudio"], "1")
            self.assertEqual(len(xml.findall(".//asset-clip")), 1)
            self.assertIn("наложения сведены", xml.find(".//asset-clip").attrib["name"])

    def test_disabled_fast_path_uses_original_project_and_output(self):
        project = timeline.TimelineProject("plain", overlay_template=template(layer(enabled=False)))
        output = Path("plain.mp4")
        with patch.object(timeline, "_render_project_base", return_value=output) as base, \
                patch.object(timeline, "ffmpeg_executable", side_effect=AssertionError("extra pass")):
            self.assertEqual(timeline.render_project(project, output), output)
        self.assertIs(base.call_args.args[0], project)
        self.assertEqual(base.call_args.args[1], output)

    def test_missing_enabled_file_fails_before_any_base_renderer(self):
        project = timeline.TimelineProject("missing", overlay_template=template(layer(path="lost.png")))
        with patch.object(timeline, "_render_project_base") as base, self.assertRaisesRegex(ValueError, "lost.png"):
            timeline.render_project(project, Path("result.mp4"))
        base.assert_not_called()

    def test_every_renderer_finishes_once_and_failed_pass_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "overlay.png"
            png(image, (255, 0, 0, 255))
            for renderer in ("ffmpeg", "gpu-timeline", "remotion"):
                project = timeline.TimelineProject("shared", overlay_template=template(layer(path=str(image))))
                output = root / "out.mp4"
                output.write_bytes(b"previous good output")
                def base(clean, target, *args, **kwargs):
                    self.assertEqual(clean.overlay_path, "")
                    self.assertFalse(timeline.remotion_payload(clean)["requiresOverlayFinishing"])
                    target.write_bytes(b"new base")
                    return target
                with self.subTest(renderer=renderer), \
                        patch.object(timeline, "_render_project_base", side_effect=base), \
                        patch.object(timeline, "video_encoder_args", return_value=["-c:v", "libx264"]), \
                        patch.object(timeline, "probe_media_duration", return_value=5), \
                        patch.object(timeline, "compose_overlays", side_effect=RuntimeError("failed finishing")), \
                        self.assertRaisesRegex(RuntimeError, "failed finishing"):
                    timeline.render_project(project, output, renderer=renderer)
                self.assertEqual(output.read_bytes(), b"previous good output")
                self.assertEqual(project.output_path, "")

    def test_many_repeats_use_filter_script_with_bounded_windows_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "square.png"
            png(image, (255, 0, 0, 255))
            observed = []
            for version, option in (("6.1.1", "-filter_complex_script"), ("7.1", "-/filter_complex"),
                                    ("9.0.1", "-/filter_complex")):
                def run(command, *, option=option):
                    self.assertIn(option, command)
                    script = Path(command[command.index(option) + 1])
                    graph = script.read_text(encoding="utf-8")
                    self.assertEqual(graph.count("trim=duration=0.05,"), 512)
                    self.assertLess(len(subprocess.list2cmdline(command)), 5000)
                    observed.append(script)
                with self.subTest(version=version), patch.object(self.overlays, "_has_audio", return_value=False), \
                        patch.object(self.overlays.subprocess, "run",
                                     return_value=SimpleNamespace(stdout=f"ffmpeg version {version}", stderr="")):
                    self.overlays.compose_overlays(root / "base.mp4", root / "out.mp4",
                        template(layer(path=str(image), mode="repeat", repeatEvery=.1, duration=.05)),
                        "16:9", total_duration=51.2, ffmpeg=f"many-ffmpeg-{version}", encoder_args=["-c:v", "libx264"], run=run)
            self.assertEqual(len(observed), 3)
            self.assertTrue(all(not script.exists() for script in observed))

    def test_unknown_ffmpeg_version_uses_short_inline_graph_and_rejects_long_graph(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "square.png"
            png(image, (255, 0, 0, 255))
            observed = []
            def run(command):
                graph = command[command.index("-filter_complex") + 1]
                self.assertIn("[0:v]", graph)
                self.assertIn("overlay=x=", graph)
                observed.append(True)
            with patch.object(self.overlays, "_has_audio", return_value=False), \
                    patch.object(self.overlays.subprocess, "run",
                                 return_value=SimpleNamespace(stdout="ffmpeg version development", stderr="")):
                self.overlays.compose_overlays(root / "base.mp4", root / "out.mp4", template(layer(path=str(image))),
                    "16:9", total_duration=1, ffmpeg="unknown-test-ffmpeg", encoder_args=["-c:v", "libx264"], run=run)
                with self.assertRaisesRegex(ValueError, "версия FFmpeg"):
                    self.overlays.compose_overlays(root / "base.mp4", root / "out.mp4",
                        template(layer(path=str(image), mode="repeat", repeatEvery=.1, duration=.05)),
                        "16:9", total_duration=51.2, ffmpeg="unknown-test-ffmpeg", encoder_args=["-c:v", "libx264"], run=run)
            self.assertEqual(observed, [True])

    def test_remotion_finishing_falls_back_when_nvenc_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "overlay.png"
            png(image, (255, 0, 0, 255))
            project = timeline.TimelineProject("cpu", overlay_template=template(layer(path=str(image))))
            output = root / "out.mp4"
            def base(clean, destination, *args, **kwargs):
                destination.write_bytes(b"base")
                return destination
            attempts = []
            def finish(source, destination, *args, **kwargs):
                attempts.append(kwargs["encoder_args"])
                if "h264_nvenc" in kwargs["encoder_args"]:
                    raise RuntimeError("NVENC driver is unavailable")
                destination.write_bytes(b"finished on CPU")
                return destination
            with patch.object(timeline, "_render_project_base", side_effect=base), \
                    patch.dict(timeline._ENCODER_CACHE), \
                    patch.object(timeline, "probe_media_duration", return_value=1), \
                    patch.object(timeline, "video_encoder_args", return_value=["-c:v", "h264_nvenc"]), \
                    patch.object(timeline, "compose_overlays", side_effect=finish), \
                    patch.object(timeline, "validate_rendered_montage", return_value=1):
                timeline.render_project(project, output, renderer="remotion")
            self.assertEqual(output.read_bytes(), b"finished on CPU")
            self.assertEqual(attempts[1][0:2], ["-c:v", "libx264"])

    def test_finished_validation_requires_audio_for_existing_narration_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image, voice = root / "overlay.png", root / "voice.wav"
            png(image, (255, 0, 0, 255))
            voice.write_bytes(b"disposable narration fixture")
            def base(clean, destination, *args, **kwargs):
                destination.write_bytes(b"base")
                return destination
            def finish(source, destination, *args, **kwargs):
                destination.write_bytes(b"finished")
                return destination
            for voice_path, required in (("", False), (str(voice), True), (str(root / "missing.wav"), False)):
                project = timeline.TimelineProject("validation", voiceover_path=voice_path,
                                                   overlay_template=template(layer(path=str(image))))
                with self.subTest(voice_path=voice_path), \
                        patch.object(timeline, "_render_project_base", side_effect=base), \
                        patch.object(timeline, "probe_media_duration", return_value=1), \
                        patch.object(timeline, "video_encoder_args", return_value=["-c:v", "libx264"]), \
                        patch.object(timeline, "compose_overlays", side_effect=finish), \
                        patch.object(timeline, "validate_rendered_montage", return_value=1) as validate:
                    timeline.render_project(project, root / "out.mp4")
                self.assertIs(validate.call_args.kwargs["require_audio"], required)

    def test_mixed_layers_and_static_images_have_no_fixed_count_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image, video = root / "overlay.png", root / "overlay.mp4"
            png(image, (255, 0, 0, 255))
            video.write_bytes(b"disposable media input boundary fixture")
            for count, include_video in ((37, True), (513, False)):
                rows = [layer(id=f"image-{index}", path=str(image)) for index in range(count)]
                if include_video:
                    rows[-1] = layer(id="video", path=str(video), kind="video")
                value = template(*rows)
                self.assertEqual(len(self.overlays.normalize_overlay_template(value)["layouts"]["16:9"]), count)
                observed = []
                def run(command, *, count=count, observed=observed):
                    self.assertEqual(command.count("-i"), count + 1)
                    graph = Path(command[command.index("-/filter_complex") + 1]).read_text(encoding="utf-8")
                    self.assertEqual(graph.count("overlay=x="), count)
                    # Every layer remains in bottom-to-top order, including
                    # the video after the images in the mixed stack.
                    self.assertIn(f"[l{count-1}out0][l{count}trim0]overlay", graph)
                    observed.append(True)
                # Hundreds of input paths can exceed the Windows process
                # command limit. This unit boundary exercises schema/graph
                # retention without launching that resource-heavy process.
                with self.subTest(count=count), patch.object(self.overlays, "_has_audio", return_value=False), \
                        patch.object(self.overlays, "_filter_graph_option", return_value="-/filter_complex"), \
                        patch.object(self.overlays.sys, "platform", "linux"):
                    self.overlays.compose_overlays(root / "base.mp4", root / "out.mp4", value,
                        "16:9", total_duration=1, ffmpeg="ffmpeg", encoder_args=["-c:v", "libx264"], run=run)
                self.assertEqual(observed, [True])


class OverlayMediaTests(unittest.TestCase):
    def setUp(self):
        # The repository binary may be an LFS pointer in a new source checkout.
        # Test with an installed real executable without mutating that asset.
        candidate = Path(timeline.ffmpeg_executable())
        real_ffmpeg = None
        if candidate.is_file():
            with candidate.open("rb") as executable:
                if sys.platform != "win32" or executable.read(2) == b"MZ":
                    real_ffmpeg = str(candidate)
        real_ffmpeg = real_ffmpeg or shutil.which("ffmpeg")
        if not real_ffmpeg:
            import imageio_ffmpeg
            real_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        self.enterContext(patch.object(timeline, "ffmpeg_executable", return_value=real_ffmpeg))

    def run_ffmpeg(self, *args):
        return subprocess.run([timeline.ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y", *args],
                              check=True, capture_output=True)

    def pixel(self, source, when, x, y):
        data = self.run_ffmpeg("-ss", str(when), "-i", str(source), "-frames:v", "1", "-vf",
                               f"crop=2:2:{x}:{y},format=rgb24", "-f", "rawvideo", "-").stdout
        return tuple(data[:3])

    def test_real_stack_short_video_repeat_resets_and_audio_reaches_final_frame(self):
        overlays = importlib.import_module("scriptor.overlays")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, video, red, green, output = [root / name for name in
                                               ("base.mp4", "insert.mp4", "red.png", "green.png", "out.mp4")]
            self.run_ffmpeg("-f", "lavfi", "-i", "color=blue:s=128x96:r=30:d=2", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000:duration=2", "-c:v", "libx264", "-c:a", "aac", str(base))
            self.run_ffmpeg("-f", "lavfi", "-i", "color=red:s=32x32:r=30:d=0.2", "-f", "lavfi", "-i",
                            "color=yellow:s=32x32:r=30:d=0.2", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                            "-map", "[v]", "-c:v", "libx264", str(video))
            png(red, (255, 0, 0, 255))
            png(green, (0, 255, 0, 128))
            value = template(layer(id="bottom", path=str(red), width=32, height=32, duration=2),
                             layer(id="alpha", path=str(green), width=32, height=32, duration=2),
                             layer(id="insert", path=str(video), kind="video", x=64, y=32, width=32, height=32,
                                   mode="repeat", start=.1, duration=.4, repeatEvery=.8),
                             layer(id="until-end", path=str(red), x=100, y=64, width=16, height=16,
                                   mode="until-end", start=1.3, duration=.1))
            overlays.compose_overlays(base, output, value, "16:9", total_duration=2,
                                       ffmpeg=timeline.ffmpeg_executable(),
                                       encoder_args=["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18"])
            mixed = self.pixel(output, .2, 12, 12)
            self.assertGreater(mixed[0], 90)
            self.assertGreater(mixed[1], 90)
            self.assertLess(mixed[2], 20)
            for when in (.2, 1.0, 1.8):
                pixel = self.pixel(output, when, 70, 40)
                self.assertGreater(pixel[0], 200)
                self.assertLess(pixel[1], 30, (when, pixel))
            self.assertGreater(self.pixel(output, .7, 70, 40)[2], 200)
            self.assertGreater(self.pixel(output, 1.2, 104, 70)[2], 200)
            self.assertGreater(self.pixel(output, 1.9, 104, 70)[0], 200)
            self.assertAlmostEqual(timeline.probe_media_duration(output), 2, delta=.05)
            audio = self.run_ffmpeg("-ss", "1.85", "-i", str(output), "-t", "0.1", "-map", "0:a", "-f", "s16le", "-").stdout
            self.assertGreater(len(audio), 4000)
            self.assertTrue(any(audio))

    def test_all_engine_routes_use_finisher_for_a_silent_base(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, image = root / "base.mp4", root / "square.png"
            self.run_ffmpeg("-f", "lavfi", "-i", "color=blue:s=128x96:r=30:d=1", "-an", "-c:v", "libx264", str(base))
            png(image, (255, 0, 0, 255))
            def render(clean, destination, *args, **kwargs):
                shutil.copy2(base, destination)
                return destination
            for renderer in ("ffmpeg", "gpu-timeline", "remotion"):
                output = root / f"{renderer}.mp4"
                project = timeline.TimelineProject("silent", overlay_template=template(layer(path=str(image), width=20, height=20)))
                with self.subTest(renderer=renderer), \
                        patch.object(timeline, "_render_project_base", side_effect=render), \
                        patch.object(timeline, "video_encoder_args", return_value=["-c:v", "libx264", "-preset", "ultrafast"]):
                    timeline.render_project(project, output, renderer=renderer)
                self.assertGreater(self.pixel(output, .5, 8, 8)[0], 200)
                self.assertEqual(project.output_path, str(output))
                self.assertAlmostEqual(timeline.probe_media_duration(output), 1, delta=.05)

    def test_chromakey_keeps_transparent_pixels_and_end_timing(self):
        overlays = importlib.import_module("scriptor.overlays")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, image, output = root / "base.mp4", root / "key.png", root / "out.mp4"
            self.run_ffmpeg("-f", "lavfi", "-i", "color=blue:s=128x96:r=30:d=1", "-an", "-c:v", "libx264", str(base))
            png(image, (0, 255, 0, 255))
            value = template(layer(path=str(image), width=30, height=30, chromaEnabled=True,
                                   mode="end", endOffset=.4, duration=.2))
            overlays.compose_overlays(base, output, value, "16:9", total_duration=1,
                                       ffmpeg=timeline.ffmpeg_executable(), encoder_args=["-c:v", "libx264"])
            self.assertGreater(self.pixel(output, .7, 10, 10)[2], 200)
            png(image, (255, 0, 0, 0))
            overlays.compose_overlays(base, output, value, "16:9", total_duration=1,
                                       ffmpeg=timeline.ffmpeg_executable(), encoder_args=["-c:v", "libx264"])
            self.assertGreater(self.pixel(output, .7, 10, 10)[2], 200)
            png(image, (255, 0, 0, 255))
            overlays.compose_overlays(base, output, value, "16:9", total_duration=1,
                                       ffmpeg=timeline.ffmpeg_executable(), encoder_args=["-c:v", "libx264"])
            self.assertGreater(self.pixel(output, .5, 10, 10)[2], 200)
            self.assertGreater(self.pixel(output, .7, 10, 10)[0], 200)
            self.assertGreater(self.pixel(output, .9, 10, 10)[2], 200)

    def test_optional_video_audio_mixes_and_pads_without_shortening_base(self):
        overlays = importlib.import_module("scriptor.overlays")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, insert, output = root / "base.mp4", root / "insert.mp4", root / "out.mp4"
            self.run_ffmpeg("-f", "lavfi", "-i", "color=blue:s=128x96:r=30:d=2", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000:duration=2", "-c:v", "libx264", "-c:a", "aac", str(base))
            self.run_ffmpeg("-f", "lavfi", "-i", "color=red:s=16x16:r=30:d=0.4", "-f", "lavfi", "-i",
                            "sine=frequency=880:sample_rate=48000:duration=0.4", "-c:v", "libx264", "-c:a", "aac", str(insert))
            value = template(layer(path=str(insert), kind="video", width=16, height=16, start=.5,
                                   duration=.3, audioEnabled=True, mode="repeat", repeatEvery=.7))
            overlays.compose_overlays(base, output, value, "16:9", total_duration=2,
                                       ffmpeg=timeline.ffmpeg_executable(), encoder_args=["-c:v", "libx264"])
            self.assertAlmostEqual(timeline.probe_media_duration(output), 2, delta=.05)
            def energy(when, frequency):
                import cmath
                data = self.run_ffmpeg("-ss", str(when), "-i", str(output), "-t", "0.1", "-map", "0:a",
                                       "-ac", "1", "-ar", "48000", "-f", "s16le", "-").stdout
                samples = struct.unpack("<" + "h" * (len(data) // 2), data)
                return abs(sum(sample * cmath.exp(-2j * cmath.pi * frequency * index / 48000)
                               for index, sample in enumerate(samples))) / len(samples)
            self.assertGreater(energy(.6, 440), 1000)
            self.assertGreater(energy(.6, 880), 1000)
            self.assertLess(energy(1.65, 880), 50)
            self.assertGreater(energy(1.65, 440), 1000)

    def test_legacy_overlay_survives_remotion_route_at_bottom_with_complete_voice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, insert, output = root / "base.mp4", root / "ticker.mp4", root / "out.mp4"
            self.run_ffmpeg("-f", "lavfi", "-i", "color=blue:s=1920x1080:r=30:d=1", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000:duration=1", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", str(base))
            self.run_ffmpeg("-f", "lavfi", "-i", "color=red:s=32x4:r=30:d=0.1", "-an", "-c:v", "libx264", str(insert))
            project = timeline.TimelineProject("legacy", overlay_path=str(insert))
            def render(clean, destination, *args, **kwargs):
                self.assertEqual(clean.overlay_path, "")
                shutil.copy2(base, destination)
                return destination
            with patch.object(timeline, "_render_project_base", side_effect=render), \
                    patch.object(timeline, "video_encoder_args", return_value=["-c:v", "libx264", "-preset", "ultrafast"]):
                timeline.render_project(project, output, renderer="remotion")
            # 32x4 scaled to width1920 => height240, bottom1056 (24px margin).
            self.assertGreater(self.pixel(output, .9, 10, 1000)[0], 200)
            self.assertGreater(self.pixel(output, .9, 1900, 1000)[0], 200)
            self.assertGreater(self.pixel(output, .9, 900, 1068)[2], 200)
            self.assertAlmostEqual(timeline.probe_media_duration(output), 1, delta=.05)
            audio = self.run_ffmpeg("-ss", "0.85", "-i", str(output), "-t", "0.1", "-map", "0:a", "-f", "s16le", "-").stdout
            self.assertGreater(len(audio), 4000)
            self.assertTrue(any(audio))


if __name__ == "__main__":
    unittest.main()
