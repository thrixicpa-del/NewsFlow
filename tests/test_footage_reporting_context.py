"""Bounded reporting references; synthetic fixtures never prove real identity."""
import copy
import unittest

from scriptor import bridge
from scriptor.scene_intent import named_people
from tests import test_footage_political_context as contracts

ARM_STORY = 'Никол Пашинян заявил об отношениях Армении с Азербайджаном. Дональд Трамп прокомментировал переговоры.'
RU_STORY = 'Никол Пашинян заявил о российской базе в Армении. Владимир Путин прокомментировал вопрос.'


def scene(narration, query='contextual news footage', *, start=0., people=(), intent_text=None):
    return {'narration': narration, 'visual_query_en': query, 'duration': 6.,
            'narration_start': start, 'narration_end': start + 6.,
            'scene_intent': {'target_people': list(people),
                             'text': narration if intent_text is None else intent_text}}


def pashinyan_anchor(*, start=0.):
    return scene('Пашинян заявил, что Армения обсуждает с Азербайджаном условия нормализации.',
                 'Nikol Pashinyan Armenia Azerbaijan official statement', start=start, people=('pashinyan',))


def armenia_reference(*, start=6.):
    return scene('говорит о намерении, а не о результате. Вслед за этим премьер перечислял направления нормализации.',
                 'Azerbaijan Baku regional context', start=start,
                 intent_text='Вслед за этим премьер перечислял направления нормализации.')


