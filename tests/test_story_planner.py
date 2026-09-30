import json
import unittest
from pathlib import Path

from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    StoryContentAtom,
    StoryPartPlan,
    StoryPlan,
    _has_concrete_story_development,
    build_story_plan_structure_repair_prompt,
    build_story_planner_prompt,
    build_story_writer_prompt,
    calculate_story_part_targets,
    parse_story_plan_response,
    repair_story_plan_parts_response,
    seam_tail,
    split_story_planner_request,
    split_story_writer_request,
    story_part_skeleton,
    story_plan_from_dict,
    story_plan_structure_repair_response_format,
    story_planner_response_format,
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

    def test_part_target_matrix_never_moves_unplanned_volume_to_final(self):
        """Every supported target distributes content budget before Writers run."""
        for target, expected_parts in (
            (12_000, 3), (12_501, 3), (20_000, 4), (24_999, 5),
            (30_000, 6), (50_000, 10), (75_001, 16), (100_000, 20),
        ):
            with self.subTest(target=target):
                targets = calculate_story_part_targets(target)
                self.assertEqual(len(targets), expected_parts)
                self.assertEqual(sum(targets) + 2 * (len(targets) - 1), target)
                self.assertLessEqual(max(targets) - min(targets), 1)

    def test_runtime_part_skeleton_is_exact_for_all_supported_part_counts(self):
        self.assertEqual(
            story_part_skeleton(calculate_story_part_targets(6000)),
            "EXACT_PART_COUNT=1; P1=COMPLETE",
        )
        self.assertEqual(
            story_part_skeleton(calculate_story_part_targets(10000)),
            "EXACT_PART_COUNT=2; P1=OPENING; P2=FINAL",
        )
        self.assertEqual(
            story_part_skeleton(calculate_story_part_targets(12000)),
            "EXACT_PART_COUNT=3; P1=OPENING; P2=MIDDLE; P3=FINAL",
        )
        self.assertIn("EXACT_PART_COUNT=10", story_part_skeleton(calculate_story_part_targets(50000)))
        self.assertIn("P30=FINAL", story_part_skeleton(calculate_story_part_targets(150000)))

    def test_exact_overall_target_includes_deterministic_assembly_separators(self):
        targets = calculate_story_part_targets(10000)
        self.assertEqual(len(targets), 2)
        self.assertEqual(sum(targets) + 2, 10000)


