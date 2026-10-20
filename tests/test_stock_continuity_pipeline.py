"""Always-on gap filling crosses persisted settings, preparation and rendering."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge, config, montage_continuity
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject
from tests import test_stock_pipeline as fixture


class StockContinuityPipelineTests(unittest.TestCase):
    setUp = fixture.StockPipelineTests.setUp
    prepare = fixture.StockPipelineTests.prepare

    def fake_hold(self, _source, root, **_kwargs):
        target = Path(root) / 'neutral.mp4'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'test-only prepared still')
        return target

    def test_empty_source_plan_completes_with_background_when_enabled(self):
        with patch.object(montage_continuity, 'prepare_continuity_media', side_effect=self.fake_hold):
            project = self.prepare('stock', empty=True)
        self.assertFalse(project.manual_replacements)
        self.assertEqual(len(project.clips), 1)
        self.assertEqual(project.clips[0].fallback_level, 'CONTINUITY_BACKGROUND')
        self.assertEqual(project.clips[0].voice_segment_ids, [17])
        self.assertEqual(project.clips[0].narration_end, 3)
        self.assertTrue(project.source_policy['autoFillGaps'])
        self.assertFalse(project.source_policy['stockHdOnly'])
        self.assertEqual(project.selection_summary['uniqueActualFamilies'], 0)

    def test_checkbox_commands_persist_false_and_true_values_strictly(self):
        self.prepare('stock')
        result = bridge.save_montage_settings({'stockHdOnly': False})
        self.assertFalse(config.load_settings().montage_stock_hd_only)
        self.assertFalse(result['montageSettings']['stockHdOnly'])
        for key in ('stockHdOnly',):
            with self.subTest(key=key), self.assertRaises(ValueError):
                bridge.save_montage_settings({key: 'false'})

    def test_saved_manual_project_uses_its_policy_for_direct_render(self):
        project = self.prepare('stock')
        original = project.clips.pop()
        project.manual_replacements = [{'sceneIndex': 0, 'narration': original.narration,
            'visualQuery': original.visual_query_en, 'duration': original.duration,
            'narrationStart': original.narration_start, 'narrationEnd': original.narration_end,
            'voiceSegmentIds': original.voice_segment_ids}]
        # Even old opt-out markers must no longer force a manual stop.
        project.source_policy['autoFillGaps'] = False
        project.save(Path(self.project_path))
        seen = []
        def render(value, output, **_kwargs):
            seen.append(value)
            self.assertFalse(value.manual_replacements)
            self.assertEqual(len(value.clips), 1)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b'test-only output')
            return output
        with patch.object(montage_continuity, 'prepare_continuity_media', side_effect=self.fake_hold), \
             patch.object(bridge, 'render_project', side_effect=render), \
             patch.object(bridge, 'validate_rendered_montage', return_value=3):
            bridge.render_montage({'projectPath': self.project_path})
        self.assertEqual(len(seen), 1)
        saved = TimelineProject.load(Path(self.project_path))
        self.assertFalse(saved.manual_replacements)
        self.assertTrue(saved.clips[0].continuity)

    def test_saved_policy_overrides_current_checkbox_template(self):
        settings = config.Settings(montage_stock_hd_only=True)
        project = TimelineProject('T', source_policy={'mode': 'stock', 'autoFillGaps': True, 'stockHdOnly': False})
        scoped = bridge._project_repair_settings(settings, project)
        self.assertFalse(scoped.montage_stock_hd_only)
        self.assertTrue(settings.montage_stock_hd_only)

    def test_selected_stock_retains_native_visual_beat_index(self):
        self.scenes[0]['visual_beat_index'] = 7
        project = self.prepare('stock')
        self.assertEqual(project.clips[0].visual_beat_index, 7)

    def test_automatic_gap_retains_native_visual_beat_index(self):
        self.scenes[0]['visual_beat_index'] = 7
        with patch.object(montage_continuity, 'prepare_continuity_media', side_effect=self.fake_hold):
            project = self.prepare('stock', empty=True)
        self.assertEqual(project.clips[0].visual_beat_index, 7)

    def test_real_replacement_clears_previous_hold_metadata(self):
        missing = self.root / 'deleted-hold.mp4'
        replacement = self.root / 'replacement.mp4'
        replacement.write_bytes(b'fixture')
        project = TimelineProject('T', clips=[TimelineClip(str(missing), 'N', 'Q', duration=3,
            continuity={'mode': 'freeze', 'anchorFamily': 'old'}, fallback_level='CONTINUITY_HOLD')])
        with patch.object(bridge, '_validated_montage_clip_duration',
                          side_effect=lambda path: 10 if path == replacement else 0):
            changed = bridge._repair_missing_project_clips(project,
                lambda *_args: [FootageItem(str(replacement), 'actual moving replacement')])
        self.assertEqual(changed, 1)
        self.assertFalse(project.clips[0].continuity)
        self.assertEqual(project.selection_summary['held'], 0)

    def test_repair_tries_thematic_selection_before_holding(self):
        from scriptor.stock_selection import StockChoice
        settings = config.Settings(montage_source_mode='stock',
            footage_download_folder=str(self.root / 'downloads'))
        clip = TimelineClip('missing.mp4', 'N', 'airport runway', duration=3)
        selected = StockChoice(FootageItem(str(self.stock), 'Airport', 'wikimedia'), 3, .8, 'actual-family')
        context_calls = []
        selector = SimpleNamespace(select=lambda *_a, **_k: None,
            select_context=lambda *args, **_kwargs: context_calls.append(args[2]) or selected)
        index = SimpleNamespace(search_many=lambda queries, **_kwargs: [[] for _ in queries])
        with patch.object(bridge, 'StockService'), patch.object(bridge, 'StockSceneSelector', return_value=selector):
            result = bridge._replacement_candidates_for_clip(index, clip, settings)
        self.assertTrue(context_calls)
        self.assertEqual(result[0].path, str(self.stock))


if __name__ == '__main__':
    unittest.main()
