"""Preview scores reuse image work without confusing changed bytes or models."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import ClipIndex


class ImageEmbedding:
    def __init__(self, reverse=False):
        self.calls = 0
        self.reverse = reverse

    def embed(self, images, **_kwargs):
        self.calls += 1
        for image in images:
            vector = [3.0, 4.0] if image == b'red' else [4.0, 3.0]
            yield np.asarray(vector[::-1] if self.reverse else vector, dtype=np.float32)


class TextEmbedding:
    def __init__(self):
        self.queries = []

    def query_embed(self, query):
        self.queries.append(query)
        yield np.asarray([1.0, 0.0] if query == 'red' else [0.0, 1.0], dtype=np.float32)


class PreviewCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='newsflow-preview-cache-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.clip = self.root / 'preview.mp4'
        self.clip.write_bytes(b'red')
        self.image_model = ImageEmbedding()
        self.text_model = TextEmbedding()
        self.index = ClipIndex(self.root / 'index.sqlite3',
                               embedder_factory=lambda: (self.image_model, self.text_model))
        self.sampled = []

        def sample(path):
            self.sampled.append(path)
            return [path.read_bytes()] * 3, 6.0, 1920, 1080, 30.0

        self.sampler = patch.object(self.index, '_sample_frames', side_effect=sample)
        self.sampler.start()
        self.addCleanup(self.sampler.stop)

    def test_different_queries_reuse_image_work_and_keep_independent_score_math(self):
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .6, places=6)
        self.assertAlmostEqual(self.index.score_file(self.clip, 'blue'), .8, places=6)
        self.assertEqual(len(self.sampled), 1)
        self.assertEqual(self.image_model.calls, 1)
        self.assertEqual(self.text_model.queries, ['red', 'blue'])
        with self.index._connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM clips').fetchone()[0], 0)

    def test_stock_visual_comparison_reuses_scored_frames_and_invalidates_changed_content(self):
        self.index.score_stock_file(self.clip, 'red')
        features = self.index.stock_visual_features(self.clip)
        np.testing.assert_allclose(features.mean, [.6, .8])
        self.assertEqual(len(features.frames), 3)
        self.assertEqual(len(self.sampled), 1)
        original = self.clip.stat()
        self.clip.write_bytes(b'blu')
        os.utime(self.clip, ns=(original.st_atime_ns, original.st_mtime_ns))
        changed = self.index.stock_visual_features(self.clip)
        np.testing.assert_allclose(changed.mean, [.8, .6])
        self.assertEqual(len(self.sampled), 2)

    def test_same_size_same_mtime_overwrite_recomputes_from_content(self):
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .6, places=6)
        stat = self.clip.stat()
        self.clip.write_bytes(b'blu')
        os.utime(self.clip, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(self.clip.stat().st_size, stat.st_size)
        self.assertEqual(self.clip.stat().st_mtime_ns, stat.st_mtime_ns)
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .8, places=6)
        self.index.score_file(self.clip, 'blue')
        self.assertEqual(len(self.sampled), 2)

    def test_replacing_image_model_invalidates_old_image_vectors(self):
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .6, places=6)
        self.index._image_embedder = ImageEmbedding(reverse=True)
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .8, places=6)
        self.index.score_file(self.clip, 'blue')
        self.assertEqual(len(self.sampled), 2)

    def test_mutation_during_decode_cannot_poison_cache_for_original_bytes(self):
        original_stat = self.clip.stat()

        def mutate(path):
            path.write_bytes(b'blu')
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            self.sampled.append(path)
            return [b'blu'] * 3, 6.0, 1920, 1080, 30.0

        with patch.object(self.index, '_sample_frames', side_effect=mutate):
            self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .8, places=6)
        self.clip.write_bytes(b'red')
        os.utime(self.clip, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .6, places=6)
        self.index.score_file(self.clip, 'blue')
        self.assertEqual(len(self.sampled), 2)

    def test_cache_is_bounded_and_evicts_old_vectors(self):
        for number in range(65):
            self.clip.write_bytes(f'clip-{number:03d}'.encode())
            self.index.score_file(self.clip, 'red')
        self.clip.write_bytes(b'clip-000')
        self.index.score_file(self.clip, 'red')
        self.assertEqual(len(self.sampled), 66)
        self.index.score_file(self.clip, 'blue')
        self.assertEqual(len(self.sampled), 66)

    def test_failed_decode_is_not_cached(self):
        with (patch.object(self.index, '_sample_frames', side_effect=ValueError('decode failed')),
              self.assertRaisesRegex(ValueError, 'decode failed')):
            self.index.score_file(self.clip, 'red')
        self.assertAlmostEqual(self.index.score_file(self.clip, 'red'), .6, places=6)
        self.index.score_file(self.clip, 'blue')
        self.assertEqual(len(self.sampled), 1)


if __name__ == '__main__':
    unittest.main()
