import json
import unittest

from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    seam_tail,
)


class StoryPartSizingTests(unittest.TestCase):
    def test_part_targets_scale_evenly_around_five_thousand_characters(self):
        self.assertEqual(calculate_story_part_targets(5000), (5000,))
        self.assertEqual(calculate_story_part_targets(15000), (5000, 5000, 5000))
        self.assertEqual(len(calculate_story_part_targets(50000)), 10)
        self.assertEqual(len(calculate_story_part_targets(150000)), 30)
        targets = calculate_story_part_targets(15123)
        self.assertEqual(sum(targets), 15123)
        self.assertLessEqual(max(targets) - min(targets), 1)


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
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "content_ids": ["C001", "C002"]},
                {"id": "P2", "role": "FINAL", "purpose": "Финал", "content_ids": ["C002"]},
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
                {"id": "P1", "role": "OPENING", "purpose": "Вход", "content_ids": ["C001"]},
                {"id": "P2", "role": "FINAL", "purpose": "Середина", "content_ids": ["C002"]},
                {"id": "P3", "role": "FINAL", "purpose": "Финал", "content_ids": ["C003"]},
            ],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "role"):
            parse_story_plan_response(response, (5000, 5000, 5000))


class StoryWriterContextTests(unittest.TestCase):
    def _plan(self):
        return parse_story_plan_response(json.dumps({
            "thesis": "История развивается один раз и приходит к одному финалу.",
            "macro_blocks": [
                {"id": "M1", "purpose": "Событие и развитие"},
                {"id": "M2", "purpose": "Последствия и финал"},
            ],
            "content_atoms": [
                {"id": "C001", "summary": "Начальное событие", "owner_part_id": "P1"},
                {"id": "C002", "summary": "Новый механизм", "owner_part_id": "P2"},
                {"id": "C003", "summary": "Последствие", "owner_part_id": "P3"},
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Открыть историю", "content_ids": ["C001"]},
                {"id": "P2", "role": "MIDDLE", "purpose": "Углубить механизм", "content_ids": ["C002"]},
                {"id": "P3", "role": "FINAL", "purpose": "Завершить историю", "content_ids": ["C003"]},
            ],
        }, ensure_ascii=False), (5000, 5000, 5000))

    def test_middle_writer_receives_only_bounded_previous_seam_and_future_index(self):
        first_part = ("Ранний материал, который не должен целиком попадать в следующий запрос. " * 120).strip()
        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT MUST STAY INTACT"),
            self._plan(),
            [{"part_id": "P1", "text": first_part, "content_ids": ["C001"]}],
            1,
        )

        self.assertIn("OPERATOR CONTRACT MUST STAY INTACT", prompt)
        self.assertIn("CURRENT PART: P2", prompt)
        self.assertIn("FUTURE RESERVED: P3", prompt)
        self.assertNotIn(first_part, prompt)
        self.assertIn(seam_tail(first_part), prompt)
        self.assertLessEqual(len(seam_tail(first_part)), 500)
        self.assertIn("NO GLOBAL FINAL", prompt)


if __name__ == "__main__":
    unittest.main()
