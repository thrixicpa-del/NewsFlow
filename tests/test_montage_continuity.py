"""Gap filling preserves each existing narration beat, not a new scene map."""
import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import montage_continuity
from scriptor.timeline import TimelineClip, TimelineProject


class MontageContinuityTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.anchor = self.root / 'allowed.mp4'
        self.anchor.write_bytes(b'unchanged authorized fixture')
        self.calls = []

        def prepare(source, output, **kwargs):
            self.calls.append((source, kwargs))
            target = Path(output) / f'hold-{len(self.calls)}.mp4'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'prepared test fixture')
            return target

        self.preparer = patch.object(montage_continuity, 'prepare_continuity_media', side_effect=prepare)
        self.preparer.start()
        self.addCleanup(self.preparer.stop)

    def clip(self, index, *, path=None):
        return TimelineClip(str(path or self.anchor), f'Words {index}', 'airport control room',
            duration=3, source_start=1, source_family=f'family-{index}',
            voice_segment_id=index + 1, voice_segment_ids=[index + 1],
            narration_start=index * 3, narration_end=(index + 1) * 3,
            stock_provenance={'provider': 'wikimedia', 'asset_id': str(index),
                              'originalStart': 1, 'selectedDuration': 3, 'license': 'CC BY 4.0'})

    def gap(self, index):
        return {'sceneIndex': index, 'narration': f'Words {index}',
                'visualQuery': 'airport control room', 'duration': 3,
                'narrationStart': index * 3, 'narrationEnd': (index + 1) * 3,
                'voiceSegmentIds': [index + 1], 'reason': 'no permitted material'}

    def resolve(self, project, **kwargs):
        return montage_continuity.resolve_project_continuity(project, self.root / 'cache',
            duration_probe=lambda _path: 10.0, **kwargs)

    def test_middle_and_trailing_gaps_hold_previous_frame_without_shifting_next(self):
        first, later = self.clip(0), self.clip(2)
        project = TimelineProject('T', clips=[first, later], voiceover_path='unchanged.wav',
            manual_replacements=[self.gap(1), self.gap(3)])
        self.assertEqual(self.resolve(project), 2)
        self.assertFalse(project.manual_replacements)
        self.assertEqual(project.duration, 12)
        self.assertEqual([clip.narration for clip in project.clips], [f'Words {i}' for i in range(4)])
        self.assertEqual([clip.narration_start for clip in project.clips], [0, 3, 6, 9])
        self.assertIs(project.clips[0], first)
        self.assertIs(project.clips[2], later)
        self.assertEqual(project.clips[1].source_family, first.source_family)
        self.assertTrue(project.clips[1].reused)
        self.assertEqual(project.clips[1].fallback_level, 'CONTINUITY_HOLD')
        self.assertAlmostEqual(self.calls[0][1]['frame_at'], 4 - 1 / 30)
        self.assertEqual(project.voiceover_path, 'unchanged.wav')
        self.assertEqual(first.stock_provenance, self.clip(0).stock_provenance)

    def test_leading_and_consecutive_gaps_hold_first_frame_of_next_accepted_clip(self):
        anchor = self.clip(2)
        project = TimelineProject('T', clips=[anchor], manual_replacements=[self.gap(0), self.gap(1)])
        self.assertEqual(self.resolve(project), 2)
        self.assertEqual([call[1]['frame_at'] for call in self.calls], [1, 1])
        self.assertIs(project.clips[-1], anchor)
        self.assertEqual([clip.voice_segment_ids for clip in project.clips], [[1], [2], [3]])

    def test_no_licensed_source_generates_neutral_background_without_manual_stop(self):
        project = TimelineProject('T', manual_replacements=[self.gap(0), self.gap(1)])
        self.assertEqual(self.resolve(project), 2)
        self.assertFalse(project.manual_replacements)
        self.assertEqual(project.duration, 6)
        self.assertTrue(all(source is None for source, _kwargs in self.calls))
        self.assertTrue(all(clip.fallback_level == 'CONTINUITY_BACKGROUND' for clip in project.clips))
        self.assertTrue(all(not clip.stock_provenance for clip in project.clips))

    def test_deleted_existing_clip_is_recovered_without_modifying_healthy_edit(self):
        first = self.clip(0)
        missing = self.clip(1, path=self.root / 'deleted.mp4')
        project = TimelineProject('T', clips=[first, missing])
        self.assertEqual(self.resolve(project, missing_paths={missing.path}), 1)
        self.assertIs(project.clips[0], first)
        self.assertEqual(project.clips[1].narration_end, 6)
        self.assertEqual(project.clips[1].voice_segment_ids, [2])

    def test_no_gap_is_a_noop_and_pause_cancellation_propagates(self):
        project = TimelineProject('T', clips=[self.clip(0)])
        self.assertEqual(self.resolve(project), 0)
        self.assertFalse(self.calls)
        project.manual_replacements = [self.gap(1)]
        before = copy.deepcopy(project)
        with self.assertRaisesRegex(InterruptedError, 'cancelled'):
            self.resolve(project, checkpoint=lambda: (_ for _ in ()).throw(InterruptedError('cancelled')))
        self.assertEqual(project, before)

    def test_hold_metadata_survives_save_reload(self):
        project = TimelineProject('T', clips=[self.clip(0)], manual_replacements=[self.gap(1)])
        self.resolve(project)
        saved = self.root / 'project.newsflow'
        project.save(saved)
        loaded = TimelineProject.load(saved)
        self.assertEqual(loaded, project)
        self.assertEqual(loaded.clips[1].continuity['anchorFamily'], 'family-0')

    def test_media_probe_prepare_and_frame_guard_cancellation_leave_plan_untouched(self):
        def cancelled(*_args, **_kwargs):
            raise InterruptedError('cancelled by user')

        prepared_media = montage_continuity.prepare_continuity_media
        for stage in ('probe', 'prepare', 'guard'):
            with self.subTest(stage=stage):
                project = TimelineProject('T', clips=[self.clip(0)], manual_replacements=[self.gap(1)])
                before = copy.deepcopy(project)
                arguments = {'duration_probe': cancelled} if stage == 'probe' else {}
                if stage == 'guard':
                    arguments['source_allowed'] = cancelled
                with patch.object(montage_continuity, 'prepare_continuity_media',
                                  side_effect=cancelled if stage == 'prepare' else prepared_media), \
                     self.assertRaisesRegex(InterruptedError, 'cancelled by user'):
                    montage_continuity.resolve_project_continuity(project, self.root / 'cache',
                        **({'duration_probe': lambda _path: 10.0} | arguments))
                self.assertEqual(project, before)

    def test_hold_does_not_invent_an_original_source_window_in_history(self):
        from scriptor.stock_history import StockUsageHistory
        gap = {**self.gap(1), 'duration': 6, 'narrationEnd': 9}
        project = TimelineProject('T', clips=[self.clip(0)], manual_replacements=[gap])
        self.resolve(project)
        history = StockUsageHistory(self.root / 'history')
        history.record('project', project.clips)
        families, windows = history.snapshot(['family-0'])
        self.assertEqual(families['family-0'][0], 1)
        self.assertEqual(set(windows), {('family-0', 1000, 4000)})

    def test_credits_describe_freeze_without_leaking_anchor_paths(self):
        from scriptor.stock_credits import stage_stock_credits
        project = TimelineProject('T', clips=[self.clip(0)], manual_replacements=[self.gap(1)])
        self.resolve(project)
        pairs = stage_stock_credits(project, self.root / 'staged/out.mp4', self.root / 'out.mp4')
        manifest = json.loads(pairs[0][0].read_text(encoding='utf-8'))
        self.assertIn('Freeze-frame', manifest['materials'][0]['changes'])
        self.assertNotIn(str(self.anchor), pairs[0][0].read_text(encoding='utf-8'))

    def test_rejected_frozen_frame_tries_another_anchor_then_neutral(self):
        first, later = self.clip(0), self.clip(2)
        for allow_future in (True, False):
            with self.subTest(allow_future=allow_future):
                project = TimelineProject('T', clips=[first, later], manual_replacements=[self.gap(1)])
                self.resolve(project, source_allowed=lambda _path, anchor, _slot, allow=allow_future:
                    allow and anchor is later)
                expected = 'CONTINUITY_HOLD' if allow_future else 'CONTINUITY_BACKGROUND'
                self.assertEqual(project.clips[1].fallback_level, expected)
                self.assertEqual(project.clips[1].continuity['anchorFamily'], later.source_family if allow_future else '')

    def test_frame_validation_error_never_publishes_unvalidated_frozen_frame(self):
        project = TimelineProject('T', clips=[self.clip(0)], manual_replacements=[self.gap(1)])
        def failed_guard(*_args):
            raise RuntimeError('cannot validate decoded frame')
        self.resolve(project, source_allowed=failed_guard)
        self.assertIsNone(self.calls[-1][0], 'A failed validation must generate neutral pixels')
        self.assertEqual(project.clips[1].path, str(self.root / 'cache' / f'hold-{len(self.calls)}.mp4'))
        self.assertFalse(project.clips[1].stock_provenance)


if __name__ == '__main__':
    unittest.main()
