import json
import unittest

from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    repair_story_plan_parts_response,
    seam_tail,
    story_plan_from_dict,
)


class StoryPartSizingTests(unittest.TestCase):
    def test_short_scenarios_stay_single_complete_parts_until_ten_thousand(self):
        """A 6–9k brief is a compact whole, not an artificial continuation."""
        self.assertEqual(calculate_story_part_targets(6000), (6000,))
        self.assertEqual(calculate_story_part_targets(7500), (7500,))
        self.assertEqual(calculate_story_part_targets(9000), (9000,))
        self.assertEqual(len(calculate_story_part_targets(10000)), 2)
        self.assertEqual(len(calculate_story_part_targets(15000)), 3)

    def test_part_targets_scale_evenly_around_five_thousand_characters(self):
        self.assertEqual(calculate_story_part_targets(5000), (5000,))
        self.assertEqual(calculate_story_part_targets(15000), (4999, 4999, 4998))
        self.assertEqual(len(calculate_story_part_targets(50000)), 10)
        self.assertEqual(len(calculate_story_part_targets(150000)), 30)
        targets = calculate_story_part_targets(15123)
        self.assertEqual(sum(targets) + 2 * (len(targets) - 1), 15123)
        self.assertLessEqual(max(targets) - min(targets), 1)

    def test_exact_overall_target_includes_deterministic_assembly_separators(self):
        targets = calculate_story_part_targets(10000)
        self.assertEqual(len(targets), 2)
        self.assertEqual(sum(targets) + 2, 10000)


