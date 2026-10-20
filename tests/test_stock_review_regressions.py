"""Independent review regressions: disposable storage and fake transport only."""
from __future__ import annotations

import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge, config, stock_selection
from scriptor.footage import FootageItem
from scriptor.stock_sources import StockCandidate
from scriptor.timeline import TimelineClip, TimelineProject
from tests import test_stock_pipeline as pipeline_fixture


class StockReviewRegressionTests(unittest.TestCase):
    def setUp(self):
        # Reuse setup/helpers without subclassing or importing its TestCase
        # into this module's namespace (which duplicates unittest discovery).
        pipeline_fixture.StockPipelineTests.setUp(self)

    def _selector(self, service):
        return stock_selection.StockSceneSelector(mode='stock', service=service,
            index=SimpleNamespace(score_file=lambda *_args: .8), cache_root=self.root / 'review-cache',
            threshold=.22, trim=False, aspect_ratio='16:9', semantic_ok=lambda *_args: True,
            source_allowed=lambda *_args: True, duration_probe=lambda *_args: 10.0, checkpoint=lambda: None)

    @staticmethod
    def _candidate(asset_id):
        return StockCandidate('pexels', asset_id, 'Cargo train',
            f'https://videos.pexels.com/{asset_id}.mp4', f'https://www.pexels.com/video/{asset_id}/',
            'Pexels License', 'https://www.pexels.com/license/', 'Test artist')

    def test_preparation_persists_stock_family_that_selector_can_deprioritize(self):
        project = pipeline_fixture.StockPipelineTests.prepare(self, 'stock')
        original_family = 'stock-sha256::' + hashlib.sha256(b'stock-fixture').hexdigest()
        self.assertEqual(project.clips[0].source_family, original_family)
        history = getattr(config.load_settings(), 'montage_stock_recent_families', [])
        self.assertIn(original_family, history,
            'Persist the original stock family, rather than only a derivative path')
        fresh = self.root / 'fresh-stock.mp4'
        fresh.write_bytes(b'fresh stock original')
        originals = {'old': self.stock, 'fresh': fresh}
        service = SimpleNamespace(enabled=('pexels',), cached=lambda *_args, **_kwargs: [],
            search=lambda *_args, **_kwargs: [self._candidate('old'), self._candidate('fresh')],
            fetch=lambda item: originals[item.asset_id])
        selector = self._selector(service)
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_args, **_kwargs: source):
            choice = selector.select(self.scenes[0], {}, ['cargo train'], used_families=set(), history_families=history)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.item.path, str(fresh))

    def test_project_repair_settings_are_independent_from_shared_template(self):
        helper = getattr(bridge, '_project_repair_settings', None)
        self.assertTrue(callable(helper), 'Project repair needs an independent settings copy')
        settings = config.Settings(montage_source_mode='hybrid', montage_stock_sources=['pexels'], montage_stock_trim=True)
        project = TimelineProject('Saved stock project', source_policy={
            'mode': 'stock', 'sources': ['nasa'], 'trim': False, 'uniquePercent': 40})
        repaired_settings = helper(settings, project)
        self.assertIsNot(repaired_settings, settings)
        self.assertEqual((repaired_settings.montage_source_mode, repaired_settings.montage_stock_sources,
                          repaired_settings.montage_stock_trim), ('stock', ['nasa'], False))
        repaired_settings.montage_stock_sources.append('wikimedia')
        self.assertEqual((settings.montage_source_mode, settings.montage_stock_sources,
                          settings.montage_stock_trim), ('hybrid', ['pexels'], True))

    def test_project_repair_preserves_saved_aspect_instead_of_current_template(self):
        settings = config.Settings(montage_aspect_ratio='9:16')
        project = TimelineProject('Wide', aspect_ratio='16:9', source_policy={'mode': 'stock'})
        self.assertEqual(bridge._project_repair_settings(settings, project).montage_aspect_ratio, '16:9')

    def test_own_project_reuse_does_not_reclaim_its_batch_family(self):
        self.scenes = [{**self.scenes[0], 'duration': 1.0, 'minimum_footage_duration': 1.0} for _ in range(3)]
        item = FootageItem(str(self.stock), 'Cargo train', 'pexels')
        first = stock_selection.StockChoice(item, 10, .8, 'family-a', provenance={'provider': 'pexels'})
        second = stock_selection.StockChoice(item, 10, .8, 'family-b', provenance={'provider': 'pexels'})
        reused = stock_selection.StockChoice(item, 10, .8, 'family-a', provenance={'provider': 'pexels'}, reused=True)
        seen = set()
        def claim(_usage, family, *_args, **_kwargs):
            if family in seen:
                return False
            seen.add(family)
            return True
        with patch.object(bridge, '_claim_batch_family', side_effect=claim), \
             patch.object(stock_selection.StockSceneSelector, 'select', side_effect=[first, second] + [reused] * 8):
            project = pipeline_fixture.StockPipelineTests.prepare(self, 'stock', fast_reuse=True)
        self.assertEqual(len(project.clips), 3)
        self.assertFalse(project.manual_replacements)

    def test_provider_fetch_cancellation_propagates_instead_of_becoming_exhaustion(self):
        def cancelled(_item):
            raise InterruptedError('production reset')
        service = SimpleNamespace(enabled=('pexels',), cached=lambda *_args, **_kwargs: [],
            search=lambda *_args, **kwargs: [self._candidate('cancel')] if kwargs.get('kind') == 'video' else [],
            fetch=cancelled)
        with self.assertRaises(InterruptedError):
            self._selector(service).select(self.scenes[0], {}, ['cargo train'], used_families=set())

    def test_missing_clip_repair_replaces_stock_attribution_family_and_score(self):
        replacement_type = getattr(stock_selection, 'StockReplacementItem', None)
        self.assertIsNotNone(replacement_type, 'Repair must carry the new selected asset metadata')
        missing = self.root / 'missing.mp4'
        new_path = self.root / 'replacement.mp4'
        new_path.write_bytes(b'new original')
        old_provenance = {'provider': 'pexels', 'asset_id': 'old', 'author': 'Old author'}
        new_provenance = {'provider': 'pixabay', 'asset_id': 'new', 'author': 'New author',
                          'license': 'Pixabay Content License'}
        new_family = 'stock-sha256::' + hashlib.sha256(b'new original').hexdigest()
        clip = TimelineClip(str(missing), 'Грузовой поезд', 'cargo train', 3.0, source='pexels',
            source_family='stock-sha256::old', score=.7, stock_provenance=old_provenance,
            voice_segment_ids=[17], narration_start=0.0, narration_end=3.0)
        project = TimelineProject('Repair', clips=[clip])
        item = replacement_type(path=str(new_path), name='Cargo train', source='pixabay',
            source_url='https://pixabay.com/videos/id-new/', license='Pixabay Content License',
            source_family=new_family, stock_provenance=new_provenance, selection_score=.91)
        with patch.object(bridge, '_validated_montage_clip_duration',
                          side_effect=lambda path: 10.0 if path == new_path else 0.0):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_args: [item]), 1)
        repaired = project.clips[0]
        self.assertEqual(repaired.stock_provenance, new_provenance)
        self.assertEqual(repaired.source_family, new_family)
        self.assertEqual(repaired.score, .91)
        self.assertEqual(repaired.voice_segment_ids, [17])
        self.assertEqual((repaired.narration_start, repaired.narration_end), (0.0, 3.0))

    def test_denied_batch_source_is_never_appended_to_prepared_project(self):
        denied = 'stock-sha256::' + hashlib.sha256(b'stock-fixture').hexdigest()
        def claim(_usage, family, *_args, **_kwargs):
            return family != denied
        with patch.object(bridge, '_claim_batch_family', side_effect=claim):
            project = pipeline_fixture.StockPipelineTests.prepare(self, 'stock')
        self.assertFalse(any(clip.source_family == denied for clip in project.clips),
            'A rejected reservation must trigger another candidate or a saved manual replacement')
        self.assertTrue(project.manual_replacements or project.clips)


if __name__ == '__main__':
    unittest.main()
