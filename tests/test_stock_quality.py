"""Original-source dimensions and HD eligibility use actual source pixels."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scriptor import stock_media


class StockQualityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='newsflow-stock-quality-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.video = self.root / 'actual-original.mp4'
        self.video.write_bytes(b'disposable video probe fixture')

    def dimensions(self, source, kind):
        probe = getattr(stock_media, 'stock_source_dimensions', None)
        if not callable(probe):
            self.fail('Original-source dimension probe is not implemented')
        return probe(source, kind)

    def hd(self, source, kind):
        gate = getattr(stock_media, 'source_is_hd', None)
        if not callable(gate):
            self.fail('Original-source HD gate is not implemented')
        return gate(source, kind)

    @staticmethod
    def result(width=None, height=None, *, returncode=0, audio_only=False):
        header = 'Duration: 00:00:01.00, start: 0.000000\n'
        header += 'Metadata: title: API claims1920x1080\n'
        header += 'Stream #0:0: Audio: aac,48000Hz,stereo\n'
        if not audio_only:
            dimensions = f', {width}x{height} [SAR 1:1 DAR 16:9]' if width is not None else ''
            header += f'Stream #0:1: Video: h264 (High), yuv420p(progressive){dimensions},30 fps\n'
        return subprocess.CompletedProcess([], returncode, '', header)

    def test_video_probe_reads_input_video_stream_not_claimed_metadata(self):
        with patch('scriptor.stock_media.subprocess.run', return_value=self.result(640, 360)):
            self.assertEqual(self.dimensions(self.video, 'video'), (640, 360))
            self.assertFalse(self.hd(self.video, 'video'))

    def test_video_hd_policy_handles_orientation_and_rejects360p_and_square(self):
        for width, height, expected in [(1280, 720, True), (720, 1280, True),
                                        (1920, 1080, True), (1280, 719, False),
                                        (1279, 720, False), (640, 360, False),
                                        (1080, 1080, False)]:
            with (self.subTest(size=(width, height)),
                  patch('scriptor.stock_media.subprocess.run', return_value=self.result(width, height))):
                self.assertEqual(self.hd(self.video, 'video'), expected)

    def test_real_photo_policy_requires720_short_side_and720p_pixel_count(self):
        for width, height, expected in [(1280, 720, True), (720, 1280, True),
                                        (1080, 1080, True), (960, 960, True),
                                        (900, 900, False), (640, 360, False),
                                        (4000, 719, False)]:
            with self.subTest(size=(width, height)):
                source = self.root / f'photo-{width}-{height}.png'
                Image.new('RGB', (width, height), '#254060').save(source)
                self.assertEqual(self.dimensions(source, 'image'), (width, height))
                self.assertEqual(self.hd(source, 'image'), expected)

    def test_upscaled_proxy_cannot_make_low_resolution_original_hd(self):
        source = self.root / 'original-360p.png'
        prepared = self.root / 'prepared-1080p.png'
        Image.new('RGB', (640, 360)).save(source)
        Image.new('RGB', (1920, 1080)).save(prepared)
        self.assertFalse(self.hd(source, 'image'))
        self.assertTrue(self.hd(prepared, 'image'))

    def test_missing_unknown_corrupt_and_truncated_images_fail_closed(self):
        corrupt = self.root / 'corrupt.png'; corrupt.write_bytes(b'not an image')
        valid = self.root / 'truncated.png'; Image.new('RGB', (1280, 720)).save(valid)
        valid.write_bytes(valid.read_bytes()[:len(valid.read_bytes())//2])
        for source, kind in [(self.root / 'missing.mp4', 'video'), (self.video, 'unknown'),
                             (corrupt, 'image'), (valid, 'image')]:
            with self.subTest(name=source.name, kind=kind):
                with self.assertRaises(ValueError):
                    self.dimensions(source, kind)
                self.assertFalse(self.hd(source, kind))

    def test_failed_video_decode_missing_dimensions_and_audio_only_fail_closed(self):
        for result in [self.result(1280, 720, returncode=1), self.result(), self.result(audio_only=True)]:
            with (self.subTest(stderr=result.stderr),
                  patch('scriptor.stock_media.subprocess.run', return_value=result)):
                with self.assertRaises(ValueError):
                    self.dimensions(self.video, 'video')
                self.assertFalse(self.hd(self.video, 'video'))

    def test_probe_timeout_is_clear_error_and_ineligible(self):
        with patch('scriptor.stock_media.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 30)):
            with self.assertRaises(ValueError):
                self.dimensions(self.video, 'video')
            self.assertFalse(self.hd(self.video, 'video'))

    def test_source_pixels_and_storage_remain_unchanged(self):
        source = self.root / 'photo.png'; Image.new('RGB', (1280, 720), '#405060').save(source)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        files = sorted(p.name for p in self.root.iterdir())
        self.assertTrue(self.hd(source, 'image'))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), files)

    def test_tiny_real_videos_report_actual720p_and360p_dimensions(self):
        for width, height, expected in [(1280, 720, True), (640, 360, False)]:
            with self.subTest(size=(width, height)):
                path = self.root / f'real-{width}-{height}.mp4'
                command = [stock_media.ffmpeg_executable(), '-v', 'error', '-nostdin', '-y',
                           '-f', 'lavfi', '-i', f'color=c=blue:s={width}x{height}:r=30:d=0.1',
                           '-frames:v', '1', '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                           '-threads', '1', '-filter_threads', '1', str(path)]
                subprocess.run(command, check=True, capture_output=True, timeout=20)
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(self.dimensions(path, 'video'), (width, height))
                self.assertEqual(self.hd(path, 'video'), expected)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)


class ContinuityMediaTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='newsflow-continuity-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / 'cache'
        self.source = self.root / 'two-colors.mp4'
        command = [stock_media.ffmpeg_executable(), '-v', 'error', '-nostdin', '-y',
                   '-f', 'lavfi', '-i', 'color=c=red:s=1280x720:r=30:d=0.2',
                   '-f', 'lavfi', '-i', 'color=c=blue:s=1280x720:r=30:d=0.2',
                   '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]',
                   '-an', '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p',
                   '-threads', '1', '-filter_complex_threads', '1', str(self.source)]
        subprocess.run(command, check=True, capture_output=True, timeout=20)

    def prepare(self, source, **kwargs):
        helper = getattr(stock_media, 'prepare_continuity_media', None)
        if not callable(helper):
            self.fail('Literal freeze/neutral continuity preparation is not implemented')
        return helper(source, self.output, **kwargs)

    @staticmethod
    def frame_pixels(path):
        command = [stock_media.ffmpeg_executable(), '-v', 'error', '-nostdin', '-threads', '1',
                   '-i', str(path), '-an', '-vf', 'scale=64:36', '-threads', '1',
                   '-filter_threads', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
        result = subprocess.run(command, capture_output=True, check=True, timeout=20)
        return [result.stdout[pos:pos+64*36*3] for pos in range(0, len(result.stdout), 64*36*3)]

    def test_actual_freeze_holds_chosen_blue_frame_without_loop_or_audio(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        result = self.prepare(self.source, duration=.2, frame_at=.23)
        self.assertEqual(stock_media.stock_source_dimensions(result, 'video'), (1920, 1080))
        duration, silent, fps30 = stock_media._inspect(result)
        self.assertAlmostEqual(duration, .2, places=2)
        self.assertTrue(silent); self.assertTrue(fps30)
        frames = self.frame_pixels(result)
        self.assertEqual(len(frames), 6)
        self.assertEqual(len(set(frames)), 1)
        self.assertLess(frames[0][0], 20); self.assertGreater(frames[0][2], 220)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)

    def test_actual_neutral_portrait_is_static_dark_blue_silent_and_text_free(self):
        result = self.prepare(None, duration=.2, aspect_ratio='9:16')
        self.assertEqual(stock_media.stock_source_dimensions(result, 'video'), (1080, 1920))
        duration, silent, fps30 = stock_media._inspect(result)
        self.assertAlmostEqual(duration, .2, places=2)
        self.assertTrue(silent); self.assertTrue(fps30)
        frames = self.frame_pixels(result)
        self.assertEqual(len(frames), 6)
        self.assertEqual(len(set(frames)), 1)
        pixels = [frames[0][n:n+3] for n in range(0, len(frames[0]), 3)]
        self.assertEqual(len(set(pixels)), 1, 'Neutral contains no lettering or objects')
        red, green, blue = pixels[0]
        self.assertLess(red, green); self.assertLess(green, blue); self.assertLess(blue, 80)

    def test_four_three_freeze_preserves_normal_display_crop_without_bars(self):
        # Normal playback fills 16:9 and center-crops the top/bottom of 4:3.
        # These bands sit exactly outside that visible area after scaling.
        pattern = Image.new('RGB', (1440, 1080), '#00ff00')
        pattern.paste('#ff0000', (0, 0, 1440, 135))
        pattern.paste('#0000ff', (0, 945, 1440, 1080))
        image = self.root / 'four-three.png'
        pattern.save(image)
        source = self.root / 'four-three.mp4'
        command = [stock_media.ffmpeg_executable(), '-v', 'error', '-nostdin', '-y',
                   '-loop', '1', '-framerate', '30', '-i', str(image), '-frames:v', '6',
                   '-an', '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p',
                   '-threads', '1', '-filter_threads', '1', str(source)]
        subprocess.run(command, check=True, capture_output=True, timeout=20)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        result = self.prepare(source, duration=.2, frame_at=.03)
        frames = self.frame_pixels(result)
        self.assertEqual(len(frames), 6)
        self.assertEqual(len(set(frames)), 1)
        for x, y in [(3, 3), (60, 3), (3, 32), (60, 32), (32, 18)]:
            with self.subTest(pixel=(x, y)):
                offset = (y * 64 + x) * 3
                red, green, blue = frames[0][offset:offset+3]
                self.assertGreater(green, 200, 'Freeze must match the green normal-playback crop')
                self.assertLess(red, 40); self.assertLess(blue, 40)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_last_frame_time_near_end_uses_available_frame_without_fallback(self):
        result = self.prepare(self.source, duration=.2, frame_at=.4-.033)
        frames = self.frame_pixels(result)
        self.assertEqual(len(frames), 6)
        self.assertEqual(len(set(frames)), 1)
        self.assertGreater(frames[0][2], 220)

    def test_seek_beyond_one_second_freezes_requested_frame_not_later_frame(self):
        source = self.root / 'red-blue-green.mp4'
        command = [stock_media.ffmpeg_executable(), '-v', 'error', '-nostdin', '-y',
                   '-f', 'lavfi', '-i', 'color=c=red:s=1280x720:r=30:d=1',
                   '-f', 'lavfi', '-i', 'color=c=blue:s=1280x720:r=30:d=0.2',
                   '-f', 'lavfi', '-i', 'color=c=green:s=1280x720:r=30:d=1.2',
                   '-filter_complex', '[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]', '-map', '[v]',
                   '-an', '-c:v', 'libx264', '-crf', '0', '-pix_fmt', 'yuv420p',
                   '-threads', '1', '-filter_complex_threads', '1', str(source)]
        subprocess.run(command, check=True, capture_output=True, timeout=20)
        result = self.prepare(source, duration=.2, frame_at=1.03)
        frames = self.frame_pixels(result)
        self.assertEqual(len(set(frames)), 1)
        self.assertLess(frames[0][0], 20); self.assertGreater(frames[0][2], 220)

    def test_cache_reuse_avoids_encoder_and_corrupt_cache_is_rebuilt(self):
        result = self.prepare(self.source, duration=.2, frame_at=.03)
        original_hash = hashlib.sha256(result.read_bytes()).hexdigest()
        with patch('scriptor.stock_media._write_continuity_media', side_effect=AssertionError('unexpected encode')):
            self.assertEqual(self.prepare(self.source, duration=.2, frame_at=.03), result)
        result.write_bytes(b'corrupt derivative')
        rebuilt = self.prepare(self.source, duration=.2, frame_at=.03)
        self.assertEqual(rebuilt, result)
        self.assertEqual(hashlib.sha256(rebuilt.read_bytes()).hexdigest(), original_hash)

    def test_duration_frame_aspect_and_content_control_cache_identity(self):
        first = self.prepare(self.source, duration=.2, frame_at=.03)
        later = self.prepare(self.source, duration=.2, frame_at=.23)
        longer = self.prepare(self.source, duration=.21, frame_at=.03)
        square = self.prepare(self.source, duration=.2, frame_at=.03, aspect_ratio='1:1')
        self.assertEqual(len({first, later, longer, square}), 4)
        self.assertEqual(len(self.frame_pixels(longer)), 7)
        self.assertEqual(stock_media.stock_source_dimensions(square, 'video'), (1080, 1080))
        source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        alternate = self.root / 'different-source.mp4'
        alternate.write_bytes(later.read_bytes())
        changed = self.prepare(alternate, duration=.2, frame_at=.03)
        self.assertNotEqual(changed, first)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), source_hash)

    def test_valid_but_wrong_cached_clip_is_not_accepted_by_metadata_alone(self):
        red = self.prepare(self.source, duration=.2, frame_at=.03)
        blue = self.prepare(self.source, duration=.2, frame_at=.23)
        red.write_bytes(blue.read_bytes())
        result = self.prepare(self.source, duration=.2, frame_at=.03)
        frame = self.frame_pixels(result)[0]
        self.assertGreater(frame[0], 220); self.assertLess(frame[2], 20)

    def test_mutation_during_encoding_does_not_publish_derivative(self):
        helper = getattr(stock_media, 'prepare_continuity_media', None)
        writer = getattr(stock_media, '_write_continuity_media', None)
        if not callable(helper) or not callable(writer):
            self.fail('Literal continuity encoder is not implemented')
        def mutate(*args, **kwargs):
            writer(*args, **kwargs)
            self.source.write_bytes(b'changed test source while encoding')
        with (patch('scriptor.stock_media._write_continuity_media', side_effect=mutate),
              self.assertRaisesRegex(ValueError, 'changed')):
            helper(self.source, self.output, duration=.2, frame_at=.03)
        self.assertEqual(list(self.output.rglob('*.mp4')), [])

    def test_missing_corrupt_and_out_of_range_sources_raise_without_neutral_substitution(self):
        corrupt = self.root / 'corrupt.mp4'; corrupt.write_bytes(b'not a video')
        for source, frame_at in [(self.root / 'missing.mp4', 0), (corrupt, 0), (self.source, 5)]:
            with self.subTest(source=source.name, frame_at=frame_at), self.assertRaises((ValueError, RuntimeError)):
                self.prepare(source, duration=.2, frame_at=frame_at)

    def test_invalid_options_are_rejected_without_artifacts(self):
        for kwargs in ({'duration': 0}, {'duration': float('nan')}, {'duration': .2, 'frame_at': -.1},
                       {'duration': .2, 'aspect_ratio': 'bad'}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                self.prepare(None, **kwargs)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
