"""Job-local story constraints are exclusion evidence, never face recognition."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import ClipIndex, IndexedFootageItem, SearchHit
from scriptor.config import Settings
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip
from tests import test_footage_political_context as contracts


class StoryScopeTests(unittest.TestCase):
    story = 'Пашинян обсуждает Армению и Азербайджан. Трамп прокомментировал переговоры.'

    def setUp(self):
        self.fixture = contracts.PoliticalContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def item(self, folder, *, name='clip.mp4', role='official', story=True):
        path = self.fixture.root / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'synthetic contract; never decoded')
        item = FootageItem(str(path), name, tags=[])
        item._visual_assessor = lambda _query, start, duration, **_kwargs: {
            'relation': 'context', 'dominant_kind': role,
            'source_start': start, 'duration': duration, 'source': 'synthetic-contract'}
        if story:
            item._montage_story_context = self.story
        return item

    def annotate(self, item, observations, *, stale=False):
        stat = self.fixture.root.joinpath(item.path).stat()
        item.person_evidence = {'size': stat.st_size + int(stale), 'mtime_ns': stat.st_mtime_ns,
                                'observations': observations}

    def test_generic_checked_role_cannot_admit_unmentioned_politician_folder(self):
        for person in ('Lukashenko', 'Putin'):
            for role, query in (('official', 'official statement government briefing'),
                                ('meeting', 'diplomatic negotiations meeting'),
                                ('interview', 'interview public media')):
                with self.subTest(person=person, role=role):
                    item = self.item(person, role=role)
                    self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=0., duration=6.))

    def test_foreign_generic_candidate_is_rejected_before_physical_probe(self):
        foreign = self.item('Lukashenko')
        related = self.item('Nikol Pashinyan')
        probed = []

        def duration(item):
            probed.append(item.path)
            self.assertNotEqual(foreign.path, item.path)
            return 8.

        result = bridge._select_montage_candidate(
            'official statement government briefing',
            strict_hits=[SearchHit(foreign, .95, 8.)], fallback_hits=[],
            safe_context_hits=[SearchHit(related, .5, 8.)], required_duration=6.,
            match_threshold=.22, used_paths=set(), used_families=set(),
            project_used_paths=set(), project_used_families=set(),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _item: True, source_duration=duration)
        self.assertEqual(related.path, result.item.path)
        self.assertEqual([related.path], probed)

    def test_curated_override_requires_fresh_full_selected_interval(self):
        query = 'official statement government briefing'
        item = self.item('Lukashenko')
        self.annotate(item, [{'person_id': 'pashinyan', 'start': 2., 'end': 8.,
                              'source': 'manual', 'complete': True}])
        self.assertTrue(bridge._semantic_clip_ok(query, item, source_start=2., duration=4.))
        self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=0., duration=2.))
        self.annotate(item, item.person_evidence['observations'], stale=True)
        self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=2., duration=4.))
        self.annotate(item, [{'person_id': 'lukashenko', 'start': 0., 'end': 8.,
                              'source': 'manual', 'complete': True}])
        self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=0., duration=6.))

    def test_partial_foreign_curated_presence_is_not_hidden_by_full_target(self):
        item = self.item('Nikol Pashinyan')
        self.annotate(item, [
            {'person_id': 'pashinyan', 'start': 0., 'end': 6., 'source': 'manual', 'complete': True},
            {'person_id': 'lukashenko', 'start': 2., 'end': 3., 'source': 'manual', 'complete': True},
        ])
        self.assertFalse(bridge._semantic_clip_ok('official statement government briefing',
                                                item, source_start=0., duration=6.))

    def test_legacy_calls_neutral_institutions_and_related_cutaways_remain_available(self):
        self.assertTrue(bridge._semantic_clip_ok('official statement government briefing',
                                                self.item('Lukashenko', story=False)))
        neutral = self.item('Neutral parliament', role='government_building')
        self.assertTrue(bridge._semantic_clip_ok('government building institutional context', neutral))
        aliyev = self.item('Ilham Aliyev', role='meeting')
        aliyev._montage_story_context = 'Алиев участвует в заседании в Азербайджане.'
        self.assertTrue(bridge._semantic_clip_ok('delegation meeting', aliyev))

    def test_existing_explicit_named_joint_meeting_contract_remains_separate(self):
        item = self.item('joint', name='Pashinyan_Putin_meeting.mp4', role='meeting')
        self.assertTrue(bridge._semantic_clip_ok('Nikol Pashinyan diplomatic meeting', item))

    def test_returned_copies_bind_only_their_own_job_story(self):
        original = IndexedFootageItem('fixture.mp4', 'fixture')
        first, second = object.__new__(ClipIndex), object.__new__(ClipIndex)
        first.montage_story_context, second.montage_story_context = self.story, 'Путин выступил в России.'
        one = first._with_visual_assessor(original, vector_dim=0)
        two = second._with_visual_assessor(original, vector_dim=0)
        self.assertEqual(self.story, getattr(one, '_montage_story_context', None))
        self.assertEqual(second.montage_story_context, getattr(two, '_montage_story_context', None))
        self.assertFalse(hasattr(original, '_montage_story_context'))
        self.assertEqual(self.story, one._montage_story_context)

    def test_replacement_route_applies_story_to_unscoped_provider_items(self):
        foreign = self.item('Lukashenko', story=False)
        related = self.item('Nikol Pashinyan', story=False)
        index = SimpleNamespace(montage_story_context=self.story,
            search_many=lambda *_args, **_kwargs: [[SearchHit(foreign, .9, 8.), SearchHit(related, .8, 8.)]])
        clip = TimelineClip('missing.mp4', self.story, 'official statement government briefing', 6.)
        settings = Settings(footage_folders=[str(self.fixture.root)], montage_auto_web=False)
        with patch.object(bridge, '_montage_screen_text_safe', return_value=True):
            candidates = bridge._replacement_candidates_for_clip(index, clip, settings)
        self.assertEqual([related.path], [item.path for item in candidates])
