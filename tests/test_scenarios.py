import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings, load_settings, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import load_session, save_session, session_path
from scriptor.story_planner import (
    calculate_story_part_targets,
    parse_story_plan_response,
)


def _story_plan(part_count: int = 2) -> str:
    roles = ["COMPLETE"] if part_count == 1 else ["OPENING", *(["MIDDLE"] * (part_count - 2)), "FINAL"]
    return json.dumps({
        "thesis": "Одна история",
        "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
        "content_atoms": [
            {"id": f"C{index:03d}", "summary": f"Факт {index}", "owner_part_id": f"P{index}",
             "content_kind": "SUPPORTED"}
            for index in range(1, part_count + 1)
        ],
        "parts": [
            {"id": f"P{index}", "role": roles[index - 1], "purpose": f"Блок {index}",
             "macro_id": "M1", "content_ids": [f"C{index:03d}"], "opens": [], "closes": [],
             "transition_direction": f"к блоку {index + 1}" if index < part_count else "финал"}
            for index in range(1, part_count + 1)
        ],
    }, ensure_ascii=False)


class ScenarioGenerationTests(unittest.TestCase):
    def test_explicit_reconcile_recovers_only_interrupted_scenarios_without_losing_recovery_data(self):
        """Explicit recovery makes an interrupted row retryable without changing its saved work."""
        title = "Прерванный сценарий"
        request = ScenarioRequest(
            0,
            title,
            "Сохранённый запрос",
            "production-item-42",
            1200,
            1000,
            1400,
        )
        interrupted = Job(
            request,
            RunState.RUNNING,
            "Частично готовый текст",
            "Предыдущий контекст ошибки",
            actual_chars=321,
            length_status="REPAIRING",
            length_repair_attempts=2,
        )
        jobs = [
            interrupted,
            Job(ScenarioRequest(1, "Готовый", ""), RunState.DONE, "Готовый текст"),
            Job(ScenarioRequest(2, "Ожидающий", ""), RunState.WAITING),
            Job(ScenarioRequest(3, "С ошибкой", ""), RunState.ERROR, error="Исходная ошибка"),
        ]
        settings = Settings()

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=([title, "Готовый", "Ожидающий", "С ошибкой"], jobs)), \
             patch.object(bridge, "save_session") as save_session_mock, \
             patch.object(bridge, "save_settings") as save_settings_mock, \
             patch.object(bridge, "HybridTextPool", side_effect=AssertionError("provider must not start")):
            bridge.snapshot()
            self.assertFalse(save_session_mock.called)

            with patch.object(bridge, "snapshot", return_value={"recovered": True}):
                result = bridge.reconcile_runtime_state({})

        self.assertEqual(result, {"recovered": True})
        save_session_mock.assert_called_once_with([title, "Готовый", "Ожидающий", "С ошибкой"], jobs)
        save_settings_mock.assert_not_called()
        self.assertEqual([job.state for job in jobs], [RunState.ERROR, RunState.DONE, RunState.WAITING, RunState.ERROR])
        self.assertEqual(interrupted.request, request)
        self.assertEqual(interrupted.result, "Частично готовый текст")
        self.assertEqual(interrupted.actual_chars, 321)
        self.assertEqual(interrupted.length_status, "REPAIRING")
        self.assertEqual(interrupted.length_repair_attempts, 2)
        self.assertIn("Предыдущий контекст ошибки", interrupted.error)
        self.assertIn("прервана", interrupted.error)

    def test_save_template_persists_the_operator_template_and_returns_snapshot(self):
        template = "USER_PROMPT_MARKER :: Напиши сценарий именно по моей инструкции для {title}. Не заменяй этот текст."
        settings = Settings()
        expected_snapshot = {"templateSettings": {"template": template}}

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings") as save, \
             patch.object(bridge, "snapshot", return_value=expected_snapshot):
            result = bridge.save_template({"template": template})

        self.assertEqual(settings.template, template)
        save.assert_called_once_with(settings)
        self.assertIs(result, expected_snapshot)

    def test_openai_generation_preserves_saved_operator_prompt_and_persists_completed_script(self):
        template = "USER_PROMPT_MARKER :: Напиши сценарий именно по моей инструкции для {title}. Не заменяй этот текст."
        title = "Проверочная тема"
        settings = Settings(scenario_provider="openai", template=template, prompt_ranges=[])
        saved_batches = []

        class FakePool:
            concurrency = 1

            def __init__(self):
                self.prompts = []

            async def generate(self, prompt):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return _story_plan(1)
                return "Готовый сценарий по проверочной теме."

        pool = FakePool()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=([title], [])), \
             patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_batches.append(jobs)), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=pool):
            bridge.generate_scenarios({"provider": "openai", "indices": [0]})

        prompt = pool.prompts[0]
        self.assertIn("USER_PROMPT_MARKER", prompt)
        self.assertIn("Напиши сценарий именно по моей инструкции", prompt)
        self.assertIn(title, prompt)
        self.assertNotIn("{title}", prompt)
        self.assertNotIn("Ты редактор новостных сценариев NewsFlow", prompt)
        self.assertIn("ФОРМАТ ОТВЕТА ОБЯЗАТЕЛЕН", prompt)
        self.assertLess(prompt.index("USER_PROMPT_MARKER"), prompt.index("ФОРМАТ ОТВЕТА ОБЯЗАТЕЛЕН"))
        self.assertEqual(saved_batches[-1][0].state, RunState.DONE)
        self.assertEqual(saved_batches[-1][0].result, "Готовый сценарий по проверочной теме.")

    def test_both_provider_modes_receive_full_template_and_priority_length_contract(self):
        template = (
            "FULL_USER_PROMPT_BEGIN :: Напиши сценарий для {title}.\\n"
            + ("Сохрани эту пользовательскую вводную без потери контекста. " * 120)
            + "\\nFULL_USER_PROMPT_END"
        )

        class FakePool:
            concurrency = 1

            def __init__(self):
                self.prompts = []

            async def generate(self, prompt):
                self.prompts.append(prompt)
                return "а" * 10000

        for provider in ("openai", "agent"):
            with self.subTest(provider=provider):
                settings = Settings(
                    scenario_provider=provider,
                    template=template,
                    prompt_ranges=[],
                    scenario_target_chars=10000,
                    scenario_allowed_min=9000,
                    scenario_allowed_max=11000,
                )
                pool = FakePool()
                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "load_session", return_value=(["Проверочная тема"], [])), \
                     patch.object(bridge, "save_session"), \
                     patch.object(bridge, "save_settings"), \
                     patch.object(bridge, "snapshot", return_value={}), \
                     patch.object(bridge, "HybridTextPool", return_value=pool):
                    bridge.generate_scenarios({"provider": provider})

                self.assertEqual(len(pool.prompts), 1)
                prompt = pool.prompts[0]
                self.assertIn("FULL_USER_PROMPT_BEGIN :: Напиши сценарий для Проверочная тема.", prompt)
                self.assertIn("FULL_USER_PROMPT_END", prompt)
                self.assertIn("ПРИОРИТЕТНЫЙ КОНТРАКТ ОБЪЕМА NEWSFLOW", prompt)
                self.assertIn("Целевой объем: 10000 символов", prompt)
                self.assertIn("Допустимый итоговый диапазон: 9000–11000 символов", prompt)
                self.assertIn("ОБЯЗАТЕЛЬНО сам контролируй количество символов", prompt)
                self.assertIn("ПЕРЕД ОТПРАВКОЙ ФИНАЛЬНОГО ОТВЕТА сам проверь длину", prompt)
                self.assertIn("len(text.strip())", prompt)
                self.assertIn("а не слова, токены или приблизительный объем", prompt)
                self.assertLess(
                    prompt.index("ПРИОРИТЕТНЫЙ КОНТРАКТ ОБЪЕМА NEWSFLOW"),
                    prompt.index("FULL_USER_PROMPT_BEGIN"),
                )

    def test_add_scenarios_persists_identity_before_any_read_only_snapshot(self):
        """A typed title gets one durable ID on the explicit Add action."""
        title = "Ручной заголовок до генерации"
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {
                    "NEWSFLOW_TEST_MODE": "1",
                    "NEWSFLOW_TEST_ROOT": directory,
                    "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(directory) / "production"),
                    "LOCALAPPDATA": directory,
                }), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            bridge.add_scenarios({"titles": title})
            settings = load_settings()
            titles, _jobs = load_session()

        self.assertEqual(titles, [title])
        self.assertEqual(len(settings.idea_production_items), 1)
        production_item_id = str(settings.idea_production_items[0]["id"])
        self.assertTrue(production_item_id)
        self.assertEqual(settings.idea_scenario_context[title]["id"], production_item_id)

    def test_manual_scenario_persists_current_production_identity_for_covers(self):
        """A manually completed script must enter Covers through a durable current ID."""
        title = "Ручной сценарий для обложки"
        text = "Готовый текст ручного сценария для полноценного production-потока."

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {
                    "NEWSFLOW_TEST_MODE": "1",
                    "NEWSFLOW_TEST_ROOT": directory,
                    "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(directory) / "production"),
                    "LOCALAPPDATA": directory,
                }), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            result = bridge.import_manual_scenario({"title": title, "text": text})
            settings = load_settings()
            titles, jobs = load_session()

        self.assertEqual(titles, [title])
        self.assertEqual(len(settings.idea_production_items), 1)
        production_item = settings.idea_production_items[0]
        production_item_id = production_item["id"]
        self.assertTrue(production_item_id)
        self.assertEqual(settings.idea_scenario_context[title]["id"], production_item_id)
        self.assertEqual(jobs[0].request.production_item_id, production_item_id)
        self.assertEqual(result["covers"][0]["production_item_id"], production_item_id)

    def test_manual_scenario_import_persists_current_production_identity_for_covers(self):
        """TXT import must use the same current-ID path as the manual editor."""
        title = "Импортированный сценарий для обложки"
        text = "Готовый текст импортированного сценария для production-потока."

        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {
                    "NEWSFLOW_TEST_MODE": "1",
                    "NEWSFLOW_TEST_ROOT": directory,
                    "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(directory) / "production"),
                    "LOCALAPPDATA": directory,
                }), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            result = bridge.import_manual_scenarios({"items": [{"title": title, "text": text}]})
            settings = load_settings()
            _titles, jobs = load_session()

        self.assertEqual(len(settings.idea_production_items), 1)
        production_item_id = settings.idea_production_items[0]["id"]
        self.assertEqual(settings.idea_scenario_context[title]["id"], production_item_id)
        self.assertEqual(jobs[0].request.production_item_id, production_item_id)
        self.assertEqual(result["covers"][0]["production_item_id"], production_item_id)

    def test_template_length_contract_is_persisted_and_used_by_generation(self):
        template = "Напиши сценарий по теме {title}."
        settings = Settings(scenario_provider="openai", template=template, prompt_ranges=[])
        saved_batches = []

        class FakePool:
            concurrency = 1

            async def generate(self, prompt):
                if "NewsFlow Story Planner" in prompt:
                    return _story_plan(2)
                return "а" * 5000

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_template({
                "template": template,
                "ranges": [],
                "targetChars": 10000,
                "allowedMin": 9000,
                "allowedMax": 11000,
            })

        self.assertEqual(
            (settings.scenario_target_chars, settings.scenario_allowed_min, settings.scenario_allowed_max),
            (10000, 9000, 11000),
        )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(["Тема"], [])), \
             patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_batches.append(jobs)), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_scenarios({"provider": "openai"})

        request = saved_batches[-1][0].request
        self.assertEqual((request.target_chars, request.allowed_min, request.allowed_max), (10000, 9000, 11000))
        self.assertEqual(saved_batches[-1][0].length_status, "READY")

    def test_template_preset_keeps_its_own_dynamic_length_contract(self):
        settings = Settings()
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_template_preset({
                "name": "10k",
                "template": "Шаблон {title}",
                "ranges": [],
                "targetChars": 10000,
                "allowedMin": 9000,
                "allowedMax": 11000,
            })

        preset = settings.scenario_templates[0]
        self.assertEqual(
            (preset["target_chars"], preset["allowed_min"], preset["allowed_max"]),
            (10000, 9000, 11000),
        )
        self.assertEqual(
            (settings.scenario_target_chars, settings.scenario_allowed_min, settings.scenario_allowed_max),
            (10000, 9000, 11000),
        )

    def test_range_target_is_included_in_the_python_owned_scenario_contract(self):
        from scriptor.core import PromptRange, build_requests

        request = build_requests(
            ["Тема"], "Напиши сценарий: {title}",
            [PromptRange(1, 1, "Без списков", target_chars=1000, allowed_min=900, allowed_max=1100)],
        )[0]

        self.assertEqual(request.target_chars, 1000)
        self.assertEqual(request.allowed_min, 900)
        self.assertEqual(request.allowed_max, 1100)
        self.assertIn("900–1100", request.prompt)

    def test_explicit_user_prompt_character_range_becomes_the_runtime_contract(self):
        """A saved human prompt must not leave a textual 10k–15k rule unenforced."""
        from scriptor.core import build_requests

        prompt = (
            "Напиши один готовый сценарий по теме {title}.\n"
            "НЕОБХОДИМОЕ КОЛИЧЕСТВО СИМВОЛОВ: 10 000 - 15 000. "
            "Считать символы при помощи Python."
        )

        request = build_requests(["Текущая тема"], prompt, [])[0]

        self.assertEqual(request.target_chars, 12500)
        self.assertEqual(request.allowed_min, 10000)
        self.assertEqual(request.allowed_max, 15000)
        self.assertIn("10000–15000", request.prompt)

    def test_scenario_length_contract_survives_session_roundtrip(self):
        from scriptor.session import _read_session, _session_data
        request = ScenarioRequest(0, "Тема", "Промпт", "item-1", 1000, 900, 1100)
        job = Job(
            request,
            RunState.DONE,
            "Готовый текст",
            actual_chars=13,
            length_status="READY",
            length_repair_attempts=1,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            path.write_text(__import__("json").dumps(_session_data(["Тема"], [job])), encoding="utf-8")
            _titles, jobs = _read_session(path)

        self.assertEqual((jobs[0].request.target_chars, jobs[0].request.allowed_min, jobs[0].request.allowed_max), (1000, 900, 1100))
        self.assertEqual((jobs[0].actual_chars, jobs[0].length_status, jobs[0].length_repair_attempts), (13, "READY", 1))

    def test_generated_script_persists_its_production_item_id(self):
        """The script queue must not use the editable title as its parent identity."""
        title = "Тема с устойчивой связью"
        settings = Settings(
            scenario_provider="agent",
            idea_production_items=[{"id": "pi-stable", "title": title}],
            prompt_ranges=[{
                "start": 1, "end": 1, "prompt": "",
                "target_chars": 20, "allowed_min": 1, "allowed_max": 100,
            }],
        )
        saved_batches = []

        class FakePool:
            concurrency = 1

            async def generate(self, _prompt):
                return "Готовый текст сценария"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=([title], [])), \
             patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_batches.append(jobs)), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_scenarios({"provider": "agent"})

        self.assertTrue(saved_batches)
        self.assertEqual(saved_batches[-1][0].request.production_item_id, "pi-stable")
        self.assertEqual(
            (saved_batches[-1][0].request.target_chars, saved_batches[-1][0].request.allowed_min, saved_batches[-1][0].request.allowed_max),
            (20, 1, 100),
        )

    def test_selected_and_all_generation_share_the_current_user_prompt_contract(self):
        """Both visible batch actions must reach the same current prompt and length gate."""
        user_prompt = "CURRENT USER RULE: 10 000 - 15 000 символов. Тема: {title}"

        class FakePool:
            concurrency = 2

            def __init__(self):
                self.prompts = []

            async def generate(self, prompt):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return _story_plan(3)
                target = int(__import__("re").search(r"CURRENT TARGET: approximately (\d+) characters", prompt).group(1))
                return "а" * target

        def run(payload):
            settings = Settings(scenario_provider="agent", template=user_prompt, prompt_ranges=[])
            pool = FakePool()
            saved_batches = []
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Первая", "Вторая"], [])), \
                 patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_batches.append(jobs)), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "HybridTextPool", return_value=pool):
                bridge.generate_scenarios(payload)
            return pool.prompts, saved_batches[-1]

        all_prompts, all_jobs = run({"provider": "agent"})
        selected_prompts, selected_jobs = run({"provider": "agent", "indices": [1]})

        self.assertEqual(len(all_prompts), 8)
        self.assertEqual(len(selected_prompts), 4)
        self.assertTrue(all("CURRENT USER RULE" in prompt for prompt in [*all_prompts, *selected_prompts]))
        self.assertTrue(all("10000–15000" in prompt for prompt in [*all_prompts, *selected_prompts]))
        self.assertTrue(all(job.length_status == "READY" for job in [*all_jobs, *selected_jobs]))
        self.assertTrue(all((job.request.target_chars, job.request.allowed_min, job.request.allowed_max) == (12500, 10000, 15000)
                            for job in [*all_jobs, *selected_jobs]))

    def test_both_provider_modes_resume_a_persisted_story_at_the_next_part(self):
        title = "Тема для возобновления"
        plan = parse_story_plan_response(
            _story_plan(2), calculate_story_part_targets(10000),
        ).to_dict()
        for provider in ("agent", "openai"):
            with self.subTest(provider=provider):
                settings = Settings(
                    scenario_provider=provider, template="USER CONTRACT {title}", prompt_ranges=[],
                    scenario_target_chars=10000, scenario_allowed_min=9000, scenario_allowed_max=11000,
                )
                old = Job(
                    ScenarioRequest(0, title, "old", target_chars=10000, allowed_min=9000, allowed_max=11000),
                    RunState.PAUSED, "а" * 5000, "", story_plan=plan,
                    accepted_story_parts=[{"part_id": "P1", "text": "а" * 5000, "content_ids": ["C001"], "target_chars": 5000}],
                    story_planner_status="READY",
                )

                class FakePool:
                    concurrency = 1

                    def __init__(self):
                        self.prompts = []

                    async def generate(self, prompt):
                        self.prompts.append(prompt)
                        if "NewsFlow Story Planner" in prompt:
                            raise AssertionError("resume must not generate a new plan")
                        return "б" * 5000

                pool = FakePool()
                saved_batches = []
                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "load_session", return_value=([title], [old])), \
                     patch.object(bridge, "save_session", side_effect=lambda _titles, jobs, batches=saved_batches: batches.append(list(jobs))), \
                     patch.object(bridge, "save_settings"), \
                     patch.object(bridge, "snapshot", return_value={}), \
                     patch.object(bridge, "HybridTextPool", return_value=pool):
                    bridge.generate_scenarios({"provider": provider, "indices": [0]})

                self.assertEqual(len(pool.prompts), 1)
                self.assertIn("CURRENT PART: P2", pool.prompts[0])
                self.assertIn("USER CONTRACT", pool.prompts[0])
                self.assertEqual(saved_batches[-1][0].state, RunState.DONE)
                self.assertEqual(len(saved_batches[-1][0].accepted_story_parts), 2)

    def test_force_rewrite_updates_only_selected_ready_scenario_and_preserves_identities(self):
        titles = ["Переписать", "Не трогать"]
        settings = Settings(
            scenario_provider="agent",
            idea_production_items=[
                {"id": "pi-rewrite", "title": titles[0]},
                {"id": "pi-keep", "title": titles[1]},
            ],
        )
        existing = [
            Job(ScenarioRequest(0, titles[0], "", "pi-rewrite"), RunState.DONE, "Старый текст A", ""),
            Job(ScenarioRequest(1, titles[1], "", "pi-keep"), RunState.DONE, "Старый текст B", ""),
        ]
        saved_batches = []

        class FakePool:
            concurrency = 1

            async def generate(self, prompt):
                if "NewsFlow Story Planner" in prompt:
                    return _story_plan(1)
                return "Новый текст A"

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(titles, existing)), \
             patch.object(bridge, "save_session", side_effect=lambda _titles, jobs: saved_batches.append(list(jobs))), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=FakePool()):
            bridge.generate_scenarios({"provider": "agent", "indices": [0], "force": True})

        final = {job.request.index: job for job in saved_batches[-1]}
        self.assertEqual(final[0].result, "Новый текст A")
        self.assertEqual(final[0].request.production_item_id, "pi-rewrite")
        self.assertEqual(final[1].result, "Старый текст B")
        self.assertEqual(final[1].request.production_item_id, "pi-keep")

    def test_normal_batch_skips_ready_scenarios_without_constructing_an_api_pool(self):
        """A click on the normal batch action must never overwrite completed scripts."""
        settings = Settings(scenario_provider="agent")
        titles = ["Первая тема", "Вторая тема"]
        jobs = [
            Job(ScenarioRequest(0, titles[0], ""), RunState.DONE, "Первый готовый сценарий", ""),
            Job(ScenarioRequest(1, titles[1], ""), RunState.DONE, "Второй готовый сценарий", ""),
        ]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=(titles, jobs)), \
             patch.object(bridge, "HybridTextPool", side_effect=AssertionError("API pool must not start")), \
             patch.object(bridge, "snapshot", return_value={"scenarios": "unchanged"}):
            result = bridge.generate_scenarios({"provider": "agent"})

        self.assertEqual(result["scenarios"], "unchanged")
        self.assertEqual(result["operationResult"]["kind"], "scenarios-skip-ready")
        self.assertEqual(result["operationResult"]["count"], 0)