class ReportingContextTests(unittest.TestCase):
    def setUp(self):
        # Reuse setup/helpers without inheriting and collecting its whole suite.
        self.fixture = contracts.PoliticalContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def queries(self, current, previous, story=ARM_STORY):
        before = copy.deepcopy((current, previous))
        result = bridge._montage_political_context_queries(current, story, previous_scenes=previous)
        self.assertEqual(before, (current, previous), 'Fallback must preserve saved narration, intent and visual query')
        return result

    def assert_person(self, queries, identity):
        self.assertTrue(queries, 'An explicit nearby reporting actor must remain available as checked archive context')
        for query in queries:
            self.assertTrue(query.startswith('archival political context,'))
            self.assertEqual([identity], named_people(query))

    def test_armenia_scene12_reporting_reference_keeps_pashinyan_and_azerbaijan(self):
        queries = self.queries(armenia_reference(), [pashinyan_anchor()])
        self.assert_person(queries, 'pashinyan')
        self.assertTrue(all('azerbaijan' in query.casefold() for query in queries))

    def test_russia_scene6_decision_refers_to_nearby_pashinyan_statement(self):
        previous = [
            scene('том, чтобы она оставалась в Армении? Никол Пашинян заявил, что присутствие',
                  start=0., intent_text='том, чтобы она оставалась в Армении?'),
            scene('российского гарнизона не имеет для Еревана жизненно важного значения. Если Москва захочет',
                  start=6., intent_text='Присутствие российского гарнизона не имеет для Еревана жизненно важного значения.'),
            scene('вывести военных, препятствовать этому армянские власти не собираются. Если Россия захочет',
                  start=12., intent_text='Если Москва захочет вывести военных, препятствовать этому армянские власти не собираются.'),
        ]
        current = scene('сохранить базу, условия готовы обсуждать. Теперь решение, которое раньше выглядело заранее',
                        start=18., intent_text='Теперь решение, которое раньше выглядело заранее')
        self.assert_person(self.queries(current, previous, RU_STORY), 'pashinyan')

    def test_explicit_current_putin_speaker_overrides_prior_pashinyan(self):
        current = scene('Владимир Путин заявил о новых условиях обсуждения.',
                        'Vladimir Putin Russia official statement', start=6., people=('putin',))
        self.assert_person(self.queries(current, [pashinyan_anchor()], RU_STORY), 'putin')

    def test_nearest_statement_actor_wins_over_earlier_actor_and_story_order(self):
        previous = [scene('Дональд Трамп заявил о своих предложениях.',
                          'Donald Trump USA official statement', people=('trump',)),
                    pashinyan_anchor(start=6.)]
        story = 'Дональд Трамп выступил в США. Никол Пашинян заявил об отношениях Армении с Азербайджаном.'
        self.assert_person(self.queries(armenia_reference(start=12.), previous, story), 'pashinyan')

    def test_unrelated_current_ukraine_topic_does_not_borrow_pashinyan(self):
        current = scene('Теперь решение по Украине обсуждают в Киеве.',
                        'Ukraine Kyiv regional context', start=6.)
        self.assertEqual([], self.queries(current, [pashinyan_anchor()]))

    def test_reporting_actor_must_also_be_named_in_the_story(self):
        self.assertEqual([], self.queries(armenia_reference(), [pashinyan_anchor()],
                                         'Дональд Трамп прокомментировал переговоры Азербайджана.'))

    def test_intervening_unrelated_country_stops_generic_or_named_decision_reference(self):
        previous = [pashinyan_anchor(),
                    scene('В Украине обсуждают условия новой программы.',
                          'Ukraine Kyiv regional context', start=6.)]
        for query in ('contextual news footage', 'Ukraine Kyiv regional context'):
            with self.subTest(query=query):
                current = scene('Теперь его решение обсуждают дальше.', query, start=12.)
                self.assertEqual([], self.queries(current, previous))

    def test_global_names_or_country_and_premier_title_do_not_invent_a_nearby_actor(self):
        previous = [scene('В Ереване обсуждали условия нормализации отношений.', start=0.)]
        self.assertEqual([], self.queries(armenia_reference(), previous))

    def test_current_independent_physical_roles_do_not_inherit_reporting_actor(self):
        for narration in ('Порт возобновил погрузку судов.',
                          'Склад начал погрузку грузовиков.',
                          'Солдаты начали наступление и артиллерийский обстрел.',
                          'Жители вышли на протест с плакатами.',
                          'Его заявление завершилось, затем порт возобновил погрузку судов.'):
            with self.subTest(narration=narration):
                dominant = narration.split('затем ')[-1]
                self.assertEqual([], self.queries(scene(narration, start=6., intent_text=dominant),
                                                  [pashinyan_anchor()]))

    def test_intervening_physical_role_or_action_cut_stops_reporting_lookback(self):
        for narration in ('Порт возобновил погрузку судов.',
                          'Склад начал погрузку грузовиков.',
                          'Солдаты начали наступление и артиллерийский обстрел.',
                          'Жители вышли на протест с плакатами.',
                          'Его заявление завершилось, затем порт возобновил погрузку судов.'):
            with self.subTest(narration=narration):
                previous = [pashinyan_anchor(), scene(narration, start=6., intent_text=narration.split('затем ')[-1])]
                self.assertEqual([], self.queries(armenia_reference(start=12.), previous))

    def test_six_adjacent_short_reporting_beats_still_have_the_explicit_actor(self):
        previous = [pashinyan_anchor()] + [
            scene('Его формулировка осталась прежней.', start=6.*number) for number in range(1, 6)]
        self.assert_person(self.queries(armenia_reference(start=36.), previous), 'pashinyan')

    def test_reporting_actor_beyond_six_beats_is_not_borrowed(self):
        previous = [pashinyan_anchor()] + [
            scene('Его формулировка осталась прежней.', start=6.*number) for number in range(1, 7)]
        self.assertEqual([], self.queries(armenia_reference(start=42.), previous))

    def test_reporting_lookback_does_not_cross_sixty_four_words(self):
        previous = [pashinyan_anchor(), scene('Его заявление ' + 'подробности '*65 + 'сохраняло прежний смысл.', start=6.)]
        self.assertEqual([], self.queries(armenia_reference(start=12.), previous))

    def test_audio_gap_stops_reporting_reference(self):
        self.assertEqual([], self.queries(armenia_reference(start=7.), [pashinyan_anchor()]))

    def test_prepare_keeps_two_checked_pashinyan_archives_without_exact_event_claim(self):
        rows = [pashinyan_anchor(), armenia_reference()]
        before = copy.deepcopy(rows)
        items = [self.fixture.item('Nikol_Pashinyan_checked_reporting_a.mp4'),
                 self.fixture.item('Nikol_Pashinyan_checked_reporting_b.mp4')]
        def archive_only(query, start, duration, **_kwargs):
            return {'relation': 'context' if query.startswith('archival political context,') else 'contradiction',
                    'dominant_kind': 'official', 'source_start': start, 'duration': duration,
                    'source': 'synthetic-contract'}
        for item in items:
            item._visual_assessor = archive_only
        project = self.fixture.prepare(ARM_STORY, [], items, scene_rows=copy.deepcopy(rows))
        self.assertEqual(2, len(project.clips))
        for clip, requested in zip(project.clips, before):
            self.assertIn(clip.path, {item.path for item in items})
            context = clip.selection_diagnostics['political_context']
            self.assertTrue(context['archival_context'])
            self.assertFalse(context['event_confirmed'])
            self.assertEqual(requested['visual_query_en'], context['requested_visual_query'])
            self.assertEqual(['pashinyan'], named_people(context['context_visual_query']))


if __name__ == '__main__':
    unittest.main()
