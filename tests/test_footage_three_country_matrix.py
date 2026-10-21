"""Owner-requested synthetic contracts, separate from real MP4 acceptance."""
import pytest

from scriptor import bridge
from scriptor.scene_intent import visual_intent
from scriptor.timeline import VISUAL_TERMS
from tests import test_footage_political_context as political

CASES = [
    ('Armenia', 'Армении', 'Ереване', 'Pashinyan', 'Пашинян'),
    ('Azerbaijan', 'Азербайджане', 'Баку', 'Aliyev', 'Алиев'),
    ('Russia', 'России', 'Москве', 'Putin', 'Путин'),
]


def test_bakunin_is_not_a_baku_city_reference():
    intent = visual_intent('Бакунин рассказал о железнодорожных перевозках.', VISUAL_TERMS)
    assert 'Azerbaijan' not in intent['visual_query']
    assert 'Azerbaijan' not in intent.get('physical_subject_places', [])


@pytest.mark.parametrize('place,country', [('бакинском районе', 'Azerbaijan'), ('ереванском районе', 'Armenia')])
def test_capital_adjective_keeps_civic_geography(place, country):
    intent = visual_intent(f'В {place} жители проводят мирный митинг.', VISUAL_TERMS)
    assert country in intent['visual_query']
    assert country in intent['protest_places']


@pytest.mark.parametrize('country,ru,capital,person,speaker', CASES)
def test_missing_protest_rotates_only_current_named_person(country, ru, capital, person, speaker):
    fixture = political.PoliticalContextTests()
    fixture.setUp()
    try:
        sources = [fixture.item(f'{name}_address_source_{suffix}.mp4')
                   for name in ('Pashinyan', 'Aliyev', 'Putin') for suffix in ('a', 'b')]
        project = fixture.prepare(
            f'В {ru} прошёл мирный митинг. {speaker} прокомментировал требования.',
            [f'{country} peaceful civilian protest placards street rally'] * 3, sources)
        assert len(project.clips) == 3
        assert len({clip.path for clip in project.clips}) == 2
        assert all(person in clip.path for clip in project.clips)
        assert all(a.path != b.path for a, b in zip(project.clips, project.clips[1:]))
        assert all(clip.fallback_level == 'SAFE_CONTEXT' for clip in project.clips)
        assert all(clip.selection_diagnostics['political_context']['archival_context'] is True
                   and clip.selection_diagnostics['political_context']['event_confirmed'] is False
                   for clip in project.clips)
    finally:
        fixture.doCleanups()


def test_three_way_topic_switch_does_not_keep_previous_politician():
    fixture = political.PoliticalContextTests()
    fixture.setUp()
    try:
        items = [fixture.item(f'{person}_address.mp4') for _, _, _, person, _ in CASES]
        story = 'Пашинян выступил в Армении. Алиев выступил в Азербайджане. Путин выступил в России.'
        project = fixture.prepare(story, [f'{country} peaceful protest placards' for country, *_ in CASES], items)
        assert [next(person for _, _, _, person, _ in CASES if person in clip.path)
                for clip in project.clips] == ['Pashinyan', 'Aliyev', 'Putin']
    finally:
        fixture.doCleanups()


@pytest.mark.parametrize('country,ru,capital,person,speaker', CASES)
@pytest.mark.parametrize('action', ['митинг', 'протест', 'шествие', 'забастовка', 'пикет'])
def test_civic_country_and_topic_switch(country, ru, capital, person, speaker, action):
    intent = visual_intent(f'В {capital} жители проводят мирный {action}.', VISUAL_TERMS)
    assert country in intent['visual_query']
    assert country in intent['protest_places']
    for other, other_ru, _, _, _ in CASES:
        if other == country:
            continue
        switched = visual_intent(f'В {other_ru} жители вышли на мирный митинг.', VISUAL_TERMS, previous=intent)
        assert switched['protest_places'] == [other]
        assert country not in switched['visual_query']


@pytest.mark.parametrize('country,ru,capital,person,speaker', CASES)
def test_cancelled_rally_does_not_require_crowd(country, ru, capital, person, speaker):
    intent = visual_intent(f'В {capital} митинг не начался.', VISUAL_TERMS)
    assert country in intent['visual_query']
    assert 'protest crowd' not in intent['visual_query']


@pytest.mark.parametrize('country,foreign', [('Armenia', 'Azerbaijani'), ('Azerbaijan', 'Russian'), ('Russia', 'Armenian')])
def test_foreign_flag_cannot_be_excused_by_checked_protest_role(country, foreign):
    fixture = political.PoliticalContextTests()
    fixture.setUp()
    try:
        item = fixture.item(f'{country}_rally_{foreign}_flags.mp4')
        assert bridge._semantic_clip_ok(f'{country} peaceful protest placards', item,
            visual_assessment={'relation': 'direct', 'dominant_kind': 'peaceful_protest'}) is False
    finally:
        fixture.doCleanups()
