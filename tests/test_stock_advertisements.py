"""A dominant full-screen advertisement cannot hide in a stock mean vector."""
import hashlib
import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import IMAGE_MODEL, TEXT_MODEL, ClipIndex
from scriptor.stock_selection import StockSceneSelector


class FrameEmbedding:
    def __init__(self, replace_ad=False):
        self.calls = 0
        self.replace_ad = replace_ad

    def embed(self, images, **_kwargs):
        self.calls += 1
        values = {'scene': [1, 0, 0], 'ad': [0, 1, 0], 'night': [0, 0, 1],
                  'logo/subtitle': [.8, .3, math.sqrt(.27)],
                  'low-ad-absolute': [.1, .25, math.sqrt(.9275)],
                  'weak-ad-margin': [.25, .3, math.sqrt(.8475)],
                  'weak-scene': [.1, .15, math.sqrt(.9675)]}
        for name in images:
            yield np.asarray(values['night' if name == 'ad' and self.replace_ad else name], dtype=np.float32)


class QueryEmbedding:
    def __init__(self, replace_ad=False):
        self.replace_ad = replace_ad
        self.queries = []

    def query_embed(self, query):
        self.queries.append(query)
        vector = [1, 0, 0]
        if query == 'advertisement software title card':
            vector = [0, 0, 1] if self.replace_ad else [0, 1, 0]
        yield np.asarray(vector, dtype=np.float32)


class StockAdvertisementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='newsflow-stock-ads-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / 'preview.mp4'
        self.path.write_bytes(b'ads')
        self.image_model = FrameEmbedding()
        self.text_model = QueryEmbedding()
        self.index = ClipIndex(self.root / 'index.sqlite3',
                               embedder_factory=lambda: (self.image_model, self.text_model))
        self.sampled = []
        self.images = ['scene', 'ad', 'scene']

        def sample(path):
            self.sampled.append(path)
            return (self.images if path.read_bytes() == b'ads' else ['scene'] * 3), 6, 1920, 1080, 30

        sampler = patch.object(self.index, '_sample_frames', side_effect=sample)
        sampler.start(); self.addCleanup(sampler.stop)
        self.query = 'aircraft flight airport runway'
        self.selector = self.make_selector(self.index)

    def make_selector(self, index):
        return StockSceneSelector(mode='stock', service=SimpleNamespace(enabled=[]), index=index,
            cache_root=self.root / 'cache', threshold=.22, trim=True, aspect_ratio='16:9',
            semantic_ok=lambda *_args: True, source_allowed=lambda *_args: True,
            duration_probe=lambda _path: 6, checkpoint=lambda: None)

    def test_dominant_ad_frame_rejected_while_default_mean_stays_unchanged(self):
        # Two aircraft frames plus one ad have a misleading mean of2/sqrt(5).
        self.assertAlmostEqual(self.index.score_file(self.path, self.query), .89442719, places=6)
        self.assertLess(self.selector._score(self.path, self.query), .22)
        self.assertEqual(len(self.sampled), 1)

    def test_old_positive_stock_cache_cannot_bypass_ad_frame_guard(self):
        model = f'{IMAGE_MODEL}|{TEXT_MODEL}|frames-v1|{type(self.index).__module__}.{type(self.index).__qualname__}'
        identity = hashlib.sha256(f'{hashlib.sha256(self.path.read_bytes()).hexdigest()}|{self.query}|{model}|stock-score-v1'.encode()).hexdigest()
        cache = self.root / 'cache'; cache.mkdir(exist_ok=True)
        with closing(sqlite3.connect(cache / 'visual-verdicts.sqlite3')) as db, db:
            db.execute('CREATE TABLE scores (id TEXT PRIMARY KEY, score REAL NOT NULL)')
            db.execute('INSERT INTO scores VALUES (?, ?)', (identity, .9))
        self.assertLess(self.selector._score(self.path, self.query), .22)
        self.assertEqual(len(self.sampled), 1)

    def test_night_sky_subtitles_and_logos_keep_original_mean_score(self):
        self.images = ['scene', 'night', 'logo/subtitle']
        plain = self.index.score_file(self.path, self.query)
        self.assertEqual(self.selector._score(self.path, self.query), plain)
        self.assertGreater(plain, .22)

    def test_weak_ad_absolute_score_does_not_reject_normal_scene(self):
        self.images = ['scene', 'low-ad-absolute', 'scene']
        plain = self.index.score_file(self.path, self.query)
        self.assertEqual(self.selector._score(self.path, self.query), plain)

    def test_weak_ad_margin_does_not_reject_normal_scene(self):
        self.images = ['scene', 'weak-ad-margin', 'scene']
        plain = self.index.score_file(self.path, self.query)
        self.assertEqual(self.selector._score(self.path, self.query), plain)

    def test_weak_scene_without_ad_preserves_its_original_low_score(self):
        self.images = ['weak-scene'] * 3
        self.assertAlmostEqual(self.selector._score(self.path, self.query), .1, places=6)

    def test_same_size_same_mtime_content_change_invalidates_frame_verdict(self):
        self.assertLess(self.selector._score(self.path, self.query), .22)
        original = self.path.stat()
        self.path.write_bytes(b'new')
        os.utime(self.path, ns=(original.st_atime_ns, original.st_mtime_ns))
        self.assertEqual(self.selector._score(self.path, self.query), 1.0)
        self.assertEqual(len(self.sampled), 2)

    def test_image_model_replacement_recomputes_per_frame_features(self):
        # Exercise the index directly: persistent selector model-versioning is
        # separate from an in-memory embedder replacement within one instance.
        self.assertLess(self.selector._score(self.path, self.query), .22)
        self.index._image_embedder = FrameEmbedding(replace_ad=True)
        scorer = getattr(self.index, 'score_stock_file', self.index.score_file)
        self.assertGreater(scorer(self.path, self.query), .22)
        self.assertEqual(len(self.sampled), 2)

    def test_text_model_replacement_invalidates_negative_query_embedding(self):
        self.assertLess(self.selector._score(self.path, self.query), .22)
        self.index._text_embedder = QueryEmbedding(replace_ad=True)
        scorer = getattr(self.index, 'score_stock_file', self.index.score_file)
        self.assertGreater(scorer(self.path, self.query), .22)
        self.assertEqual(len(self.sampled), 1)

    def test_legacy_and_dynamic_index_doubles_use_normal_score_file(self):
        class DynamicIndex:
            def score_file(self, *_args):
                return .7
            def __getattr__(self, _name):
                return lambda *_args: .99
        for index in (SimpleNamespace(score_file=lambda *_args: .7), DynamicIndex()):
            with self.subTest(kind=type(index).__name__):
                self.assertEqual(self.make_selector(index)._score(self.path, self.query), .7)


if __name__ == '__main__':
    unittest.main()