class ScenarioDeletionRecoveryTests(unittest.TestCase):
    def test_explicit_idea_readd_after_delete_mints_current_identity_for_covers(self):
        """A deliberate same-title hand-off must not revive the deleted identity."""
        title = "Тема для повторного переноса в обложки"
        deleted_id = "pi-deleted"
        original = {
            "id": deleted_id,
            "title": title,
            "status": "READY",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {
                    "NEWSFLOW_TEST_MODE": "1",
                    "NEWSFLOW_TEST_ROOT": directory,
                    "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(directory) / "production"),
                    "LOCALAPPDATA": directory,
                }), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            save_settings(Settings(
                idea_results=[title],
                idea_production_items=[original],
                idea_scenario_context={title: dict(original)},
            ))
            save_session([title], [
                Job(ScenarioRequest(0, title, "", deleted_id), RunState.DONE, "Старый текст", ""),
            ])

            bridge.remove_scenarios_command({"indices": [0]})
            result = bridge.transfer_ideas({"ideas": [title], "target": "covers"})
            titles, jobs = load_session()
            settings = load_settings()

        self.assertEqual(titles, [title])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].state, RunState.WAITING)
        current_id = settings.idea_scenario_context[title]["id"]
        self.assertNotEqual(current_id, deleted_id)
        self.assertNotIn(current_id, settings.deleted_scenario_production_ids)
        self.assertEqual(jobs[0].request.production_item_id, current_id)
        self.assertEqual(len(settings.cover_queue), 1)
        self.assertEqual(settings.cover_queue[0]["production_item_id"], current_id)
        self.assertEqual(result["operationResult"]["kind"], "ideas-transfer")

    def test_stale_settings_save_retains_deleted_script_production_id(self):
        """A competing worker cannot erase the tombstone that guards backup recovery."""
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            save_settings(Settings(deleted_scenario_production_ids=["pi-deleted"]))
            save_settings(Settings())
            restored = load_settings()

        self.assertEqual(restored.deleted_scenario_production_ids, ["pi-deleted"])

    def test_deleted_script_is_rejected_from_backup_by_production_item_id(self):
        """A renamed backup script cannot bypass the durable parent-ID tombstone."""
        titles = ["Первый сценарий", "Исходное название"]
        jobs = [
            Job(ScenarioRequest(0, titles[0], "", "pi-keep"), RunState.DONE, "Первый текст", ""),
            Job(ScenarioRequest(1, titles[1], "", "pi-deleted"), RunState.DONE, "Удалённый текст", ""),
        ]
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            save_settings(Settings(idea_results=titles))
            save_session(titles, jobs)
            save_session(titles, jobs)

            bridge.remove_scenarios_command({"indices": [1]})
            session_path().unlink()  # recovery now only has a stale backup

            restored_titles, restored_jobs = load_session()
            restored_settings = load_settings()

        self.assertEqual(restored_titles, ["Первый сценарий"])
        self.assertEqual([job.request.production_item_id for job in restored_jobs], ["pi-keep"])
        self.assertEqual(restored_settings.deleted_scenario_production_ids, ["pi-deleted"])

    def test_deleted_scenario_is_excluded_when_primary_session_is_recovered_from_backup(self):
        """A stale backup must not resurrect a script deliberately removed from the current batch."""
        titles = ["Первый сценарий", "Удалённый сценарий"]
        jobs = [
            Job(ScenarioRequest(0, titles[0], ""), RunState.DONE, "Первый текст", ""),
            Job(ScenarioRequest(1, titles[1], ""), RunState.DONE, "Удалённый текст", ""),
        ]
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                patch("scriptor.config._newsflow_auth_library_candidates", return_value=[]), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"):
            save_settings(Settings(idea_results=titles))
            save_session(titles, jobs)
            save_session(titles, jobs)  # creates the independent last-known-good session

            bridge.remove_scenarios_command({"indices": [1]})
            session_path().unlink()  # simulate a missing/corrupt primary after deletion

            restored_titles, restored_jobs = load_session()

        self.assertEqual(restored_titles, ["Первый сценарий"])
        self.assertEqual([job.result for job in restored_jobs], ["Первый текст"])
