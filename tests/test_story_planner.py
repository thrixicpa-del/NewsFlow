import json
import unittest

from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    repair_story_plan_face_metadata_response,
    repair_story_plan_parts_response,
    seam_tail,
    story_plan_from_dict,
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

    def test_planner_cannot_disable_core_face_requirement(self):
        person = {"name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
                  "relation_to_story": "выступил", "source": "selected_people", "confidence": 0.94}

        with self.assertRaisesRegex(ValueError, "cover_face_required"):
            parse_story_plan_response(
                self._single_part_cover_response(candidates=[person], primary=person, required=False), (5000,),
            )

    def test_fresh_planner_response_cannot_leave_cover_face_for_manual_review(self):
        """Malformed face metadata becomes bounded repair work, not a Writer blocker."""
        plan = parse_story_plan_response(
            self._single_part_cover_response(candidates=[], primary=None, status="NEEDS_REVIEW"),
            (5000,), require_cover_person=True,
        )
        self.assertTrue(plan.cover_face_repair_needed)
        self.assertEqual(plan.cover_face_resolution_status, "LOW_CONFIDENCE")

    def test_ranked_people_require_primary_first_and_non_increasing_confidence(self):
        primary = {"name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
                   "relation_to_story": "выступил", "source": "selected_people", "confidence": 0.94}
        weaker = {"name": "Амина Диалло", "entity_type": "person", "role_in_story": "министр",
                  "relation_to_story": "участвует", "source": "entities", "confidence": 0.71}
        ranked = parse_story_plan_response(
            self._single_part_cover_response(candidates=[primary, weaker], primary=primary), (5000,),
        )
        self.assertEqual(ranked.to_dict()["cover_people_candidates"][0]["name"], "Марек Новак")

        reordered = parse_story_plan_response(
            self._single_part_cover_response(candidates=[weaker, primary], primary=primary), (5000,),
        )
        self.assertEqual(reordered.cover_people_candidates[0]["name"], "Марек Новак")

    def test_anchor_derived_person_requires_low_confidence_evidence_not_resolved(self):
        person = {"name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "председатель",
                  "relation_to_story": "отвечает за решение комиссии", "source": "institution-decision-maker",
                  "confidence": 0.62, "evidence_type": "ANCHOR_DERIVED",
                  "evidence_summary": "Контекст связывает комиссию с решением и её председателем."}

        self.assertEqual(parse_story_plan_response(
            self._single_part_cover_response(candidates=[person], primary=person), (5000,),
        ).cover_face_resolution_status, "LOW_CONFIDENCE")
        plan = parse_story_plan_response(
            self._single_part_cover_response(candidates=[person], primary=person, status="LOW_CONFIDENCE"), (5000,),
        )
        self.assertEqual(plan.to_dict()["cover_primary_person"]["evidence_type"], "ANCHOR_DERIVED")
    def test_parser_persists_ranked_cover_people_and_primary_person(self):
        response = json.dumps({
            "thesis": "История с проверяемым главным действующим лицом.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1",
                               "content_kind": "SUPPORTED"}],
            "cover_face_required": True,
            "cover_people_candidates": [
                {"name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
                 "relation_to_story": "выступил по центральному вопросу", "source": "selected_people",
                 "confidence": 0.94},
                {"name": "Амина Диалло", "entity_type": "person", "role_in_story": "министр",
                 "relation_to_story": "участвует в переговорах", "source": "entities", "confidence": 0.71},
            ],
            "cover_primary_person": {"name": "Марек Новак", "entity_type": "public_figure",
                                     "role_in_story": "президент", "relation_to_story": "выступил по центральному вопросу",
                                     "source": "selected_people", "confidence": 0.94},
            "cover_face_resolution_status": "RESOLVED",
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"]}],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,))
        persisted = plan.to_dict()

        self.assertTrue(persisted["cover_face_required"])
        self.assertEqual(persisted["cover_primary_person"]["name"], "Марек Новак")
        self.assertEqual([row["name"] for row in persisted["cover_people_candidates"]], ["Марек Новак", "Амина Диалло"])
        self.assertEqual(persisted["cover_face_resolution_status"], "LOW_CONFIDENCE")
        self.assertEqual(persisted["cover_primary_person"]["provider_evidence_claim"]["source"], "selected_people")

    def test_parser_rejects_non_person_primary_cover_entity(self):
        response = json.dumps({
            "thesis": "История.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1",
                               "content_kind": "SUPPORTED"}],
            "cover_face_required": True,
            "cover_people_candidates": [{"name": "Европейский Союз", "entity_type": "organization",
                                         "role_in_story": "сторона", "relation_to_story": "контекст",
                                         "source": "entities", "confidence": 0.9}],
            "cover_primary_person": {"name": "Европейский Союз", "entity_type": "organization",
                                     "role_in_story": "сторона", "relation_to_story": "контекст",
                                     "source": "entities", "confidence": 0.9},
            "cover_face_resolution_status": "RESOLVED",
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"]}],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,))
        self.assertTrue(plan.cover_face_repair_needed)
        self.assertIsNone(plan.cover_primary_person)

    def test_malformed_face_metadata_does_not_invalidate_valid_story_structure(self):
        response = self._single_part_cover_response(
            candidates=[
                {"name": "Европейский Союз", "entity_type": "organization", "role_in_story": "сторона", "relation_to_story": "решение", "source": "provider", "confidence": 0.9},
                {"name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "председатель", "relation_to_story": "подписал решение", "source": "provider", "confidence": 0.7},
            ],
            primary={"name": "Европейский Союз", "entity_type": "organization", "role_in_story": "сторона", "relation_to_story": "решение", "source": "provider", "confidence": 0.9},
        )
        plan = parse_story_plan_response(response, (5000,))
        self.assertEqual(plan.parts[0].id, "P1")
        self.assertEqual(plan.cover_primary_person["name"], "Марек Новак")
        self.assertTrue(plan.cover_face_repair_needed)

    def test_face_only_repair_normalizes_a_named_role_without_rewriting_story(self):
        plan = parse_story_plan_response(
            self._single_part_cover_response(candidates=[], primary=None, status="NEEDS_REVIEW"), (5000,),
        )
        repaired = repair_story_plan_face_metadata_response(json.dumps({
            "cover_people_candidates": [{"name": "Иван Петров", "entity_type": "president", "role_in_story": "президент", "relation_to_story": "принял решение", "source": "repair", "confidence": 0.61}],
            "cover_primary_person": {"name": "Иван Петров", "entity_type": "president", "role_in_story": "президент", "relation_to_story": "принял решение", "source": "repair", "confidence": 0.61},
            "cover_face_resolution_status": "LOW_CONFIDENCE",
        }, ensure_ascii=False), plan)
        self.assertEqual(repaired.thesis, plan.thesis)
        self.assertEqual(repaired.parts, plan.parts)
        self.assertEqual(repaired.cover_primary_person["entity_type"], "public_figure")
        self.assertFalse(repaired.cover_face_repair_needed)

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

    def test_parser_accepts_low_confidence_real_person_after_deeper_actor_resolution(self):
        response = json.dumps({
            "thesis": "История решения институции.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1",
                               "content_kind": "SUPPORTED"}],
            "cover_face_required": True,
            "cover_people_candidates": [{"name": "Марек Новак", "entity_type": "public_figure",
                                         "role_in_story": "председатель комиссии", "relation_to_story": "отвечает за решение",
                                         "source": "institution-decision-maker", "confidence": 0.62}],
            "cover_primary_person": {"name": "Марек Новак", "entity_type": "public_figure",
                                     "role_in_story": "председатель комиссии", "relation_to_story": "отвечает за решение",
                                     "source": "institution-decision-maker", "confidence": 0.62},
            "cover_face_resolution_status": "LOW_CONFIDENCE",
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"]}],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,))

        self.assertEqual(plan.to_dict()["cover_face_resolution_status"], "LOW_CONFIDENCE")

    def test_legacy_persisted_plan_defaults_cover_resolution_to_needs_review(self):
        legacy = {
            "thesis": "Старая история.", "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Контекст", "owner_part_id": "P1"}],
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "Вся история", "macro_id": "M1",
                       "content_ids": ["C001"], "target_chars": 5000}],
        }

        persisted = story_plan_from_dict(legacy).to_dict()

        self.assertTrue(persisted["cover_face_required"])
        self.assertEqual(persisted["cover_people_candidates"], [])
        self.assertIsNone(persisted["cover_primary_person"])
        self.assertEqual(persisted["cover_face_resolution_status"], "NEEDS_REVIEW")
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

    def test_planner_prompt_requires_ranked_public_figure_resolution_for_covers(self):
        prompt = build_story_planner_prompt(ScenarioRequest(0, "Тема", "Контекст"), (5000,))

        self.assertIn("cover_people_candidates", prompt)
        self.assertIn("cover_primary_person", prompt)
        self.assertIn("LOW_CONFIDENCE", prompt)
        self.assertIn("Never infer a person from geography", prompt)
        self.assertIn("Never return NEEDS_REVIEW", prompt)

    def test_planner_uses_place_or_institution_as_an_anchor_for_contextual_actor_resolution(self):
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "ЕС вводит новые ограничения", "Сторона решения: Еврокомиссия."),
            (5000,),
        )

        self.assertIn("institution/place/event as a semantic", prompt)
        self.assertIn("decision maker", prompt)
        self.assertIn("Do not stop at the institution/place/event", prompt)

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
        self.assertIn("USED CONTENT (do not repeat): C001 [SUPPORTED]: Начальное событие уже раскрыто", prompt)
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
