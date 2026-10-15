"""PR403 owner follow-up. Contract fixtures do not prove visual semantics.

Loaded by test_voice_map's unittest suite, including the existing Linux CI.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.footage import FootageItem
from scriptor.scene_intent import visual_intent
from scriptor.timeline import (
    VISUAL_TERMS,
    TimelineClip,
    TimelineProject,
    fallback_scene_plan,
    fallback_visual_query,
)
from scriptor.voice_map import VoiceMapStatus

PROTEST_MATRIX = [
    ("Жители вышли на митинг против повышения тарифов", "protest", "artillery"),
    ("В центре города проходит мирная демонстрация", "peaceful", "clashes"),
    ("Фермеры протестуют из-за падения доходов и вывели тракторы к зданию правительства", "protest", "harvest"),
    ("Рабочие завода объявили забастовку и вышли на пикет", "labor strike", "industrial factory workers"),
    ("Студенты провели акцию протеста у университета", "protest", "classroom"),
    ("Участники митинга потребовали прекратить войну", "protest", "battlefield"),
    ("На площади прошёл митинг в поддержку армии", "protest", "army soldiers"),
    ("Полиция охраняет мирный митинг", "peaceful", "clashes"),
    ("Полиция начала разгон демонстрации, произошли столкновения", "police dispersal", "battlefield"),
    ("Министерство направило дипломатический протест", "diplomatic", "protest crowd"),
    ("На выставке прошла демонстрация нового оборудования", "equipment", "protest crowd"),
    ("Компания начала рекламную акцию, стоимость её акций выросла", "finance", "protest"),
    ("Фермеры завершили уборку урожая", "harvest", "protest"),
    ("Рабочие завода увеличили выпуск продукции", "factory", "labor strike"),
    ("Митинг отменили", "statement", "protest crowd"),
    ("Протесты не начались", "statement", "protest crowd"),
    ("Забастовку удалось предотвратить", "statement", "labor strike"),
    ("На митинге не было столкновений", "peaceful", "clashes"),
    ("Митинг не отменили, участники собрались на площади", "protest", "statement"),
    ("Рабочие угрожают забастовкой", "statement", "labor strike"),
    ("Власти обсуждают протест", "statement", "protest crowd"),
    ("Если начнутся протесты, власти выступят с заявлением", "statement", "protest crowd"),
]


def voice_scenes(texts, authored=None):
    status = VoiceMapStatus("ready", "ready", path="fixture.json", data={
        "audioDuration": len(texts) * 6, "timingMode": "aligned", "schemaVersion": 1,
        "productionItemId": "fixture", "scriptSha256": "test", "audioSha256": "test", "alignmentEngine": "test",
        "segments": [{"id": i + 1, "start": i * 6, "end": (i + 1) * 6, "duration": 6,
                      "text": text, "visualQuery": (authored or [""] * len(texts))[i]}
                     for i, text in enumerate(texts)],
    })
    return bridge._voice_map_scenes(status)[0]


def select(query, items):
    return bridge._select_montage_candidate(
        query, strict_hits=[SearchHit(item, .95 - i * .01, 6) for i, item in enumerate(items)],
        fallback_hits=[], required_duration=6, match_threshold=.22,
        used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
        reserved_paths=set(), reserved_families=set(), source_exists=lambda _: True, source_duration=lambda _: 6,
    )


class FootageFollowupTests(unittest.TestCase):
    def test_three_review_reproductions(self):
        scenes = fallback_scene_plan("На фронте продолжаются бои. Делегации встретились для обсуждения соглашения.")
        self.assertIn("frontline", scenes[0]["visual_query_en"])
        self.assertIn("diplomatic", scenes[1]["visual_query_en"])
        self.assertNotIn("frontline", scenes[1]["visual_query_en"])
        intent = visual_intent("Заявление Путина прокомментировал Зеленский.", VISUAL_TERMS)
        self.assertEqual(["zelensky"], intent["target_people"])
        self.assertEqual(["putin", "zelensky"], intent["mentioned_people"])
        self.assertNotIn("advancing", fallback_visual_query("Наступление не началось."))

    def test_diplomatic_synonyms_and_multitopic_local_and_voice_map(self):
        for meeting in ("Делегации провели встречу", "Стороны обсудили соглашение", "Представители продолжили консультации"):
            texts = ["На фронте продолжаются бои", meeting, "В порту возобновилась погрузка", "Экономика растёт"]
            for scenes in (fallback_scene_plan('. '.join(texts) + '.'), voice_scenes(texts)):
                for scene, wanted in zip(scenes, ("frontline", "diplomatic", "port", "economy")):
                    self.assertIn(wanted, scene["visual_query_en"])
                self.assertNotIn("frontline", scenes[1]["visual_query_en"])

    def test_speaker_roles_and_ambiguity(self):
        for verb in ("прокомментировал", "отверг", "подтвердил", "ответил"):
            for text in (f"Заявление Путина {verb} Зеленский", f"Зеленский {verb} заявление Путина"):
                self.assertEqual(["zelensky"], visual_intent(text, VISUAL_TERMS)["target_people"], text)
        ambiguous = visual_intent("Путин и Зеленский прокомментировали заявление", VISUAL_TERMS)
        self.assertNotEqual(["putin"], ambiguous["target_people"])
        self.assertEqual(["putin", "zelensky"], visual_intent("Путин и Зеленский встретились", VISUAL_TERMS)["target_people"])
        self.assertEqual(["zelensky"], visual_intent("На заявление Путина ответил Зеленский", VISUAL_TERMS)["target_people"])
        texts = ["Заявление Путина прокомментировал Зеленский", "Он выступил перед журналистами", "В порту идёт погрузка"]
        scenes = voice_scenes(texts, ["Vladimir Putin press conference", "", ""])
        self.assertIn("Zelensky", scenes[0]["visual_query_en"])
        self.assertIn("Zelensky", scenes[1]["visual_query_en"])
        self.assertNotIn("Zelensky", scenes[2]["visual_query_en"])

    def test_event_local_negation(self):
        for text in ("Наступление не началось", "Наступление так и не началось", "Наступление пока не началось",
                     "Наступление отменили", "Наступление удалось предотвратить", "Если начнётся наступление"):
            self.assertNotIn("advancing", fallback_visual_query(text), text)
        self.assertIn("artillery", fallback_visual_query("Наступление не началось, но обстрел продолжился"))
        self.assertIn("explosion", fallback_visual_query("Атаку не отменили, удар произошёл"))
        self.assertIn("advancing", fallback_visual_query("Наступление началось"))

    def test_protest_matrix_local_and_voice_map(self):
        for text, wanted, forbidden in PROTEST_MATRIX:
            with self.subTest(text=text):
                for query in (fallback_visual_query(text), voice_scenes([text])[0]["visual_query_en"]):
                    self.assertIn(wanted, query)
                    self.assertNotIn(forbidden, query)

    def test_protest_word_forms(self):
        for word in ("митинги", "митингующие", "протестующие", "демонстранты", "шествие", "пикетчики", "бастующие"):
            self.assertIn("protest", fallback_visual_query(f"На площади собрались {word}"), word)

    def test_mixed_protest_sequence(self):
        texts = ["На фронте продолжаются бои", "Жители собрались на мирный митинг",
                 "Представители властей начали переговоры", "Рабочие объявили забастовку", "В порту возобновилась погрузка"]
        for scenes in (fallback_scene_plan('. '.join(texts) + '.'), voice_scenes(texts)):
            for scene, wanted in zip(scenes, ("frontline", "protest", "diplomatic", "labor strike", "port")):
                self.assertIn(wanted, scene["visual_query_en"])
            self.assertNotIn("frontline", scenes[1]["visual_query_en"])
        self.assertIn("frontline", fallback_scene_plan("Протест завершился. На фронте продолжаются бои.")[1]["visual_query_en"])
        self.assertIn("diplomatic", fallback_scene_plan("Протест завершился. Делегации встретились.")[1]["visual_query_en"])

    def test_speakers_surround_actual_protest(self):
        texts = ["Путин прокомментировал протесты", "Участники акции собрались на площади", "Зеленский выступил с заявлением"]
        for scenes in (fallback_scene_plan('. '.join(texts) + '.'), voice_scenes(texts)):
            self.assertIn("Putin", scenes[0]["visual_query_en"])
            self.assertNotIn("protest crowd", scenes[0]["visual_query_en"])
            self.assertIn("protest", scenes[1]["visual_query_en"])
            self.assertNotIn("Putin", scenes[1]["visual_query_en"])
            self.assertIn("Zelensky", scenes[2]["visual_query_en"])

    def test_peaceful_protest_rejects_close_negatives_all_selection_paths(self):
        query = fallback_visual_query("Полиция охраняет мирный митинг")
        good = FootageItem("peace.mp4", "peaceful civilian protest placards", tags=["protest-crowd"])
        for name, tag in (("concert crowd", "concert"), ("football fans crowd", "sports"),
                          ("military parade", "military-vehicles"), ("religious procession", "religion"),
                          ("people queue", "city-urban"), ("factory workers", "factory-industry"),
                          ("harvest tractors", "agriculture-farming"), ("frontline battle", "frontline-combat"),
                          ("police dispersal clashes", "public-unrest-police"),
                          ("industrial equipment demonstration", "documentary-neutral"),
                          ("technology product demonstration exhibition", "documentary-neutral"),
                          ("Donald Trump press conference", "press-conference")):
            bad = FootageItem("bad.mp4", name, tags=[tag])
            with self.subTest(name=name):
                self.assertFalse(bridge._semantic_clip_ok(query, bad))
                self.assertEqual(good.path, select(query, [bad, good]).item.path)
                with self.assertRaises(bridge.MontageSelectionFailure):
                    select(query, [bad])
                self.assertIsNone(bridge._select_visual_continuity_candidate(
                    [bad], scene_query=query, required_duration=6, project_used_paths=set(),
                    project_used_families=set(), recent_project_paths=set(), source_exists=lambda _: True,
                    source_duration=lambda _: 6, source_allowed=lambda _: True, diversity_seed="fixture"))

    def test_labor_context_and_actual_clashes(self):
        factory = FootageItem("factory.mp4", "factory exterior union venue", tags=["factory-industry"])
        query = fallback_visual_query("Рабочие объявили забастовку")
        result = select(query, [factory])
        self.assertIsNotNone(result.item)
        self.assertEqual("SAFE_CONTEXT", result.fallback_level)
        clash = FootageItem("clashes.mp4", "police dispersal clashes", tags=["public-unrest-police"])
        self.assertTrue(bridge._semantic_clip_ok(fallback_visual_query("Полиция начала разгон демонстрации, произошли столкновения"), clash))

    def test_repair_and_tail_preserve_protest_suitability(self):
        query = fallback_visual_query("На митинге не было столкновений")
        bad = FootageItem("battle.mp4", "frontline battle", tags=["frontline-combat"])
        good = FootageItem("peace.mp4", "peaceful civilian protest placards", tags=["protest-crowd"])
        project = TimelineProject("repair", clips=[TimelineClip("missing.mp4", "Мирный митинг", query, duration=6)])
        with patch.object(bridge, "_validated_montage_clip_duration", side_effect=lambda p: 0 if str(p) == 'missing.mp4' else 6):
            self.assertEqual(1, bridge._repair_missing_project_clips(project, lambda *_: [bad, good]))
        self.assertEqual(good.path, project.clips[0].path)

    def test_later_actual_action_and_referenced_speaker_clauses(self):
        for text, wanted in (
            ("Митинг отменили, но участники акции собрались на площади", "protest"),
            ("МИД направил дипломатический протест, затем жители вышли на митинг", "protest"),
            ("Протест завершился, затем делегации начали переговоры", "diplomatic"),
            ("Путин прокомментировал протесты, затем полиция начала разгон митинга", "police dispersal"),
        ):
            self.assertIn(wanted, fallback_visual_query(text))
            self.assertIn(wanted, voice_scenes([text])[0]["visual_query_en"])
        for text, identity in (
            ("Зеленский прокомментировал заявление о том, что Путин выступит завтра", "zelensky"),
            ("Путин заявил, что Зеленский отверг предложение", "putin"),
        ):
            self.assertEqual([identity], visual_intent(text, VISUAL_TERMS)["target_people"])

    def test_police_presence_advisory_tag_does_not_prove_dispersal(self):
        item = FootageItem("peace.mp4", "peaceful rally placards police guarding",
                           tags=["protest-crowd", "public-unrest-police"])
        self.assertTrue(bridge._semantic_clip_ok(fallback_visual_query("Полиция охраняет мирный митинг"), item))

    def test_independent_events_geography_and_marches(self):
        query = fallback_visual_query("Наступление не началось и артиллерия продолжила огонь")
        self.assertNotIn("advancing", query)
        self.assertIn("artillery", query)
        self.assertIn("unrest", fallback_visual_query("На улицах вспыхнули беспорядки"))
        query = fallback_visual_query("В Киеве жители вышли на митинг")
        self.assertIn("Kyiv", query)
        self.assertFalse(bridge._semantic_clip_ok(query, FootageItem("x.mp4", "Moscow peaceful rally", tags=["protest-crowd"])))
        for description in ("peaceful demonstration placards", "peaceful march placards"):
            self.assertTrue(bridge._semantic_clip_ok("peaceful civilian protest rally", FootageItem("x.mp4", description)))

    def test_fast_reuse_escapes_previous_battle_pool_for_protest(self):
        query = fallback_visual_query("На митинге не было столкновений")
        bad = FootageItem("battle.mp4", "frontline battle", tags=["frontline-combat"])
        good = FootageItem("march.mp4", "peaceful march placards", tags=["protest-crowd"])
        levels = {"STRICT_MATCH": [SearchHit(bad, .99, 6), SearchHit(good, .8, 6)]}
        pool = {bridge._montage_clip_key(bad.path): TimelineClip(bad.path, "", "frontline", duration=6)}
        cached = bridge._fast_reuse_pool_hits(levels, pool, 6, lambda _: 6, scene_query=query)
        self.assertEqual([], cached["STRICT_MATCH"])
        self.assertEqual(good.path, select(query, [bad, good]).item.path)

    def test_new_child_process_inherits_disposable_storage(self):
        import json
        import os
        import subprocess
        import sys
        code = "import json,os; from scriptor.config import app_data_root; print(json.dumps([str(app_data_root()),os.environ['NEWSFLOW_RENDER_TEMP_ROOT'],os.environ['LOCALAPPDATA']]))"
        paths = json.loads(subprocess.check_output([sys.executable, '-c', code], text=True))
        boundary = Path(os.environ['NEWSFLOW_TEST_ROOT']).resolve()
        self.assertTrue(all(Path(path).resolve().is_relative_to(boundary) for path in paths))

    def test_protest_tail_chooses_peaceful_context_over_battle(self):
        from scriptor.config import Settings
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            voice = root / 'voice.wav'
            voice.touch()
            query = fallback_visual_query("Мирный митинг проходит на площади")
            project = TimelineProject('tail', voiceover_path=str(voice), clips=[
                TimelineClip(str(root / 'old.mp4'), "Мирный митинг", query, duration=6)])
            bad = FootageItem(str(root / 'battle.mp4'), 'frontline battle', tags=['frontline-combat'])
            good = FootageItem(str(root / 'peace.mp4'), 'peaceful march placards', tags=['protest-crowd'])
            with (patch.object(bridge, 'probe_media_duration', return_value=10),
                  patch.object(bridge, '_cached_or_probed_montage_duration', return_value=6),
                  patch.object(bridge, '_replacement_candidates_for_clip', return_value=[bad, good])):
                self.assertEqual(1, bridge._complete_project_visual_tail(project, None, Settings()))
            self.assertEqual(good.path, project.clips[-1].path)
            self.assertAlmostEqual(project.clips[-1].source_start, 0)

    def test_mixed_model_tags_cannot_make_battle_a_civilian_port(self):
        battle = FootageItem('map.mp4', 'frontline operations map',
                             tags=['frontline-combat', 'war-action', 'oil-pipeline-refinery'])
        self.assertFalse(bridge._semantic_clip_ok('seaport cargo cranes ships', battle))
        with self.assertRaises(bridge.MontageSelectionFailure):
            select('seaport cargo cranes ships', [battle])

    def test_generic_rally_is_context_for_workers_or_farmers_not_exact_action(self):
        rally = FootageItem('rally.mp4', 'peaceful civilian rally placards', tags=['protest-crowd'])
        for text in ('Рабочие объявили забастовку', 'Фермеры протестуют у здания правительства'):
            result = select(fallback_visual_query(text), [rally])
            self.assertEqual('SAFE_CONTEXT', result.fallback_level)

    def test_ceasefire_is_not_fire_and_contextual_clashes_remain_real(self):
        battle = FootageItem('battle.mp4', 'frontline operations map',
                             tags=['frontline-combat', 'war-action', 'diplomatic-negotiations'])
        self.assertFalse(bridge._semantic_clip_ok(fallback_visual_query('Стороны договорились о прекращении огня'), battle))
        for text in ('На площади прошёл митинг, произошли столкновения',
                     'На митинге не было столкновений, затем полиция начала разгон'):
            self.assertIn('police dispersal', fallback_visual_query(text))

    def test_fast_context_does_not_hide_available_direct_labor_action(self):
        query = fallback_visual_query('Рабочие объявили забастовку')
        context = FootageItem('rally.mp4', 'peaceful civilian rally placards', tags=['protest-crowd'])
        direct = FootageItem('labor.mp4', 'workers labor strike picket line', tags=['workers-strike'])
        levels = {'STRICT_MATCH': [SearchHit(context, .99, 6), SearchHit(direct, .4, 6)]}
        pool = {bridge._montage_clip_key(context.path): TimelineClip(context.path, '', '', duration=6)}
        self.assertEqual([], bridge._fast_reuse_pool_hits(levels, pool, 6, lambda _: 6, scene_query=query)['STRICT_MATCH'])
        self.assertEqual(direct.path, select(query, [context, direct]).item.path)
        # No direct action in the library: reuse of suitable context still works.
        fallback = bridge._fast_reuse_pool_hits({'STRICT_MATCH': levels['STRICT_MATCH'][:1]}, pool, 6,
                                               lambda _: 6, scene_query=query)
        self.assertEqual(context.path, fallback['STRICT_MATCH'][0].item.path)

