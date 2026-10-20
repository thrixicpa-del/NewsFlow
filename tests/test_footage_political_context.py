"""Synthetic context contracts; labels never prove real faces or flags."""
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, timeline
from scriptor.config import Settings
from scriptor.core import ScenarioRequest
from scriptor.footage import FootageItem
from scriptor.runner import Job, RunState


class PoliticalContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def item(self, name):
        path = self.root / name
        path.write_bytes(b'synthetic source; never decoded')
        item = FootageItem(str(path), name, tags=['press-conference'])
        def assess(query, start, duration, **_kwargs):
            from scriptor.visual_evidence import query_topic
            topic = query_topic(query)
            return {'relation': 'direct' if topic and topic[0] in {'official', 'meeting', 'political_context'} else 'contradiction',
                    'dominant_kind': 'official', 'source_start': start, 'duration': duration,
                    'source': 'synthetic-contract'}
        item._visual_assessor = assess
        return item

    def prepare(self, story, queries, items):
        voice = self.root / 'voice.mp3'
        voice.write_bytes(b'synthetic audio; never decoded')
        settings = Settings(footage_folders=[str(self.root)], montage_auto_web=False,
                            montage_project_folder=str(self.root / 'projects'),
                            montage_output_folder=str(self.root / 'outputs'), montage_use_script_text=True)
        settings.voice_scenario_outputs = {'1': str(voice)}
        job = Job(ScenarioRequest(0, story, ''), RunState.DONE, story, '')
        scenes = [{'narration': query, 'visual_query_en': query, 'duration': 6.} for query in queries]
        with (patch.object(bridge, 'load_settings', return_value=settings),
              patch.object(bridge, 'load_session', return_value=([story], [job])),
              patch.object(bridge, 'save_settings'), patch.object(bridge, 'snapshot', return_value={}),
              patch.object(bridge, 'scan_folders', return_value=items),
              patch.object(bridge.ClipIndex, 'count', return_value=0),
              patch.object(bridge, '_montage_screen_text_safe', return_value=True),
              patch.object(bridge, 'fallback_scene_plan', return_value=scenes),
              patch.object(bridge, 'probe_media_duration', return_value=6. * len(scenes)),
              patch.object(bridge, '_cached_or_probed_montage_duration', return_value=8.)):
            result = bridge.prepare_montage({'scenarioIndex': 0})
        return timeline.TimelineProject.load(Path(result['preparedProject']['path']))

    def test_missing_protest_uses_mentioned_local_politician_with_rotation(self):
        items = [self.item(name) for name in ('Lukashenko_address_source_a.mp4',
                 'Lukashenko_interview_source_b.mp4', 'Putin_press_conference.mp4')]
        project = self.prepare('В Беларуси прошёл митинг. Лукашенко прокомментировал требования.',
                               ['Belarus peaceful civilian protest placards street rally'] * 3, items)
        self.assertEqual(3, len(project.clips))
        self.assertEqual(2, len({clip.path for clip in project.clips}))
        self.assertTrue(all('Lukashenko' in clip.path for clip in project.clips))
        self.assertTrue(all(a.path != b.path for a, b in zip(project.clips, project.clips[1:])))
        for clip in project.clips:
            evidence = clip.selection_diagnostics
            self.assertTrue(evidence['political_context']['archival_context'])
            self.assertFalse(evidence['political_context']['event_confirmed'])
            self.assertIn('protest', evidence['political_context']['requested_visual_query'])
            self.assertEqual('SAFE_CONTEXT', clip.fallback_level)

    def test_topic_switch_uses_only_the_current_country_mentioned_person(self):
        items = [self.item('Lukashenko_address.mp4'), self.item('Zelensky_address.mp4')]
        project = self.prepare('Лукашенко выступил в Беларуси. Зеленский выступил в Украине.',
                               ['Belarus peaceful protest placards', 'Ukraine peaceful protest placards'], items)
        self.assertIn('Lukashenko', project.clips[0].path)
        self.assertIn('Zelensky', project.clips[1].path)

    def test_no_politician_is_invented_when_script_only_names_a_country(self):
        with self.assertRaisesRegex(RuntimeError, 'Нет допустимого тематического'):
            self.prepare('В Беларуси прошёл мирный митинг.', ['Belarus peaceful protest placards'],
                         [self.item('Lukashenko_address.mp4')])

    def test_exact_protest_remains_preferred_to_political_context(self):
        exact = self.item('Belarus_peaceful_protest_placards.mp4')
        exact._visual_assessor = lambda _q, start, duration, **_kw: {
            'relation': 'direct', 'dominant_kind': 'peaceful_protest',
            'source_start': start, 'duration': duration, 'source': 'synthetic-contract'}
        project = self.prepare('В Беларуси митинг. Лукашенко прокомментировал требования.',
                               ['Belarus peaceful protest placards'],
                               [self.item('Lukashenko_address.mp4'), exact])
        self.assertEqual(exact.path, project.clips[0].path)
        self.assertNotIn('political_context', project.clips[0].selection_diagnostics)

    def test_missing_indexed_verdict_does_not_reactivate_filename_acceptance(self):
        item = self.item('government_meeting_unchecked.mp4')
        item._visual_assessor = lambda *_args, **_kwargs: None
        query = 'diplomatic negotiations delegations meeting consultations'
        self.assertFalse(bridge._semantic_clip_ok(query, item))

    def test_legacy_metadata_and_supplied_checked_verdict_remain_available(self):
        item = self.item('government_meeting_legacy.mp4')
        del item._visual_assessor
        query = 'diplomatic negotiations delegations meeting consultations'
        self.assertTrue(bridge._semantic_clip_ok(query, item))
        item._visual_assessor = lambda *_args, **_kwargs: None
        self.assertTrue(bridge._semantic_clip_ok(query, item, visual_assessment={
            'relation': 'context', 'dominant_kind': 'meeting'}))

    def test_unchecked_candidate_never_probes_health_ahead_of_checked_context(self):
        from scriptor.ai_index import SearchHit
        unchecked = self.item('Nikol_Pashinyan_meeting_unchecked.mp4')
        unchecked._visual_assessor = lambda *_args, **_kwargs: None
        checked = self.item('Nikol_Pashinyan_meeting_checked.mp4')
        checked._visual_assessor = lambda _query, start, duration, **_kwargs: {
            'relation': 'context', 'dominant_kind': 'meeting',
            'source_start': start, 'duration': duration, 'source': 'synthetic-contract'}
        probed = []

        def duration(item):
            probed.append(item.path)
            self.assertNotEqual(unchecked.path, item.path,
                                'Unchecked indexed candidate reached physical verification')
            return 8.

        result = bridge._select_montage_candidate(
            'Nikol Pashinyan diplomatic negotiations meeting',
            strict_hits=[SearchHit(unchecked, .95, 8.)], fallback_hits=[],
            safe_context_hits=[SearchHit(checked, .5, 8.)], required_duration=6.,
            match_threshold=.22, used_paths=set(), used_families=set(),
            project_used_paths=set(), project_used_families=set(),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=duration)
        self.assertEqual(checked.path, result.item.path)
        self.assertEqual([checked.path], probed)

    def test_missing_indexed_meeting_uses_checked_script_mentioned_archive(self):
        unchecked = self.item('Nikol_Pashinyan_meeting_unchecked.mp4')
        unchecked._visual_assessor = lambda *_args, **_kwargs: None
        checked = self.item('Nikol_Pashinyan_address_checked.mp4')

        def assess(query, start, duration, **_kwargs):
            return {'relation': 'context' if query.startswith('archival political context,') else 'contradiction',
                    'dominant_kind': 'official', 'source_start': start,
                    'duration': duration, 'source': 'synthetic-contract'}

        checked._visual_assessor = assess
        project = self.prepare('Пашинян обсуждает переговоры Армении.',
                               ['Nikol Pashinyan diplomatic negotiations meeting'], [unchecked, checked])
        clip = project.clips[0]
        self.assertEqual(checked.path, clip.path)
        self.assertTrue(clip.selection_diagnostics['political_context']['archival_context'])
        self.assertFalse(clip.selection_diagnostics['political_context']['event_confirmed'])

    def test_checked_role_cannot_hide_explicit_foreign_flags(self):
        for wanted, foreign in (('Armenia', 'Azerbaijani'), ('Belarus', 'Russian'),
                                ('Ukraine', 'Belarusian'), ('Georgia', 'Russian'),
                                ('Kazakhstan', 'Uzbek'), ('Moldova', 'Russian')):
            with self.subTest(wanted=wanted, foreign=foreign):
                item = self.item(f'{wanted}_rally_with_{foreign}_flags.mp4')
                self.assertFalse(bridge._semantic_clip_ok(
                    f'{wanted} peaceful protest placards', item,
                    visual_assessment={'relation': 'direct', 'dominant_kind': 'peaceful_protest'}))

    def test_shared_person_hint_cannot_hide_an_unrelated_foreign_politician(self):
        for query, title in (
            ('Nikol Pashinyan, Azerbaijan Baku', 'Pashinyan_Lukashenko_Minsk.mp4'),
            ('Nikol Pashinyan, Azerbaijan Baku negotiations', 'Pashinyan_Lukashenko_Minsk_meeting.mp4'),
            ('Volodymyr Zelensky Ukraine', 'Zelensky_Putin_Moscow.mp4'),
            ('Vladimir Putin Russia', 'Putin_Macron_Paris.mp4'),
        ):
            item = self.item(title)
            del item._visual_assessor
            for visual in (None, {'relation': 'direct', 'dominant_kind': 'official'}):
                with self.subTest(query=query, checked_role=visual is not None):
                    self.assertFalse(bridge._semantic_clip_ok(query, item, visual_assessment=visual))

    def test_scene_related_bilateral_person_hints_remain_available(self):
        item = self.item('Pashinyan_Aliyev_Armenia_Azerbaijan.mp4')
        self.assertTrue(bridge._semantic_clip_ok(
            'Nikol Pashinyan, Armenia Azerbaijan negotiations', item,
            visual_assessment={'relation': 'context', 'dominant_kind': 'meeting'}))
        item = self.item('Pashinyan_Lukashenko_meeting.mp4')
        self.assertTrue(bridge._semantic_clip_ok(
            'Nikol Pashinyan Alexander Lukashenko meeting', item,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'meeting'}))

    def test_checked_target_window_corrects_a_mixed_person_filename(self):
        item = self.item('Pashinyan_Lukashenko_meeting.mp4')
        stat = Path(item.path).stat()
        item.person_evidence = {
            'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'observations': [{'person_id': 'pashinyan', 'source': 'manual',
                              'complete': True, 'start': 0., 'end': 8.}],
        }
        self.assertTrue(bridge._semantic_clip_ok(
            'Nikol Pashinyan Armenia press conference', item, source_start=0., duration=6.,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'official'}))

    def test_cis_geography_cannot_be_cancelled_by_an_unrelated_title_mention(self):
        for requested, actual in (('Georgia Tbilisi', 'Russia Moscow'),
                                  ('Moldova Chisinau', 'Belarus Minsk'),
                                  ('Uzbekistan Tashkent', 'Kazakhstan Astana'),
                                  ('Kyrgyzstan Bishkek', 'Tajikistan Dushanbe')):
            with self.subTest(requested=requested):
                self.assertTrue(bridge._montage_entity_conflict(requested, actual))

    def test_wav_duration_uses_samples_not_centisecond_console_rounding(self):
        voice = self.root / 'precise.wav'
        with wave.open(str(voice), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(b'\0\0' * 198192)
        self.assertAlmostEqual(12.387, timeline.probe_media_duration(voice), places=9)

    def test_person_only_query_still_checks_a_real_official_window(self):
        item = self.item('Zelensky_address.mp4')
        for query in ('Volodymyr Zelensky', 'Volodymyr Zelensky.', 'Volodymyr Zelensky:'):
            visual = bridge._montage_window_visual(query, item, 0., 3.1935)
            self.assertIn(visual['relation'], {'direct', 'context'})
        bad = self.item('Zelensky_wrong_warehouse.mp4')
        bad._visual_assessor = lambda _q, start, duration, **_kw: {
            'relation': 'contradiction', 'dominant_kind': 'warehouse',
            'source_start': start, 'duration': duration}
        self.assertFalse(bridge._semantic_clip_ok('Volodymyr Zelensky', bad, duration=3.1935))

    def test_archive_role_accepts_interviews_without_turning_them_into_exact_statements(self):
        from scriptor.visual_evidence import classify_window
        query = 'archival political context, Alexander Lukashenko Belarus press conference interview'
        for role in ('official', 'meeting', 'interview'):
            with self.subTest(role=role):
                result = classify_window(query, [{role: .35, 'combat': .10}] * 3)
                self.assertEqual('direct', result['relation'])
                self.assertFalse(result['event_confirmed'])
                self.assertFalse(result['motion_verified'])
        for role in ('government_building', 'combat', 'warehouse', 'peaceful_protest'):
            with self.subTest(negative=role):
                result = classify_window(query, [{role: .35, 'official': .10}] * 3)
                self.assertNotIn(result['relation'], {'direct', 'context'})
        self.assertNotIn(classify_window('Alexander Lukashenko press conference',
            [{'interview': .35, 'official': .10}] * 3)['relation'], {'direct', 'context'})

    def test_archive_never_claims_checked_people_from_metadata_alone(self):
        item = self.item('Lukashenko_address_without_checked_window.mp4')
        del item._visual_assessor
        self.assertFalse(bridge._semantic_clip_ok(
            'archival political context, Alexander Lukashenko Belarus press conference', item))

    def test_cis_country_and_capital_survive_protest_negation_and_topic_switch(self):
        from scriptor.scene_intent import visual_intent
        from scriptor.timeline import VISUAL_TERMS
        cases = [('Армении', 'Тавуше', 'Armenia'), ('Грузии', 'Тбилиси', 'Georgia'), ('Молдове', 'Кишинёве', 'Moldova'),
                 ('Казахстане', 'Астане', 'Kazakhstan'), ('Узбекистане', 'Ташкенте', 'Uzbekistan'),
                 ('Кыргызстане', 'Бишкеке', 'Kyrgyzstan'), ('Таджикистане', 'Душанбе', 'Tajikistan'),
                 ('Туркменистане', 'Ашхабаде', 'Turkmenistan')]
        for country, capital, expected in cases:
            with self.subTest(country=country):
                for place in (country, capital):
                    active = visual_intent(f'В {place} жители вышли на мирный митинг.', VISUAL_TERMS)
                    self.assertIn(expected, active['visual_query'])
                    self.assertIn(expected, active['protest_places'])
                    cancelled = visual_intent(f'В {place} митинг не начался.', VISUAL_TERMS)
                    self.assertIn(expected, cancelled['visual_query'])
                    self.assertNotIn('protest crowd', cancelled['visual_query'])
                    switched = visual_intent('В Беларуси прошёл мирный митинг.', VISUAL_TERMS, previous=active)
                    self.assertEqual(['Belarus'], switched['protest_places'])
                    self.assertNotIn(expected, switched['visual_query'])

    def test_named_cis_politicians_can_be_archive_context_without_inventing_leaders(self):
        from scriptor.scene_intent import named_people
        for country, person, identity in (
                ('Moldova', 'Майя Санду', 'sandu'), ('Uzbekistan', 'Шавкат Мирзиёев', 'mirziyoyev'),
                ('Kyrgyzstan', 'Садыр Жапаров', 'japarov'), ('Tajikistan', 'Эмомали Рахмон', 'rahmon'),
                ('Turkmenistan', 'Сердар Бердымухамедов', 'berdymukhamedov'),
                ('Armenia', 'Ваагн Хачатурян', 'khachaturyan')):
            with self.subTest(country=country):
                queries = bridge._montage_political_context_queries(
                    {'visual_query_en': f'{country} peaceful protest'}, f'{person} прокомментировал требования.')
                self.assertTrue(queries)
                self.assertTrue(all(named_people(query) == [identity] for query in queries))
                self.assertEqual([], bridge._montage_political_context_queries(
                    {'visual_query_en': f'{country} peaceful protest'}, f'В {country} прошёл митинг.'))