class StoryPlanValidationTests(unittest.TestCase):
    def _single_part_cover_response(self, *, candidates, primary, status="RESOLVED", required=True):
        return json.dumps({
            "thesis": "Проверяемая история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1",
                               "content_kind": "SUPPORTED"}],
            "cover_face_required": required,
            "cover_people_candidates": candidates,
            "cover_primary_person": primary,
            "cover_face_resolution_status": status,
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"]}],
        }, ensure_ascii=False)

    def test_parser_accepts_transport_wrapped_json_without_relaxing_schema(self):
        response = self._single_part_cover_response(candidates=[], primary=None, status="NEEDS_REVIEW")
        for wrapped in (
            f"```json\n{response}\n```",
            f"Вот JSON Story Map:\n{response}\nГотово.",
        ):
            with self.subTest(wrapped=wrapped[:20]):
                plan = parse_story_plan_response(wrapped, (5000,))
                self.assertEqual(plan.parts[0].id, "P1")
                self.assertEqual(plan.thesis, "Проверяемая история.")

    def test_cover_metadata_is_inert_for_a_scenario_story_map(self):
        """A valid story neither requires nor persists Covers-only fields."""
        raw = json.loads(self._single_part_cover_response(
            candidates=[{"name": "Не человек", "entity_type": "organization"}],
            primary={"name": "Не человек", "entity_type": "organization"},
            required=False,
        ))
        plan = parse_story_plan_response(json.dumps(raw, ensure_ascii=False), (5000,))

        persisted = plan.to_dict()
        self.assertEqual(plan.parts[0].role, "COMPLETE")
        self.assertFalse(any(key.startswith("cover_") for key in persisted))

    def test_structural_repair_accepts_fenced_original_and_repair_json(self):
        original = json.dumps({
            "thesis": "Одна история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P1", "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001", "C002"]},
            ],
        }, ensure_ascii=False)
        repair = json.dumps({"parts": [
            {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
             "content_ids": ["C001"], "opens": [], "closes": []},
            {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
             "content_ids": ["C002"], "opens": [], "closes": []},
        ]}, ensure_ascii=False)

        plan = repair_story_plan_parts_response(
            f"```json\n{repair}\n```",
            f"Planner result:\n```json\n{original}\n```",
            (5000, 5000),
        )

        self.assertEqual([part.id for part in plan.parts], ["P1", "P2"])
        self.assertEqual([atom.owner_part_id for atom in plan.content_atoms], ["P1", "P2"])

    def test_exact_two_part_repair_changes_only_parts_and_requires_opening_final(self):
        original = json.dumps({
            "thesis": "Одна история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P2", "content_kind": "SUPPORTED"},
            ],
            "parts": [{"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001"]}],
        }, ensure_ascii=False)
        repaired = repair_story_plan_parts_response(json.dumps({"parts": [
            {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001"], "opens": [], "closes": []},
            {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1", "content_ids": ["C002"], "opens": [], "closes": []},
        ]}, ensure_ascii=False), original, (5000, 5000))
        self.assertEqual([part.role for part in repaired.parts], ["OPENING", "FINAL"])
        self.assertEqual(repaired.thesis, "Одна история.")

    def test_exact_two_part_repair_redistributes_atoms_owned_only_by_missing_part(self):
        """A one-part provider map may put every atom on P1; repair owns P2 explicitly."""
        original = json.dumps({
            "thesis": "Одна история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P1", "content_kind": "DRAMATIZED"},
            ],
            "parts": [{"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001", "C002"]}],
        }, ensure_ascii=False)
        repaired = repair_story_plan_parts_response(json.dumps({"parts": [
            {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001"], "opens": ["финал"], "closes": []},
            {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1", "content_ids": ["C002"], "opens": [], "closes": ["финал"]},
        ]}, ensure_ascii=False), original, (5000, 5000))

        self.assertEqual([part.role for part in repaired.parts], ["OPENING", "FINAL"])
        self.assertEqual([(atom.id, atom.owner_part_id, atom.content_kind) for atom in repaired.content_atoms], [
            ("C001", "P1", "SUPPORTED"), ("C002", "P2", "DRAMATIZED"),
        ])

    def test_exact_two_part_repair_collapses_three_part_ownership_without_rewriting_atoms(self):
        """A three-part provider map is repaired to two parts by the returned content ownership."""
        original = json.dumps({
            "thesis": "Одна история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Развитие", "owner_part_id": "P2", "content_kind": "SUPPORTED"},
                {"id": "C003", "summary": "Финал", "owner_part_id": "P3", "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001"]},
                {"id": "P2", "role": "MIDDLE", "purpose": "Развитие", "macro_id": "M1", "content_ids": ["C002"]},
                {"id": "P3", "role": "FINAL", "purpose": "Финал", "macro_id": "M1", "content_ids": ["C003"]},
            ],
        }, ensure_ascii=False)
        repaired = repair_story_plan_parts_response(json.dumps({"parts": [
            {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1", "content_ids": ["C001"], "opens": ["финал"], "closes": []},
            {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1", "content_ids": ["C002", "C003"], "opens": [], "closes": ["финал"]},
        ]}, ensure_ascii=False), original, (5000, 5000))

        self.assertEqual([part.id for part in repaired.parts], ["P1", "P2"])
        self.assertEqual([(atom.id, atom.owner_part_id, atom.summary, atom.content_kind) for atom in repaired.content_atoms], [
            ("C001", "P1", "Вход", "SUPPORTED"),
            ("C002", "P2", "Развитие", "SUPPORTED"),
            ("C003", "P2", "Финал", "DRAMATIZED"),
        ])

    def test_legacy_persisted_plan_ignores_cover_metadata_on_scenario_resume(self):
        legacy = {
            "thesis": "Старая история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1"}],
            "cover_face_required": False,
            "cover_primary_person": {"name": "Неважно", "entity_type": "organization"},
            "cover_face_resolution_status": "FACE_REPAIR_DEFERRED",
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"], "target_chars": 5000}],
        }

        persisted = story_plan_from_dict(legacy).to_dict()

        self.assertEqual(persisted["thesis"], "Старая история.")
        self.assertFalse(any(key.startswith("cover_") for key in persisted))
    def test_parser_persists_novelty_contract_and_legacy_parts_get_safe_fallbacks(self):
        explicit = json.dumps({
            "thesis": "История движется по разным вопросам.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Что изменило исходную ситуацию", "owner_part_id": "P1",
                 "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Как ответила другая сторона", "owner_part_id": "P2",
                 "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Показать исходное изменение", "macro_id": "M1",
                 "content_ids": ["C001"], "novelty_question": "Что именно изменилось в начале?",
                 "novelty_payload": "Зритель впервые узнаёт конкретное исходное изменение."},
                {"id": "P2", "role": "FINAL", "purpose": "Показать ответ и результат", "macro_id": "M1",
                 "content_ids": ["C002"], "novelty_question": "Какой ответ последовал на это изменение?",
                 "novelty_payload": "Зритель впервые узнаёт реакцию и её новое последствие."},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(explicit, (5000, 5000))
        self.assertEqual(plan.parts[0].novelty_question, "Что именно изменилось в начале?")
        self.assertIn("реакцию", plan.parts[1].novelty_payload)

        legacy = {
            "thesis": "Старая карта без novelty-полей.",
            "macro_blocks": [{"id": "M1", "purpose": "Вся история"}],
            "content_atoms": [{"id": "C001", "summary": "Старый самостоятельный смысл",
                               "owner_part_id": "P1", "content_kind": "SUPPORTED"}],
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Раскрыть старый смысл",
                       "macro_id": "M1", "content_ids": ["C001"], "target_chars": 5000}],
        }
        restored = story_plan_from_dict(legacy)
        self.assertEqual(restored.parts[0].novelty_question, "Раскрыть старый смысл")
        self.assertEqual(restored.parts[0].novelty_payload, "Старый самостоятельный смысл")

    def test_parser_rejects_obvious_near_copy_semantic_atoms(self):
        response = json.dumps({
            "thesis": "История без смысловых дублей.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Высокая цена помидоров вызывает устойчивое раздражение покупателей",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED",
                 "novelty_question": "Почему цена раздражает покупателей?",
                 "novelty_payload": "Высокая цена помидоров вызывает устойчивое раздражение покупателей."},
                {"id": "C002", "summary": "Высокая цена помидоров вызывает устойчивое раздражение покупателей снова",
                 "owner_part_id": "P2", "content_kind": "DRAMATIZED",
                 "novelty_question": "Почему цена снова раздражает покупателей?",
                 "novelty_payload": "Высокая цена помидоров вызывает устойчивое раздражение покупателей снова."},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Показать исходный ценовой шок",
                 "macro_id": "M1", "content_ids": ["C001"]},
                {"id": "P2", "role": "FINAL", "purpose": "Показать отдельное последствие",
                 "macro_id": "M1", "content_ids": ["C002"]},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "materially distinct"):
            parse_story_plan_response(response, (5000, 5000))

    def test_parser_rejects_obvious_near_copy_part_novelty_contracts(self):
        response = json.dumps({
            "thesis": "Части обязаны отвечать на разные вопросы.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Покупатели замечают новый ценовой уровень на рынке",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Продавцы меняют закупочную тактику из-за поставок",
                 "owner_part_id": "P2", "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Первый механизм", "macro_id": "M1",
                 "content_ids": ["C001"],
                 "novelty_question": "Почему высокая цена вызывает устойчивое раздражение покупателей?",
                 "novelty_payload": "Высокая цена становится постоянным повседневным раздражителем покупателей."},
                {"id": "P2", "role": "FINAL", "purpose": "Второй механизм", "macro_id": "M1",
                 "content_ids": ["C002"],
                 "novelty_question": "Почему высокая цена вызывает устойчивое раздражение покупателей?",
                 "novelty_payload": "Высокая цена становится постоянным повседневным раздражителем покупателей."},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "parts must own materially distinct"):
            parse_story_plan_response(response, (5000, 5000))


    def test_related_story_atoms_with_shared_topic_words_are_not_false_duplicates(self):
        """Same topic is allowed when actor/mechanism/consequence actually advances."""
        response = json.dumps({
            "thesis": "Одна тема развивается через разные причинные шаги.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие давления"}],
            "content_atoms": [
                {"id": "C001", "summary": "Высокая цена помидоров раздражает покупателей на городском рынке",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED",
                 "novelty_question": "Что первым замечают покупатели?",
                 "novelty_payload": "Покупатели фиксируют устойчиво высокий ценник на повседневный товар."},
                {"id": "C002", "summary": "Поставщики сокращают объём дешёвых партий после роста логистических затрат",
                 "owner_part_id": "P2", "content_kind": "DRAMATIZED",
                 "novelty_question": "Какой механизм удерживает цену?",
                 "novelty_payload": "Новый дефицит дешёвых поставок меняет закупочную тактику продавцов."},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Показать бытовой ценовой сигнал",
                 "macro_id": "M1", "content_ids": ["C001"],
                 "novelty_question": "Что первым замечают покупатели?",
                 "novelty_payload": "Покупатели видят устойчиво высокий ценник."},
                {"id": "P2", "role": "FINAL", "purpose": "Раскрыть отдельный механизм поставок",
                 "macro_id": "M1", "content_ids": ["C002"],
                 "novelty_question": "Почему цена не снижается после ожиданий?",
                 "novelty_payload": "Поставки и закупочная тактика создают новый механизм удержания цены."},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000, 5000))
        self.assertEqual([part.id for part in plan.parts], ["P1", "P2"])

    def test_legacy_persisted_repetitive_map_remains_readable(self):
        """New semantic guards must never invalidate an accepted legacy resume artifact."""
        legacy = {
            "thesis": "Старая карта.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Высокая цена вызывает устойчивое раздражение покупателей",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Высокая цена вызывает устойчивое раздражение покупателей снова",
                 "owner_part_id": "P2", "content_kind": "SUPPORTED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Первый шаг", "macro_id": "M1",
                 "content_ids": ["C001"], "target_chars": 5000},
                {"id": "P2", "role": "FINAL", "purpose": "Второй шаг", "macro_id": "M1",
                 "content_ids": ["C002"], "target_chars": 5000},
            ],
        }

        restored = story_plan_from_dict(legacy)
        self.assertEqual([part.id for part in restored.parts], ["P1", "P2"])
        self.assertEqual(restored.content_atoms[0].novelty_payload,
                         "Высокая цена вызывает устойчивое раздражение покупателей")

    def test_single_complete_writer_consumes_atom_novelty_in_one_way_order(self):
        """N=1 still needs internal progression; cross-part novelty cannot protect it."""
        response = json.dumps({
            "thesis": "Одна длинная COMPLETE-история движется по новым смысловым шагам.",
            "macro_blocks": [{"id": "M1", "purpose": "Полная причинная цепочка"}],
            "content_atoms": [
                {"id": "C001", "summary": "Одиночный протест начинается на площади",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED",
                 "novelty_question": "Что произошло первым?",
                 "novelty_payload": "Протестующий появляется в символическом месте."},
                {"id": "C002", "summary": "Охрана замечает акцию и вмешивается",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Как развивается реакция на месте?",
                 "novelty_payload": "Силовой ответ меняет ход сцены и прекращает акцию."},
                {"id": "C003", "summary": "Дело переходит из площади в судебную процедуру",
                 "owner_part_id": "P1", "content_kind": "SUPPORTED",
                 "novelty_question": "Что меняется после задержания?",
                 "novelty_payload": "Уличный эпизод превращается в отдельное юридическое последствие."},
                {"id": "C004", "summary": "Решение суда создаёт новое последствие для героя",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Чем заканчивается причинная цепочка?",
                 "novelty_payload": "Финал показывает конкретное последствие судебного решения."},
                {"id": "C005", "summary": "История получает более широкий общественный эффект",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Какой новый эффект остаётся после финала?",
                 "novelty_payload": "Событие становится отдельным общественным сигналом, а не повтором сцены."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Раскрыть всю причинную цепочку",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003", "C004", "C005"],
                "novelty_question": "Как одиночный эпизод проходит путь от события до последствия?",
                "novelty_payload": "Зритель получает пять последовательных новых смысловых шагов.",
            }],
        }, ensure_ascii=False)
        plan = parse_story_plan_response(response, (7000,))
        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Протест", "USER CONTRACT"),
            plan,
            [],
            0,
            7000,
        )

        self.assertIn("CURRENT ROLE: COMPLETE", prompt)
        self.assertIn("CURRENT CONTENT ORDER: consume the following atoms once, in listed order.", prompt)
        self.assertIn("CURRENT CONTENT:\n", prompt)
        self.assertIn("C001 [SUPPORTED]", prompt)
        self.assertIn("C005 [DRAMATIZED]", prompt)
        self.assertIn("Q=Что произошло первым?", prompt)
        self.assertIn("NEW=Уличный эпизод превращается", prompt)
        self.assertIn("Once an atom's question/new information has been explained", prompt)
        self.assertIn("single COMPLETE 6-9k story", prompt)

    def test_parser_requires_every_planned_part_and_unique_content_ownership(self):
        response = json.dumps({
            "thesis": "Одна история без второго круга.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Первый факт", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Второй факт", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001", "C002"]},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
                 "content_ids": ["C002"]},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "content atom"):
            parse_story_plan_response(response, (5000, 5000))

    def test_parser_requires_opening_middle_and_final_positions(self):
        response = json.dumps({
            "thesis": "Одна история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Середина", "owner_part_id": "P2", "content_kind": "SUPPORTED"},
                {"id": "C003", "summary": "Финал", "owner_part_id": "P3", "content_kind": "SUPPORTED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001"]},
                {"id": "P2", "role": "FINAL", "purpose": "Середина", "macro_id": "M1",
                 "content_ids": ["C002"]},
                {"id": "P3", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
                 "content_ids": ["C003"]},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "role"):
            parse_story_plan_response(response, (5000, 5000, 5000))

    def test_parser_requires_each_part_to_belong_to_a_real_macro_block(self):
        response = json.dumps({
            "thesis": "Одна история.",
            "macro_blocks": [{"id": "M1", "purpose": "Вход"}],
            "content_atoms": [
                {"id": "C001", "summary": "Факт", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P2", "content_kind": "SUPPORTED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001"]},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M404",
                 "content_ids": ["C002"]},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "unknown macro"):
            parse_story_plan_response(response, (5000, 5000))

    def test_orphan_provider_loop_hints_do_not_block_an_otherwise_valid_story_map(self):
        response = json.dumps({
            "thesis": "Одна непрерывная история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P2", "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001"], "opens": [], "closes": ["P2"]},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
                 "content_ids": ["C002"], "opens": [],
                 "closes": ["Вопрос о том, станет ли эта риторика началом переговоров"]},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000, 5000))

        self.assertEqual([part.id for part in plan.parts], ["P1", "P2"])
        self.assertEqual([part.opens for part in plan.parts], [(), ()])
        self.assertEqual([part.closes for part in plan.parts], [(), ()])

    def test_valid_cross_part_loop_hint_is_preserved_but_duplicate_or_unpaired_hints_are_advisory(self):
        response = json.dumps({
            "thesis": "Одна непрерывная история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1", "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P2", "content_kind": "SUPPORTED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001"], "opens": ["peace-question", "peace-question", "orphan"], "closes": []},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
                 "content_ids": ["C002"], "opens": [], "closes": ["peace-question"]},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000, 5000))

        self.assertEqual(plan.parts[0].opens, ("peace-question",))
        self.assertEqual(plan.parts[1].closes, ("peace-question",))

    def test_parser_persists_supported_and_dramatized_content_kinds(self):
        response = json.dumps({
            "thesis": "История развивается без повтора.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Подтверждённый контекст", "owner_part_id": "P1",
                 "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Драматизированный поворот", "owner_part_id": "P2",
                 "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                 "content_ids": ["C001"]},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "macro_id": "M1",
                 "content_ids": ["C002"]},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000, 5000))
        self.assertEqual(
            [atom.get("content_kind") for atom in plan.to_dict()["content_atoms"]],
            ["SUPPORTED", "DRAMATIZED"],
        )

    def test_parser_rejects_unknown_content_kind(self):
        response = json.dumps({
            "thesis": "Одна история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Материал", "owner_part_id": "P1",
                               "content_kind": "UNVERIFIED"}],
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"]}],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "content_kind"):
            parse_story_plan_response(response, (5000,))

    def test_legacy_persisted_plan_defaults_missing_content_kind_to_supported(self):
        legacy = {
            "thesis": "Старая сохранённая история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Старый материал", "owner_part_id": "P1"}],
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"], "target_chars": 5000}],
        }

        restored = story_plan_from_dict(legacy)
        self.assertEqual(restored.to_dict()["content_atoms"][0].get("content_kind"), "SUPPORTED")

    def test_capacity_failure_payload_is_no_longer_a_supported_plan_contract(self):
        response = json.dumps({
            "content_capacity_insufficient": True,
            "capacity_reason": "Старый capacity-сигнал.",
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "thesis"):
            parse_story_plan_response(response, (5000,))


class StoryPlannerPromptTests(unittest.TestCase):
    def test_operator_style_rules_are_reference_constraints_not_content_atoms(self):
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема", "МИКРО-ХУКИ. НЕ ПОВТОРЯЙСЯ. Факт темы: объект повреждён."),
            (4999, 4999),
        )
        self.assertIn("REFERENCE DATA FOR PLANNING", prompt)
        self.assertIn("constraints, NOT story material", prompt)
        self.assertIn("never turn rules such as hooks", prompt)
        self.assertIn("Факт темы: объект повреждён", prompt)
        self.assertNotIn("content_capacity_insufficient", prompt)
        self.assertIn("Even if only a headline is available", prompt)
        self.assertIn("DRAMATIZED", prompt)
        self.assertIn("novelty_question", prompt)
        self.assertIn("novelty_payload", prompt)
        self.assertIn("3-5 genuinely different atoms", prompt)
        self.assertIn("5-7", prompt)
        self.assertIn("novelty_question and novelty_payload", prompt)
        self.assertIn("synonym swap", prompt)

    def test_planner_prompt_contains_only_story_planning_contract(self):
        prompt = build_story_planner_prompt(ScenarioRequest(0, "Тема", "Контекст"), (5000,))

        self.assertNotIn("COVER FACE RESOLUTION", prompt)
        self.assertNotIn("cover_people_candidates", prompt)
        self.assertNotIn("cover_primary_person", prompt)

    def test_single_part_planner_prompt_requires_one_complete_part(self):
        prompt = build_story_planner_prompt(ScenarioRequest(0, "Тема", "Контекст"), (5000,))

        self.assertIn("For one part, use P1 as COMPLETE", prompt)

    def test_single_part_planner_without_length_uses_natural_complete_length(self):
        prompt = build_story_planner_prompt(ScenarioRequest(0, "Тема", "Контекст"), (0,))

        self.assertIn("P1=natural complete length", prompt)
        self.assertNotIn("P1≈0 chars", prompt)


