"""Independent synthetic review probes. No original media or production writes."""
import unittest
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings
from scriptor.timeline import TimelineClip, TimelineProject
from tests import test_footage_political_context as contracts


class IndependentPoliticalReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = contracts.PoliticalContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_context_does_not_add_unmentioned_foreign_politician(self):
        with self.assertRaisesRegex(RuntimeError, 'Нет допустимого тематического'):
            self.fixture.prepare(
                'В Беларуси прошёл митинг. Лукашенко прокомментировал требования.',
                ['Belarus peaceful protest placards'],
                [self.fixture.item('Lukashenko_Putin_meeting.mp4')])

    def test_coordinated_foreign_flags_remain_a_contradiction(self):
        item = self.fixture.item('Belarus_rally_Russian_and_Belarusian_flags.mp4')
        self.assertFalse(bridge._semantic_clip_ok(
            'Belarus peaceful protest placards', item,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'peaceful_protest'}))

    def test_named_foreign_flag_outside_current_cis_aliases_is_rejected(self):
        item = self.fixture.item('Armenia_rally_Turkish_flags.mp4')
        self.assertFalse(bridge._semantic_clip_ok(
            'Armenia peaceful protest placards', item,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'peaceful_protest'}))

    def test_mirziyoyev_subject_survives_yo_normalization(self):
        from scriptor.scene_intent import visual_intent
        from scriptor.timeline import VISUAL_TERMS
        for name in ('Мирзиёев', 'Мирзиеев'):
            with self.subTest(name=name):
                intent = visual_intent(f'{name} выступил с заявлением в Ташкенте.', VISUAL_TERMS)
                self.assertEqual(['mirziyoyev'], intent['target_people'])

    def test_archive_does_not_hide_foreign_politician_in_partial_curated_overlap(self):
        item = self.fixture.item('Lukashenko_address_curated_overlap.mp4')
        stat = self.fixture.root.joinpath(item.name).stat()
        item.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                                'observations': [
                                    {'person_id': 'lukashenko', 'start': 0., 'end': 6.,
                                     'source': 'manual', 'complete': True},
                                    {'person_id': 'putin', 'start': 3., 'end': 6.,
                                     'source': 'manual', 'complete': True}]}
        self.assertFalse(bridge._semantic_clip_ok(
            'archival political context, Alexander Lukashenko Belarus official statement', item,
            source_start=0., duration=6.,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'official'}))

    def test_explicit_bilateral_host_flag_is_not_foreign(self):
        self.assertFalse(bridge._montage_flag_conflict(
            'Alexander Lukashenko Belarus Germany diplomatic meeting',
            'Lukashenko_Belarus_delegation_German_flags_meeting.mp4'))

    def test_archive_fallback_preserves_fast_reuse_exact_proxy_windows(self):
        def fast_settings(**kwargs):
            return Settings(**kwargs, montage_fast_reuse_enabled=True,
                            montage_unique_footage_percent=5)
        with patch.object(contracts, 'Settings', side_effect=fast_settings):
            project = self.fixture.prepare(
                'В Беларуси прошёл митинг. Лукашенко прокомментировал требования.',
                ['Belarus peaceful protest placards'] * 4,
                [self.fixture.item('Lukashenko_address.mp4')])
        self.assertEqual(2, project.selection_summary['uniqueTargetScenes'])
        origins = {}
        for clip in project.clips[:2]:
            origins.setdefault(clip.path, clip.source_start)
        for clip in project.clips[2:]:
            self.assertEqual(origins[clip.path], clip.source_start)

    def archive_clip(self, path):
        query = 'Alexander Lukashenko, belarus official statement press conference interview'
        return TimelineClip(str(path), 'В Беларуси прошёл митинг.', query, 6.,
                            selection_diagnostics={'political_context': {
                                'archival_context': True, 'event_confirmed': False,
                                'requested_visual_query': 'Belarus peaceful protest placards',
                                'context_visual_query': query}})

    def test_archive_source_repair_keeps_unmentioned_person_exclusion(self):
        bad = self.fixture.item('Lukashenko_Putin_meeting_repair.mp4')
        project = TimelineProject('Belarus Lukashenko', clips=[self.archive_clip(
            self.fixture.root / 'missing-source.mp4')])
        with patch.object(bridge, '_validated_montage_clip_duration',
                          side_effect=lambda path: 8. if path.is_file() else 0.):
            self.assertEqual(0, bridge._repair_missing_project_clips(
                project, lambda *_: [bad]))

    def test_archive_tail_recovery_keeps_unmentioned_person_exclusion(self):
        old = self.fixture.item('Lukashenko_address_origin.mp4')
        bad = self.fixture.item('Lukashenko_Putin_meeting_tail.mp4')
        voice = self.fixture.root / 'voice-tail.mp3'
        voice.touch()
        project = TimelineProject('Belarus Lukashenko', clips=[self.archive_clip(old.path)],
                                  voiceover_path=str(voice))
        with (patch.object(bridge, 'probe_media_duration', return_value=12.),
              patch.object(bridge, '_cached_or_probed_montage_duration', return_value=6.),
              patch.object(bridge, '_replacement_candidates_for_clip', return_value=[bad]),
              self.assertRaises(ValueError)):
            bridge._complete_project_visual_tail(project, None, Settings())