class StoryPlanValidationTests(unittest.TestCase):
    def test_structured_output_schemas_match_new_and_legacy_story_map_contracts(self):
        """Fresh transport is strict without making legacy maps unreadable."""
        planner_format = story_planner_response_format()
        repair_format = story_plan_structure_repair_response_format()
        schema = planner_format["schema"]
        atom_schema = schema["properties"]["content_atoms"]["items"]

        self.assertTrue(planner_format["strict"])
        self.assertTrue(repair_format["strict"])
        self.assertEqual(planner_format["type"], "json_schema")
        self.assertIn("event_steps", atom_schema["required"])
        self.assertIn("event_spine", schema["required"])
        self.assertNotIn("writer_material", atom_schema["properties"])
        self.assertFalse(any("minItems" in repr(value) for value in (schema, repair_format["schema"])))

    def test_parser_persists_optional_event_spine_without_blocking_legacy_maps(self):
        raw = json.loads(self._single_part_cover_response(
            candidates=[], primary=None, status="NEEDS_REVIEW",
        ))
        raw["event_spine"] = [
            "Служба фиксирует сбой подачи ресурса.",
            "Дежурная бригада переключает резервный маршрут.",
            "Подача на критический участок восстанавливается.",
        ]
        plan = parse_story_plan_response(json.dumps(raw, ensure_ascii=False), (5000,))
        self.assertEqual(
            plan.event_spine,
            tuple(raw["event_spine"]),
        )
        self.assertEqual(plan.to_dict()["event_spine"], raw["event_spine"])

    def test_parser_rejects_damaged_root_instead_of_accepting_nested_macro(self):
        """A complete child object is never a substitute for a broken Story Map root."""
        damaged = (
            '{"thesis":"ROOT_EXISTS","macro_blocks":'
            '[{"id":"M1","purpose":"complete child"}],"parts":['
        )

        with self.assertRaisesRegex(ValueError, "must return strict JSON"):
            parse_story_plan_response(damaged, (5000,))

    def test_parser_accepts_one_plain_or_fenced_root_but_not_multiple_roots(self):
        response = self._single_part_cover_response(
            candidates=[], primary=None, status="NEEDS_REVIEW",
        )
        for wrapped in (response, f"```json\n{response}\n```"):
            with self.subTest(wrapped=wrapped[:8]):
                self.assertEqual(
                    parse_story_plan_response(wrapped, (5000,)).thesis,
                    "Проверяемая история.",
                )
        with self.assertRaisesRegex(ValueError, "must return strict JSON"):
            parse_story_plan_response(f"{response}\n{response}", (5000,))

    def test_parser_rejects_nested_object_in_damaged_array_and_multiple_wrapped_roots(self):
        """A complete child is not a root and a wrapper never selects one reply."""
        response = self._single_part_cover_response(
            candidates=[], primary=None, status="NEEDS_REVIEW",
        )
        damaged_array = f"[{response},"
        multiple_prose_roots = f"Planner reply follows:\n{response}\nSecond reply:\n{response}"
        multiple_fenced_roots = f"```json\n{response}\n```\n```json\n{response}\n```"

        for malformed in (damaged_array, multiple_prose_roots, multiple_fenced_roots):
            with (
                self.subTest(malformed=malformed[:32]),
                self.assertRaisesRegex(ValueError, "must return strict JSON"),
            ):
                parse_story_plan_response(malformed, (5000,))

    def test_parser_keeps_braces_in_json_strings_and_rejects_wrong_or_truncated_roots(self):
        raw = json.loads(self._single_part_cover_response(
            candidates=[], primary=None, status="NEEDS_REVIEW",
        ))
        raw["thesis"] = "Строка с {literal} braces остаётся в корне."
        response = json.dumps(raw, ensure_ascii=False)
        self.assertEqual(
            parse_story_plan_response(response, (5000,)).thesis,
            raw["thesis"],
        )
        with self.assertRaisesRegex(TypeError, "must be an object"):
            parse_story_plan_response("[]", (5000,))
        for malformed in ('{"thesis":"unterminated', '{"parts":['):
            with (
                self.subTest(malformed=malformed),
                self.assertRaisesRegex(ValueError, "must return strict JSON"),
            ):
                parse_story_plan_response(malformed, (5000,))

    def test_parser_normalizes_provider_nested_part_atoms_without_relaxing_ownership(self):
        """Responses may place the complete atom records beside their part IDs."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Одна последовательность.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Завершить", "macro_id": "M1",
                "content_ids": ["C001"], "content_atoms": [{
                    "id": "C001", "summary": "Служба публикует итог", "owner_part_id": "P1",
                    "content_kind": "DRAMATIZED", "state_before": "Проверка идёт.",
                    "changed_subject": "Статус проверки", "development": "Служба завершает проверку.",
                    "resulting_state": "Итог опубликован.", "state_after": "Проверка закрыта.",
                }],
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,), require_state_transitions=True)
        self.assertEqual(plan.content_atoms[0].id, "C001")
        self.assertEqual(plan.parts[0].content_ids, ("C001",))

    def test_saved_low_density_planner_maps_are_structurally_accepted(self):
        """Atom counts guide planning but never invalidate a complete Story Map.

        These are the two unmodified Responses returned during the prior
        event-spine acceptance.  P2 in the first and P3 in the second have
        fewer atoms than the old heuristic demanded, while their JSON,
        topology, ownership and transition fields are all complete.
        """
        evidence_root = Path(__file__).resolve().parents[1] / "docs" / "verification" / "evidence" / "scenario-live-293-event-spine-20260930-143000"
        for filename in ("response-01-visible.txt", "response-02-visible.txt"):
            with self.subTest(filename=filename):
                plan = parse_story_plan_response(
                    (evidence_root / filename).read_text(encoding="utf-8"),
                    (3999, 3999, 3998),
                    require_state_transitions=True,
                )
                self.assertEqual([part.id for part in plan.parts], ["P1", "P2", "P3"])

    def test_writer_semantic_memory_stays_bounded_for_a_large_plan(self):
        """A long plan reserves future material without dumping all prior detail."""
        atoms = []
        parts = []
        for part_number in range(1, 21):
            content_ids = []
            for atom_number in range(1, 4):
                atom_id = f"C{part_number:02d}_{atom_number}"
                content_ids.append(atom_id)
                atoms.append(StoryContentAtom(
                    id=atom_id,
                    summary=f"summary-{atom_id}-" + "s" * 800,
                    owner_part_id=f"P{part_number}",
                    content_kind="DRAMATIZED",
                    novelty_question=f"question-{atom_id}",
                    novelty_payload=f"payload-{atom_id}-" + "n" * 800,
                    state_before=f"before-{atom_id}",
                    changed_subject=f"subject-{atom_id}",
                    development=f"development-{atom_id}",
                    resulting_state=f"result-{atom_id}",
                    state_after=f"after-{atom_id}",
                    writer_material=(f"beat-{atom_id}",),
                ))
            role = "OPENING" if part_number == 1 else "FINAL" if part_number == 20 else "MIDDLE"
            parts.append(StoryPartPlan(
                id=f"P{part_number}", role=role, purpose=f"purpose-{part_number}", macro_id="M1",
                content_ids=tuple(content_ids), target_chars=4999,
                novelty_question=f"part-question-{part_number}",
                novelty_payload=f"part-payload-{part_number}",
            ))
        plan = StoryPlan(
            thesis="Большая история.", macro_blocks=({"id": "M1", "purpose": "развитие"},),
            content_atoms=tuple(atoms), parts=tuple(parts),
        )
        accepted = [
            {"part_id": part.id, "content_ids": list(part.content_ids),
             "text": f"OLD_BODY_{part.id}_" + "x" * 3000}
            for part in parts[:15]
        ]

        prompt = build_story_writer_prompt(
            ScenarioRequest(
                0, "Тема", "Контекст", target_chars=100000,
                allowed_min=95000, allowed_max=100500,
            ),
            plan,
            accepted,
            15,
        )

        self.assertIn("EARLIER USED IDS:", prompt)
        self.assertIn("FUTURE RESERVED IDS ONLY:", prompt)
        self.assertIn("C16_1 [DRAMATIZED]", prompt)
        self.assertIn("FIRST-PASS PART VOLUME: write roughly 4849-5025 characters", prompt)
        self.assertNotIn("OLD_BODY_P1", prompt)
        self.assertLess(len(prompt), 16000)

    def test_structured_transition_with_system_subject_is_not_rejected_by_lexical_guessing(self):
        """A valid state transition is not an analytical failure because of one noun."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Режим работы магазина меняется после решения владельца.",
            "macro_blocks": [{"id": "M1", "purpose": "Изменение режима работы"}],
            "content_atoms": [{
                "id": "C001", "summary": "Магазин открывает ночную смену",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "state_before": "Магазин работал только днём.",
                "changed_subject": "Режим работы магазина",
                "development": "Владелец открыл ночную смену.",
                "resulting_state": "Покупатели получили круглосуточный доступ.",
                "state_after": "Магазин стал доступен круглосуточно.",
                "novelty_question": "Как изменился режим работы?",
                "novelty_payload": "После решения владельца магазин начал работать ночью.",
                "do_not_repeat": "",
            }],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Показать решение и результат",
                "macro_id": "M1", "content_ids": ["C001"],
                "novelty_question": "Что изменило режим работы?",
                "novelty_payload": "Владелец открыл ночную смену, и магазин стал круглосуточным.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (2000,), require_state_transitions=True)

        self.assertEqual(plan.content_atoms[0].changed_subject, "Режим работы магазина")

    def test_novelty_duplicate_guard_preserves_numeric_and_negation_changes(self):
        """10→20 and permits→does not permit are different story states."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Сервис меняет лимит и затем закрывает экспорт.",
            "macro_blocks": [{"id": "M1", "purpose": "Последовательные изменения правил"}],
            "content_atoms": [
                {
                    "id": "C001", "summary": "Лимит сервиса повышен с 10 до 20 запросов",
                    "owner_part_id": "P1", "content_kind": "SUPPORTED",
                    "state_before": "Сервис принимает до 10 запросов в минуту.",
                    "changed_subject": "Лимит сервиса",
                    "development": "Администратор повысил лимит до 20 запросов в минуту.",
                    "resulting_state": "Пользователи могут отправлять 20 запросов в минуту.",
                    "state_after": "Сервис принимает до 20 запросов в минуту.",
                    "novelty_question": "Как изменился лимит?",
                    "novelty_payload": "Лимит вырос с 10 до 20 запросов в минуту.",
                },
                {
                    "id": "C002", "summary": "Сервис больше не разрешает экспорт отчётов",
                    "owner_part_id": "P2", "content_kind": "SUPPORTED",
                    "state_before": "Сервис разрешает клиентам экспортировать готовые отчёты.",
                    "changed_subject": "Правило экспорта",
                    "development": "Администратор запретил экспорт завершённых отчётов.",
                    "resulting_state": "Клиенты не могут выгружать готовые отчёты.",
                    "state_after": "Сервис не разрешает клиентам экспортировать готовые отчёты.",
                    "novelty_question": "Что изменилось в экспорте?",
                    "novelty_payload": "Экспорт завершённых отчётов больше не разрешён.",
                },
            ],
            "parts": [
                {"id": "P1", "role": "OPENING", "purpose": "Показать новый лимит", "macro_id": "M1", "content_ids": ["C001"],
                 "novelty_question": "Как изменился лимит?", "novelty_payload": "Лимит вырос с 10 до 20."},
                {"id": "P2", "role": "FINAL", "purpose": "Показать запрет", "macro_id": "M1", "content_ids": ["C002"],
                 "novelty_question": "Как изменился экспорт?", "novelty_payload": "Экспорт больше не разрешён."},
            ],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (2000, 2000), require_state_transitions=True)

        self.assertEqual([atom.id for atom in plan.content_atoms], ["C001", "C002"])

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

    def test_atom_transition_error_precedes_wrong_part_count(self):
        """A parts-only repair must never hide the first invalid atom contract."""
        raw = {
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Проверяемая история.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{
                "id": "C001", "summary": "Новое действие", "owner_part_id": "P1",
                "content_kind": "SUPPORTED", "state_before": "До действия.",
                "changed_subject": "Сторона", "development": "приняла решение",
                "resulting_state": "решение изменило статус",
            }],
            "parts": [{
                "id": "P1", "role": "OPENING", "purpose": "Вход", "macro_id": "M1",
                "content_ids": ["C001"],
            }],
        }

        with self.assertRaisesRegex(ValueError, "structured concrete change"):
            parse_story_plan_response(
                json.dumps(raw, ensure_ascii=False), (4000, 4000, 4000),
                require_state_transitions=True,
            )

    def test_exact_runtime_skeleton_is_embedded_in_planner_and_repair_prompts(self):
        request = ScenarioRequest(0, "Тема", "Контекст", target_chars=12000)
        targets = calculate_story_part_targets(12000)
        expected = "EXACT_PART_COUNT=3; P1=OPENING; P2=MIDDLE; P3=FINAL"

        planner = build_story_planner_prompt(request, targets)
        repair = build_story_plan_structure_repair_prompt(request, "{}", targets)

        self.assertIn(expected, planner)
        self.assertIn(expected, repair)
        self.assertIn("Do not add or remove parts", planner)
        self.assertIn("Do not rename part IDs", planner)

    def test_structural_repair_uses_complete_id_projection_not_a_truncated_raw_map(self):
        atoms = [
            {
                "id": f"C{index:03d}",
                "summary": "RAW_PROVIDER_TEXT_MUST_NOT_BE_COPIED " * 40,
                "owner_part_id": "P1",
                "content_kind": "DRAMATIZED",
            }
            for index in range(1, 161)
        ]
        original = json.dumps({
            "thesis": "RAW_PROVIDER_TEXT_MUST_NOT_BE_COPIED " * 300,
            "macro_blocks": [{"id": "M1", "purpose": "RAW_PROVIDER_TEXT_MUST_NOT_BE_COPIED"}],
            "content_atoms": atoms,
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "raw", "macro_id": "M1",
                       "content_ids": [atom["id"] for atom in atoms]}],
        }, ensure_ascii=False)

        prompt = build_story_plan_structure_repair_prompt(
            ScenarioRequest(0, "Тема", "Контекст", target_chars=10000),
            original,
            (4999, 4999),
        )

        self.assertIn('"id":"C160"', prompt)
        self.assertIn('"macro_blocks":[{"id":"M1"}]', prompt)
        self.assertNotIn("RAW_PROVIDER_TEXT_MUST_NOT_BE_COPIED", prompt)

    def test_writer_receives_ordered_material_and_a_per_atom_volume_allocation(self):
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Система проходит через два разных изменения.",
            "macro_blocks": [{"id": "M1", "purpose": "Последовательность решений"}],
            "content_atoms": [
                {
                    "id": "C001", "summary": "Оператор меняет правило", "owner_part_id": "P1",
                    "content_kind": "SUPPORTED", "state_before": "Правило было старым.",
                    "changed_subject": "Правило", "development": "Оператор ввёл новое правило.",
                    "resulting_state": "Порядок обработки изменился.", "state_after": "Новое правило действует.",
                    "writer_material": ["объявление решения", "порядок применения", "первая реакция"],
                },
                {
                    "id": "C002", "summary": "Служба меняет процесс", "owner_part_id": "P1",
                    "content_kind": "DRAMATIZED", "state_before": "Служба работала по старому порядку.",
                    "changed_subject": "Процесс службы", "development": "Служба перестроила очередь.",
                    "resulting_state": "Заявки проходят по новому маршруту.", "state_after": "Новый маршрут действует.",
                    "writer_material": ["перестройка очереди", "проверка результата"],
                },
                {
                    "id": "C003", "summary": "Пользователи получают итог", "owner_part_id": "P1",
                    "content_kind": "DRAMATIZED", "state_before": "Результат перестройки неизвестен.",
                    "changed_subject": "Доступ пользователей", "development": "Служба публикует новый порядок.",
                    "resulting_state": "Пользователи видят новый маршрут.", "state_after": "Новый порядок доступен.",
                    "writer_material": ["публикация порядка", "доступный результат"],
                },
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Раскрыть цепочку изменений", "macro_id": "M1",
                "content_ids": ["C001", "C002", "C003"],
            }],
        }, ensure_ascii=False)
        plan = parse_story_plan_response(response, (3999,), require_state_transitions=True)

        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "Контекст", target_chars=3999),
            plan,
            [],
            0,
        )

        self.assertIn("MATERIAL ALLOCATION: this part has 3 owned atoms; reserve roughly 1333 characters", prompt)
        self.assertIn("FIRST-PASS PART VOLUME: write roughly 3879-4119 characters", prompt)
        self.assertIn("NewsFlow independently records the actual length after this response", prompt)
        self.assertNotIn("without a length retry, trim or rewrite", prompt)
        self.assertIn("C001 [SUPPORTED]:\n  1. объявление решения\n  2. порядок применения\n  3. первая реакция", prompt)
        self.assertIn("C002 [DRAMATIZED]:\n  1. перестройка очереди\n  2. проверка результата", prompt)
        self.assertEqual(
            plan.to_dict()["content_atoms"][0]["writer_material"],
            ("объявление решения", "порядок применения", "первая реакция"),
        )

    def test_writer_keeps_the_last_current_material_beat_with_its_result(self):
        """Current coverage is bounded per beat, rather than cutting its final action."""
        beats = [
            f"Шаг {index}: служба документирует отдельное действие и его проверяемую деталь. "
            + "Контекст этого шага описан достаточно подробно для самостоятельного абзаца. " * 2
            for index in range(1, 6)
        ]
        beats.append(
            "LAST_ACTION_MARKER: комиссия публикует итоговое решение после проверки. "
            "LAST_RESULT_MARKER: новый порядок вступает в силу и меняет следующий этап истории. "
            + "Детали результата остаются в материале текущего атома. " * 2
        )
        plan = StoryPlan(
            thesis="Одна полная цепочка действий.",
            macro_blocks=({"id": "M1", "purpose": "Цепочка решения"},),
            content_atoms=(StoryContentAtom(
                id="C001", summary="Комиссия завершает процедуру", owner_part_id="P1",
                content_kind="DRAMATIZED", novelty_question="Чем завершается процедура?",
                novelty_payload="Комиссия публикует решение и запускает новый порядок.",
                state_before="Проверка ещё продолжалась.", changed_subject="Порядок процедуры",
                development="Комиссия публикует итоговое решение.",
                resulting_state="Новый порядок вступает в силу.",
                state_after="Следующий этап идёт по новому порядку.", writer_material=tuple(beats),
            ),),
            parts=(StoryPartPlan(
                id="P1", role="COMPLETE", purpose="Раскрыть решение", macro_id="M1",
                content_ids=("C001",), target_chars=5000,
                novelty_question="Как меняется процедура?",
                novelty_payload="Итоговое решение меняет порядок работы.",
            ),),
        )

        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "Контекст", target_chars=5000), plan, [], 0,
        )

        self.assertIn("LAST_ACTION_MARKER", prompt)
        self.assertIn("LAST_RESULT_MARKER", prompt)

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

    def test_parser_keeps_obvious_near_copy_semantic_atoms_as_editorial_advice(self):
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

        plan = parse_story_plan_response(response, (5000, 5000))
        self.assertEqual([atom.id for atom in plan.content_atoms], ["C001", "C002"])

    def test_parser_rejects_analytic_atoms_without_declared_state_transitions(self):
        """Different interpretations cannot substitute for before/development/after."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Переговорная ситуация становится всё жёстче.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие истории"}],
            "content_atoms": [
                {"id": "C001", "summary": "Давление вокруг переговоров усиливается",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Почему выросло давление?",
                 "novelty_payload": "Политическая цена решения становится выше."},
                {"id": "C002", "summary": "Пространство для манёвра становится уже",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Как изменилась переговорная рамка?",
                 "novelty_payload": "Новая конфигурация ограничивает поле выбора."},
                {"id": "C003", "summary": "Москва получает новый сигнал",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Что означает этот сдвиг?",
                 "novelty_payload": "Баланс становится менее устойчивым."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Раскрыть изменение политической логики",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003"],
                "novelty_question": "Как меняется политическая ситуация?",
                "novelty_payload": "Зритель получает несколько новых трактовок одного сдвига.",
            }],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "structured concrete change"):
            parse_story_plan_response(response, (3000,))

    def test_concrete_development_requires_a_distinct_before_and_after_state(self):
        """An event mention alone cannot substitute for a state transition."""
        def atom(
            summary: str,
            before: str = "",
            after: str = "",
            *,
            changed_subject: str = "",
            development: str = "",
            resulting_state: str = "",
        ) -> StoryContentAtom:
            record = StoryContentAtom("C001", summary, "P1", "DRAMATIZED")
            object.__setattr__(record, "state_before", before)
            object.__setattr__(record, "state_after", after)
            object.__setattr__(record, "changed_subject", changed_subject)
            object.__setattr__(record, "development", development)
            object.__setattr__(record, "resulting_state", resulting_state)
            return record

        self.assertTrue(_has_concrete_story_development(atom(
            "Россия нанесла новый удар по Киеву",
            "В городе действовал обычный режим тревоги.",
            "Городские службы перевели критические объекты на резервное питание.",
            changed_subject="Работа критической инфраструктуры",
            development="службы перевели критические объекты на резервное питание",
            resulting_state="объекты работают на резервном режиме",
        )))
        self.assertTrue(_has_concrete_story_development(atom(
            "Стороны перенесли следующую встречу",
            "Следующий раунд переговоров был назначен.",
            "Следующая встреча перенесена.",
            changed_subject="Следующий раунд переговоров",
            development="стороны не согласовали условия",
            resulting_state="следующая встреча перенесена",
        )))
        self.assertTrue(_has_concrete_story_development(atom(
            "Совет директоров отменил расширение",
            "План расширения компании был активен.",
            "Расширение отменено.",
            changed_subject="План расширения компании",
            development="совет директоров пересмотрел решение после отчёта",
            resulting_state="расширение отменено",
        )))
        self.assertTrue(_has_concrete_story_development(atom(
            "Компания остановила публичный релиз",
            "Публичный релиз был запланирован.",
            "Релиз остановлен.",
            changed_subject="Публичный релиз",
            development="компания обнаружила критическую ошибку",
            resulting_state="релиз остановлен",
        )))
        self.assertTrue(_has_concrete_story_development(atom(
            "Муниципальный сервис изменил порядок обработки заявок",
            "Заявки обрабатывались в прежнем порядке.",
            "Заявки направляются через резервный маршрут.",
            changed_subject="Порядок обработки заявок",
            development="оператор перевёл заявки на резервный маршрут",
            resulting_state="заявки направляются через резервный маршрут",
        )))
        # A changed system state may be named with an abstract noun when the
        # declared development itself is an observable action and the result
        # is concrete.  Rejecting this solely because it contains
        # "ситуация" would turn a lexical blacklist into a false semantic
        # gate and reject otherwise valid maps from any news domain.
        self.assertTrue(_has_concrete_story_development(atom(
            "Городские службы перевели критические объекты на резервное питание",
            "После атаки критические объекты работали по обычной схеме.",
            "Критические объекты работают на резервном питании.",
            changed_subject="Оперативная ситуация в городе",
            development="городские службы перевели критические объекты на резервное питание",
            resulting_state="критические объекты перешли на резервное питание",
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Удар меняет политическую цену конфликта"
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Атака показывает, что мир отдаляется"
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Москва получает новый сигнал о смене логики"
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Компания опубликовала отчёт",
            "Компания готовила отчёт.",
            "Компания готовила отчёт.",
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Удар становится политическим сигналом",
            "Удар воспринимался как военный эпизод.",
            "Удар воспринимается как политический сигнал.",
            changed_subject="Политический смысл удара",
            development="удар стал более важным сигналом",
            resulting_state="политическая цена выросла",
        )))
        self.assertFalse(_has_concrete_story_development(atom(
            "Давление усилилось",
            "Переговоры продолжались.",
            "Пространство для манёвра сузилось.",
            changed_subject="Переговорная ситуация",
            development="давление усилилось",
            resulting_state="пространство для манёвра сузилось",
        )))
        # A fully populated transition is still not a development when it
        # merely relabels one already-known event as a harsher "phase".  This
        # is deliberately topic-neutral: the defect is an interpretive state
        # change, not the subject matter of the headline.
        self.assertFalse(_has_concrete_story_development(atom(
            "Известное событие воспринимается как более жёсткая фаза",
            "Событие уже произошло.",
            "Участники ожидают дальнейшего давления.",
            changed_subject="Интенсивность процесса",
            development="событие воспринимается как более жёсткая фаза",
            resulting_state="участники действуют с ожиданием затяжного давления",
        )))

    def test_parser_requires_structured_concrete_change_for_fresh_transition_maps(self):
        """Different BEFORE/AFTER sentences alone must not certify a development."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Один удар получает только новую трактовку.",
            "macro_blocks": [{"id": "M1", "purpose": "Ложное развитие"}],
            "content_atoms": [{
                "id": "C001", "summary": "Удар становится политическим сигналом",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "state_before": "Удар воспринимался как военный эпизод",
                "state_after": "Удар воспринимается как политический сигнал",
                "novelty_question": "Что изменилось?",
                "novelty_payload": "Политическая цена выросла.",
            }],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Показать изменение",
                "macro_id": "M1", "content_ids": ["C001"],
            }],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "structured concrete change"):
            parse_story_plan_response(response, (2000,), require_state_transitions=True)

    def test_parser_keeps_structurally_complete_transition_for_writer_material(self):
        """Lexical interpretation is guidance, not a schema rejection path."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Один известный факт не должен стать несколькими трактовками.",
            "macro_blocks": [{"id": "M1", "purpose": "Проверить переход"}],
            "content_atoms": [{
                "id": "C001",
                "summary": "Известное событие воспринимается как более жёсткая фаза",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "state_before": "Событие уже произошло.",
                "changed_subject": "Интенсивность процесса",
                "development": "Событие воспринимается как более жёсткая фаза.",
                "resulting_state": "Участники действуют с ожиданием затяжного давления.",
                "state_after": "Ожидания участников стали более тревожными.",
                "novelty_question": "Как воспринимается известное событие?",
                "novelty_payload": "Событие получает более тревожную трактовку.",
                "do_not_repeat": "",
            }],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Дать новое развитие",
                "macro_id": "M1", "content_ids": ["C001"],
                "novelty_question": "Какое действие произошло?",
                "novelty_payload": "Новое действие меняет состояние истории.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (2000,), require_state_transitions=True)
        self.assertEqual(plan.content_atoms[0].id, "C001")

    def test_parser_does_not_aggregate_lexical_advice_into_a_story_map_veto(self):
        """Several complete transitions remain valid when lexical advice is negative."""
        atoms = []
        for index in range(1, 4):
            atoms.append({
                "id": f"C00{index}",
                "summary": f"Режим сервиса получает трактовку этапа {index}",
                "owner_part_id": "P1",
                "content_kind": "DRAMATIZED",
                "state_before": f"Режим сервиса воспринимался как этап {index - 1}.",
                "changed_subject": "Режим сервиса",
                "development": f"Участники воспринимают режим как символ этапа {index}.",
                "resulting_state": f"Обсуждение трактует режим как новый сигнал этапа {index}.",
                "state_after": f"Режим сервиса воспринимается как этап {index}.",
                "novelty_question": f"Как изменилась трактовка этапа {index}?",
                "novelty_payload": f"Режим сервиса получил отдельную трактовку этапа {index}.",
                "do_not_repeat": f"Не повторять трактовку этапа {index - 1}.",
            })
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Проверка структурного договора без лексического veto.",
            "macro_blocks": [{"id": "M1", "purpose": "Последовательность изменений"}],
            "content_atoms": atoms,
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Собрать переходы",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003"],
                "novelty_question": "Как развивалась история?",
                "novelty_payload": "Каждый атом сохранил свой формальный переход.",
            }],
        }, ensure_ascii=False)

        self.assertTrue(all(
            not _has_concrete_story_development(StoryContentAtom(
                id=atom["id"], summary=atom["summary"], owner_part_id=atom["owner_part_id"],
                content_kind=atom["content_kind"], novelty_question=atom["novelty_question"],
                novelty_payload=atom["novelty_payload"], do_not_repeat=atom["do_not_repeat"],
                state_before=atom["state_before"], changed_subject=atom["changed_subject"],
                development=atom["development"], resulting_state=atom["resulting_state"],
                state_after=atom["state_after"],
            ))
            for atom in atoms
        ))
        plan = parse_story_plan_response(response, (2000,), require_state_transitions=True)
        self.assertEqual([atom.id for atom in plan.content_atoms], ["C001", "C002", "C003"])

    def test_parser_rejects_analytic_atoms_that_only_mention_event_nouns(self):
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Один удар получает несколько аналитических трактовок.",
            "macro_blocks": [{"id": "M1", "purpose": "Ложное развитие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Новая атака показывает, что мир отдаляется",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Что означает атака?",
                 "novelty_payload": "Удар делает переговорную рамку жёстче."},
                {"id": "C002", "summary": "Усиление ударов меняет политическую цену конфликта",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Что меняют удары?",
                 "novelty_payload": "Атака становится новым сигналом для сторон."},
                {"id": "C003", "summary": "Москва получает новый сигнал о смене логики",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Что значит этот сигнал?",
                 "novelty_payload": "Баланс после удара становится менее устойчивым."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Пересказать одну трактовку",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003"],
                "novelty_question": "Как меняется контекст?",
                "novelty_payload": "Зритель получает три формулировки одного вывода.",
            }],
        }, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "structured concrete change"):
            parse_story_plan_response(response, (3000,))

    def test_parser_accepts_dramatized_concrete_event_chain(self):
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "После новой атаки стороны проходят через последовательную цепочку решений.",
            "macro_blocks": [{"id": "M1", "purpose": "Событие, ответ и последствие"}],
            "content_atoms": [
                {"id": "C001", "summary": "Россия наносит новый удар по инфраструктуре Киева",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Что запускает историю?",
                 "novelty_payload": "Ночной удар нарушает работу нескольких районов Киева."},
                {"id": "C002", "summary": "Городские службы переводят критические объекты на резервный режим",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "Как отвечает Киев?",
                 "novelty_payload": "После атаки службы меняют режим работы инфраструктуры."},
                {"id": "C003", "summary": "Украина направляет партнёрам срочный запрос на дополнительную защиту",
                 "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                 "novelty_question": "К чему приводит ответ?",
                 "novelty_payload": "Новый запрос переводит последствия атаки в дипломатический канал."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Провести историю от удара к новому решению",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003"],
                "novelty_question": "Как один эпизод меняет следующий ход?",
                "novelty_payload": "Зритель видит конкретную цепочку событие, ответ и новое последствие.",
            }],
        }, ensure_ascii=False)

        payload = json.loads(response)
        for index, atom in enumerate(payload["content_atoms"], start=1):
            atom["state_before"] = f"Состояние до шага {index}."
            atom["state_after"] = f"Новое состояние после шага {index}."
            atom["changed_subject"] = f"Рабочий объект {index}"
            atom["development"] = f"исполнитель выполнил действие {index}"
            atom["resulting_state"] = f"рабочий объект {index} получил новый статус"
        plan = parse_story_plan_response(
            json.dumps(payload, ensure_ascii=False),
            (3000,),
        )

        self.assertEqual([atom.id for atom in plan.content_atoms], ["C001", "C002", "C003"])

    def test_parser_accepts_concrete_action_for_a_named_system_state(self):
        """A system-state label cannot override its concrete event evidence."""
        response = json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Оперативная ситуация меняется после конкретного действия служб.",
            "macro_blocks": [{"id": "M1", "purpose": "Показать действие и его результат"}],
            "content_atoms": [{
                "id": "C001",
                "summary": "Городские службы переводят критические объекты на резервное питание",
                "owner_part_id": "P1",
                "content_kind": "DRAMATIZED",
                "state_before": "После атаки критические объекты работали по обычной схеме.",
                "changed_subject": "Оперативная ситуация в городе",
                "development": "городские службы перевели критические объекты на резервное питание",
                "resulting_state": "критические объекты перешли на резервное питание",
                "state_after": "Критические объекты работают на резервном питании.",
                "novelty_question": "Как службы изменили работу объектов?",
                "novelty_payload": "Службы перевели критические объекты на резервное питание.",
                "do_not_repeat": "",
            }],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Показать конкретное действие служб",
                "macro_id": "M1", "content_ids": ["C001"],
                "novelty_question": "Как изменилась работа критических объектов?",
                "novelty_payload": "Объекты переходят на резервное питание.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (2000,), require_state_transitions=True)

        self.assertEqual(plan.content_atoms[0].changed_subject, "Оперативная ситуация в городе")

    def test_parser_keeps_near_copy_part_novelty_as_editorial_advice(self):
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

        plan = parse_story_plan_response(response, (5000, 5000))
        self.assertEqual([part.id for part in plan.parts], ["P1", "P2"])


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

        plan = parse_story_plan_response(response, (2000, 2000))
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
        self.assertIn("CURRENT EVENT SEQUENCE (the only content to develop):", prompt)
        self.assertIn("TECHNICAL OWNERSHIP INDEX (navigation only; not prose material):", prompt)
        self.assertIn("C001 [SUPPORTED]", prompt)
        self.assertIn("C005 [DRAMATIZED]", prompt)
        self.assertNotIn("CURRENT NOVELTY QUESTION:", prompt)
        self.assertNotIn("CURRENT NEW INFORMATION:", prompt)
        self.assertIn("Once an event's result has been explained", prompt)
        self.assertIn("single COMPLETE 6-9k story", prompt)
        self.assertIn("last owned atom must be written as a genuinely new terminal development", prompt)

    def test_fresh_five_thousand_part_keeps_atom_count_as_advisory(self):
        """A small map is a planning-quality signal, not a schema rejection."""
        response = json.dumps({
            "thesis": "Плотная история.",
            "macro_blocks": [{"id": "M1", "purpose": "Полная история"}],
            "content_atoms": [
                {"id": "C001", "summary": "Исходное изменение на рынке", "owner_part_id": "P1",
                 "content_kind": "SUPPORTED", "novelty_question": "Что изменилось?",
                 "novelty_payload": "Цена закрепилась выше ожидаемого уровня.", "do_not_repeat": ""},
                {"id": "C002", "summary": "Покупатели меняют поведение", "owner_part_id": "P1",
                 "content_kind": "DRAMATIZED", "novelty_question": "Как реагируют покупатели?",
                 "novelty_payload": "Люди сокращают покупки и ищут замену.", "do_not_repeat": "Цена уже выросла."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Раскрыть всю историю",
                "macro_id": "M1", "content_ids": ["C001", "C002"],
                "novelty_question": "Как развивается ситуация?",
                "novelty_payload": "История движется от изменения цены к реакции людей.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,))
        self.assertEqual(plan.parts[0].content_ids, ("C001", "C002"))

    def test_fresh_six_to_nine_thousand_complete_keeps_atom_count_as_advisory(self):
        """Coverage guidance must not create a paid Planner recovery loop."""
        atoms = [
            {
                "id": "C001", "summary": "На рынке сохраняется высокий ценник",
                "owner_part_id": "P1", "content_kind": "SUPPORTED",
                "novelty_question": "Что изменилось в цене?",
                "novelty_payload": "Стоимость товара не снизилась после ожидаемого сезонного периода.",
                "do_not_repeat": "",
            },
            {
                "id": "C002", "summary": "Логистические расходы меняют закупочную схему",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "novelty_question": "Какой механизм удерживает стоимость?",
                "novelty_payload": "Поставщики сокращают дешёвые партии из-за новых затрат.",
                "do_not_repeat": "Не доказывать заново сам факт высокой цены.",
            },
            {
                "id": "C003", "summary": "Покупатели меняют корзину и частоту покупок",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "novelty_question": "Как люди адаптируют повседневные расходы?",
                "novelty_payload": "Семьи сокращают объём покупок и переходят на заменители.",
                "do_not_repeat": "Не повторять механизм поставок.",
            },
            {
                "id": "C004", "summary": "Продавцы реагируют на изменение спроса",
                "owner_part_id": "P1", "content_kind": "DRAMATIZED",
                "novelty_question": "Как рынок отвечает на новое поведение покупателей?",
                "novelty_payload": "Торговцы меняют ассортимент и объём закупок вслед за спросом.",
                "do_not_repeat": "Не возвращаться к семейным расходам как к главному выводу.",
            },
        ]
        response = json.dumps({
            "thesis": "Одна длинная COMPLETE-история.",
            "macro_blocks": [{"id": "M1", "purpose": "Последовательное развитие"}],
            "content_atoms": atoms,
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Пройти четыре шага",
                "macro_id": "M1", "content_ids": [atom["id"] for atom in atoms],
                "novelty_question": "Как меняется ситуация по ходу истории?",
                "novelty_payload": "Четыре разных шага пока недостаточны для 7k.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (7000,))
        self.assertEqual(len(plan.parts[0].content_ids), 4)

    def test_do_not_repeat_is_persisted_and_exposed_only_for_current_atoms(self):
        response = json.dumps({
            "thesis": "Каждый смысл раскрывается один раз.",
            "macro_blocks": [{"id": "M1", "purpose": "Полная история"}],
            "content_atoms": [
                {"id": "C001", "summary": "Причина изменения цены", "owner_part_id": "P1",
                 "content_kind": "SUPPORTED", "novelty_question": "Почему цена не снизилась?",
                 "novelty_payload": "Поставка стала дороже и изменила себестоимость.", "do_not_repeat": ""},
                {"id": "C002", "summary": "Реакция покупателей", "owner_part_id": "P1",
                 "content_kind": "DRAMATIZED", "novelty_question": "Как меняется поведение людей?",
                 "novelty_payload": "Покупатели сокращают объём и выбирают заменители.",
                 "do_not_repeat": "Не объяснять заново, почему цена не снизилась."},
                {"id": "C003", "summary": "Ответ продавцов", "owner_part_id": "P1",
                 "content_kind": "DRAMATIZED", "novelty_question": "Что делают продавцы?",
                 "novelty_payload": "Продавцы меняют закупки и ассортимент.",
                 "do_not_repeat": "Не повторять реакцию покупателей."},
            ],
            "parts": [{
                "id": "P1", "role": "COMPLETE", "purpose": "Раскрыть три разных шага",
                "macro_id": "M1", "content_ids": ["C001", "C002", "C003"],
                "novelty_question": "Как цена меняет рынок?",
                "novelty_payload": "Причина, реакция людей и ответ продавцов раскрываются отдельно.",
            }],
        }, ensure_ascii=False)

        plan = parse_story_plan_response(response, (5000,))
        persisted = plan.to_dict()
        self.assertEqual(
            persisted["content_atoms"][1]["do_not_repeat"],
            "Не объяснять заново, почему цена не снизилась.",
        )
        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Цены", "CONTRACT"), plan, [], 0, 5000,
        )
        self.assertIn("DO_NOT_REPEAT=Не объяснять заново, почему цена не снизилась.", prompt)
        self.assertIn("do not create a fresh paragraph", prompt)

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
    def test_stage_split_never_promotes_manual_or_story_headings_to_instructions(self):
        """Headers are valid data; their presence must not change API priority."""
        manual = (
            'MANUAL_MARKER_MUST_REMAIN_USER_DATA\n\nSTORY THESIS: quoted heading\n'
            '\nPOSITION RULE: quoted heading\n{"literal":"{brace}"}'
        )
        request = ScenarioRequest(0, "TOPIC: quoted heading", manual, target_chars=5000)
        plan = StoryPlan(
            thesis="STORY THESIS: model-owned quoted heading",
            macro_blocks=({"id": "M1", "purpose": "POSITION RULE: quoted"},),
            content_atoms=(StoryContentAtom(
                id="C001", summary="CURRENT CONTENT: model heading", owner_part_id="P1",
                content_kind="DRAMATIZED", state_before="До.", changed_subject="Служба",
                development="Служба действует.", resulting_state="Есть результат.", state_after="После.",
                writer_material=("первая строка\nPOSITION RULE: внутри материала", "последний результат"),
            ),),
            parts=(StoryPartPlan(
                id="P1", role="COMPLETE", purpose="Завершение", macro_id="M1",
                content_ids=("C001",), target_chars=5000,
            ),),
        )

        planner_instructions, planner_input = split_story_planner_request(request, (5000,))
        writer_instructions, writer_input = split_story_writer_request(request, plan, [], 0)

        for marker in ("MANUAL_MARKER_MUST_REMAIN_USER_DATA", "STORY THESIS: quoted heading", "{brace}"):
            self.assertNotIn(marker, planner_instructions)
            self.assertIn(marker, planner_input)
        for marker in ("MANUAL_MARKER_MUST_REMAIN_USER_DATA", "model-owned quoted heading", "POSITION RULE: внутри материала"):
            self.assertNotIn(marker, writer_instructions)
            self.assertIn(marker, writer_input)

    def test_stage_requests_keep_manual_contract_in_user_input(self):
        request = ScenarioRequest(
            0,
            "Тема",
            "MANUAL_TEMPLATE_ONLY: сохраняй этот ручной контракт.",
            target_chars=12000,
            allowed_min=11500,
            allowed_max=12500,
        )
        planner_instructions, planner_input = split_story_planner_request(
            request, (3999, 3999, 3998),
        )
        self.assertIn("NewsFlow Story Planner", planner_instructions)
        self.assertIn("RUNTIME TECHNICAL SKELETON", planner_instructions)
        self.assertNotIn("MANUAL_TEMPLATE_ONLY", planner_instructions)
        self.assertIn("MANUAL_TEMPLATE_ONLY", planner_input)

        plan = StoryPlan(
            thesis="Последовательность событий.",
            macro_blocks=({"id": "M1", "purpose": "Развитие"},),
            content_atoms=(StoryContentAtom(
                id="C001", summary="Служба меняет статус", owner_part_id="P1",
                content_kind="DRAMATIZED", state_before="Статус прежний.",
                changed_subject="Статус службы", development="Служба меняет статус.",
                resulting_state="Новый статус опубликован.", state_after="Статус обновлён.",
            ),),
            parts=(StoryPartPlan(
                id="P1", role="COMPLETE", purpose="Завершить развитие", macro_id="M1",
                content_ids=("C001",), target_chars=5000,
            ),),
        )
        writer_instructions, writer_input = split_story_writer_request(request, plan, [], 0)
        self.assertIn("MULTIPART PRECEDENCE", writer_instructions)
        self.assertIn("WRITER EXECUTION BOUNDARY", writer_instructions)
        self.assertNotIn("MANUAL_TEMPLATE_ONLY", writer_instructions)
        self.assertIn("MANUAL_TEMPLATE_ONLY", writer_input)
        self.assertIn("CURRENT EVENT SEQUENCE", writer_input)
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
        self.assertIn("4-5 genuinely different atoms", prompt)
        self.assertIn("5-7", prompt)
        self.assertIn("novelty_question, novelty_payload and do_not_repeat", prompt)
        self.assertIn("semantic-density requirements", prompt)
        self.assertIn("coverage guidance: normally 3 or more distinct atoms", prompt)
        self.assertIn("terminal development", prompt)
        self.assertIn("For EVERY atom in this NEW map, include event_steps", prompt)
        self.assertIn("ordered JSON list of 4 to 6 distinct concrete coverage beats", prompt)
        self.assertIn("detailed enough to develop into a paragraph", prompt)
        self.assertIn("rather than a label such as 'background', 'mechanism', 'result' or 'transition'", prompt)
        self.assertIn("not a parser gate", prompt)
        self.assertIn("coverage beats must be a causal chain, not four ways to state one conclusion", prompt)
        self.assertIn("For a roughly 4-5k part, allocate enough distinct chronological material", prompt)
        self.assertIn("Before returning JSON, check that every atom", prompt)
        self.assertIn("different declared states", prompt)
        self.assertIn("synonym swap", prompt)

    def test_planner_distinguishes_title_only_from_supported_and_dramatized_material(self):
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема без источников", "КОНТЕКСТ: отсутствует"),
            (3999, 3999, 3998),
        )

        self.assertIn("TITLE/TOPIC names the subject, not verified evidence", prompt)
        self.assertIn("title alone is not SUPPORTED", prompt)
        self.assertIn("declarative chronological content", prompt)
        self.assertIn("not a writing command such as 'show', 'describe', 'frame', 'keep', 'use' or 'avoid'", prompt)
        self.assertIn("Example only, never reuse it as story content", prompt)
        self.assertIn("FINAL's last event_steps entry", prompt)
        self.assertIn("Do not fabricate source attribution such as reports from the scene", prompt)

    def test_writer_keeps_a_current_beat_result_after_the_old_220_character_boundary(self):
        long_tail = (
            "Промежуточная деталь описывает ход проверки и передачу результата между службами. " * 4
            + "FINAL_RESULT_AFTER_220: оператор публикует подтверждённый итоговый статус."
        )
        plan = StoryPlan(
            thesis="Одна цепочка.",
            macro_blocks=({"id": "M1", "purpose": "Проверка"},),
            content_atoms=(StoryContentAtom(
                id="C001", summary="Проверка завершается", owner_part_id="P1",
                content_kind="DRAMATIZED", novelty_question="Чем завершилась проверка?",
                novelty_payload="Опубликован итоговый статус.", state_before="Проверка идёт.",
                changed_subject="Статус проверки", development="Оператор завершает проверку.",
                resulting_state="Статус опубликован.", state_after="Проверка закрыта.",
                writer_material=(long_tail,),
            ),),
            parts=(StoryPartPlan(
                id="P1", role="COMPLETE", purpose="Завершить проверку", macro_id="M1",
                content_ids=("C001",), target_chars=5000,
                novelty_question="Какой итог получен?", novelty_payload="Статус опубликован.",
            ),),
        )

        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "Контекст", target_chars=5000), plan, [], 0,
        )

        self.assertGreater(long_tail.index("FINAL_RESULT_AFTER_220"), 220)
        self.assertIn("FINAL_RESULT_AFTER_220", prompt)

    def test_twelve_thousand_plan_requires_event_density_before_writer(self):
        targets = calculate_story_part_targets(12000)
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема", "Контекст", target_chars=12000),
            targets,
        )

        self.assertEqual(targets, (3999, 3999, 3998))
        self.assertIn("P1≈3999 chars; coverage guidance: normally 3 or more distinct atoms", prompt)
        self.assertIn("P2≈3999 chars; coverage guidance: normally 3 or more distinct atoms", prompt)
        self.assertIn("P3≈3998 chars; coverage guidance: normally 3 or more distinct atoms", prompt)
        self.assertIn("not an essay outline, opinion column, literary narrative", prompt)

    def test_planner_builds_an_event_spine_before_allocating_parts(self):
        """New maps begin with content progression, not authorial presentation tasks."""
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема", "Ручной шаблон остаётся справочным."),
            (3999, 3999, 3998),
        )

        self.assertIn("FIRST construct a causal-temporal EVENT SPINE", prompt)
        self.assertIn("Return that sequence first as event_spine", prompt)
        self.assertIn("each event-spine item exactly once to P1...PN", prompt)
        self.assertIn("not a list of angles, questions, themes, moods, stakes or explanations", prompt)
        self.assertIn("Choose the FINAL terminal result before allocating FINAL", prompt)
        self.assertIn(
            "'expand context', 'show significance' or 'leave a question' are presentation tasks, not event steps",
            prompt,
        )
        self.assertIn("optional final question may follow that result but cannot replace it", prompt)

    def test_dramatized_event_spine_precedes_conflicting_manual_no_invention_rule(self):
        """The trusted mode must prepare events, not invite analytical evasions."""
        manual_contract = "Не придумывай события и объясняй значение происходящего."
        prompt = build_story_planner_prompt(
            ScenarioRequest(
                0, "Тема без supplied context", manual_contract,
                dramatized_allowed=True,
            ),
            (3999, 3999, 3998),
        )

        self.assertIn(manual_contract, prompt)
        self.assertIn(
            "takes precedence over a generic manual instruction not to invent",
            prompt,
        )
        self.assertIn(
            "a concrete action, response, decision, process step or recorded result",
            prompt,
        )
        self.assertIn(
            "Do not use an interpretation of the initial headline as an event-spine item",
            prompt,
        )

    def test_planner_prompt_contains_only_story_planning_contract(self):
        prompt = build_story_planner_prompt(ScenarioRequest(0, "Тема", "Контекст"), (5000,))

        self.assertNotIn("COVER FACE RESOLUTION", prompt)
        self.assertNotIn("cover_people_candidates", prompt)
        self.assertNotIn("cover_primary_person", prompt)

    def test_planner_execution_boundary_follows_conflicting_writer_template(self):
        manual_contract = (
            "Верни ТОЛЬКО готовый цельный сценарий. Не придумывай события. "
            "Это ручное требование должно сохраниться как reference."
        )
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема без источника", manual_contract), (3999, 3999, 3998),
        )

        self.assertIn(manual_contract, prompt)
        self.assertIn("PLANNER EXECUTION BOUNDARY", prompt)
        self.assertGreater(
            prompt.index("PLANNER EXECUTION BOUNDARY"), prompt.index(manual_contract),
        )
        self.assertIn("Return ONLY the strict JSON Story Map", prompt)
        self.assertIn("do not return finished scenario prose", prompt)

    def test_headline_only_marker_requires_dramatized_atoms_in_final_planner_boundary(self):
        prompt = build_story_planner_prompt(
            ScenarioRequest(0, "Тема", "FACTUAL_CONTEXT_AVAILABILITY: NONE"), (5000,),
        )

        self.assertIn("EVERY atom must be DRAMATIZED", prompt)

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
        }, ensure_ascii=False), (5000, 5000, 5000), validate_semantic_novelty=False)

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
        self.assertIn("CURRENT EVENT SEQUENCE (the only content to develop):", prompt)
        self.assertIn("TECHNICAL OWNERSHIP INDEX (navigation only; not prose material):", prompt)
        self.assertNotIn("CURRENT NOVELTY QUESTION:", prompt)
        self.assertNotIn("CURRENT NEW INFORMATION:", prompt)
        self.assertIn("USED CONTENT (do not repeat): C001 [SUPPORTED]: Начальное событие уже раскрыто", prompt)
        self.assertIn("USED SEMANTIC MEANINGS (forbidden to restate): P1:", prompt)
        self.assertIn("PARAPHRASE DOES NOT COUNT AS NEW INFORMATION", prompt)
        self.assertIn("A paragraph that adds no new story information should not be written", prompt)
        self.assertIn("P3/M2: Завершить историю", prompt)
        self.assertIn("C002 [DRAMATIZED] (legacy state path):", prompt)
        self.assertIn("Новый механизм для текущей части", prompt)
        self.assertIn("C003 [DRAMATIZED]: Будущее последствие, которое ещё нельзя раскрывать", prompt)
        self.assertIn("OPEN LOOPS BEFORE THIS PART: L1", prompt)
        self.assertIn("MACRO MAP: M1: Событие и развитие", prompt)
        self.assertNotIn(first_part, prompt)
        self.assertIn(seam_tail(first_part), prompt)
        self.assertLessEqual(len(seam_tail(first_part)), 500)
        self.assertIn("NO GLOBAL FINAL", prompt)
        self.assertIn("first 30 seconds", prompt)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", prompt)
        self.assertIn("EVENT-FIRST STYLE CONTRACT", prompt)
        self.assertIn("This is not an essay, analysis, op-ed, literary story", prompt)
        self.assertIn("Every substantive paragraph must contain a concrete actor/action/decision/reaction/result/state change", prompt)
        self.assertIn("two substantive event-driven paragraphs per CURRENT atom", prompt)

    def test_writer_receives_one_ordered_event_sequence_without_competing_current_map(self):
        """Only canonical steps are Writer prose material; metadata stays technical."""
        persisted = self._plan().to_dict()
        persisted["content_atoms"][1].update({
            "summary": "ANALYTIC_SUMMARY_MUST_NOT_BECOME_CURRENT_PROSE",
            "state_before": "Заявка ждёт решения.",
            "changed_subject": "Комиссия",
            "development": "Комиссия утверждает новый порядок.",
            "resulting_state": "Заявка получает утверждённый маршрут.",
            "state_after": "Исполнители получают новый порядок.",
            "writer_material": [
                "Комиссия получает заявку с прежним порядком.",
                "Комиссия утверждает новый порядок обработки.",
                "STEP_THREE: исполнители получают утверждённый маршрут.",
            ],
        })
        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=15000),
            story_plan_from_dict(persisted),
            [{"part_id": "P1", "text": "Первый фрагмент.", "content_ids": ["C001"]}],
            1,
        )

        self.assertIn("CURRENT EVENT SEQUENCE (the only content to develop):", prompt)
        self.assertIn(
            "C002 [DRAMATIZED]:\n"
            "  1. Комиссия получает заявку с прежним порядком.\n"
            "  2. Комиссия утверждает новый порядок обработки.\n"
            "  3. STEP_THREE: исполнители получают утверждённый маршрут.",
            prompt,
        )
        self.assertEqual(prompt.count("STEP_THREE: исполнители получают утверждённый маршрут."), 1)
        self.assertEqual(prompt.count("Комиссия получает заявку с прежним порядком."), 1)
        self.assertEqual(prompt.count("Комиссия утверждает новый порядок обработки."), 1)
        self.assertNotIn("ANALYTIC_SUMMARY_MUST_NOT_BECOME_CURRENT_PROSE", prompt)
        self.assertNotIn("CURRENT PURPOSE:", prompt)
        self.assertNotIn("CURRENT NOVELTY QUESTION:", prompt)
        self.assertNotIn("CURRENT NEW INFORMATION:", prompt)
        self.assertIn("TECHNICAL OWNERSHIP INDEX (navigation only; not prose material):", prompt)
        self.assertLess(
            prompt.index("CURRENT EVENT SEQUENCE (the only content to develop):"),
            prompt.index("TECHNICAL OWNERSHIP INDEX (navigation only; not prose material):"),
        )

    def test_new_canonical_event_steps_reach_writer_in_order_and_keep_terminal_result(self):
        """Fresh plans have one event source; legacy writer_material remains a fallback."""
        plan = StoryPlan(
            thesis="Последовательность меняет исходную ситуацию и приходит к результату.",
            macro_blocks=({"id": "M1", "purpose": "Полная последовательность"},),
            content_atoms=(StoryContentAtom(
                id="C001", summary="Процесс завершается", owner_part_id="P1",
                content_kind="DRAMATIZED", state_before="Процесс не завершён.",
                changed_subject="Комиссия", development="Комиссия принимает решение.",
                resulting_state="Решение опубликовано.", state_after="Процесс завершён.",
                event_steps=(
                    "Комиссия получает материалы после незавершённой проверки.",
                    "Комиссия принимает решение по материалам.",
                    "Исполнители выполняют утверждённое решение.",
                    "EVENT_TERMINAL_RESULT: решение опубликовано и процесс завершён.",
                ),
                writer_material=("LEGACY_MATERIAL_MUST_NOT_WIN",),
            ),),
            parts=(StoryPartPlan(
                id="P1", role="COMPLETE", purpose="Довести процесс до результата", macro_id="M1",
                content_ids=("C001",), target_chars=5000,
            ),),
        )

        prompt = build_story_writer_prompt(ScenarioRequest(0, "Тема", "CONTRACT"), plan, [], 0)
        restored = story_plan_from_dict(plan.to_dict())

        self.assertIn("CURRENT EVENT SEQUENCE (the only content to develop):", prompt)
        self.assertIn("EVENT_TERMINAL_RESULT", prompt)
        self.assertNotIn("LEGACY_MATERIAL_MUST_NOT_WIN", prompt)
        self.assertLess(prompt.index("Комиссия получает материалы"), prompt.index("EVENT_TERMINAL_RESULT"))
        self.assertEqual(restored.content_atoms[0].event_steps, plan.content_atoms[0].event_steps)

    def test_writer_execution_boundary_follows_conflicting_whole_story_length(self):
        prompt = build_story_writer_prompt(
            ScenarioRequest(0, "Тема", "НЕОБХОДИМОЕ КОЛИЧЕСТВО СИМВОЛОВ: 10 000", target_chars=12000),
            self._plan(), [], 0, 3999,
        )

        self.assertIn("WRITER EXECUTION BOUNDARY", prompt)
        self.assertGreater(
            prompt.index("WRITER EXECUTION BOUNDARY"),
            prompt.index("НЕОБХОДИМОЕ КОЛИЧЕСТВО СИМВОЛОВ: 10 000"),
        )
        self.assertIn("approximately 3999 characters", prompt)

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
        self.assertIn("Start with one or two strong event/hook sentences", opening)
        self.assertIn("never as the first sentence", opening)
        self.assertIn("After that hook, write the one short natural disclosure", opening)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", middle)
        self.assertNotIn("DRAMATIZED OPENING DISCLOSURE", final)

    def test_all_supported_atoms_do_not_request_a_dramatized_disclosure(self):
        supported = self._plan().to_dict()
        for atom in supported["content_atoms"]:
            atom["content_kind"] = "SUPPORTED"
        plan = story_plan_from_dict(supported)

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
        self.assertIn("Start with one or two strong event/hook sentences", prompt)
        self.assertIn("never as the first sentence", prompt)


if __name__ == "__main__":
    unittest.main()
