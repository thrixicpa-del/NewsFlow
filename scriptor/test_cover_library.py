from __future__ import annotations

import tempfile
import unittest
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .cover_library import CoverLibrary
from .config import Settings
from .covers import FastGenClient
from . import bridge


class CoverLibraryTests(unittest.TestCase):
    def test_word_engine_v2_handoff_keeps_approved_words_unchanged_for_visual_prompt(self):
        """The later visual stage consumes ready words; it never generates or rewrites them."""
        settings = Settings(cover_prompt_template="Scene for {title}. Context: {excerpt}")
        item = {
            "title": "Тарифы на импорт", "script": "Трамп ввёл новые тарифы.",
            "cover_headline": "ТРАМП ДАВИТ", "headline_status": "READY",
            "cover_subheadline": "Тарифы бьют по импорту", "subheadline_status": "READY",
        }

        prompt = bridge._cover_instruction(item, 0, settings)

        self.assertIn("ТРАМП ДАВИТ", prompt)
        self.assertIn("Тарифы бьют по импорту", prompt)
        self.assertIn("Не рисуй буквы сам", prompt)

    def test_word_engine_v2_persists_ready_metadata_across_library_hydration(self):
        """Restart hydration must preserve a ready pair, structures, variation and repair history."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            original = {
                "production_item_id": "persist-word-1", "title": "Ормуз и поставки нефти",
                "cover_headline": "НЕФТЬ ПОД УГРОЗОЙ", "headline_source": "AI", "headline_status": "READY",
                "headline_structure_id": "H06", "headline_variation_index": 2, "headline_attempt_count": 3,
                "cover_subheadline": "Ормузский пролив и поставки", "subheadline_source": "AI",
                "subheadline_status": "READY", "subheadline_structure_id": "S03",
                "subheadline_variation_index": 2, "subheadline_attempt_count": 2,
                "headline_repair_history": [{"attempt": 1, "validation": {"valid": True}}],
            }
            library.persist([original], {"image": [], "video": []}, {})

            restored, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})

            self.assertEqual(restored[0]["headline_status"], "READY")
            self.assertEqual(restored[0]["headline_structure_id"], "H06")
            self.assertEqual(restored[0]["headline_variation_index"], 2)
            self.assertEqual(restored[0]["subheadline_structure_id"], "S03")
            self.assertEqual(restored[0]["headline_repair_history"], original["headline_repair_history"])

    def test_word_engine_v2_real_bridge_flow_generates_words_before_any_visual_prompt(self):
        """The bridge persists a validated pair while READY/MANUAL rows are skipped."""
        class FakeWordPool:
            def __init__(self, *_args):
                pass

            async def generate(self, prompt, before_request=None):
                if before_request:
                    await before_request()
                return "Тарифы бьют по импорту" if "УЖЕ УТВЕРЖДЁННЫЙ HEADLINE" in prompt else "ТРАМП ДАВИТ"

        settings = Settings(openai_api_keys=["test"], idea_scenario_context={
            "Трамп повысил тарифы на импорт": {"id": "flow-1"},
            "Готовая тема": {"id": "flow-2"},
            "Ручная тема": {"id": "flow-3"},
        }, cover_queue=[
            {"production_item_id": "flow-1", "title": "Трамп повысил тарифы на импорт", "script": "Трамп ввёл тарифы на импорт."},
            {"production_item_id": "flow-2", "title": "Готовая тема", "cover_headline": "ГОТОВО", "headline_status": "READY", "headline_source": "AI"},
            {"production_item_id": "flow-3", "title": "Ручная тема", "cover_headline": "МОЙ ТЕКСТ", "headline_status": "MANUAL", "headline_source": "MANUAL"},
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "load_session", return_value=(["Трамп повысил тарифы на импорт", "Готовая тема", "Ручная тема"], [])), \
             patch.object(bridge, "HybridTextPool", FakeWordPool):
            bridge.generate_cover_headlines({"indices": [0, 1, 2], "productionItemIds": ["flow-1", "flow-2", "flow-3"], "provider": "agent"})
            bridge.generate_cover_subheadlines({"indices": [0], "productionItemIds": ["flow-1"], "provider": "agent"})

        generated = settings.cover_queue[0]
        self.assertEqual(generated["cover_headline"], "ТРАМП ДАВИТ")
        self.assertEqual(generated["headline_status"], "READY")
        self.assertEqual(generated["cover_subheadline"], "Тарифы бьют по импорту")
        self.assertEqual(generated["subheadline_status"], "READY")
        self.assertNotIn("image_prompt", generated)
        self.assertEqual(settings.cover_queue[1]["cover_headline"], "ГОТОВО")
        self.assertEqual(settings.cover_queue[2]["cover_headline"], "МОЙ ТЕКСТ")

    def test_word_engine_v2_generates_missing_headline_even_when_subheadline_is_ready(self):
        """The two independent fields must not make a ready subheadline suppress headline generation."""
        class FakeWordPool:
            def __init__(self, *_args):
                pass

            async def generate(self, _prompt, before_request=None):
                if before_request:
                    await before_request()
                return "ТАРИФЫ ДАВЯТ"

        settings = Settings(openai_api_keys=["test"], idea_scenario_context={
            "Трамп повысил тарифы на импорт": {"id": "headline-after-sub"},
        }, cover_queue=[{
            "production_item_id": "headline-after-sub", "title": "Трамп повысил тарифы на импорт",
            "script": "Трамп ввёл новые тарифы на импорт.",
            "cover_subheadline": "Импорт под давлением", "subheadline_status": "READY",
        }])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "_save_cover_text_progress"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "load_session", return_value=(["Трамп повысил тарифы на импорт"], [])), \
             patch.object(bridge, "HybridTextPool", FakeWordPool):
            bridge.generate_cover_headlines({"indices": [0], "productionItemIds": ["headline-after-sub"], "provider": "agent"})

        self.assertEqual(settings.cover_queue[0]["cover_headline"], "ТАРИФЫ ДАВЯТ")
        self.assertEqual(settings.cover_queue[0]["headline_status"], "READY")

    def test_word_engine_v2_does_not_overwrite_manual_subheadline_in_normal_batch(self):
        """Create subheadlines fills only missing rows; a manual line is immutable without force."""
        class FakeWordPool:
            def __init__(self, *_args):
                pass

            async def generate(self, _prompt, before_request=None):
                if before_request:
                    await before_request()
                return "Импорт несёт потери"

        settings = Settings(openai_api_keys=["test"], idea_scenario_context={
            "Трамп повысил тарифы на импорт": {"id": "sub-manual"},
            "Импорт под давлением": {"id": "sub-missing"},
        }, cover_queue=[
            {
                "production_item_id": "sub-manual", "title": "Трамп повысил тарифы на импорт",
                "script": "Трамп ввёл новые тарифы на импорт.", "cover_headline": "ТАРИФЫ ДАВЯТ",
                "cover_subheadline": "МОЯ ВТОРАЯ СТРОКА", "subheadline_status": "MANUAL",
            },
            {
                "production_item_id": "sub-missing", "title": "Импорт под давлением",
                "script": "Трамп ввёл новые тарифы на импорт.", "cover_headline": "ТАРИФЫ ДАВЯТ",
            },
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "_save_cover_text_progress"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "load_session", return_value=(["Трамп повысил тарифы на импорт", "Импорт под давлением"], [])), \
             patch.object(bridge, "HybridTextPool", FakeWordPool):
            bridge.generate_cover_subheadlines({"indices": [0, 1], "productionItemIds": ["sub-manual", "sub-missing"], "provider": "agent"})

        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "МОЯ ВТОРАЯ СТРОКА")
        self.assertEqual(settings.cover_queue[0]["subheadline_status"], "MANUAL")
        self.assertEqual(settings.cover_queue[1]["cover_subheadline"], "Импорт несёт потери")

    def test_word_engine_v2_distributes_structure_pairs_over_a_thirty_topic_batch(self):
        """A batch must not collapse into one hook pattern or one subheadline role."""
        rows = [
            {"production_item_id": f"batch-{index}", "title": f"Тема {index} о поставках и рынке"}
            for index in range(30)
        ]
        pairs = [bridge._cover_word_structure_pair(item) for item in rows]

        self.assertGreaterEqual(len({pair["headline_structure_id"] for pair in pairs}), 12)
        self.assertGreaterEqual(len({pair["subheadline_structure_id"] for pair in pairs}), 8)

    def test_word_engine_v2_manual_save_marks_the_line_immutable_to_batch_work(self):
        """Typing a line in the UI is persisted as MANUAL rather than an expendable suggestion."""
        settings = Settings(cover_queue=[{"title": "Тарифы на импорт", "cover_headline": ""}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library"), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_cover_headline({"index": 0, "headline": "ТАРИФЫ ДАВЯТ"})

        item = settings.cover_queue[0]
        self.assertEqual(item["headline_source"], "MANUAL")
        self.assertEqual(item["headline_status"], "MANUAL")
        self.assertFalse(bridge._cover_word_should_generate(item, "headline"))

    def test_word_engine_v2_repairs_invalid_output_twice_then_keeps_the_valid_clickable_hook(self):
        """Two bounded repairs may recover a bad model response without changing source facts."""
        class ScriptedPool:
            def __init__(self):
                self.responses = iter(["ВАЖНЫЕ НОВОСТИ", "ТАРИФЫ МЕНЯЮТСЯ УЖЕ СЕГОДНЯ", "ТРАМП ДАВИТ"])
                self.calls = 0

            async def generate(self, _prompt, before_request=None):
                self.calls += 1
                if before_request:
                    await before_request()
                return next(self.responses)

        item = {
            "title": "Трамп повысил тарифы на импорт", "script": "Трамп ввёл новые тарифы на импорт.",
            "production_item_id": "repair-1",
        }
        pool = ScriptedPool()
        structure = bridge._cover_word_structure_pair(item)

        value, validation, history = asyncio.run(
            bridge._generate_cover_word_v2(pool, "headline", item, "", structure)
        )

        self.assertEqual(value, "ТРАМП ДАВИТ")
        self.assertTrue(validation["valid"])
        self.assertEqual(pool.calls, 3)
        self.assertEqual(len(history), 3)

    def test_word_engine_v2_stops_after_two_repairs_and_does_not_create_a_fallback_phrase(self):
        """A permanently generic model response must surface as failed after three calls."""
        class GenericPool:
            def __init__(self):
                self.calls = 0

            async def generate(self, _prompt, before_request=None):
                self.calls += 1
                return "ВАЖНЫЕ НОВОСТИ"

        item = {"title": "Поставки газа в Европу", "script": "Поставки газа сократились.", "production_item_id": "repair-2"}
        pool = GenericPool()

        with self.assertRaisesRegex(ValueError, "NOT_GROUNDED"):
            asyncio.run(bridge._generate_cover_word_v2(
                pool, "headline", item, "", bridge._cover_word_structure_pair(item),
            ))
        self.assertEqual(pool.calls, 3)

    def test_word_engine_v2_assigns_stable_and_varied_complementary_structures(self):
        """Same topic is stable, while explicit regenerate changes the compatible pair."""
        item = {
            "production_item_id": "item-energy-1",
            "title": "Трамп сделал заявление по поставкам нефти через Ормуз",
            "script": "Поставки нефти могут сократиться, если ситуация в Ормузском проливе усилится.",
        }

        initial = bridge._cover_word_structure_pair(item, 0)
        repeat = bridge._cover_word_structure_pair(item, 0)
        regenerated = bridge._cover_word_structure_pair(item, 1)

        self.assertEqual(initial, repeat)
        self.assertTrue(initial["headline_structure_id"].startswith("H"))
        self.assertTrue(initial["subheadline_structure_id"].startswith("S"))
        self.assertNotEqual(initial, regenerated)
        self.assertGreaterEqual(len(bridge._COVER_WORD_HEADLINE_STRUCTURES), 18)
        self.assertGreaterEqual(len(bridge._COVER_WORD_SUBHEADLINE_ROLES), 18)

    def test_word_engine_v2_rejects_a_subheadline_that_repeats_the_headline_meaning(self):
        """Different words must not smuggle the same collapse-of-supply meaning into line two."""
        item = {
            "title": "Поставки нефти через Ормуз могут сократиться",
            "script": "Экспорт нефти находится под риском из-за напряжённости в проливе.",
        }

        result = bridge._validate_cover_word(
            "subheadline", "Экспорт может обвалиться", item,
            headline="Поставки рухнут?", structure={"semantic_slots": ["consequence"]},
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason_code"], "DUPLICATE_MEANING")

    def test_word_engine_v2_rejects_truncation_instead_of_marking_it_ready(self):
        """A four-word headline must request repair, not silently lose its final meaning."""
        item = {"title": "Европа осталась без газа", "script": "Поставки газа в Европу сократились."}

        result = bridge._validate_cover_word(
            "headline", "Европа осталась без газа", item,
            structure={"semantic_slots": ["location", "consequence"]},
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason_code"], "TOO_MANY_WORDS")
        self.assertEqual(result["value"], "Европа осталась без газа")

    def test_word_engine_v2_preserves_manual_words_during_ordinary_batch_generation(self):
        """Manual wording must be excluded unless the caller explicitly forces replacement."""
        item = {
            "title": "Тарифы меняются", "cover_headline": "МОЙ ЗАГОЛОВОК",
            "headline_source": "MANUAL", "headline_status": "MANUAL",
        }

        self.assertFalse(bridge._cover_word_should_generate(item, "headline", force=False))
        self.assertTrue(bridge._cover_word_should_generate(item, "headline", force=True))

    def test_word_engine_v2_reads_pattern_cooldown_from_persisted_headlines(self):
        """Restarted queues lack transient signatures, so cooldown must derive them from saved words."""
        item = {
            "title": "Трамп повысил тарифы на импорт",
            "script": "Трамп ввёл новые тарифы на импорт.",
        }
        recent = [{"cover_headline": "ТАРИФЫ ДАВЯТ"} for _ in range(3)]

        result = bridge._validate_cover_word(
            "headline", "ТАРИФЫ ДАВЯТ", item,
            structure={"semantic_slots": ["pressure"]}, recent=recent,
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason_code"], "RECENT_PATTERN_REPEAT")

    def test_remove_cover_prompts_updates_the_durable_cover_library(self):
        """A deleted prompt must not reappear from covers-library.json on the next snapshot."""
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(idea_scenario_context={"Тарифы на импорт": {"id": "remove-prompt-1"}}, cover_queue=[{
                "production_item_id": "remove-prompt-1", "title": "Тарифы на импорт",
                "image_prompt": "old visual prompt", "image_prompt_options": ["old visual prompt"],
            }])
            with patch.object(bridge, "app_data_root", return_value=Path(temporary)), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Тарифы на импорт"], [])), \
                 patch.object(bridge, "save_settings"):
                bridge._save_cover_state(settings)
                bridge.remove_cover_prompts({"indices": [0]})

                restored = Settings(idea_scenario_context={"Тарифы на импорт": {"id": "remove-prompt-1"}}, cover_queue=[])
                bridge._hydrate_cover_library(restored)

        self.assertNotIn("image_prompt", restored.cover_queue[0])
        self.assertNotIn("image_prompt_options", restored.cover_queue[0])

    def test_remove_cover_prompts_wins_against_a_stale_snapshot_after_restart(self):
        """A polling bridge with an old prompt must not resurrect an explicitly deleted prompt."""
        with tempfile.TemporaryDirectory() as temporary:
            old_item = {
                "production_item_id": "remove-prompt-race", "title": "Тарифы на импорт",
                "image_prompt": "old visual prompt", "image_prompt_options": ["old visual prompt"],
                "updatedAt": "2026-09-10T10:00:00",
            }
            settings = Settings(idea_scenario_context={"Тарифы на импорт": {"id": "remove-prompt-race"}}, cover_queue=[dict(old_item)])
            with patch.object(bridge, "app_data_root", return_value=Path(temporary)), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Тарифы на импорт"], [])), \
                 patch.object(bridge, "save_settings"):
                bridge._save_cover_state(settings)
                bridge.remove_cover_prompts({"indices": [0]})

                stale = Settings(idea_scenario_context={"Тарифы на импорт": {"id": "remove-prompt-race"}}, cover_queue=[dict(old_item)])
                bridge._hydrate_cover_library(stale)

        self.assertNotIn("image_prompt", stale.cover_queue[0])
        self.assertNotIn("image_prompt_options", stale.cover_queue[0])

    def test_unknown_fastgen_schema_omits_optional_count(self):
        """A capabilities timeout must not make text-only providers reject count=1."""
        payload, supports_count, maximum = FastGenClient("test-key")._generation_payload(
            "flower_image_generate", "a scene", "16:9", [], None, None, None, False, {}
        )

        self.assertNotIn("count", payload)
        self.assertFalse(supports_count)
        self.assertEqual(maximum, 1)

    def test_fastgen_full_prompt_names_a_matched_person_without_a_remote_reference(self):
        """Flower can draw a named person even though its schema forbids image inputs."""
        instruction = bridge._cover_fastgen_identity_instruction("путин", has_remote_reference=False)

        self.assertIn("путин", instruction.casefold())
        self.assertIn("recognisable", instruction.casefold())
        self.assertNotIn("supplied portrait reference", instruction.casefold())

    def test_second_cover_batch_cannot_claim_an_active_generation_lock(self):
        """A second click must not silently double the configured ten-worker limit."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_cover_generation_process_is_running", return_value=True):
                first = bridge._claim_cover_generation_lock()
                second = bridge._claim_cover_generation_lock()

            self.assertIsNotNone(first)
            self.assertIsNone(second)

    def test_ten_parallel_persists_keep_every_cover_record(self):
        """Provider concurrency must not corrupt the durable thumbnail registry."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")

            def persist_one(index: int) -> None:
                library.persist(
                    [{"title": f"Тема {index}", "production_item_id": f"production-{index}",
                      "status": "Генерируется", "updatedAt": f"2026-09-10T12:00:{index:02d}"}],
                    {"image": [], "video": []}, {},
                )

            with ThreadPoolExecutor(max_workers=10) as executor:
                list(executor.map(persist_one, range(10)))

            restored, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})
            self.assertEqual({item["production_item_id"] for item in restored}, {f"production-{index}" for index in range(10)})

    def test_persist_retries_a_transient_windows_file_lock(self):
        """A transient sharing violation must not fail a cover task or lose its registry row."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            original_replace = Path.replace
            calls = 0

            def sharing_violation_once(source: Path, destination: Path):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise PermissionError(5, "Access is denied", str(destination))
                return original_replace(source, destination)

            with patch.object(Path, "replace", sharing_violation_once):
                library.persist(
                    [{"production_item_id": "locked-save", "title": "Тема", "status": "Ожидает"}],
                    {"image": [], "video": []}, {},
                )

            restored, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})
            self.assertEqual(calls, 2)
            self.assertEqual(restored[0]["production_item_id"], "locked-save")

    def test_recovery_restores_only_missing_subheadlines_from_an_interrupted_snapshot(self):
        """Recovery must bring back completed second lines without overwriting newer user text."""
        settings = Settings(cover_queue=[
            {"production_item_id": "one", "title": "Первая тема", "cover_headline": "ПЕРВЫЙ ХУК"},
            {"production_item_id": "two", "title": "Вторая тема", "cover_headline": "ВТОРОЙ ХУК",
             "cover_subheadline": "МОЯ НОВАЯ СТРОКА", "subheadline_status": "MANUAL"},
        ])
        interrupted = [
            {"production_item_id": "one", "title": "Первая тема", "cover_subheadline": "ДЕТАЛЬ СОБЫТИЯ",
             "subheadline_source": "AI", "subheadline_status": "READY", "subheadline_structure_id": "S03"},
            {"production_item_id": "two", "title": "Вторая тема", "cover_subheadline": "СТАРАЯ СТРОКА",
             "subheadline_source": "AI", "subheadline_status": "READY"},
        ]

        restored = bridge._restore_missing_cover_subheadlines(settings, interrupted)

        self.assertEqual(restored, 1)
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "ДЕТАЛЬ СОБЫТИЯ")
        self.assertEqual(settings.cover_queue[0]["subheadline_status"], "READY")
        self.assertEqual(settings.cover_queue[1]["cover_subheadline"], "МОЯ НОВАЯ СТРОКА")
        self.assertEqual(settings.cover_queue[1]["subheadline_status"], "MANUAL")

    def test_face_mode_with_does_not_require_a_local_portrait_reference(self):
        """A face is a visual requirement, not a reason to cancel a render."""
        self.assertEqual(bridge._cover_face_requirement_message("with", ""), "")
        self.assertIn("face", bridge._cover_face_visual_requirement("with", "").casefold())

    def test_cover_counters_use_physical_ready_state_as_the_single_truth(self):
        """A saved image is ready even if an old worker left a stale status."""
        rows = [
            {"status": "Ошибка FastGen", "galleryPaths": [{"state": "ready"}]},
            {"status": "Готово", "galleryPaths": [{"state": "missing"}]},
            {"status": "Ошибка FastGen", "galleryPaths": []},
            {"status": "FastGen генерирует", "galleryPaths": []},
            {"status": "Ожидает", "galleryPaths": []},
        ]

        self.assertEqual(bridge.cover_queue_counts(rows), {
            "total": 5, "ready": 1, "missing": 4, "failed": 1,
            "generating": 1, "queued": 1,
        })

    def test_cover_counters_include_prompt_ready_topics_in_the_queue(self):
        """Prepared prompts are pending render work, never invisible queue rows."""
        rows = [{"status": "Промпты готовы", "galleryPaths": []}]

        self.assertEqual(bridge.cover_queue_counts(rows)["queued"], 1)

    def test_gallery_snapshot_uses_fast_file_existence_check(self):
        """Opening the Gallery must not decode every image before first paint."""
        with patch.object(bridge, "cover_file_state", return_value={
            "path": "cover.png", "state": "ready", "message": "ok",
        }) as file_state:
            result = bridge.cover_gallery_paths({"paths": ["cover.png"]})

        self.assertEqual(result[0]["state"], "ready")
        file_state.assert_called_once_with("cover.png", verify=False)

    def test_retry_plan_uses_four_prompt_rounds_with_four_attempts_each(self):
        """A recoverable provider failure gets 16 transparent chances per prompt."""
        plan = bridge._cover_retry_plan("Трамп и переговоры", "Исходный конкретный промпт")

        self.assertEqual(len(plan), 4)
        self.assertEqual(plan[0]["round"], 1)
        self.assertEqual(plan[0]["prompt"], "Исходный конкретный промпт")
        self.assertTrue(all(item["attempts"] == 4 for item in plan))
        # A transport retry must preserve the builder-owned final provider
        # prompt byte-for-byte: rewriting it here would reintroduce a second
        # prompt authority after Universal V2 assembly.
        self.assertEqual(len({item["prompt"] for item in plan}), 1)
        self.assertTrue(all(item["prompt"] == "Исходный конкретный промпт" for item in plan))

    def test_retryable_fastgen_failure_records_all_sixteen_attempts(self):
        """The final error must prove every prompt round was actually sent."""
        class FailingPool:
            calls = 0

            def __init__(self, _keys):
                pass

            def generate_media(self, *_args, **_kwargs):
                type(self).calls += 1
                raise TimeoutError("network timeout")

        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(
                cover_output_folder=temporary,
                cover_variant_count=1,
                cover_auto_overlay_text=False,
                idea_scenario_context={"Тестовая тема": {"id": "retry-fastgen-1"}},
                cover_queue=[{"production_item_id": "retry-fastgen-1", "title": "Тестовая тема", "image_prompt": "Исходная сцена"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library"), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "load_session", return_value=(["Тестовая тема"], [])), \
                 patch.object(bridge, "FastGenPool", FailingPool), \
                 patch.object(bridge, "_cover_references_for_item", return_value=([], "")), \
                 patch.object(bridge.time, "sleep"):
                bridge.generate_covers({"indices": [0], "productionItemIds": ["retry-fastgen-1"], "_parallel_cover_worker": True})

            item = settings.cover_queue[0]
            self.assertEqual(FailingPool.calls, 16)
            self.assertEqual(item["generation_total_attempt"], 16)
            self.assertEqual(len(item["generation_history"]), 16)
            self.assertEqual(item["status"], "Ошибка FastGen")
            self.assertIn("4 кругов × 4 попытки", item["error"])

    def test_newer_persistent_cover_restores_stale_release_queue(self):
        """A stale settings writer must not erase a completed cover record."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            completed = {
                "title": "Тема",
                "production_item_id": "production-1",
                "status": "Готово",
                "path": r"D:\NewsFlow Studio\Обложки\001.png",
                "paths": [r"D:\NewsFlow Studio\Обложки\001.png"],
                "attempts": 2,
                "updatedAt": "2026-09-10T12:00:00",
            }
            library.persist([completed], {"image": [{"id": "model-1"}], "video": []}, {})

            restored, capabilities, _usage = library.hydrate(
                [{"title": "Тема", "production_item_id": "production-1", "status": "Ожидает", "updatedAt": "2026-09-10T11:00:00"}],
                {"image": [], "video": []},
                {},
            )

            self.assertEqual(restored[0]["status"], "Готово")
            self.assertEqual(restored[0]["path"], completed["path"])
            self.assertEqual(restored[0]["attempts"], 2)
            self.assertEqual(capabilities["image"][0]["id"], "model-1")

    def test_persisted_items_receive_stable_fallback_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            library.persist([{"title": "Одна тема", "scenario_index": 4}], {"image": [], "video": []}, {})

            restored, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})

            self.assertEqual(len(restored), 1)
            self.assertTrue(restored[0]["production_item_id"].startswith("legacy-cover:"))

    def test_hydration_collapses_duplicate_legacy_production_rows(self):
        """A stale duplicate must not create a phantom topic in gallery/counters."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            duplicate = {
                "title": "Одна и та же тема", "production_item_id": "legacy-cover:shared",
                "status": "Готово", "updatedAt": "2026-09-10T12:00:00",
            }
            library.persist([duplicate], {"image": [], "video": []}, {})

            restored, _capabilities, _usage = library.hydrate(
                [duplicate, {**duplicate, "updatedAt": "2026-09-10T11:00:00"}],
                {"image": [], "video": []}, {},
            )

            self.assertEqual(len(restored), 1)
            self.assertEqual(restored[0]["production_item_id"], "legacy-cover:shared")

    def test_face_library_configuration_survives_a_release_settings_reset(self):
        """The semantic portrait library is cover state and must be release-independent."""
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            face_config = {
                "enabled": True,
                "folder": r"D:\Faces",
                "preparedFolder": r"D:\Faces\_prepared",
                "removeBackground": True,
            }

            library.persist([], {"image": [], "video": []}, {}, face_config=face_config)

            self.assertEqual(library.face_config(), face_config)

    def test_explicitly_removed_item_does_not_reappear_after_hydration(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = CoverLibrary(Path(temporary) / "covers-library.json")
            library.persist(
                [{"title": "Тема", "production_item_id": "production-1", "status": "Готово"}],
                {"image": [], "video": []}, {},
            )

            library.remove(["production-1"])
            restored, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})

            self.assertEqual(restored, [])

    def test_bridge_recovers_library_state_when_settings_cache_is_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            library_path = Path(temporary) / "covers-library.json"
            CoverLibrary(library_path).persist(
                [{"title": "Тема", "production_item_id": "production-1", "status": "Готово",
                  "path": "cover.png", "updatedAt": "2026-09-10T12:00:00"}],
                {"image": [{"id": "model-1"}], "video": []}, {"updatedAt": "now"},
            )
            settings = Settings(
                idea_scenario_context={"Тема": {"id": "production-1"}},
                cover_queue=[{"title": "Тема", "production_item_id": "production-1", "status": "Ожидает",
                              "updatedAt": "2026-09-10T11:00:00"}],
                fastgen_capabilities_cache={"image": [], "video": []},
            )
            with patch.object(bridge, "_cover_library_path", return_value=library_path), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [])):
                bridge._hydrate_cover_library(settings)

            self.assertEqual(settings.cover_queue[0]["status"], "Готово")
            self.assertEqual(settings.fastgen_capabilities_cache["image"][0]["id"], "model-1")

    def test_bridge_restores_persisted_face_library_when_release_settings_are_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            library_path = Path(temporary) / "covers-library.json"
            CoverLibrary(library_path).persist(
                [], {"image": [], "video": []}, {},
                face_config={
                    "enabled": True, "folder": r"D:\Faces",
                    "preparedFolder": r"D:\Faces\_prepared", "removeBackground": True,
                },
            )
            settings = Settings(
                cover_face_library_enabled=False,
                cover_face_library_folder="",
                cover_face_prepared_folder="",
                cover_face_remove_background=False,
            )
            with patch.object(bridge, "_cover_library_path", return_value=library_path):
                bridge._hydrate_cover_library(settings)

            self.assertTrue(settings.cover_face_library_enabled)
            self.assertEqual(settings.cover_face_library_folder, r"D:\Faces")
            self.assertEqual(settings.cover_face_prepared_folder, r"D:\Faces\_prepared")
            self.assertTrue(settings.cover_face_remove_background)

    def test_gallery_reconcile_reads_durable_library_before_classifying_missing_files(self):
        """A newer registry record must survive an empty release settings file."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "covers" / "001.png"
            image_path.parent.mkdir()
            image_path.write_bytes(b"not-used-by-this-test")
            library_path = root / "covers-library.json"
            CoverLibrary(library_path).persist(
                [{"title": "Тема", "production_item_id": "production-1", "status": "Готово",
                  "path": str(image_path), "paths": [str(image_path)], "updatedAt": "2026-09-10T12:00:00"}],
                {"image": [], "video": []}, {},
            )
            settings = Settings(
                cover_output_folder=str(image_path.parent),
                idea_scenario_context={"Тема": {"id": "production-1"}},
                cover_queue=[{"title": "Тема", "production_item_id": "production-1", "status": "Ожидает",
                              "updatedAt": "2026-09-10T11:00:00"}],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_cover_library_path", return_value=library_path), \
                 patch.object(bridge, "load_session", return_value=(["Тема"], [])), \
                 patch.object(bridge, "cover_file_state", return_value={"path": str(image_path), "state": "ready", "message": "ok"}), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "save_settings"):
                result = bridge.reconcile_cover_gallery()

            self.assertEqual(result["operationResult"]["health"]["missing"], 0)
            self.assertEqual(settings.cover_queue[0]["status"], "Готово")

    def test_reconcile_recovers_the_legacy_missing_local_face_error(self):
        """An optional portrait miss from an old release is safely retryable."""
        with tempfile.TemporaryDirectory() as temporary:
            settings = Settings(
                cover_output_folder=str(Path(temporary) / "covers"),
                cover_queue=[{
                    "title": "Тема", "status": "Нет подходящего лица",
                    "error": "Для темы не найдено подходящее лицо. Назовите файл или подпапку именем из темы.",
                }],
            )
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_cover_library_path", return_value=Path(temporary) / "covers-library.json"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "save_settings"):
                bridge.reconcile_cover_gallery()

            self.assertEqual(settings.cover_queue[0]["status"], "Ожидает")
            self.assertIn("перезапустить", settings.cover_queue[0]["error"].casefold())

    def test_legacy_face_failure_recovery_does_not_hide_provider_errors(self):
        settings = Settings(cover_queue=[
            {"title": "Старая", "status": "Нет подходящего лица", "error": "старый локальный портрет"},
            {"title": "Провайдер", "status": "Ошибка FastGen", "error": "timeout"},
        ])

        recovered = bridge._recover_legacy_cover_face_blocks(settings)

        self.assertEqual(recovered, 1)
        self.assertEqual(settings.cover_queue[0]["status"], "Ожидает")
        self.assertEqual(settings.cover_queue[1]["status"], "Ошибка FastGen")
