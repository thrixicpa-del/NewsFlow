import json
import unittest

from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    StoryPlanCapacityInsufficient,
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    seam_tail,
)


class StoryPartSizingTests(unittest.TestCase):
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
    def test_parser_requires_every_planned_part_and_unique_content_ownership(self):
        response = json.dumps({
            "thesis": "Одна история без второго круга.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Первый факт", "owner_part_id": "P1"},
                {"id": "C002", "summary": "Второй факт", "owner_part_id": "P1"},
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
                {"id": "C001", "summary": "Вход", "owner_part_id": "P1"},
                {"id": "C002", "summary": "Середина", "owner_part_id": "P2"},
                {"id": "C003", "summary": "Финал", "owner_part_id": "P3"},
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
                {"id": "C001", "summary": "Факт", "owner_part_id": "P1"},
                {"id": "C002", "summary": "Финал", "owner_part_id": "P2"},
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

    def test_capacity_insufficient_is_an_explicit_planner_signal(self):
        response = json.dumps({
            "content_capacity_insufficient": True,
            "capacity_reason": "Доступный контекст не даёт десять разных смысловых блоков без повторов.",
        }, ensure_ascii=False)

        with self.assertRaises(StoryPlanCapacityInsufficient) as raised:
            parse_story_plan_response(response, (5000,) * 10)

        self.assertIn("без повторов", raised.exception.reason)


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


class StoryWriterContextTests(unittest.TestCase):
    def _plan(self):
        return parse_story_plan_response(json.dumps({
            "content_capacity_insufficient": False,
            "thesis": "История развивается один раз и приходит к одному финалу.",
            "macro_blocks": [
                {"id": "M1", "purpose": "Событие и развитие"},
                {"id": "M2", "purpose": "Последствия и финал"},
            ],
            "content_atoms": [
                {"id": "C001", "summary": "Начальное событие уже раскрыто", "owner_part_id": "P1"},
                {"id": "C002", "summary": "Новый механизм для текущей части", "owner_part_id": "P2"},
                {"id": "C003", "summary": "Будущее последствие, которое ещё нельзя раскрывать", "owner_part_id": "P3"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Открыть историю", "macro_id": "M1",
                 "content_ids": ["C001"], "opens": ["L1"], "closes": [],
                 "transition_direction": "к механизму"},
                {"id": "P2", "role": "MIDDLE", "purpose": "Углубить механизм", "macro_id": "M1",
                 "content_ids": ["C002"], "opens": [], "closes": [],
                 "transition_direction": "к последствиям"},
                {"id": "P3", "role": "FINAL", "purpose": "Завершить историю", "macro_id": "M2",
                 "content_ids": ["C003"], "opens": [], "closes": ["L1"],
                 "transition_direction": "финал"},
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
        self.assertIn("USED CONTENT (do not repeat): C001: Начальное событие уже раскрыто", prompt)
        self.assertIn("P3/M2: Завершить историю", prompt)
        self.assertIn("C003: Будущее последствие, которое ещё нельзя раскрывать", prompt)
        self.assertIn("OPEN LOOPS BEFORE THIS PART: L1", prompt)
        self.assertIn("CURRENT MACRO: M1: Событие и развитие", prompt)
        self.assertNotIn(first_part, prompt)
        self.assertIn(seam_tail(first_part), prompt)
        self.assertLessEqual(len(seam_tail(first_part)), 500)
        self.assertIn("NO GLOBAL FINAL", prompt)
        self.assertIn("first 30 seconds", prompt)


if __name__ == "__main__":
    unittest.main()
