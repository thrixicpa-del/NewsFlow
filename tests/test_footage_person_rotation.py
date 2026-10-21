"""Regressions from the genuine five-video UI run; synthetic inputs only."""
import unittest
from pathlib import Path

from scriptor import bridge
from scriptor.ai_index import SearchHit
from tests import test_footage_political_context as contracts


class PersonRotationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = contracts.PoliticalContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def unknown_meeting(self):
        item = self.fixture.item('Putin_source_with_unknown_delegates.mp4')
        stat = Path(item.path).stat()
        item.person_evidence = {'version': 1, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                                'observations': []}
        return item

    def test_unknown_meeting_cannot_impersonate_explicit_named_speaker(self):
        for query in ('Vladimir Putin', 'Vladimir Putin press conference',
                      'Vladimir Putin official statement', 'Vladimir Putin diplomatic meeting',
                      'Vladimir Putin interview'):
            with self.subTest(query=query):
                self.assertFalse(bridge._semantic_clip_ok(query, self.unknown_meeting(),
                    visual_assessment={'relation': 'context', 'dominant_kind': 'meeting'}))

    def test_country_institution_context_remains_available_without_requested_person(self):
        self.assertTrue(bridge._semantic_clip_ok('Russia government building exterior', self.unknown_meeting(),
            visual_assessment={'relation': 'context', 'dominant_kind': 'meeting'}))

    def test_neutral_institution_fallback_stays_available_for_named_statement(self):
        for annotated in (False, True):
            with self.subTest(annotated=annotated):
                item = self.fixture.item('Russia_government_delegation.mp4')
                if annotated:
                    stat = Path(item.path).stat()
                    item.person_evidence = {'version': 1, 'size': stat.st_size,
                                            'mtime_ns': stat.st_mtime_ns, 'observations': []}
                self.assertTrue(bridge._semantic_clip_ok('Vladimir Putin official statement', item,
                    visual_assessment={'relation': 'context', 'dominant_kind': 'meeting'}))

    def select(self, direct, context, *, confirmed=False):
        if confirmed:
            stat = Path(direct.path).stat()
            direct.person_evidence = {'version': 1, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'observations': [{'person_id': 'zelensky', 'start': 0., 'end': 6., 'source': 'manual', 'complete': True}]}
        context._visual_assessor = lambda _q, start, duration, **_kw: {
            'relation': 'context', 'dominant_kind': 'meeting', 'source_start': start, 'duration': duration,
            'source': 'synthetic-contract'}
        return bridge._select_montage_candidate('Volodymyr Zelensky',
            strict_hits=[SearchHit(direct, .9, source_family='a'), SearchHit(context, .85, source_family='b')],
            fallback_hits=[], required_duration=3., match_threshold=.4,
            used_paths=set(), used_families=set(),
            project_used_paths={bridge._montage_clip_key(direct.path)}, project_used_families={'a'},
            reserved_paths=set(), reserved_families=set(), source_exists=lambda _i: True,
            source_duration=lambda _i: 6., immediately_previous_path=direct.path)

    def test_adjacent_portrait_repeat_yields_to_safe_context_of_same_requested_person(self):
        direct = self.fixture.item('Zelensky_speech_a.mp4')
        context = self.fixture.item('Zelensky_meeting_b.mp4')
        selected = self.select(direct, context)
        self.assertEqual(context.path, selected.item.path)
        self.assertEqual('SAFE_CONTEXT', selected.fallback_level)

    def test_confirmed_requested_person_stays_ahead_of_only_metadata_context(self):
        direct = self.fixture.item('Zelensky_speech_confirmed.mp4')
        context = self.fixture.item('Zelensky_meeting_hint.mp4')
        self.assertEqual(direct.path, self.select(direct, context, confirmed=True).item.path)