class StoryWriterContextTests(unittest.TestCase):
    def _plan(self):
        return parse_story_plan_response(json.dumps({
            "thesis": "История развивается один раз и приходит к одному финалу.",
            "macro_blocks": [
                {"id": "M1", "purpose": "Событие и развитие"},
                {"id": "M2", "purpose": "Последствия и финал"},
            ],
            "content_atoms": [
                {"id": "C001", "summary": "Начальное событие уже раскрыто", "owner_part_id": "P1",
                 "content_kind": "SUPPORTED"},
                {"id": "C002", "summary": "Новый механизм для текущей части", "owner_part_id": "P2",
                 "content_kind": "DRAMATIZED"},
                {"id": "C003", "summary": "Будущее последствие, которое ещё нельзя раскрывать", "owner_part_id": "P3",
                 "content_kind": "DRAMATIZED"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Открыть историю", "macro_id": "M1",
                 "content_ids": ["C001"], "opens": ["L1"], "closes": [],
                 "transition_direction": "к механизму",
                 "novelty_question": "Что именно произошло в начале?",
                 "novelty_payload": "Начальное событие и его непосредственный новый эффект."},
                {"id": "P2", "role": "MIDDLE", "purpose": "Углубить механизм", "macro_id": "M1",
                 "content_ids": ["C002"], "opens": [], "closes": [],
                 "transition_direction": "к последствиям",
                 "novelty_question": "Как работает новый механизм давления?",
                 "novelty_payload": "Механизм, участники и реакция, которых не было в открытии."},
                {"id": "P3", "role": "FINAL", "purpose": "Завершить историю", "macro_id": "M2",
                 "content_ids": ["C003"], "opens": [], "closes": ["L1"],
                 "transition_direction": "финал",
                 "novelty_question": "Какое новое последствие завершает историю?",
                 "novelty_payload": "Финальное последствие и закрытие причинной цепочки."},
            ],
        }, ensure_ascii=False), (5000, 5000, 5000))

    def test_middle_writer_receives_bounded_seam_plus_semantic_past_and_future_memory(self):
        first_part = ("Ранний материал, который не должен целиком попадать в следующий запрос. " * 120).strip()
        prompt = build_story_writer_prompt(
            ScenarioRequest(
                0, "Тема",
                "OPERATOR CONTRACT MUST STAY INTACT. OVERALL TARGET 15000. RETURN THE COMPLETE FINISHED SCENARIO.",
            ),
            self._plan(),
            [{"part_id": "P1", "text": first_part, "content_ids": ["C001"]}],
            1,
        )

        self.assertIn("OPERATOR CONTRACT MUST STAY INTACT", prompt)
        self.assertIn("OVERALL TARGET 15000", prompt)
        self.assertIn("CURRENT TARGET: approximately 5000 characters", prompt)
        self.assertIn("not the overall scenario target", prompt)
        self.assertIn("FINAL ASSEMBLED STORY", prompt)
        self.assertIn("CURRENT PART: P2", prompt)
        self.assertIn("CURRENT NOVELTY QUESTION: Как работает новый механизм давления?", prompt)
        self.assertIn("CURRENT NEW INFORMATION: Механизм, участники и реакция", prompt)
        self.assertIn("CURRENT CONTENT ORDER: consume the following atoms once, in listed order.", prompt)
        self.assertIn("CURRENT CONTENT:\n", prompt)
        self.assertIn("Q=", prompt)
        self.assertIn("NEW=", prompt)
        self.assertIn("USED CONTENT (do not repeat): C001 [SUPPORTED]: Начальное событие уже раскрыто", prompt)
        self.assertIn("USED SEMANTIC MEANINGS (forbidden to restate): P1:", prompt)
        self.assertIn("PARAPHRASE DOES NOT COUNT AS NEW INFORMATION", prompt)
        self.assertIn("A paragraph that adds no new story information should not be written", prompt)
        self.assertIn("P3/M2: Завершить историю", prompt)
        self.assertIn("C002 [DRAMATIZED]: Новый механизм для текущей части", prompt)
        self.assertIn("C003 [DRAMATIZED]: Будущее последствие, которое ещё нельзя раскрывать", prompt)
        self.assertIn("OPEN LOOPS BEFORE THIS PART: L1", prompt)
        self.assertIn("CURRENT MACRO: M1: Событие и развитие", prompt)
        self.assertNotIn(first_part, prompt)
        self.assertIn(seam_tail(first_part), prompt)
        self.assertLessEqual(len(seam_tail(first_part)), 500)
        self.assertIn("NO GLOBAL FINAL", prompt)
        self.assertIn("first 30 seconds", prompt)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", prompt)

    def test_only_opening_gets_one_dramatized_disclosure_instruction(self):
        request = ScenarioRequest(0, "Тема", "OPERATOR CONTRACT")
        plan = self._plan()

        opening = build_story_writer_prompt(request, plan, [], 0)
        middle = build_story_writer_prompt(
            request, plan,
            [{"part_id": "P1", "text": "Готовый первый фрагмент.", "content_ids": ["C001"]}],
            1,
        )
        final = build_story_writer_prompt(
            request, plan,
            [
                {"part_id": "P1", "text": "Готовый первый фрагмент.", "content_ids": ["C001"]},
                {"part_id": "P2", "text": "Готовый второй фрагмент.", "content_ids": ["C002"]},
            ],
            2,
        )

        self.assertEqual(opening.count("DRAMATIZED OPENING DISCLOSURE"), 1)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", middle)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", final)

    def test_all_supported_atoms_do_not_request_a_dramatized_disclosure(self):
        supported = self._plan().to_dict()
        for atom in supported["content_atoms"]:
            atom["content_kind"] = "SUPPORTED"
        plan = parse_story_plan_response(json.dumps(supported, ensure_ascii=False), (5000, 5000, 5000))

        opening = build_story_writer_prompt(ScenarioRequest(0, "Тема", "CONTRACT"), plan, [], 0)

        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", opening)

    def test_complete_writer_owns_opening_final_and_unbounded_length_rules(self):
        plan = parse_story_plan_response(json.dumps({
            "thesis": "Одна полная история.",
            "macro_blocks": [{"id": "M1", "purpose": "Вся история"}],
            "content_atoms": [{
                "id": "C001",
                "summary": "Драматизированное развитие",
                "owner_part_id": "P1",
                "content_kind": "DRAMATIZED",
            }],
            "parts": [{
                "id": "P1",
                "role": "COMPLETE",
                "purpose": "Открыть, развить и завершить",
                "macro_id": "M1",
                "content_ids": ["C001"],
            }],
        }, ensure_ascii=False), (0,))

        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "CONTRACT"),
            plan,
            [],
            0,
            current_target_chars=0,
        )

        self.assertIn("CURRENT TARGET: no explicit character target", prompt)
        self.assertNotIn("approximately 1 characters", prompt)
        self.assertIn("first-30-seconds", prompt)
        self.assertIn("final-section rules once", prompt)
        self.assertIn("Apply operator factual-discipline to SUPPORTED atoms", prompt)
        self.assertIn("for DRAMATIZED atoms use the explicit NewsFlow", prompt)
        self.assertNotIn("Preserve all global style, factual-discipline", prompt)
        self.assertEqual(prompt.count("DRAMATIZED OPENING DISCLOSURE"), 1)


if __name__ == "__main__":
    unittest.main()
