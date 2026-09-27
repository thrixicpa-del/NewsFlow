import asyncio
import json
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor.bridge import (
    _clean_cover_headline,
    _compress_prepared_face_for_fastgen,
    _cover_ai_reference_paths_for_item,
    _cover_face_catalog,
    _cover_face_files,
    _cover_face_layout,
    _cover_face_library_summary,
    _cover_instruction,
    _cover_lines_repeat_meaningful_words,
    _cover_local_face_composite,
    _cover_reference_instruction,
    _cover_reference_paths_for_item,
    _cover_references_for_item,
    _cover_text_matches_topic,
    _cover_text_prompt,
    _cover_text_structure,
    _cover_topic_visual_plan,
    _cover_word_provider_prompt,
    _cover_word_structure_pair,
    _match_cover_face_reference,
    _migrate_legacy_cover_photo_prompts,
    _normalize_cover_photo_prompt,
    _validate_cover_word,
    compose_cover_faces,
    generate_cover_headlines,
    generate_cover_prompts,
    generate_cover_subheadlines,
    generate_covers,
    prepare_cover_face_library,
    regenerate_covers,
    regenerate_covers_new_prompts,
    remove_cover_image,
    remove_cover_results,
    render_cover_text,
    render_cover_text_fastgen,
    save_cover_settings,
    select_cover_variant,
    select_cover_visual_reference,
    set_cover_visual_reference_target,
)
from scriptor.config import FastGenKey, OpenAIKey, Settings, load_settings
from scriptor.cover_rate_limit import cover_rate_limit_decision, next_fastgen_resume_at
from scriptor.covers import (
    FastGenClient,
    FastGenError,
    FastGenPool,
    reference_mime_type,
)
from scriptor.runner import RunState


class CoverGalleryFileStateTests(unittest.TestCase):
    def test_story_planner_context_includes_selected_and_typed_people(self):
        from scriptor import bridge

        prompt = bridge.production_item_prompt({
            "selected_people": ["Марек Новак"],
            "entities": [{"name": "Амина Диалло", "type": "person"}],
        })

        self.assertIn("Марек Новак", prompt)
        self.assertIn("Амина Диалло", prompt)

    def test_story_planner_primary_person_wins_over_face_tree_and_is_persisted_to_cover(self):
        from scriptor import bridge

        title = "Переговоры о соглашении"
        primary = {
            "name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
            "relation_to_story": "возглавил переговоры", "source": "story-planner", "confidence": 0.94,
        }
        settings = Settings(
            idea_production_items=[{"id": "production:planner", "title": title}],
            idea_scenario_context={title: {"id": "production:planner", "title": title}},
            cover_queue=[],
        )
        job = SimpleNamespace(
            request=SimpleNamespace(production_item_id="production:planner"), result="Сценарий", state=RunState.DONE,
            story_plan={"cover_face_required": True, "cover_people_candidates": [primary],
                        "cover_primary_person": primary, "cover_face_resolution_status": "RESOLVED"},
        )

        self.assertTrue(bridge._project_story_plan_face_resolution(settings, title, job))
        self.assertTrue(bridge._sync_scenario_to_covers(settings, 0, title, job))
        resolved = bridge._resolve_cover_portrait(settings.cover_queue[0], settings, face_mode="auto", allow_manual_reference=False)

        self.assertEqual(resolved["portrait_subject"], "Марек Новак")
        self.assertEqual(resolved["portrait_source"], "story-planner")
        self.assertEqual(settings.cover_queue[0]["cover_primary_person"]["name"], "Марек Новак")

    def test_org_or_place_never_become_primary_portrait_and_no_subject_needs_review(self):
        from scriptor import bridge

        for item in (
            {"title": "Европейский Союз обсуждает санкции", "entities": [{"name": "Европейский Союз", "type": "organization"}]},
            {"title": "Митинг в Киеве", "primary_entities": [{"name": "Киев", "type": "place"}]},
        ):
            with self.subTest(title=item["title"]):
                item.update(cover_face_required=True, cover_face_resolution_status="NEEDS_REVIEW")
                resolved = bridge._resolve_cover_portrait(item, Settings(), face_mode="auto", allow_manual_reference=False)
                self.assertEqual(resolved["portrait_subject"], "")
                self.assertEqual(item["cover_face_resolution_status"], "NEEDS_REVIEW")

    def test_every_unresolved_item_stops_before_fastgen_not_only_political_items(self):
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "production_item_id": "production:unresolved", "title": "Городской транспорт меняет маршрут",
            "image_prompt": "Городская сцена", "status": "Ожидает", "cover_face_required": True,
            "cover_face_resolution_status": "NEEDS_REVIEW",
        }]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.FastGenPool, "generate_media") as create:
            bridge.generate_covers({"indices": [0], "productionItemIds": ["production:unresolved"],
                                    "_parallel_cover_worker": True, "buildMode": "fastgen-full", "forceRegenerate": True})

        create.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["status"], "Нужно определить лицо для обложки")
    def test_cover_text_generation_projects_a_current_context_row_before_provider_call(self):
        """A durable current scenario must not need a prior manual Covers transfer."""
        from scriptor import bridge

        title = "Переговоры о новом соглашении"
        settings = Settings(
            idea_production_items=[{"id": "production:current", "title": title}],
            idea_scenario_context={title: {"id": "production:current", "title": title, "script": "Контекст."}},
            cover_queue=[],
        )
        calls: list[str] = []

        async def generated(_pool, kind, *_args, **_kwargs):
            calls.append(kind)
            return ("ГЛАВНЫЙ ЗАГОЛОВОК" if kind == "headline" else "Вторая строка",
                    {"semantic_slots": ["subject"], "valid": True}, [{"attempt": 1}])

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "load_session", return_value=([], [])), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "_save_cover_text_progress"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=SimpleNamespace()), \
             patch.object(bridge, "_generate_cover_word_v2", side_effect=generated):
            bridge.generate_cover_texts({"provider": "agent"})

        self.assertEqual(calls, ["headline", "subheadline"])
        self.assertEqual(settings.cover_queue[0]["production_item_id"], "production:current")

    def test_portrait_resolver_uses_an_arbitrary_explicit_person_from_script_without_country_mapping(self):
        from scriptor import bridge

        item = {
            "title": "Парламент обсуждает новое соглашение",
            "script": "Президент Лидии Марек Новак выступил перед парламентом и ответил на вопросы.",
        }

        resolved = bridge._resolve_cover_portrait(item, Settings(), face_mode="auto", allow_manual_reference=False)

        self.assertEqual(resolved["portrait_subject"], "Марек Новак")
        self.assertIn(resolved["portrait_side"], {"LEFT", "RIGHT"})
        self.assertNotEqual(resolved["portrait_source"], "none")

    def test_portrait_resolver_accepts_an_arbitrary_typed_person_entity_from_current_context(self):
        from scriptor import bridge

        item = {"title": "Переговоры о торговле", "entities": [{"name": "Amina Diallo", "type": "person"}]}
        resolved = bridge._resolve_cover_portrait(item, Settings(), face_mode="auto", allow_manual_reference=False)

        self.assertEqual(resolved["portrait_subject"], "Amina Diallo")
        self.assertEqual(resolved["portrait_source"], "structured-entities")

    def test_portrait_resolver_never_treats_typed_organisation_as_a_person(self):
        from scriptor import bridge

        for name in ("Европейский Союз", "Белый Дом"):
            with self.subTest(name=name):
                item = {"title": "Переговоры о торговле", "entities": [{"name": name, "type": "organization"}]}
                resolved = bridge._resolve_cover_portrait(item, Settings(), face_mode="auto", allow_manual_reference=False)

                self.assertEqual(resolved["portrait_subject"], "")
                self.assertEqual(resolved["portrait_source"], "none")

    def test_named_political_subject_without_legacy_marker_stops_before_fastgen(self):
        """Political/public-figure detection cannot depend on a marker dictionary."""
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "production_item_id": "production:tariffs", "title": "Трамп повысил тарифы для Китая",
            "image_prompt": "Торговая сцена", "status": "Ожидает",
        }]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.FastGenPool, "generate_media") as create:
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:tariffs"],
                "_parallel_cover_worker": True, "buildMode": "fastgen-full", "forceRegenerate": True,
            })

        create.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["status"], "Нужно определить политического субъекта")

    def test_political_topic_without_explicit_person_stays_recoverable_before_provider_call(self):
        """Generic politics cannot silently reach FastGen with an empty portrait subject."""
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "production_item_id": "production:politics", "title": "Парламент обсуждает санкции",
            "image_prompt": "Парламентская сцена", "status": "Ожидает",
        }]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.FastGenPool, "generate_media") as create:
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:politics"],
                "_parallel_cover_worker": True, "buildMode": "fastgen-full", "forceRegenerate": True,
            })

        create.assert_not_called()
        row = settings.cover_queue[0]
        self.assertEqual(row["portrait_source"], "none")
        self.assertEqual(row["status"], "Нужно определить политического субъекта")
        self.assertIn("явно указан", row["error"])

    def test_accepted_generation_retry_checks_existing_generation_without_create(self):
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_queue=[{
            "production_item_id": "production:recovery", "title": "Тема", "image_prompt": "scene",
            "status": "Требуется восстановление FastGen", "accepted_generation_id": "gen-existing",
            "render_profile": {"build_mode": "fastgen-full", "face_mode": "auto", "text_mode": "fastgen",
                               "local_face_only": False, "operation": "nano_banana_pro_image_generate"},
        }])
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        pool = SimpleNamespace(recover_generation=lambda *_args, **_kwargs: {"status": "processing", "error": ""})

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "FastGenPool", return_value=pool), \
             patch.object(bridge, "generate_covers") as create:
            bridge.retry_cover_generation({"indices": [0], "productionItemIds": ["production:recovery"]})

        create.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["provider_generation_id"], "gen-existing")

    def test_accepted_generation_recovery_materializes_success_and_records_terminal_failure_per_item(self):
        """One stale provider job must not prevent another accepted job from recovering."""
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_queue=[
            {
                "production_item_id": "production:failed", "title": "Failed", "image_prompt": "scene",
                "accepted_generation_id": "gen-failed", "status": "Требуется восстановление FastGen",
            },
            {
                "production_item_id": "production:done", "title": "Done", "image_prompt": "scene",
                "accepted_generation_id": "gen-done", "status": "Требуется восстановление FastGen",
            },
        ])
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        pool = SimpleNamespace(recover_generation=lambda generation_id, *_args: (
            {"status": "failed", "error": "Generation failed, please try again later"}
            if generation_id == "gen-failed" else {"status": "succeeded", "paths": [Path("recovered.png")]}
        ))
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "FastGenPool", return_value=pool):
            bridge.recover_cover_generation({
                "indices": [0, 1], "productionItemIds": ["production:failed", "production:done"],
            })

        failed, done = settings.cover_queue
        self.assertEqual(failed["provider_generation_id"], "gen-failed")
        self.assertEqual(failed["provider_generation_status"], "failed")
        self.assertIn("Generation failed", failed["provider_generation_error"])
        self.assertEqual(failed["status"], "Требуется создать заново FastGen")
        self.assertIn("recovery_checked_at", failed)
        self.assertEqual(done["status"], "Готово")
        self.assertEqual(done["paths"], ["recovered.png"])
        self.assertNotIn("accepted_generation_id", done)

    def test_recovery_transport_error_is_terminal_for_one_row_but_other_rows_continue(self):
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_queue=[
            {"production_item_id": "production:broken", "title": "Broken", "image_prompt": "scene", "accepted_generation_id": "gen-broken"},
            {"production_item_id": "production:processing", "title": "Processing", "image_prompt": "scene", "accepted_generation_id": "gen-processing"},
        ])
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]

        def recover(generation_id, *_args):
            if generation_id == "gen-broken":
                raise FastGenError("FastGen API (404): generation expired", 404)
            return {"status": "processing", "error": ""}

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "FastGenPool", return_value=SimpleNamespace(recover_generation=recover)):
            bridge.recover_cover_generation({
                "indices": [0, 1], "productionItemIds": ["production:broken", "production:processing"],
            })

        self.assertEqual(settings.cover_queue[0]["provider_generation_status"], "failed")
        self.assertEqual(settings.cover_queue[0]["status"], "Требуется создать заново FastGen")
        self.assertEqual(settings.cover_queue[1]["provider_generation_status"], "processing")
        self.assertEqual(settings.cover_queue[1]["status"], "FastGen генерирует")

    def test_failed_recovery_requires_explicit_new_paid_retry(self):
        from scriptor import bridge

        settings = Settings(cover_output_folder=".", cover_queue=[{
            "production_item_id": "production:failed", "title": "Тема", "image_prompt": "scene",
            "status": "Требуется создать заново FastGen", "accepted_generation_id": "gen-failed",
            "provider_generation_status": "failed",
            "render_profile": {"build_mode": "fastgen-full", "face_mode": "auto", "text_mode": "fastgen",
                               "local_face_only": False, "operation": "nano_banana_pro_image_generate"},
        }])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "regenerate_covers", return_value={}) as paid_create:
            bridge.retry_cover_generation_new_paid({
                "indices": [0], "productionItemIds": ["production:failed"],
            })

        self.assertNotIn("accepted_generation_id", settings.cover_queue[0])
        paid_create.assert_called_once()

    def test_fastgen_pool_skips_expired_license_and_uses_next_active_key(self):
        """One expired FastGen key must not block another active key."""
        from scriptor.covers import FastGenPool

        keys = [FastGenKey(label="expired", secret="expired"), FastGenKey(label="active", secret="active")]
        calls = []

        class FakeClient:
            def __init__(self, key):
                self.key = key

            def generate_media(self, *args, **kwargs):
                calls.append(self.key)
                if self.key == "expired":
                    raise FastGenError("FastGen API (403): License expired", 403)
                return [Path("D:/generated.png")]

        with patch("scriptor.covers.FastGenClient", FakeClient):
            generated = FastGenPool(keys).generate_media("prompt", Path("D:/out"), "topic", "flower_image_generate")

        self.assertEqual(generated, [Path("D:/generated.png")])
        self.assertEqual(calls, ["expired", "active"])

    def test_cover_worker_pool_runs_up_to_ten_topics_concurrently(self):
        """A slow FastGen request must not serialize the whole cover batch."""
        from scriptor.bridge import _run_parallel_cover_workers

        lock = threading.Lock()
        active = maximum = 0

        def work(index: int) -> int:
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return index

        result = _run_parallel_cover_workers(list(range(12)), work)
        self.assertEqual(result, list(range(12)))
        self.assertEqual(maximum, 10)

    def test_gallery_file_state_distinguishes_ready_missing_and_invalid_without_mutating_paths(self):
        from PIL import Image

        from scriptor.bridge import cover_file_state

        with TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / "готовая.png"
            invalid = root / "повреждённая.png"
            missing = root / "нет-файла.png"
            Image.new("RGB", (16, 9), "red").save(ready)
            invalid.write_text("это не изображение", encoding="utf-8")

            self.assertEqual(cover_file_state(str(ready))["state"], "ready")
            self.assertEqual(cover_file_state(str(missing))["state"], "missing")
            self.assertEqual(cover_file_state(str(invalid))["state"], "invalid")
            self.assertEqual(str(missing), cover_file_state(str(missing))["path"])

    def test_gallery_paths_preserve_all_persisted_paths_and_report_each_file_state(self):
        from scriptor.bridge import cover_gallery_paths

        with TemporaryDirectory() as directory:
            root = Path(directory)
            ready = root / "готовая.png"
            ready.write_bytes(b"not needed for state stub")
            missing = root / "нет-файла.png"
            with patch("scriptor.bridge.cover_file_state", side_effect=lambda path, **_kwargs: {"path": path, "state": "ready" if path == str(ready) else "missing"}):
                records = cover_gallery_paths({"paths": [str(ready), str(missing)]})

        self.assertEqual(records, [
            {"path": str(ready), "state": "ready"},
            {"path": str(missing), "state": "missing"},
        ])

    def test_reconciliation_restores_a_valid_file_without_regeneration(self):
        from PIL import Image

        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "001 — Тестовая тема — промпт 01.png"
            Image.new("RGB", (32, 18), "blue").save(image)
            settings = Settings(cover_output_folder=str(root))
            settings.cover_queue = [{"title": "Тестовая тема", "status": "Ошибка FastGen", "paths": []}]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.reconcile_cover_gallery()
            row = settings.cover_queue[0]
            self.assertEqual(row["status"], "Готово")
            self.assertEqual(row["selected_path"], str(image))
            self.assertEqual(result["operationResult"]["health"]["missing"], 0)

    def test_valid_existing_cover_is_skipped_by_normal_batch_generation(self):
        from PIL import Image

        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "ready.png"
            Image.new("RGB", (32, 18), "green").save(image)
            settings = Settings(cover_output_folder=str(root), cover_auto_overlay_text=False)
            settings.cover_queue = [{"title": "Готовая тема", "status": "Готово", "paths": [str(image)]}]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media") as generate:
                bridge.generate_covers({})
            generate.assert_not_called()

    def test_explicit_generation_resumes_a_paused_queue_and_sends_fastgen_request(self):
        """A deliberate Create Covers click must not silently loop over paused rows."""
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(
                cover_output_folder=directory,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_generation_paused=True,
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.cover_queue = [{"title": "Ормуз", "image_prompt": "тестовая сцена"}]
            def render(_prompt, output, *_args, **_kwargs):
                generated = output / "generated.png"
                generated.write_bytes(b"generated")
                return [generated]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge._save_cover_state"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render) as render:
                bridge.generate_covers({"indices": [0], "resumeGeneration": True})

        self.assertFalse(settings.cover_generation_paused)
        render.assert_called_once()
        self.assertEqual(settings.cover_queue[0]["status"], "Готово")

    def test_batch_generation_dispatches_topics_to_the_parallel_worker_pool(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_queue = [
            {"title": "Первая тема", "image_prompt": "scene one"},
            {"title": "Вторая тема", "image_prompt": "scene two"},
        ]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge._hydrate_cover_library"), \
                patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                patch("scriptor.bridge._release_cover_generation_lock"), \
                patch("scriptor.bridge.snapshot", return_value={}), \
                patch("scriptor.bridge._run_parallel_cover_workers", return_value=[]) as workers:
            bridge.generate_covers({})
        self.assertEqual(workers.call_args.args[0], [0, 1])

    def test_prompt_writer_uses_universal_v2_core_not_saved_legacy_preprompt(self):
        """A disabled custom template must never leak the old prompt stack into V2."""
        from scriptor import bridge

        settings = Settings(
            cover_use_custom_prompt=False,
            cover_prompt_template=(
                "Visual-only 16:9 YouTube news thumbnail for {title}. "
                "legacy cinematic panoramic background"
            ),
        )
        prompt = bridge._cover_instruction({
            "title": "Трамп сделал заявление по поставкам нефти",
            "script": "Трамп говорит журналистам о поставках нефти.",
            "face_reference_label": "Donald Trump",
            "main_consequence": "риск перебоев на рынке топлива",
        }, 0, settings)

        self.assertIn("semantic scene descriptions", prompt)
        self.assertIn("конкретное действие", prompt)
        self.assertIn("визуальное доказательство", prompt)
        self.assertIn("профессиональный арт-директор YouTube-обложек", prompt)
        self.assertIn("заметно отличаться композицией", prompt)
        self.assertIn("только когда это подтверждено темой или сценарием", prompt)
        self.assertIn("Final Prompt Builder", prompt)
        self.assertNotIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", prompt)
        self.assertNotIn("CLICKABILITY = HIGH.", prompt)
        self.assertNotIn("legacy cinematic panoramic background", prompt)
        self.assertNotIn("breaking-news", prompt.casefold())

    def test_fastgen_payload_keeps_universal_v2_rules_for_existing_scene_prompt(self):
        """The provider receives V2 even if an old stored scene prompt is rendered."""
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_auto_overlay_text=False)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.cover_queue = [{
                "title": "Трамп сделал заявление по поставкам нефти",
                "image_prompt": "Photorealistic documentary news photograph. Trump near an oil tanker.",
                "face_reference_label": "Donald Trump",
            }]
            payloads = []
            def render(prompt, output, *_args, **_kwargs):
                payloads.append(prompt)
                generated = output / "generated.png"
                generated.write_bytes(b"generated")
                return [generated]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge._save_cover_state"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render):
                bridge.generate_covers({"indices": [0], "textMode": "fastgen"})

        self.assertEqual(len(payloads), 1)
        self.assertIn("CLICKABILITY = HIGH.", payloads[0])
        self.assertIn("ACTION = HIGH.", payloads[0])
        self.assertIn("straight vivid red frame", payloads[0])
        self.assertNotIn("breaking-news", payloads[0].casefold())

    def test_prompt_has_single_style_block(self):
        """The provider contract contains the V2 style source exactly once."""
        from scriptor import bridge

        prompt = bridge._normalize_cover_photo_prompt(
            "Photorealistic editorial news image. CLICKABILITY = HIGH. "
            "NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2. "
            "SCENE DETAILS: oil tankers near Hormuz.",
            {"title": "Ормуз на грани! Иран давит на танкеры!"},
        )

        self.assertEqual(prompt.count("CORE STYLE:"), 1)
        self.assertEqual(prompt.count("CLICKABILITY = HIGH."), 1)
        self.assertEqual(prompt.count("PHOTOREALISM = MAXIMUM."), 1)

    def test_prompt_has_single_headline_block(self):
        """Headline instructions are owned by one final block, never the scene."""
        from scriptor import bridge

        prompt = bridge._normalize_cover_photo_prompt(
            "Oil tanker scene. HEADLINE: ОРМУЗ НА ГРАНИ. Render this exact headline.",
            {
                "title": "Ормуз на грани! Иран давит на танкеры!",
                "cover_headline": "ОРМУЗ НА ГРАНИ",
                "cover_subheadline": "ТАНКЕРЫ ПОД ДАВЛЕНИЕМ",
            },
        )

        self.assertEqual(prompt.count("\nHEADLINE:\n"), 1)
        self.assertEqual(prompt.count("ОРМУЗ НА ГРАНИ"), 1)

    def test_prompt_has_single_subheadline_block(self):
        """Subheadline instructions are owned by one final block, never the scene."""
        from scriptor import bridge

        prompt = bridge._normalize_cover_photo_prompt(
            "Tanker crisis. SUBHEADLINE: ТАНКЕРЫ ПОД ДАВЛЕНИЕМ. Render this exact subheadline.",
            {
                "title": "Ормуз на грани! Иран давит на танкеры!",
                "cover_headline": "ОРМУЗ НА ГРАНИ",
                "cover_subheadline": "ТАНКЕРЫ ПОД ДАВЛЕНИЕМ",
            },
        )

        self.assertEqual(prompt.count("\nSUBHEADLINE:\n"), 1)
        self.assertEqual(prompt.count("ТАНКЕРЫ ПОД ДАВЛЕНИЕМ"), 1)

    def test_prompt_has_no_legacy_tail(self):
        """A former generic safety tail cannot override a topic-specific scene."""
        from scriptor import bridge

        prompt = bridge._normalize_cover_photo_prompt(
            "Oil tankers near Strait of Hormuz. No explosions, no missiles, no drones, "
            "no military vehicles, no breaking-news template.",
            {"title": "Ормуз на грани! Иран давит на танкеры!"},
        )

        self.assertNotIn("No explosions, no missiles, no drones, no military vehicles", prompt)
        self.assertNotIn("breaking-news", prompt.casefold())

    def test_prompt_has_no_duplicate_sections(self):
        """Legacy prompt fragments become one structured final provider prompt."""
        from scriptor import bridge

        prompt = bridge._normalize_cover_photo_prompt(
            "NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2. PHOTOREALISM = MAXIMUM. "
            "SCENE DETAILS: Tankers face pressure. TYPOGRAPHY: large text. "
            "FINAL NEGATIVE RULES: no logos.",
            {"title": "Ормуз на грани! Иран давит на танкеры!"},
        )

        for section in (
            "CORE STYLE:", "STORY CONTEXT:", "MAIN SUBJECT:", "SELECTED PEOPLE:",
            "VISIBLE ACTION:", "VISUAL EVIDENCE:", "ENVIRONMENT:", "EMOTION:",
            "SELECTED COMPOSITION:", "IDENTITY / REFERENCES:", "HEADLINE:", "SUBHEADLINE:",
            "TYPOGRAPHY:", "RED EDGE ACCENTS:", "FINAL NEGATIVE RULES:",
        ):
            self.assertEqual(sum(line == section for line in prompt.splitlines()), 1, section)

    def test_final_prompt_extracts_only_story_context_from_prior_structured_v2_prompt(self):
        """A prior V2 prompt must never leak its CORE STYLE label into the next scene block."""
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        previous = (
            "CORE STYLE:\nNEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2. "
            "CLICKABILITY = HIGH.\n\n"
            "STORY CONTEXT:\nOil tankers move through a tense Strait of Hormuz shipping lane.\n\n"
            "MAIN SUBJECT:\nIranian pressure on oil shipping routes\n\n"
            "FINAL NEGATIVE RULES:\nNo logos."
        )

        prompt = build_final_provider_prompt(
            previous,
            {"title": "Ормуз на грани! Иран давит на танкеры!"},
        )

        scene = prompt.split("STORY CONTEXT:\n", 1)[1].split("\n\nMAIN SUBJECT:", 1)[0]
        self.assertEqual(scene, "Oil tankers move through a tense Strait of Hormuz shipping lane.")
        self.assertNotIn("CORE STYLE", scene)
        self.assertEqual(prompt.count("CORE STYLE:"), 1)

    def test_final_prompt_preserves_structured_scene_fields_over_generic_script_fallback(self):
        """The planner's concrete scene must win over incidental script keywords."""
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        scene = (
            "STORY CONTEXT:\nArmenia and Azerbaijan negotiate the Karabakh settlement under visible pressure.\n\n"
            "MAIN SUBJECT:\nArmenian and Azerbaijani negotiators at a Karabakh peace meeting\n\n"
            "VISIBLE ACTION:\nDelegations study a marked map and exchange documents across the table\n\n"
            "VISUAL EVIDENCE:\nKarabakh map, signed papers, microphones and both national flags\n\n"
            "ENVIRONMENT:\nReal diplomatic negotiation room in the South Caucasus\n\n"
            "EMOTION:\nTense, consequential bargaining"
        )

        prompt = build_final_provider_prompt(
            scene,
            {
                "title": "Армения и Азербайджан: почему буксует мирный процесс по Карабаху",
                "script": "В тексте вскользь упоминаются рынок, цены и поставки, но они не являются сценой.",
            },
        )

        self.assertIn("MAIN SUBJECT:\nArmenian and Azerbaijani negotiators at a Karabakh peace meeting", prompt)
        self.assertIn("VISIBLE ACTION:\nDelegations study a marked map and exchange documents across the table", prompt)
        self.assertIn("VISUAL EVIDENCE:\nKarabakh map, signed papers, microphones and both national flags", prompt)
        self.assertIn("ENVIRONMENT:\nReal diplomatic negotiation room in the South Caucasus", prompt)
        self.assertNotIn("Energy traders react to changing oil prices", prompt)


    def test_unstructured_fallback_is_universal_for_arbitrary_topics(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        titles = [
            "Красные овощи исчезают из магазинов после сбоя поставок",
            "Северный Маяк меняет правила доставки в регионы",
            "Учёные представили новый способ очистки воды",
            "Город меняет схему движения общественного транспорта",
        ]

        for title in titles:
            with self.subTest(title=title):
                prompt = build_final_provider_prompt("", {"title": title, "script": "Дополнительный контекст без готовой сцены."})
                self.assertIn(f"MAIN SUBJECT:\n{title}", prompt)
                self.assertIn("current topic/context", prompt)
                self.assertNotIn("Energy-market trading floor", prompt)
                self.assertNotIn("NATO summit", prompt)
                self.assertNotIn("Karabakh", prompt)


    def test_structured_scene_fields_are_authoritative_without_category_router(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        scene = (
            "STORY CONTEXT:\nCurrent synthetic story context.\n\n"
            "MAIN SUBJECT:\nResearchers testing a new water filter\n\n"
            "VISIBLE ACTION:\nEngineers inspect clear water leaving the prototype\n\n"
            "VISUAL EVIDENCE:\nTransparent pipes, filter cartridge and measurement instruments\n\n"
            "ENVIRONMENT:\nReal laboratory test bench\n\n"
            "EMOTION:\nFocused scientific urgency"
        )
        prompt = build_final_provider_prompt(
            scene,
            {"title": "Новый фильтр меняет очистку воды", "script": "В другом абзаце упомянуты цены на нефть."},
        )

        self.assertIn("Researchers testing a new water filter", prompt)
        self.assertIn("Engineers inspect clear water leaving the prototype", prompt)
        self.assertIn("Real laboratory test bench", prompt)
        self.assertNotIn("Energy-market trading floor", prompt)


    def test_provider_receives_arbitrary_current_scene_without_named_topic_router(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_variant_count=1)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.cover_queue = [{
                "title": "Новый фильтр меняет очистку воды",
                "topic": "Испытания новой технологии очистки",
                "production_item_id": "production:synthetic",
                "image_prompt_options": ["Engineers inspect a transparent water-filtration prototype in a real laboratory."],
                "cover_headline": "ВОДА СТАЛА ЧИЩЕ",
                "paths": [],
            }]
            payloads = []

            def render(prompt, output, *_args, **_kwargs):
                payloads.append(prompt)
                result = output / "synthetic.png"
                result.write_bytes(b"cover")
                return [result]

            with patch.object(bridge, "load_settings", return_value=settings),                  patch.object(bridge, "_hydrate_cover_library", return_value=False),                  patch.object(bridge, "_save_cover_state"),                  patch.object(bridge, "snapshot", return_value={}),                  patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:synthetic"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full",
                    "faceMode": "auto",
                    "textMode": "fastgen",
                })

        self.assertEqual(len(payloads), 1)
        self.assertIn("water-filtration prototype", payloads[0])
        self.assertIn("professional YouTube thumbnail designer and art director", payloads[0])

    def test_fastgen_payload_keeps_multiline_scene_slots_from_the_saved_prompt(self):
        """The bridge must not flatten the planner draft before the provider boundary."""
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_variant_count=1)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            scene = (
                "STORY CONTEXT:\nArmenia and Azerbaijan negotiate the Karabakh settlement.\n\n"
                "MAIN SUBJECT:\nArmenian and Azerbaijani negotiators at a Karabakh peace meeting\n\n"
                "VISIBLE ACTION:\nDelegations exchange documents over a Karabakh map\n\n"
                "VISUAL EVIDENCE:\nKarabakh map, signed papers and both national flags\n\n"
                "ENVIRONMENT:\nReal diplomatic negotiation room in the South Caucasus\n\n"
                "EMOTION:\nTense bargaining"
            )
            settings.cover_queue = [{
                "title": "Армения и Азербайджан: почему буксует мирный процесс по Карабаху",
                "script": "Есть случайное упоминание рынка и цен.",
                "production_item_id": "production:karabakh",
                "image_prompt_options": [scene],
                "cover_headline": "ПЕРЕГОВОРЫ БУКСУЮТ",
                "paths": [],
            }]
            payloads: list[str] = []

            def render(prompt, output, *_args, **_kwargs):
                payloads.append(prompt)
                result = output / "karabakh.png"
                result.write_bytes(b"cover")
                return [result]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0], "productionItemIds": ["production:karabakh"],
                    "_parallel_cover_worker": True, "buildMode": "fastgen-full",
                    "faceMode": "auto", "textMode": "fastgen",
                })

        self.assertEqual(len(payloads), 1)
        self.assertIn("VISIBLE ACTION:\nDelegations exchange documents over a Karabakh map", payloads[0])
        self.assertIn("ENVIRONMENT:\nReal diplomatic negotiation room in the South Caucasus", payloads[0])
        self.assertNotIn("Energy traders react to changing oil prices", payloads[0])


    def test_provider_payload_equals_final_prompt(self):
        """No adapter, retry or render guard may append or replace provider text."""
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_auto_overlay_text=False)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            scene = (
                "STORY CONTEXT:\nA new water filter is tested in a laboratory.\n\n"
                "MAIN SUBJECT:\nEngineers testing a transparent water-filtration prototype\n\n"
                "VISIBLE ACTION:\nEngineers inspect clear water leaving the prototype\n\n"
                "VISUAL EVIDENCE:\nTransparent pipes, filter cartridge and measuring instruments\n\n"
                "ENVIRONMENT:\nReal laboratory test bench\n\n"
                "EMOTION:\nFocused scientific urgency"
            )
            item = {
                "title": "Новая мембрана ускоряет очистку воды",
                "image_prompt": scene,
                "cover_headline": "ВОДА СТАЛА ЧИЩЕ",
                "cover_subheadline": "НОВАЯ МЕМБРАНА В ДЕЛЕ",
            }
            settings.cover_queue = [item]
            payloads = []

            def render(prompt, output, *_args, **_kwargs):
                payloads.append(prompt)
                generated = output / "generated.png"
                generated.write_bytes(b"generated")
                return [generated]

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge._save_cover_state"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render):
                bridge.generate_covers({"indices": [0], "textMode": "fastgen"})

            self.assertEqual(payloads, [settings.cover_queue[0]["final_provider_prompt"]])
            self.assertIn(
                "MAIN SUBJECT:\nEngineers testing a transparent water-filtration prototype",
                payloads[0],
            )
            self.assertIn(
                "VISIBLE ACTION:\nEngineers inspect clear water leaving the prototype",
                payloads[0],
            )
            self.assertIn("ENVIRONMENT:\nReal laboratory test bench", payloads[0])
            self.assertEqual(settings.cover_queue[0]["prompt_sources"], {
                "CORE STYLE": "Universal V2",
                "SCENE": "Topic Planner",
                "PEOPLE": "Reference Resolver",
                "TEXT": "Thumbnail Text Engine",
                "NEGATIVE": "Universal V2",
            })

    def test_exact_cover_text_is_delimited_without_adding_punctuation(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        prompt = build_final_provider_prompt(
            "Current editorial scene",
            {
                "title": "Current topic",
                "cover_headline": "ЭНЕРГИЯ ПОД КОНТРОЛЕМ",
                "cover_subheadline": "Форум обсуждает безопасность поставок",
            },
            text_mode="fastgen",
        )

        headline = prompt.split("HEADLINE:\n", 1)[1].split("\n\nSUBHEADLINE:", 1)[0]
        subheadline = prompt.split("SUBHEADLINE:\n", 1)[1].split("\n\nTYPOGRAPHY:", 1)[0]
        self.assertIn("<exact-text>ЭНЕРГИЯ ПОД КОНТРОЛЕМ</exact-text>", headline)
        self.assertIn("<exact-text>Форум обсуждает безопасность поставок</exact-text>", subheadline)
        self.assertNotIn("КОНТРОЛЕМ.", headline)
        self.assertNotIn("поставок.", subheadline)
        self.assertIn("Do not add punctuation", headline)
        self.assertIn("Do not add punctuation", subheadline)


    def test_final_prompt_keeps_current_scene_and_design_contract_without_category_substitution(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        scene = "Warehouse staff inspect damaged conveyor equipment after a logistics failure."
        prompt = build_final_provider_prompt(
            scene,
            {
                "title": "Склад остановил отправки после сбоя конвейера",
                "script": "В справочном абзаце упомянуты цены на топливо.",
                "cover_headline": "ОТПРАВКИ ВСТАЛИ",
            },
        )

        body = prompt.casefold()
        self.assertIn("warehouse staff inspect damaged conveyor equipment", body)
        self.assertNotIn("energy-market trading floor", body)
        self.assertIn("create a realistic, highly clickable, photorealistic youtube news thumbnail image", body)
        self.assertIn("professional youtube thumbnail designer and art director", body)
        self.assertIn("straight vivid red frame", body)
        self.assertIn("yellow or light lettering on a red panel", body)

    def test_final_fastgen_prompt_enforces_square_frame_and_palette_policy(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        fixed = build_final_provider_prompt(
            "A real editorial negotiation scene",
            {"title": "Трамп и Зеленский обсуждают переговоры", "cover_headline": "ДАВЛЕНИЕ РАСТЁТ"},
            allow_varied_text_palette=False,
        )
        varied = build_final_provider_prompt(
            "A real editorial negotiation scene",
            {"title": "Трамп и Зеленский обсуждают переговоры", "cover_headline": "ДАВЛЕНИЕ РАСТЁТ"},
            allow_varied_text_palette=True,
        )

        for prompt in (fixed, varied):
            self.assertTrue(prompt.startswith(
                "CORE STYLE:\nCreate a realistic, highly clickable, photorealistic YouTube news thumbnail image. "
                "You are a professional YouTube thumbnail designer and art director."
            ))
            self.assertIn("professional YouTube thumbnail designer and art director", prompt)
            self.assertIn("straight vivid red frame", prompt)
            self.assertIn("square corners", prompt)
            self.assertIn("No circles, ovals, circular frames or rings", prompt)
            self.assertNotIn("curved-corner frame", prompt)
        self.assertIn("yellow or light lettering on a red panel", fixed.casefold())
        self.assertIn("choose a different contrasting text and panel colour pair", varied.casefold())


    def test_unstructured_scene_planner_remains_title_grounded_for_unseen_topics(self):
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        samples = (
            "Новый материал снижает шум поездов",
            "Система полива экономит воду в теплицах",
            "Портативный прибор ускоряет анализ крови",
            "Компания меняет логистику холодных продуктов",
        )
        forbidden = ("NATO summit", "Energy-market trading floor", "Karabakh", "Donald Trump", "Vladimir Putin")

        for title in samples:
            with self.subTest(title=title):
                prompt = build_final_provider_prompt("", {"title": title})
                self.assertIn(f"MAIN SUBJECT:\n{title}", prompt)
                self.assertTrue(all(term not in prompt for term in forbidden), prompt)

    def test_word_engine_v2_persists_validated_pairs_before_visual_prompt_generation(self):
        """The public UI commands use V2 structures, provider parsing and persistence end-to-end."""
        settings = Settings()
        settings.openai_api_keys = [OpenAIKey(label="test", secret="test")]
        settings.cover_queue = [
            {"title": "Трамп усиливает давление на поставки нефти", "script": "Трамп говорит журналистам, а танкеры ждут решения."},
            {"title": "Путин и Макрон обсуждают переговоры", "script": "Макрон требует гарантий, переговоры под давлением."},
            {"title": "Цены на нефть могут вырасти", "script": "Рынок ждёт дефицита после сокращения поставок."},
            {"title": "Порт закрыт из-за кризиса", "script": "Контейнеры застряли на терминале после закрытия порта."},
            {"title": "Поставки газа могут сократиться", "script": "Заводы сокращают выпуск на фоне риска дефицита."},
        ]
        transcript: list[str] = []

        async def generate(prompt, **_kwargs):
            transcript.append(prompt)
            title = prompt.split("ТЕМА: «", 1)[1].split("»", 1)[0]
            headline = {
                "Трамп усиливает давление на поставки нефти": "ТРАМП ДАВИТ",
                "Путин и Макрон обсуждают переговоры": "ПУТИН ДАВИТ",
                "Цены на нефть могут вырасти": "НЕФТЬ РВАНЁТ?",
                "Порт закрыт из-за кризиса": "ПОРТ ЗАКРЫТ",
                "Поставки газа могут сократиться": "ПОСТАВКИ ПОД РИСКОМ?",
            }
            subheadline = {
                "Трамп усиливает давление на поставки нефти": "Танкеры ждут решения",
                "Путин и Макрон обсуждают переговоры": "Макрон требует гарантий",
                "Цены на нефть могут вырасти": "Рынок ждёт дефицита",
                "Порт закрыт из-за кризиса": "Контейнеры застряли на терминале",
                "Поставки газа могут сократиться": "Заводы сокращают выпуск",
            }
            if '"headline"' in prompt:
                return json.dumps({"headline": headline[title]}, ensure_ascii=False)
            return json.dumps({"subheadline": subheadline[title]}, ensure_ascii=False)

        pool = SimpleNamespace(generate=generate)
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=pool):
            generate_cover_headlines({"provider": "openai", "useDefault": True})
            generate_cover_subheadlines({"provider": "openai", "useDefault": True})

        # A controlled repair is permitted by V2; the important contract is
        # that every item reaches persisted READY rather than aborting a batch.
        self.assertGreaterEqual(len(transcript), 10)
        self.assertLessEqual(len(transcript), 15)
        self.assertTrue(all("ДОСТУПНЫЕ СЕМАНТИЧЕСКИЕ СЛОТЫ" in prompt for prompt in transcript))
        self.assertEqual(
            [{"status": row["headline_status"], "error": row.get("headline_error", "")} for row in settings.cover_queue],
            [{"status": "READY", "error": ""}] * 5,
        )
        self.assertTrue(all(row["subheadline_status"] == "READY" for row in settings.cover_queue))
        self.assertTrue(all(len(row["cover_headline"].split()) <= 5 for row in settings.cover_queue))
        self.assertTrue(all(3 <= len(row["cover_subheadline"].split()) <= 7 for row in settings.cover_queue))
        self.assertTrue(all(not _cover_lines_repeat_meaningful_words(row["cover_headline"], row["cover_subheadline"])
                            for row in settings.cover_queue))
        self.assertTrue(all(row["headline_editorial_evaluation"]["naturalness_pass"]
                            and row["headline_selection_evidence"]["factual_pass"]
                            for row in settings.cover_queue))

    def test_word_engine_repairs_an_overlong_headline_instead_of_silently_truncating_it(self):
        """A valid READY line must be authored, not the first three words of a bad response."""
        from scriptor import bridge

        item = {"title": "Порт закрыт из-за кризиса", "script": "Контейнеры застряли на терминале."}
        calls: list[str] = []

        async def generate(prompt, **_kwargs):
            calls.append(prompt)
            return json.dumps({
                "headline": "ПОРТ ЗАКРЫТ" if len(calls) > 1 else "ПОРТ ЗАКРЫТ ПРЯМО СЕЙЧАС ВЕСЬ ДЕНЬ"
            }, ensure_ascii=False)

        value, validation, attempts = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", bridge._cover_word_structure_pair(item),
        ))
        self.assertEqual(value, "ПОРТ ЗАКРЫТ")
        self.assertTrue(validation["valid"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(attempts[0]["validation"]["reason_code"], "TOO_MANY_WORDS")

    def test_five_topic_visual_workflow_passes_approved_words_into_fastgen_v2_payloads(self):
        """Controlled provider-boundary smoke test; it never touches the production queue."""
        settings = Settings(cover_prompt_variant_count=1, cover_variant_count=1, cover_auto_overlay_text=False)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        rows = [
            ("Трамп усиливает давление на поставки нефти", "ТРАМП ДАВИТ", "Танкеры ждут решения", "Дональд Трамп"),
            ("Путин и Макрон обсуждают переговоры", "ПУТИН ДАВИТ", "Макрон требует гарантий", "Владимир Путин"),
            ("Цены на нефть могут вырасти", "НЕФТЬ РВАНЁТ?", "Рынок ждёт дефицита", ""),
            ("Порт закрыт из-за кризиса", "ПОРТ ЗАКРЫТ", "Контейнеры застряли на терминале", ""),
            ("Поставки газа могут сократиться", "ПОСТАВКИ ПОД РИСКОМ?", "Заводы сокращают выпуск", ""),
        ]
        settings.cover_queue = [
            {"title": title, "script": f"Контекст: {title}", "cover_headline": headline,
             "cover_subheadline": subheadline, "selected_people": [person] if person else [],
             "headline_status": "READY", "subheadline_status": "READY"}
            for title, headline, subheadline, person in rows
        ]
        payloads: list[str] = []

        async def prompt_writer(prompt, **_kwargs):
            title = prompt.split("ТЕМА: ", 1)[1].split("\n", 1)[0]
            return json.dumps({"prompts": [f"Real-world press scene for {title} with visible action and concrete evidence"]}, ensure_ascii=False)

        def fastgen(prompt, *_args, **_kwargs):
            payloads.append(prompt)
            return [Path(f"cover-{len(payloads)}.png")]

        pool = SimpleNamespace(generate=prompt_writer)
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=pool), \
             patch("scriptor.bridge.FastGenPool.generate_media", side_effect=fastgen):
            generate_cover_prompts({"provider": "agent"})
            generate_covers({"indices": list(range(5)), "textMode": "fastgen"})

        self.assertEqual(len(payloads), 5)
        for _title, headline, subheadline, _person in rows:
            matching = [payload for payload in payloads if f"HEADLINE:\n<exact-text>{headline}</exact-text>" in payload]
            self.assertEqual(len(matching), 1)
            payload = matching[0]
            self.assertEqual(payload.count("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2"), 1)
            self.assertIn("CLICKABILITY = HIGH.", payload)
            self.assertIn("PHOTOREALISM = MAXIMUM.", payload)
            self.assertIn("SELECTED COMPOSITION:\n", payload)
            self.assertIn("straight vivid red frame", payload)
            self.assertIn(f"HEADLINE:\n<exact-text>{headline}</exact-text>", payload)
            self.assertIn(f"SUBHEADLINE:\n<exact-text>{subheadline}</exact-text>", payload)
            self.assertNotIn("breaking-news", payload.casefold())


class CoverRateLimitTests(unittest.TestCase):
    def test_provider_queue_resumes_at_one_minute_after_the_next_hour(self):
        now = datetime(2026, 9, 7, 12, 59, 30, tzinfo=timezone.utc)
        self.assertEqual(next_fastgen_resume_at(now), datetime(2026, 9, 7, 13, 1, tzinfo=timezone.utc))

    def test_waits_until_the_oldest_completed_batch_leaves_the_hour_window(self):
        now = datetime(2026, 8, 31, 12, 30, tzinfo=timezone.utc)
        decision = cover_rate_limit_decision(
            [{"at": (now - timedelta(minutes=50)).isoformat(), "count": 60},
             {"at": (now - timedelta(minutes=20)).isoformat(), "count": 40}],
            requested=1,
            limit_per_hour=100,
            now=now,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.used, 100)
        self.assertEqual(decision.resume_at, now + timedelta(minutes=10))

    def test_cover_generation_leaves_the_unstarted_item_waiting_for_the_hourly_limit(self):
        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_rate_limit_per_hour = 1
        settings.cover_rate_usage_events = [{"at": datetime.now(timezone.utc).isoformat(), "count": 1}]
        settings.cover_queue = [{"title": "Ормуз", "image_prompt": "scene"}]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.FastGenPool.generate_media") as render:
            generate_covers({"indices": [0]})
        render.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["status"], "Ожидает лимит FastGen")
        self.assertTrue(settings.cover_queue[0]["rate_limit_wait_until"])


class FastGenClientTests(unittest.TestCase):
    def test_recovery_polls_an_accepted_generation_with_get_only(self):
        client = FastGenClient("test-key")
        with TemporaryDirectory() as directory, \
             patch.object(client, "_json", return_value={"status": "succeeded", "results": ["image"]}) as request, \
             patch.object(client, "_save_result", return_value=Path(directory) / "recovered.png"):
            recovered = client.recover_generation("accepted-123", Path(directory), "cover")

        self.assertEqual(recovered["status"], "succeeded")
        self.assertEqual(recovered["paths"], [Path(directory) / "recovered.png"])
        request.assert_called_once_with("GET", "/api/v6/generations/accepted-123")

    def test_same_reference_upload_id_is_reused_across_create_retries(self):
        with TemporaryDirectory() as directory:
            reference = Path(directory) / "face.png"
            reference.write_bytes(b"same-reference")
            client = FastGenClient("test-key")
            with patch.object(client, "_upload_reference", return_value="stored-reference-1") as upload:
                first = client.upload_reference(reference)
                second = client.upload_reference(reference)

        self.assertEqual(first, "stored-reference-1")
        self.assertEqual(second, "stored-reference-1")
        upload.assert_called_once()

    def test_reference_files_become_provider_storage_ids_in_generation_payload(self):
        client = FastGenClient("test-key")
        capability = {
            "inputs": {"min": 1, "max": 2},
            "outputs": {"max_items": 1},
            "options": {"aspect_ratio": {"enum": ["16:9"]}},
        }
        requests = []

        def wait(payload, _folder, _title, _start_index, *_args):
            requests.append(dict(payload))
            return [Path("provider-final.png")]

        with patch.object(client, "_operation_capability", return_value=capability), \
             patch.object(client, "upload_reference", side_effect=["storage-base", "storage-face"]) as upload, \
             patch.object(client, "_wait_for_generation", side_effect=wait):
            paths = client.generate_media(
                "exact composition prompt",
                Path("out"),
                "title",
                "reference_image_edit",
                references=[Path("base.png"), Path("face.png")],
            )

        self.assertEqual(paths, [Path("provider-final.png")])
        self.assertEqual([call.args[0] for call in upload.call_args_list], [Path("base.png"), Path("face.png")])
        self.assertEqual(requests[0]["inputs"], ["storage-base", "storage-face"])
        self.assertEqual(requests[0]["prompt"], "exact composition prompt")

    def test_error_after_generation_acceptance_carries_remote_id(self):
        client = FastGenClient("test-key")
        with TemporaryDirectory() as directory, \
             patch.object(client, "_json", side_effect=[
                 {"id": "accepted-generation-1"},
                 FastGenError("polling interrupted"),
             ]), self.assertRaises(FastGenError) as raised:
            client._wait_for_generation(
                {"operation": "test", "prompt": "same"}, Path(directory), "cover", 1,
            )

        self.assertTrue(raised.exception.generation_accepted)
        self.assertEqual(raised.exception.generation_id, "accepted-generation-1")

    def test_selected_fastgen_keys_filter_the_generation_pool(self):
        from scriptor.bridge import _selected_fastgen_keys
        settings = Settings(cover_api_keys=[FastGenKey("A", "a"), FastGenKey("B", "b")])
        settings.cover_selected_key_labels = ["B"]
        self.assertEqual([key.label for key in _selected_fastgen_keys(settings)], ["B"])

    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            FastGenClient("")

    def test_rotates_only_when_credits_are_exhausted(self):
        keys = [SimpleNamespace(label="Первый", secret="one", active=True),
                SimpleNamespace(label="Второй", secret="two", active=True)]
        pool = FastGenPool(keys)

        def generate(client, *args, **kwargs):
            if client.api_key == "one":
                raise FastGenError("insufficient credits", 402)
            return "ready.png"

        with patch.object(FastGenClient, "generate_cover", generate):
            self.assertEqual(pool.generate_cover("p", "folder", "title"), "ready.png")
            self.assertIn(0, pool.exhausted)

    def test_nano_banana_payload_omits_unsupported_count_and_empty_inputs(self):
        client = FastGenClient("test")
        capability = {
            "inputs": {"min": 0, "max": 10},
            "outputs": {"max_items": 1},
            "options": {"aspect_ratio": {"enum": ["16:9", "1:1"]}, "seed": {}},
        }
        payload, supports_count, max_items = client._generation_payload(
            "nano_banana_2_image_generate", "prompt", "16:9", [], None, None, None, False, capability,
        )
        self.assertEqual(payload, {"operation": "nano_banana_2_image_generate", "prompt": "prompt", "aspect_ratio": "16:9"})
        self.assertFalse(supports_count)
        self.assertEqual(max_items, 1)

    def test_single_item_model_splits_requested_variants_into_safe_requests(self):
        client = FastGenClient("test")
        capability = {"inputs": {"min": 0, "max": 10}, "outputs": {"max_items": 1}, "options": {"aspect_ratio": {}}}
        requests = []

        def wait(payload, _folder, _title, start_index, *_args):
            requests.append((payload, start_index))
            return [Path(f"variant-{start_index}.png")]

        with patch.object(client, "_operation_capability", return_value=capability), \
             patch.object(client, "_wait_for_generation", side_effect=wait):
            paths = client.generate_media("prompt", Path("out"), "title", "nano_banana_2_image_generate", count=3)
        self.assertEqual([str(path) for path in paths], ["variant-1.png", "variant-2.png", "variant-3.png"])
        self.assertEqual([payload for payload, _index in requests], [
            {"operation": "nano_banana_2_image_generate", "prompt": "prompt", "aspect_ratio": "16:9"},
        ] * 3)

    def test_retries_only_the_missing_results_when_fastgen_returns_a_short_batch(self):
        """A provider that silently returns one image for count=2 must not make the topic look complete."""
        client = FastGenClient("test")
        capability = {"inputs": {"min": 0, "max": 10}, "outputs": {"max_items": 4},
                      "options": {"aspect_ratio": {}, "count": {}}}
        requests = []

        def wait(payload, _folder, _title, start_index, *_args):
            requests.append((dict(payload), start_index))
            return [Path(f"variant-{start_index}.png")]

        with patch.object(client, "_operation_capability", return_value=capability), \
             patch.object(client, "_wait_for_generation", side_effect=wait):
            paths = client.generate_media("prompt", Path("out"), "title", "flower_image_generate", count=2)
        self.assertEqual([str(path) for path in paths], ["variant-1.png", "variant-2.png"])
        self.assertEqual([payload["count"] for payload, _index in requests], [2, 1])

    def test_retries_without_count_when_unknown_live_schema_rejects_it(self):
        client = FastGenClient("test")
        requests = []

        def wait(payload, _folder, _title, start_index, *_args):
            requests.append(dict(payload))
            if "count" in payload:
                raise FastGenError("Model 'nano-banana-2' does not support option 'count'", 400)
            return [Path(f"variant-{start_index}.png")]

        with patch.object(client, "_operation_capability", return_value={}), \
             patch.object(client, "_wait_for_generation", side_effect=wait):
            paths = client.generate_media("prompt", Path("out"), "title", "nano_banana_2_image_generate", count=2)

        self.assertEqual([str(path) for path in paths], ["variant-1.png", "variant-2.png"])
        # Unknown live schemas intentionally use the safe one-image shape;
        # FastGen must not be probed with an invented `count` option.
        self.assertEqual(["count" in payload for payload in requests], [False, False])

    def test_upload_reference_sends_real_image_mime_type(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b'{"id":"reference-id"}'

        with TemporaryDirectory() as directory:
            source = Path(directory) / "portrait.png"
            source.write_bytes(b"png-bytes")
            with patch("scriptor.covers.urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(FastGenClient("key").upload_reference(source), "reference-id")
            request = urlopen.call_args.args[0]
            self.assertIn(b"Content-Type: image/png", request.data)
            self.assertEqual(reference_mime_type(source), "image/png")

    def test_upload_reference_rejects_unsupported_mime_before_network_request(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "portrait.tiff"
            source.write_bytes(b"not-needed")
            with self.assertRaises(FastGenError):
                FastGenClient("key").upload_reference(source)

    def test_upload_reference_prepares_temporary_copy_when_portrait_exceeds_fastgen_limit(self):
        """A large source portrait must remain untouched while FastGen gets a valid smaller copy."""
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b'{"id":"reference-id"}'

        from PIL import Image
        with TemporaryDirectory() as directory:
            source = Path(directory) / "portrait.bmp"
            Image.new("RGB", (1800, 1200), (32, 64, 96)).save(source)
            original_size = source.stat().st_size
            self.assertGreater(original_size, 5 * 1024 * 1024)
            with patch("scriptor.covers.urllib.request.urlopen", return_value=Response()) as urlopen:
                self.assertEqual(FastGenClient("key").upload_reference(source), "reference-id")
            self.assertEqual(source.stat().st_size, original_size)
            self.assertIn(b"Content-Type: image/webp", urlopen.call_args.args[0].data)


class CoverHeadlineGuardTests(unittest.TestCase):
    def test_editorial_quality_rejects_novel_awkward_phrase_outside_legacy_patterns(self):
        """A source anchor alone must not turn a nonsensical hook into READY."""
        from scriptor import bridge

        item = {"title": "Европа обсуждает поставки помидоров после нового решения"}

        self.assertNotIn("перекручивает помидоры", bridge._COVER_WORD_UNNATURAL_PATTERNS)

        validation = _validate_cover_word("headline", "Европа перекручивает помидоры", item)

        self.assertFalse(validation["valid"], validation)
        self.assertEqual(validation["reason_code"], "EDITORIAL_QUALITY_FAILED")
        self.assertFalse(validation["editorial_evaluation"]["semantic_coherence_pass"])

    def test_editorial_quality_does_not_reject_natural_contextual_word_by_legacy_substring(self):
        item = {"title": "Россия нагнетает давление в переговорах"}

        validation = _validate_cover_word("headline", "Россия нагнетает давление", item)

        self.assertTrue(validation["valid"], validation)
        self.assertTrue(validation["editorial_evaluation"]["naturalness_pass"])

    def test_editorial_evaluation_is_compact_and_structured(self):
        item = {"title": "Трамп повысил тарифы для Китая"}

        validation = _validate_cover_word("headline", "Трамп повысил тарифы", item)

        self.assertTrue(validation["valid"], validation)
        evidence = validation["editorial_evaluation"]
        self.assertEqual(set(evidence), {
            "naturalness_pass", "semantic_coherence_pass", "literal_clarity_pass", "cliche_penalty",
            "editorial_plausibility_pass", "specificity_score", "hook_score", "factual_pass",
            "grounding_pass", "duplicate_pass", "quality_reasons",
        })

    def test_editorial_quality_selects_strong_natural_candidate_from_safe_batch(self):
        from scriptor import bridge

        item = {"title": "Трамп повысил тарифы для Китая: торговый спор усилился"}

        async def generate(_prompt, **_kwargs):
            return json.dumps({"candidates": [
                "Трамп перекручивает тарифы", "Важные новости", "Трамп усилил торговый спор",
            ]}, ensure_ascii=False)

        value, validation, attempts = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", _cover_word_structure_pair(item),
        ))

        self.assertEqual(value, "Трамп усилил торговый спор")
        self.assertTrue(validation["editorial_evaluation"]["naturalness_pass"])
        self.assertFalse(attempts[0]["validation"]["valid"])
        self.assertFalse(attempts[1]["validation"]["valid"])

    def test_naturalness_gate_rejects_editorially_awkward_but_grounded_hooks(self):
        cases = (
            ("Европа поджимает помидоры", "Европа обсуждает поставки помидоров после нового решения"),
            ("Сделка трещит по швам", "Сделка по поставкам помидоров оказалась под угрозой"),
        )
        for value, title in cases:
            with self.subTest(value=value):
                item = {"title": title, "topic": title}
                validation = _validate_cover_word("headline", value, item)
                self.assertFalse(validation["valid"], validation)
                self.assertEqual(validation["reason_code"], "EDITORIAL_QUALITY_FAILED")

    def test_candidate_prompt_requests_multiple_editorial_options_not_a_hash_template(self):
        item = {"production_item_id": "production:tomatoes", "title": "Европа обсуждает поставки помидоров"}
        prompt = _cover_word_provider_prompt(
            "headline", "", item, _cover_word_structure_pair(item), tabloid_mode=True,
        )
        self.assertIn("4–6", prompt)
        self.assertIn("TABLOID", prompt)
        self.assertIn('"candidates"', prompt)
        self.assertIn("не является обязательным шаблоном", prompt)

    def test_candidate_pipeline_selects_natural_grounded_option_after_quality_gate(self):
        from scriptor import bridge

        item = {"title": "Европа меняет поставки помидоров после нового решения"}

        async def generate(_prompt, **_kwargs):
            return json.dumps({"candidates": [
                "Европа поджимает помидоры", "Европа меняет поставки",
            ]}, ensure_ascii=False)

        value, validation, attempts = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", _cover_word_structure_pair(item),
        ))
        self.assertEqual(value, "Европа меняет поставки")
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["candidate_count"], 2)
        self.assertEqual(attempts[0]["validation"]["reason_code"], "EDITORIAL_QUALITY_FAILED")

    def test_standard_and_tabloid_select_different_safe_editorial_strength(self):
        from scriptor import bridge

        item = {"title": "Трамп повысил тарифы для Китая: торговый спор усилился"}

        async def generate(_prompt, **_kwargs):
            return json.dumps({"candidates": [
                "Трамп повысил тарифы", "Трамп усилил торговый спор",
            ]}, ensure_ascii=False)

        standard, standard_evidence, _ = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", _cover_word_structure_pair(item),
            tabloid_mode=False,
        ))
        tabloid, tabloid_evidence, _ = asyncio.run(bridge._generate_cover_word_v2(
            SimpleNamespace(generate=generate), "headline", item, "", _cover_word_structure_pair(item),
            tabloid_mode=True,
        ))

        self.assertEqual(standard, "Трамп повысил тарифы")
        self.assertEqual(tabloid, "Трамп усилил торговый спор")
        self.assertLess(
            standard_evidence["editorial_evaluation"]["hook_score"],
            tabloid_evidence["editorial_evaluation"]["hook_score"],
        )

    def test_headline_is_limited_to_five_words(self):
        self.assertEqual(
            _clean_cover_headline("ОРМУЗ ПОД УГРОЗОЙ ПРЯМО СЕЙЧАС НОЧЬЮ"),
            "ОРМУЗ ПОД УГРОЗОЙ ПРЯМО СЕЙЧАС",
        )

    def test_rejects_an_unrelated_example_from_user_prompt(self):
        title = "Тегеран усиливает давление на Ормузский пролив"
        self.assertFalse(_cover_text_matches_topic("АЛИЕВ НА КОЛЕНЯХ", title))

    def test_accepts_phrase_with_actual_topic_anchor(self):
        title = "Тегеран усиливает давление на Ормузский пролив"
        self.assertTrue(_cover_text_matches_topic("ОРМУЗ ПОД УГРОЗОЙ", title))

    def test_rejects_repeated_meaningful_word_between_cover_lines(self):
        self.assertTrue(_cover_lines_repeat_meaningful_words(
            "ОРМУЗ В ОГНЕ", "Ормуз загнал нефтяников в панику"
        ))

    def test_rejects_word_forms_between_cover_lines(self):
        self.assertTrue(_cover_lines_repeat_meaningful_words(
            "НЕФТЬ НА ГРАНИ", "Нефтяников охватила паника"
        ))

    def test_allows_complementary_cover_lines(self):
        self.assertFalse(_cover_lines_repeat_meaningful_words(
            "ОРМУЗ В ОГНЕ", "Тегеран давит сильнее"
        ))

    def test_rejects_weak_headlines_that_drop_named_people_from_the_topic(self):
        item = {
            "title": "ТРАМП ДАВИТ НА ЗЕЛЕНСКОГО — переговоры по Украине меняют тон — Киеву ставят новые условия",
            "topic": "Трамп-Зеленский — давление и переговоры",
        }
        for weak in ("Новые условия", "Не уступает"):
            validation = _validate_cover_word("headline", weak, item)
            self.assertFalse(validation["valid"], weak)
            self.assertEqual(validation["reason_code"], "MISSING_NAMED_ANCHOR")

    def test_accepts_a_standalone_headline_with_a_named_topic_anchor(self):
        item = {
            "title": "ЗЕЛЕНСКИЙ НЕ УСТУПАЕТ ТРАМПУ — спор вокруг Украины обостряется — помощь США под вопросом",
            "topic": "Трамп-Зеленский — давление и переговоры",
        }
        validation = _validate_cover_word("headline", "Зеленский держит курс", item)
        self.assertTrue(validation["valid"], validation)

    def test_accepts_a_natural_headline_with_subject_action_and_object(self):
        item = {
            "title": "ТРАМП ДАВИТ НА ЗЕЛЕНСКОГО — переговоры по Украине меняют тон — Киеву ставят новые условия",
            "topic": "Трамп-Зеленский — давление и переговоры",
        }
        validation = _validate_cover_word("headline", "Трамп давит на Киев", item)
        self.assertTrue(validation["valid"], validation)

    def test_does_not_require_an_incidental_script_person_as_the_headline_anchor(self):
        item = {
            "title": "Поставки газа на рынок",
            "script": "Трамп обсудил поставки газа с чиновниками.",
        }
        validation = _validate_cover_word("headline", "Поставки под угрозой", item)
        self.assertTrue(validation["valid"], validation)

    def test_provider_prompt_for_named_topics_forbids_bare_actions_and_abstract_hooks(self):
        item = {
            "title": "ЗЕЛЕНСКИЙ НЕ УСТУПАЕТ ТРАМПУ — спор вокруг Украины обостряется — помощь США под вопросом",
            "topic": "Трамп-Зеленский — давление и переговоры",
        }
        prompt = _cover_word_provider_prompt(
            "headline", "", item, _cover_word_structure_pair(item),
        )
        self.assertIn("самодостаточным", prompt)
        self.assertIn("Не уступает", prompt)
        self.assertIn("Не усиливай исходное действие", prompt)

    def test_named_anchor_guard_covers_new_direction_entities_not_in_legacy_vocabulary(self):
        item = {
            "title": "Мирный процесс снова в центре внимания",
            "direction": "Армения-Азербайджан — мирный процесс и Карабах",
            "topic": "Армения-Азербайджан — мирный процесс и Карабах",
        }

        abstract = _validate_cover_word("headline", "Мирный процесс буксует", item)
        concrete = _validate_cover_word("headline", "Армения обсуждает мирный процесс", item)

        self.assertFalse(abstract["valid"], abstract)
        self.assertEqual(abstract["reason_code"], "MISSING_NAMED_ANCHOR")
        self.assertTrue(concrete["valid"], concrete)

    def test_named_anchor_guard_uses_structured_entities_even_when_they_are_lowercase(self):
        item = {
            "title": "Мирный процесс меняет повестку",
            "primary_entities": ["армении", "азербайджана"],
        }

        abstract = _validate_cover_word("headline", "Мирный процесс меняется", item)
        concrete = _validate_cover_word("headline", "Армения меняет подход", item)

        self.assertFalse(abstract["valid"], abstract)
        self.assertEqual(abstract["reason_code"], "MISSING_NAMED_ANCHOR")
        self.assertTrue(concrete["valid"], concrete)

    def test_named_anchor_guard_supports_arbitrary_structured_entity_without_vocabulary(self):
        item = {
            "title": "Компания меняет поставки после нового решения",
            "primary_entities": ["lumira"],
        }

        abstract = _validate_cover_word("headline", "Поставки меняют рынок", item)
        concrete = _validate_cover_word("headline", "Lumira меняет поставки", item)

        self.assertFalse(abstract["valid"], abstract)
        self.assertEqual(abstract["reason_code"], "MISSING_NAMED_ANCHOR")
        self.assertTrue(concrete["valid"], concrete)

    def test_foreign_entity_guard_rejects_arbitrary_new_name_not_in_source(self):
        item = {
            "title": "Компания Lumira меняет поставки",
            "primary_entities": ["lumira"],
        }

        validation = _validate_cover_word("headline", "Lumira и Norvel меняют поставки", item)

        self.assertFalse(validation["valid"], validation)
        self.assertEqual(validation["reason_code"], "FOREIGN_ENTITY")

    def test_cover_word_runtime_has_no_fixed_known_entity_vocabulary(self):
        from scriptor import bridge

        source = Path(bridge.__file__).read_text(encoding="utf-8")
        self.assertNotIn("_COVER_WORD_FOREIGN_ENTITIES", source)
        semantic = source.split("def _cover_word_semantic_plan", 1)[1].split(
            "def _cover_word_semantic_groups", 1
        )[0].casefold()
        for forbidden in ("трамп", "путин", "зеленск", "нато", "иран", "украин"):
            self.assertNotIn(forbidden, semantic)

    def test_headline_guard_rejects_stronger_challenge_or_ultimatum_than_the_source(self):
        item = {
            "title": "Зеленский не уступает Трампу",
            "topic": "Трамп-Зеленский — давление и переговоры",
        }

        for value in ("Зеленский бросил вызов", "Трамп выдвинул ультиматум"):
            with self.subTest(value=value):
                validation = _validate_cover_word("headline", value, item)
                self.assertFalse(validation["valid"], validation)
                self.assertEqual(validation["reason_code"], "CLAIM_STRENGTH_ERROR")

    def test_headline_guard_allows_strong_wording_when_the_source_contains_it(self):
        item = {
            "title": "Трамп выдвинул ультиматум Зеленскому",
            "topic": "Трамп-Зеленский — ультиматум на переговорах",
        }

        validation = _validate_cover_word("headline", "Трамп выдвинул ультиматум", item)

        self.assertTrue(validation["valid"], validation)

    def test_topic_gets_one_clear_pair_structure(self):
        headline, subheadline = _cover_text_structure("Тегеран усиливает давление на Ормузский пролив")
        self.assertTrue(headline)
        self.assertTrue(subheadline)
        self.assertNotEqual(headline, subheadline)

    def test_prompt_without_structure_keeps_topic_guard_but_removes_format_constraint(self):
        prompt = _cover_text_prompt(
            "headline", "Сделай жёстко", "Тегеран усиливает давление на Ормуз", "", use_structure=False,
        )
        self.assertIn("ЕДИНСТВЕННАЯ ТЕМА", prompt)
        self.assertNotIn("СТРУКТУРА ГЛАВНОЙ", prompt)

    def test_subheadline_prompt_can_disable_repeat_guard(self):
        prompt = _cover_text_prompt(
            "subheadline", "Сделай жёстко", "Тегеран усиливает давление на Ормуз", "", "ОРМУЗ В ОГНЕ",
            avoid_repeats=False,
        )
        self.assertNotIn("Нельзя повторять", prompt)
        self.assertIn("Вторая строка должна дополнять главную", prompt)


class CoverFaceLibraryTests(unittest.TestCase):
    def test_face_tree_matches_only_story_planner_primary_not_another_visual_person(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            primary = root / "Марек Новак" / "portrait.jpg"
            other = root / "Амина Диалло" / "portrait.jpg"
            primary.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            primary.write_bytes(b"primary")
            other.write_bytes(b"other")
            settings = Settings(cover_face_library_folder=str(root), cover_face_library_enabled=True)
            item = {
                "title": "Амина Диалло на встрече с Мареком Новаком",
                "cover_face_required": True,
                "cover_face_resolution_status": "RESOLVED",
                "cover_primary_person": {
                    "name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
                    "relation_to_story": "принял решение", "source": "story-planner", "confidence": 0.94,
                },
                "visual_reference_path": str(other),
            }

            resolved = bridge._resolve_cover_portrait(item, settings, face_mode="auto", allow_manual_reference=False)
            path, label, source = _match_cover_face_reference(item, settings)

        self.assertEqual(resolved["portrait_subject"], "Марек Новак")
        self.assertEqual(Path(path), primary)
        self.assertEqual(label, "Марек Новак")
        self.assertEqual(source, "auto")

    def test_missing_planner_person_png_keeps_same_subject_with_zero_reference(self):
        from scriptor import bridge

        item = {
            "title": "Марек Новак выступил", "cover_face_required": True,
            "cover_face_resolution_status": "RESOLVED",
            "cover_primary_person": {
                "name": "Марек Новак", "entity_type": "public_figure", "role_in_story": "президент",
                "relation_to_story": "выступил", "source": "story-planner", "confidence": 0.94,
            },
        }
        settings = Settings(cover_face_library_enabled=True, cover_face_library_folder="missing-face-tree")

        resolved = bridge._resolve_cover_portrait(item, settings, face_mode="auto", allow_manual_reference=False)
        match = _match_cover_face_reference(item, settings, prepared_only=True)

        self.assertEqual(resolved["portrait_subject"], "Марек Новак")
        self.assertEqual(match, ("", "", ""))
    def test_does_not_treat_a_dot_as_a_face_library(self):
        files, truncated = _cover_face_files(".")
        self.assertEqual(files, [])
        self.assertFalse(truncated)

    def test_matches_only_a_topic_relevant_named_portrait(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            portrait = folder / "Алиев" / "portrait.jpg"
            portrait.parent.mkdir()
            portrait.write_bytes(b"test")
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)
            path, label, source = _match_cover_face_reference({"title": "Алиев обсуждает мирный процесс"}, settings)
            self.assertEqual(Path(path), portrait)
            self.assertEqual(label, "Алиев")
            self.assertEqual(source, "auto")
            self.assertEqual(_match_cover_face_reference({"title": "Тегеран усиливает давление на Ормуз"}, settings), ("", "", ""))

    def test_prepared_only_auto_match_returns_prepared_png_even_when_background_flag_is_off(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "Лица"
            prepared_root = root / "Готовые PNG"
            source = sources / "Зеленский" / "portrait.jpg"
            prepared = prepared_root / "Зеленский" / "portrait.png"
            source.parent.mkdir(parents=True)
            prepared.parent.mkdir(parents=True)
            source.write_bytes(b"source-jpg")
            prepared.write_bytes(b"prepared-png")
            settings = Settings(
                cover_face_library_folder=str(sources),
                cover_face_prepared_folder=str(prepared_root),
                cover_face_library_enabled=True,
                cover_face_remove_background=False,
            )

            path, label, source_kind = _match_cover_face_reference(
                {"title": "Зеленский обсуждает переговоры"},
                settings,
                prepared_only=True,
            )

        self.assertEqual(Path(path), prepared)
        self.assertEqual(label, "Зеленский")
        self.assertEqual(source_kind, "auto")
        self.assertEqual(Path(path).suffix.casefold(), ".png")

    def test_prepared_only_auto_match_does_not_fall_back_to_raw_source_portrait(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "Лица"
            source = sources / "Зеленский" / "portrait.jpg"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"source-jpg")
            settings = Settings(
                cover_face_library_folder=str(sources),
                cover_face_prepared_folder=str(root / "Готовые PNG"),
                cover_face_library_enabled=True,
            )

            result = _match_cover_face_reference(
                {"title": "Зеленский обсуждает переговоры"},
                settings,
                prepared_only=True,
            )

        self.assertEqual(result, ("", "", ""))

    def test_my_faces_route_uses_prepared_auto_png_and_fastgen_only_route_sends_no_user_face(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "Лица"
            prepared_root = root / "Готовые PNG"
            source = sources / "Зеленский" / "portrait.jpg"
            prepared = prepared_root / "Зеленский" / "portrait.png"
            source.parent.mkdir(parents=True)
            prepared.parent.mkdir(parents=True)
            source.write_bytes(b"source-jpg")
            prepared.write_bytes(b"prepared-png")

            def make_settings():
                settings = Settings(
                    cover_output_folder=directory,
                    cover_variant_count=1,
                    cover_operation="reference_image_edit",
                    cover_face_library_folder=str(sources),
                    cover_face_prepared_folder=str(prepared_root),
                    cover_face_library_enabled=True,
                    cover_face_remove_background=False,
                )
                settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
                settings.fastgen_capabilities_cache = {"image": [{
                    "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
                }]}
                settings.cover_queue = [{
                    "title": "Зеленский обсуждает переговоры",
                    "topic": "Трамп-Зеленский — давление и переговоры",
                    "selected_people": ["Владимир Зеленский"],
                    "production_item_id": "production:0",
                    "image_prompt": "Topic-accurate editorial news scene",
                    "cover_headline": "ЗЕЛЕНСКИЙ НА ПЕРЕГОВОРАХ",
                    "cover_subheadline": "ДАВЛЕНИЕ НА КИЕВ РАСТЁТ",
                    "paths": [],
                }]
                return settings

            for build_mode, expected in (
                ("fastgen-full-my-face", (str(prepared),)),
                ("fastgen-full", ()),
            ):
                settings = make_settings()
                calls = []

                def render(_prompt, _output, _stem, _operation, _ratio, *,
                           _calls=calls, _build_mode=build_mode, **kwargs):
                    _calls.append(tuple(str(path) for path in kwargs.get("references") or []))
                    return [root / f"{_build_mode}.png"]

                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                     patch.object(bridge, "_save_cover_state"), \
                     patch.object(bridge, "snapshot", return_value={}), \
                     patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                    bridge.generate_covers({
                        "indices": [0],
                        "productionItemIds": ["production:0"],
                        "_parallel_cover_worker": True,
                        "buildMode": build_mode,
                        "faceMode": "auto",
                        "textMode": "fastgen",
                        "localFaceOnly": False,
                        "operation": "reference_image_edit",
                    })

                self.assertEqual(calls, [expected])
                if build_mode == "fastgen-full-my-face":
                    self.assertEqual(settings.cover_queue[0]["face_reference_path"], str(prepared))
                    self.assertEqual(settings.cover_queue[0]["face_reference_source"], "auto")
                    self.assertEqual(settings.cover_queue[0]["faceSelectionMode"], "prepared-reference")
                    self.assertIn("prepared face-tree match", settings.cover_queue[0]["faceSelectionReason"])
                else:
                    self.assertEqual(settings.cover_queue[0]["semantic_face_label"], "Владимир Зеленский")
                    self.assertEqual(settings.cover_queue[0]["semantic_face_source"], "structured-selected_people")
                    self.assertEqual(settings.cover_queue[0]["faceSelectionMode"], "semantic-only")
                    self.assertIn("political portrait resolved", settings.cover_queue[0]["faceSelectionReason"])
                    self.assertIn("recognisable editorial portrait of Владимир Зеленский", settings.cover_queue[0]["final_provider_prompt"])
                    self.assertNotIn(str(prepared), settings.cover_queue[0]["final_provider_prompt"])

    def test_mixed_mode_ranges_send_zero_then_exactly_one_prepared_png(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "Лица"
            prepared_root = root / "Готовые PNG"
            source = sources / "Зеленский" / "portrait.jpg"
            prepared = prepared_root / "Зеленский" / "portrait.png"
            source.parent.mkdir(parents=True)
            prepared.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            prepared.write_bytes(b"prepared")
            settings = Settings(
                cover_output_folder=directory,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
                cover_face_library_folder=str(sources),
                cover_face_prepared_folder=str(prepared_root),
                cover_face_library_enabled=True,
            )
            settings.cover_build_mode_ranges = [
                {"start": 1, "end": 1, "buildMode": "fastgen-full"},
                {"start": 2, "end": 2, "buildMode": "fastgen-full-my-face"},
            ]
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
            }]}
            settings.cover_queue = [
                {
                    "title": "Зеленский обсуждает переговоры", "scenario_index": 1,
                    "production_item_id": "production:1", "image_prompt": "Negotiation scene",
                    "cover_headline": "ПЕРЕГОВОРЫ", "paths": [],
                },
                {
                    "title": "Зеленский не уступает", "scenario_index": 2,
                    "production_item_id": "production:2", "image_prompt": "Press conference scene",
                    "cover_headline": "НЕ УСТУПАЕТ", "paths": [],
                },
            ]
            calls: list[tuple[str, ...]] = []

            def render(_prompt, _output, _stem, _operation, _ratio, **kwargs):
                calls.append(tuple(str(path) for path in kwargs.get("references") or []))
                return [root / f"result-{len(calls)}.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_run_parallel_cover_workers",
                              side_effect=lambda indices, worker: [worker(index) for index in indices]), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge._generate_covers_unlocked({
                    "indices": [0, 1],
                    "productionItemIds": ["production:1", "production:2"],
                    "buildMode": "fastgen-full",
                    "useBuildModeRanges": True,
                    "faceMode": "auto",
                    "textMode": "fastgen",
                    "operation": "reference_image_edit",
                })

        self.assertEqual(calls, [(), (str(prepared),)])
        self.assertEqual(settings.cover_queue[0]["render_profile"]["build_mode"], "fastgen-full")
        self.assertEqual(settings.cover_queue[1]["render_profile"]["build_mode"], "fastgen-full-my-face")
        self.assertEqual(settings.cover_queue[0]["face_reference_count"], 0)
        self.assertEqual(settings.cover_queue[1]["face_reference_count"], 1)

    def test_my_faces_mode_continues_without_reference_when_no_prepared_topic_match(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(
                cover_output_folder=directory,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
                cover_build_mode="fastgen-full-my-face",
                cover_face_library_folder=str(Path(directory) / "missing-faces"),
                cover_face_prepared_folder=str(Path(directory) / "missing-prepared"),
                cover_face_library_enabled=True,
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
            }]}
            settings.cover_queue = [{
                "title": "Зеленский обсуждает переговоры", "scenario_index": 1,
                "selected_people": ["Владимир Зеленский"],
                "production_item_id": "production:1", "image_prompt": "Negotiation scene",
                "cover_headline": "ПЕРЕГОВОРЫ", "paths": [],
            }]
            calls: list[tuple[str, ...]] = []

            def render(_prompt, output, _stem, _operation, _ratio, **kwargs):
                calls.append(tuple(str(path) for path in kwargs.get("references") or []))
                generated = output / "fallback-without-face.png"
                generated.write_bytes(b"generated")
                return [generated]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0], "productionItemIds": ["production:1"],
                    "_parallel_cover_worker": True, "buildMode": "fastgen-full-my-face",
                    "faceMode": "auto", "textMode": "fastgen",
                    "operation": "reference_image_edit",
                })

        self.assertEqual(calls, [()])
        self.assertEqual(settings.cover_queue[0]["status"], "Готово")
        self.assertEqual(settings.cover_queue[0]["face_reference_count"], 0)
        self.assertIn("no prepared PNG", settings.cover_queue[0]["faceSelectionReason"])
        self.assertNotIn("face_reference_path", settings.cover_queue[0])

    def test_political_portrait_resolver_reaches_both_fastgen_routes_without_a_png(self):
        """A political scene must keep an identified side portrait even without local files."""
        from scriptor import bridge

        for build_mode in ("fastgen-full", "fastgen-full-my-face"):
            with self.subTest(build_mode=build_mode), TemporaryDirectory() as directory:
                root = Path(directory)
                settings = Settings(
                    cover_output_folder=directory,
                    cover_variant_count=1,
                    cover_operation="reference_image_edit",
                    cover_face_library_folder=str(root / "missing-faces"),
                    cover_face_prepared_folder=str(root / "missing-prepared"),
                    cover_face_library_enabled=True,
                )
                settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
                settings.fastgen_capabilities_cache = {"image": [{
                    "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
                }]}
                settings.cover_queue = [{
                    "title": "Кремль усилил давление: переговоры по Украине меняют тон",
                    "selected_people": ["Владимир Путин"],
                    "scenario_index": 1,
                    "production_item_id": "production:kremlin",
                    "image_prompt": "Topic-accurate editorial negotiation scene",
                    "cover_headline": "КРЕМЛЬ ДАВИТ",
                    "cover_subheadline": "ПЕРЕГОВОРЫ МЕНЯЮТ ТОН",
                    "paths": [],
                }]
                calls: list[tuple[str, tuple[str, ...]]] = []

                def render(prompt, output, _stem, _operation, _ratio, *, _calls=calls,
                           _build_mode=build_mode, **kwargs):
                    _calls.append((prompt, tuple(str(path) for path in kwargs.get("references") or [])))
                    generated = output / f"{_build_mode}.png"
                    generated.write_bytes(b"generated")
                    return [generated]

                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                     patch.object(bridge, "_save_cover_state"), \
                     patch.object(bridge, "snapshot", return_value={}), \
                     patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                    bridge.generate_covers({
                        "indices": [0], "productionItemIds": ["production:kremlin"],
                        "_parallel_cover_worker": True, "buildMode": build_mode,
                        "faceMode": "auto", "textMode": "fastgen",
                        "operation": "reference_image_edit",
                    })

                item = settings.cover_queue[0]
                self.assertEqual(calls[0][1], ())
                self.assertEqual(item["portrait_subject"], "Владимир Путин")
                self.assertIn(item["portrait_side"], {"LEFT", "RIGHT"})
                self.assertEqual(item["portrait_source"], "structured-selected_people")
                self.assertIn("selected_people", item["portrait_resolver_reason"])
                self.assertIn("Владимир Путин", calls[0][0])
                self.assertIn("large side portrait", calls[0][0])
                self.assertEqual(item["face_reference_count"], 0)

    def test_explicit_without_faces_bypasses_political_portrait_resolution(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_variant_count=1)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
            }]}
            settings.cover_queue = [{
                "title": "Кремль усилил давление: переговоры по Украине меняют тон",
                "scenario_index": 1,
                "production_item_id": "production:kremlin-without",
                "image_prompt": "Topic-accurate editorial negotiation scene",
                "cover_headline": "КРЕМЛЬ ДАВИТ",
                "cover_subheadline": "ПЕРЕГОВОРЫ МЕНЯЮТ ТОН",
                "paths": [],
            }]
            prompts: list[str] = []

            def render(prompt, output, _stem, _operation, _ratio, **_kwargs):
                prompts.append(prompt)
                generated = output / "without-face.png"
                generated.write_bytes(b"generated")
                return [generated]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0], "productionItemIds": ["production:kremlin-without"],
                    "_parallel_cover_worker": True, "buildMode": "fastgen-full",
                    "faceMode": "without", "textMode": "fastgen",
                    "operation": "reference_image_edit",
                })

            item = settings.cover_queue[0]
            self.assertEqual(item["portrait_subject"], "")
            self.assertEqual(item["portrait_side"], "")
            self.assertEqual(item["portrait_source"], "disabled")
            self.assertNotIn("Владимир Путин", prompts[0])
            self.assertEqual(item["face_reference_count"], 0)


    def test_face_match_does_not_infer_a_person_from_place_only(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            portrait = folder / "Марина Орлова" / "portrait.jpg"
            portrait.parent.mkdir()
            portrait.write_bytes(b"test")
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)

            self.assertEqual(
                _match_cover_face_reference({"title": "Город Северный меняет правила парковки"}, settings),
                ("", "", ""),
            )


    def test_face_match_uses_arbitrary_identity_metadata_and_generic_transliteration(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            matching = folder / "Marina Orlova" / "portrait.jpg"
            unrelated = folder / "Anton Reed" / "portrait.jpg"
            matching.parent.mkdir()
            unrelated.parent.mkdir()
            matching.write_bytes(b"match")
            unrelated.write_bytes(b"other")
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)

            path, label, source = _match_cover_face_reference(
                {"title": "Новый проект", "selected_people": ["Марина Орлова"]},
                settings,
            )

            self.assertEqual(Path(path), matching)
            self.assertEqual(label, "Marina Orlova")
            self.assertEqual(source, "auto")


    def test_remembers_side_portrait_composition_profile_for_same_item(self):
        settings = Settings()
        item = {"production_item_id": "synthetic:1", "title": "Марина Орлова представляет проект"}
        first = _cover_face_layout(item, settings, "C:/faces/Marina Orlova/portrait.png", "Marina Orlova")
        second = _cover_face_layout(item, settings, "C:/faces/Marina Orlova/portrait.png", "Marina Orlova")
        self.assertEqual(first, second)
        self.assertTrue(item["face_layout"].startswith("крупный боковой портрет"))
        self.assertTrue("left" in first.casefold() or "right" in first.casefold())


    def test_side_portrait_reserves_opposite_text_safe_zone(self):
        settings = Settings(cover_auto_overlay_text=True, cover_text_mode="overlay")
        item = {"production_item_id": "synthetic:2", "title": "Марина Орлова представляет проект"}
        instruction = _cover_face_layout(item, settings, "C:/faces/Marina Orlova/portrait.png", "Marina Orlova")
        self.assertIn("opposite", instruction.casefold())
        self.assertIn("headline", instruction.casefold())
        self.assertIn("текст на", item["face_layout"])

    def test_randomly_chooses_between_matching_portraits_but_keeps_manual_choice(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            portraits = []
            for number in range(1, 5):
                portrait = folder / "Путин" / f"Путин_{number}.jpg"
                portrait.parent.mkdir(exist_ok=True)
                portrait.write_bytes(b"test")
                portraits.append(portrait)
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)
            with patch(
                "scriptor.bridge.random.choice",
                side_effect=lambda values: max(values, key=lambda path: path.name),
            ):
                path, _label, source = _match_cover_face_reference({"title": "Путин сделал заявление"}, settings)
            self.assertEqual(Path(path), portraits[-1])
            self.assertEqual(source, "auto")
            # Auto matches are allowed to change on the next render, while a
            # reference explicitly marked manual is not randomized. Directory
            # iteration order is intentionally not part of this contract.
            with patch(
                "scriptor.bridge.random.choice",
                side_effect=lambda values: min(values, key=lambda path: path.name),
            ):
                changed, _label, source = _match_cover_face_reference({
                    "title": "Путин сделал заявление", "face_reference_path": str(portraits[-1]),
                    "face_reference_source": "auto",
                }, settings)
            self.assertEqual(Path(changed), portraits[0])
            fixed, _label, source = _match_cover_face_reference({
                "title": "Путин сделал заявление", "face_reference_path": str(portraits[1]),
                "face_reference_source": "manual",
            }, settings)
            self.assertEqual(Path(fixed), portraits[1])
            self.assertEqual(source, "manual")

    def test_summary_uses_separate_prepared_folder_and_lists_preview_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "Исходники"
            prepared = root / "Готовые PNG"
            source = sources / "Путин" / "portrait.jpg"
            output = prepared / "Путин" / "portrait.png"
            source.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            output.write_bytes(b"png")
            summary = _cover_face_library_summary(Settings(
                cover_face_library_folder=str(sources), cover_face_prepared_folder=str(prepared),
            ))
            self.assertEqual(summary["preparedFolder"], str(prepared))
            self.assertEqual(summary["preparedCount"], 1)
            self.assertEqual(summary["preparedPaths"], [str(output)])

    def test_catalog_prefers_prepared_person_folders_for_gallery_selection(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "алиев" / "source.jpg"
            cutout = root / "_вырезанные" / "алиев" / "portrait.png"
            source.parent.mkdir(parents=True); cutout.parent.mkdir(parents=True)
            source.write_bytes(b"source"); cutout.write_bytes(b"cutout")
            catalog = _cover_face_catalog(Settings(cover_face_library_folder=str(root)))
            self.assertEqual(catalog[0]["name"], "алиев")
            self.assertEqual(catalog[0]["paths"], [str(cutout)])
            self.assertTrue(catalog[0]["prepared"])
            self.assertEqual(len(catalog), 1)

    def test_preparing_existing_cutouts_does_not_need_to_download_rembg_model(self):
        """Existing reusable PNGs are only compressed, never blocked by a model download."""
        import sys
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "трамп" / "portrait.png"
            target = root / "_вырезанные" / "трамп" / "portrait.png"
            source.parent.mkdir(parents=True); target.parent.mkdir(parents=True)
            source.write_bytes(b"source")
            target.write_bytes(b"prepared")
            settings = Settings(cover_face_library_folder=str(root))
            fake_rembg = SimpleNamespace(new_session=lambda *_args: self.fail("model must not be loaded"))
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                 patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                 patch("scriptor.bridge._release_cover_generation_lock"), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}), \
                 patch("scriptor.bridge._compress_prepared_face_for_fastgen", return_value=True), \
                 patch.dict(sys.modules, {"rembg": fake_rembg}):
                result = prepare_cover_face_library({})
            self.assertIn("сжато для FastGen ≤5 МБ: 1", result["operationResult"]["message"])


class CoverVisualInstructionTests(unittest.TestCase):
    def test_new_fastgen_reference_settings_persist_and_keep_missing_paths_visible(self):
        from scriptor import bridge

        settings = Settings()
        with TemporaryDirectory() as directory:
            available = Path(directory) / "style.png"
            missing = Path(directory) / "removed.webp"
            folder = Path(directory) / "reference-pack"
            folder.mkdir()
            from_folder = folder / "mood.jpeg"
            ignored = folder / "notes.txt"
            available.write_bytes(b"style")
            from_folder.write_bytes(b"jpeg")
            ignored.write_text("not an image", encoding="utf-8")
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}):
                save_cover_settings({
                    "useReferences": True,
                    "referenceImagePaths": [str(available), str(missing)],
                    "referenceModeStyle": True,
                    "referenceModeComposition": True,
                    "referenceModeMoodLighting": False,
                    "referenceModeAuto": False,
                    "referenceImageFolders": [str(folder)],
                })
            selection = bridge._cover_fastgen_visual_reference_selection(settings, max_references=8)
            self.assertEqual(selection["paths"], [str(available), str(from_folder)])
            self.assertEqual(selection["missing"], [str(missing)])
        self.assertTrue(settings.cover_fastgen_use_references)
        self.assertEqual(settings.cover_fastgen_reference_paths, [str(available), str(missing), str(from_folder)])
        self.assertTrue(settings.cover_fastgen_reference_mode_style)
        self.assertTrue(settings.cover_fastgen_reference_mode_composition)
        self.assertFalse(settings.cover_fastgen_reference_mode_auto)

    def test_new_fastgen_references_are_visual_only_and_portrait_slot_has_priority(self):
        from PIL import Image

        from scriptor import bridge

        with TemporaryDirectory() as directory:
            root = Path(directory)
            portrait = root / "portrait.png"
            style_a = root / "style-a.png"
            style_b = root / "style-b.png"
            for path in (portrait, style_a, style_b):
                Image.new("RGB", (640, 360), (20, 60, 90)).save(path)
            settings = Settings(
                cover_fastgen_use_references=True,
                cover_fastgen_reference_paths=[str(style_a), str(style_b)],
                cover_fastgen_reference_mode_style=True,
                cover_fastgen_reference_mode_composition=True,
            )
            selection = bridge._cover_fastgen_visual_reference_selection(settings, max_references=1)
            self.assertEqual(selection["paths"], [str(style_a)])
            self.assertIn("visual guidance only", bridge._cover_fastgen_reference_instruction(settings).casefold())
            self.assertIn("productionitem", bridge._cover_fastgen_reference_instruction(settings).casefold())
            references, _label = _cover_references_for_item(
                {"face_reference_path": str(portrait), "face_reference_label": "Current Person", "face_reference_source": "manual"},
                settings,
                face_mode="with",
                prepared_auto_face=True,
                max_references=2,
            )
        self.assertEqual(references[-1], str(portrait))
        self.assertEqual(len(references), 2)
    def test_scenario_cover_inherits_saved_production_context(self):
        from scriptor.bridge import _sync_scenario_to_covers

        settings = Settings()
        title = "ПВО отражает атаку: что увидят жители приграничья"
        settings.idea_scenario_context = {title: {
            "direction": "Россия и Европа", "topic": "ПВО на границе",
            "angle": "последствия для приграничных городов", "event_ids": ["evt-17"],
            "supporting_context": "Ночная атака дронов у приграничной инфраструктуры",
            "primary_entity": "ПВО", "geography": ["Белгородская область"],
            "conflict": "атака дронов", "main_consequence": "риск перебоев", "framing_type": "EDITORIAL",
        }}

        self.assertTrue(_sync_scenario_to_covers(settings, 0, title, None))
        cover = settings.cover_queue[0]
        self.assertEqual(cover["direction"], "Россия и Европа")
        self.assertEqual(cover["topic"], "ПВО на границе")
        self.assertEqual(cover["event_ids"], ["evt-17"])
        self.assertEqual(cover["main_consequence"], "риск перебоев")

    def test_instruction_carries_full_structured_production_context(self):
        item = {
            "direction": "Россия и Европа",
            "topic": "ПВО на границе",
            "angle": "последствия для приграничных городов",
            "title": "ПВО отражает атаку: что увидят жители приграничья",
            "supporting_context": "Ночная атака дронов у приграничной инфраструктуры",
            "primary_entities": ["ПВО", "жители", "экстренные службы"],
            "geography": ["Белгородская область"],
            "conflict": "атака дронов на инфраструктуру",
            "main_consequence": "риск перебоев для города",
            "framing_type": "EDITORIAL",
        }
        instruction = _cover_instruction(item, 0, Settings())
        self.assertIn("НАПРАВЛЕНИЕ: Россия и Европа", instruction)
        self.assertIn("УГОЛ: последствия для приграничных городов", instruction)
        self.assertIn("КОНТЕКСТ СОБЫТИЯ: Ночная атака дронов", instruction)
        self.assertIn("ОСНОВНЫЕ УЧАСТНИКИ: ПВО, жители, экстренные службы", instruction)
        self.assertIn("ГЕОГРАФИЯ: Белгородская область", instruction)
        self.assertIn("ПОСЛЕДСТВИЕ: риск перебоев для города", instruction)
        self.assertIn("ДРАМАТИЧЕСКАЯ ВОЕННАЯ ВИЗУАЛИЗАЦИЯ", instruction)

    def test_prompt_builder_keeps_structured_context_for_existing_prompt(self):
        item = {
            "title": "Экономика Европы", "topic": "Рост цен на газ", "angle": "счета домохозяйств",
            "main_consequence": "рост зимних счетов", "framing_type": "EDITORIAL",
        }
        prompt = _normalize_cover_photo_prompt("Households confronting higher winter gas bills", item)
        self.assertIn("MAIN SUBJECT:\nРост цен на газ", prompt)
        self.assertIn("VISUAL EVIDENCE:\nрост зимних счетов", prompt)
        self.assertEqual(prompt.count("CORE STYLE:"), 1)

    def test_reference_ranges_apply_only_to_their_scenarios_and_can_be_disabled(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.png"; second = root / "second.png"
            first.write_bytes(b"one"); second.write_bytes(b"two")
            settings = Settings(cover_reference_mode="ranges", cover_reference_ranges=[
                {"start": 1, "end": 10, "paths": [str(first)]},
                {"start": 11, "end": 20, "paths": [str(second)]},
            ])
            self.assertEqual(_cover_reference_paths_for_item({"scenario_index": 4}, 3, settings), [str(first)])
            self.assertEqual(_cover_reference_paths_for_item({"scenario_index": 15}, 14, settings), [str(second)])
            settings.cover_reference_mode = "off"
            self.assertEqual(_cover_reference_paths_for_item({"scenario_index": 4}, 3, settings), [])

    def test_reference_instruction_demands_abstract_style_not_copying(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "reference.png"; source.write_bytes(b"x")
            settings = Settings(cover_reference_paths=[str(source)])
            instruction = _cover_reference_instruction({"scenario_index": 1}, 0, settings)
            self.assertIn("композицию", instruction)
            self.assertIn("Не копируй", instruction)

    def test_manual_person_is_an_explicit_part_of_the_prompt_rewrite(self):
        with TemporaryDirectory() as directory:
            portrait = Path(directory) / "алиев.png"; portrait.write_bytes(b"x")
            item = {"title": "Переговоры в Баку", "face_reference_path": str(portrait),
                    "face_reference_label": "алиев", "face_reference_source": "manual"}
            instruction = _cover_instruction(item, 0, Settings())
            self.assertIn("ВЫБРАННОЕ ЛИЦО", instruction)
            self.assertIn("алиев", instruction)

    def test_visual_prompt_requires_event_appropriate_realistic_human_activity(self):
        instruction = _cover_instruction(
            {"title": "Взрыв на промышленном объекте", "script": ""}, 0, Settings(),
        )
        self.assertIn("краткое, естественное английское описание фактов сцены", instruction)
        self.assertIn("конкретное действие, визуальное доказательство и тему", instruction)
        self.assertIn("УНИВЕРСАЛЬНЫЙ ВИЗУАЛЬНЫЙ КОНТРАКТ", instruction)
        self.assertNotIn("ACTION = HIGH.", instruction)

    def test_visual_prompt_requires_a_real_press_photograph_not_an_illustration(self):
        instruction = _cover_instruction({"title": "Удар по промышленному объекту", "script": ""}, 0, Settings())
        prompt = _normalize_cover_photo_prompt("Wide view of a damaged factory with responders", {"title": "Удар по промышленному объекту"})
        self.assertIn("Не добавляй style prompt", instruction)
        self.assertIn("CORE STYLE:\n", prompt)
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2.", prompt)
        self.assertIn("PHOTOREALISM = MAXIMUM.", prompt)
        self.assertIn("No artwork, illustration", prompt)

    def test_every_new_saved_fastgen_prompt_carries_the_universal_v2_contract_once(self):
        prompt = _normalize_cover_photo_prompt("Wide view of a damaged factory with responders")
        self.assertTrue(prompt.startswith("CORE STYLE:\n"))
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2.", prompt)
        self.assertIn("PHOTOREALISM = MAXIMUM.", prompt)
        self.assertIn("STORY CONTEXT:\nWide view of a damaged factory with responders", prompt)
        self.assertEqual(prompt.count("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2"), 1)

    def test_snapshot_does_not_rewrite_existing_visual_prompts_without_user_action(self):
        settings = Settings()
        settings.cover_queue = [{
            "image_prompt": "Cinematic tanker conflict at dusk",
            "image_prompt_options": ["Cinematic tanker conflict at dusk", "Photorealistic documentary news photograph, real port"],
            "selected_prompt_index": 0,
        }]
        self.assertFalse(_migrate_legacy_cover_photo_prompts(settings))
        item = settings.cover_queue[0]
        self.assertEqual(item["image_prompt"], "Cinematic tanker conflict at dusk")
        self.assertEqual(item["image_prompt_options"], ["Cinematic tanker conflict at dusk", "Photorealistic documentary news photograph, real port"])

    def test_disabled_custom_visual_brief_is_not_sent_to_the_v2_provider_prompt(self):
        settings = Settings(cover_prompt_template="Сделай всё фиолетовым", cover_use_custom_prompt=False)
        instruction = _cover_instruction({"title": "Ормузский пролив", "script": ""}, 0, settings)
        self.assertNotIn("Сделай всё фиолетовым", instruction)


    def test_prompt_builder_owns_realistic_art_direction_without_named_fallback(self):
        prompt = _normalize_cover_photo_prompt(
            "Engineers inspect a transparent water-filtration prototype in a real laboratory.",
            {"title": "Новая мембрана ускоряет очистку воды"},
        )
        self.assertNotIn("breaking-news", prompt.casefold())
        self.assertIn(
            "CORE STYLE:\nCreate a realistic, highly clickable, photorealistic YouTube news thumbnail image.",
            prompt,
        )
        self.assertIn("water-filtration prototype", prompt.casefold())
        self.assertNotIn("Official NATO and EU fabric flags", prompt)

    def test_runtime_cover_routing_has_no_named_fixture_tables(self):
        from scriptor import bridge, thumbnail_prompt_v2

        prompt_source = Path(thumbnail_prompt_v2.__file__).read_text(encoding="utf-8")
        fallback = prompt_source.split("def _topic_scene_defaults", 1)[1].split("def visual_brief", 1)[0].casefold()
        bridge_source = Path(bridge.__file__).read_text(encoding="utf-8")
        visual_plan = bridge_source.split("def _cover_topic_visual_plan", 1)[1].split(
            "def _cover_news_conflict_requirement", 1
        )[0].casefold()

        for forbidden in (
            "karabakh", "карабах", "wildberries", "вайлдберриз", "hormuz", "ормуз",
            "donald trump", "vladimir putin", "nato summit",
        ):
            self.assertNotIn(forbidden, fallback)
            self.assertNotIn(forbidden, visual_plan)
        self.assertNotIn("_COVER_FACE_TOPIC_HINTS", bridge_source)
        self.assertNotIn("_COVER_FACE_ALIASES", bridge_source)

    def test_topic_plan_is_universal_and_agent_owned(self):
        plan = _cover_topic_visual_plan({
            "title": "Редкий минерал меняет производство аккумуляторов",
            "topic": "Новая производственная технология",
            "primary_entities": ["Компания Север", "лаборатория"],
        })
        lowered = plan.casefold()
        self.assertIn("самостоятельно выбери", lowered)
        self.assertIn("не применяй готовый шаблон", lowered)
        self.assertIn("компания север", lowered)
        self.assertNotIn("ормузский визуальный план", lowered)
        self.assertNotIn("план нато", lowered)


    def test_default_topic_plan_does_not_invent_a_preclassified_event(self):
        plan = _cover_topic_visual_plan({"title": "Новые изменения в правилах"})
        lowered = plan.casefold()
        self.assertIn("строго из текущей темы", lowered)
        self.assertIn("не подменяй тему знакомым сюжетом", lowered)
        self.assertIn("не выдуманным происшествием", lowered)


    def test_named_fixture_does_not_activate_named_runtime_recipe(self):
        plan = _cover_topic_visual_plan({"title": "НАТО и Россия — риск новой эскалации"})
        lowered = plan.casefold()
        self.assertIn("универсальный визуальный контракт", lowered)
        self.assertNotIn("план нато—россия", lowered)
        self.assertNotIn("обязательно покажи официальные флаги", lowered)
        self.assertNotIn("ракетный пуск", lowered)


class CoverLocalCompositorTests(unittest.TestCase):
    def test_legacy_local_face_route_migrates_to_the_remote_my_faces_route(self):
        with TemporaryDirectory() as directory:
            settings_path = Path(directory) / "settings.json"
            settings_path.write_text(json.dumps({
                "schema_version": 4,
                "cover_build_mode": "fastgen-text-local-face",
            }), encoding="utf-8")
            with patch("scriptor.config.config_path", return_value=settings_path):
                settings = load_settings()

        self.assertEqual(settings.cover_build_mode, "fastgen-full-my-face")

    def test_render_stores_profile_that_describes_the_created_cover(self):
        """The retry button needs a record of the actual route, not today's UI default."""
        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_auto_overlay_text=False)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.cover_queue = [{"title": "Ормуз", "image_prompt": "realistic tanker scene"}]
            output = Path(directory) / "cover.png"
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}), \
                 patch("scriptor.bridge.FastGenPool.generate_media", return_value=[output]):
                generate_covers({
                    "indices": [0], "buildMode": "fastgen-full-my-face",
                    "faceMode": "auto", "textMode": "fastgen", "localFaceOnly": False,
                })
        self.assertEqual(settings.cover_queue[0]["render_profile"], {
            "build_mode": "fastgen-full-my-face", "face_mode": "auto",
            "text_mode": "fastgen", "local_face_only": False,
            "operation": "flower_image_generate",
        })

    def test_repeat_current_uses_saved_render_profile_instead_of_new_defaults(self):
        """A retry must preserve the my-faces FastGen route."""
        settings = Settings()
        settings.cover_queue = [{
            "title": "Ормуз", "image_prompt": "scene",
            "final_provider_prompt": "SAVED FINAL PROMPT",
            "final_provider_prompt_options": ["SAVED FINAL PROMPT"],
            "render_profile": {
                "build_mode": "fastgen-full-my-face", "face_mode": "auto",
                "text_mode": "fastgen", "local_face_only": False,
                "operation": "flower_image_generate",
            },
        }]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.generate_covers", return_value={}) as render:
            regenerate_covers({"indices": [0], "currentProfile": True})
        payload = render.call_args.args[0]
        self.assertEqual({key: value for key, value in payload.items() if key != "productionItemIds"}, {
            "indices": [0], "buildMode": "fastgen-full-my-face", "faceMode": "auto",
            "textMode": "fastgen", "localFaceOnly": False,
            "operation": "flower_image_generate", "repeatCurrentContract": True,
        })
        self.assertEqual(len(payload["productionItemIds"]), 1)
        self.assertTrue(payload["productionItemIds"][0].startswith("production:manual:"))


    def test_repeat_current_contract_reuses_saved_prompt_profile_and_reference_without_reselection(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            reference = Path(temporary) / "saved-face.png"
            reference.write_bytes(b"saved-face")
            saved_prompt = "SAVED FINAL FASTGEN PROMPT\nBYTE FOR BYTE"
            settings = Settings(
                cover_output_folder=temporary,
                cover_variant_count=1,
                cover_operation="new-current-operation-that-must-be-ignored",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            # Deliberately no current capability metadata for the saved
            # reference operation: exact repeat must not silently drop the PNG.
            settings.fastgen_capabilities_cache = {"image": []}
            settings.cover_queue = [{
                "production_item_id": "production:repeat",
                "title": "Repeat",
                "image_prompt": "semantic prompt that must not be rebuilt",
                "final_provider_prompt": saved_prompt,
                "final_provider_prompt_options": [saved_prompt],
                "final_provider_reference_paths": [str(reference)],
                "final_provider_face_label": "Saved Person",
                "final_provider_face_reference_count": 1,
                "face_reference_path": str(reference),
                "face_reference_label": "Saved Person",
                "face_reference_source": "auto",
                "face_reference_count": 1,
                "render_profile": {
                    "build_mode": "fastgen-full-my-face",
                    "face_mode": "auto",
                    "text_mode": "fastgen",
                    "local_face_only": False,
                    "operation": "saved-reference-operation",
                },
                "paths": [],
            }]
            calls = []

            def render(prompt, _output, _title, operation, _ratio, **kwargs):
                calls.append((prompt, operation, tuple(kwargs.get("references", []))))
                return [Path(temporary) / "repeat.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "build_final_provider_prompt", side_effect=AssertionError("prompt rebuilt")), \
                 patch.object(bridge, "_match_cover_face_reference", side_effect=AssertionError("face reselected")), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:repeat"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full",
                    "faceMode": "without",
                    "textMode": "overlay",
                    "operation": "new-current-operation-that-must-be-ignored",
                    "repeatCurrentContract": True,
                })

            self.assertEqual(
                calls,
                [(saved_prompt, "saved-reference-operation", (str(reference),))],
            )
            self.assertEqual(settings.cover_queue[0]["final_provider_prompt"], saved_prompt)
            self.assertEqual(settings.cover_queue[0]["face_reference_count"], 1)
            self.assertEqual(
                settings.cover_queue[0]["render_profile"]["operation"],
                "saved-reference-operation",
            )

    def test_repeat_current_rejects_legacy_row_before_deleting_existing_image(self):
        """Without a saved provider prompt, Repeat Current must not destroy the current image."""
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            old_path = Path(temporary) / "existing.png"
            old_path.write_bytes(b"existing-cover")
            settings = Settings(cover_output_folder=temporary)
            settings.cover_queue = [{
                "production_item_id": "production:legacy",
                "title": "Legacy",
                "image_prompt": "legacy semantic prompt only",
                "paths": [str(old_path)],
                "render_profile": {
                    "build_mode": "fastgen-full", "face_mode": "auto",
                    "text_mode": "fastgen", "local_face_only": False,
                    "operation": "flower_image_generate",
                },
            }]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "generate_covers") as generate, \
                 self.assertRaisesRegex(ValueError, "Final FastGen prompt"):
                regenerate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:legacy"],
                    "currentProfile": True,
                })

            self.assertTrue(old_path.exists())
            generate.assert_not_called()

    def test_repeat_current_rejects_missing_render_profile_before_deleting_existing_image(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            old_path = Path(temporary) / "existing-profile.png"
            old_path.write_bytes(b"existing-cover")
            settings = Settings(cover_output_folder=temporary)
            settings.cover_queue = [{
                "production_item_id": "production:no-profile",
                "title": "No profile",
                "image_prompt": "saved semantic prompt",
                "final_provider_prompt": "SAVED FINAL PROMPT",
                "final_provider_prompt_options": ["SAVED FINAL PROMPT"],
                "paths": [str(old_path)],
            }]
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "generate_covers") as generate, \
                 self.assertRaisesRegex(ValueError, "render profile"):
                regenerate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:no-profile"],
                    "currentProfile": True,
                    "operation": "caller-must-not-override",
                })

            self.assertTrue(old_path.exists())
            generate.assert_not_called()


    def test_arbitrary_cover_request_uses_current_scene_without_a_legacy_render_tail(self):
        settings = Settings(cover_auto_overlay_text=False)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "title": "Новая мембрана ускоряет очистку воды",
            "image_prompt": "Engineers inspect a transparent water-filtration prototype in a real laboratory.",
        }]
        captured = []
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.FastGenPool.generate_media", side_effect=lambda prompt, *args, **kwargs: captured.append(prompt) or [Path("cover.png")]):
            generate_covers({"indices": [0], "textMode": "overlay", "localFaceOnly": False})

        self.assertIn("water-filtration prototype", captured[0].casefold())
        self.assertEqual(captured[0].count("CORE STYLE:"), 1)
        self.assertEqual(captured[0].count("FINAL NEGATIVE RULES:"), 1)
        self.assertNotIn("nato summit", captured[0].casefold())
        self.assertNotIn("energy-market trading floor", captured[0].casefold())

    def test_prepared_cutout_is_resaved_under_fastgen_size_limit(self):
        from PIL import Image
        with TemporaryDirectory() as directory:
            portrait = Path(directory) / "portrait.png"
            # Noisy transparent PNG is a realistic worst case for a cut-out
            # and reliably exceeds FastGen's 5 MiB reference limit.
            noise = Image.effect_noise((2200, 1800), 100).convert("RGBA")
            noise.save(portrait, optimize=False)
            self.assertGreater(portrait.stat().st_size, 5 * 1024 * 1024)
            self.assertTrue(_compress_prepared_face_for_fastgen(portrait))
            self.assertLessEqual(portrait.stat().st_size, int(4.7 * 1024 * 1024))
            with Image.open(portrait) as result:
                self.assertEqual(result.mode, "RGBA")

    def test_local_face_composite_puts_portrait_on_the_right(self):
        from PIL import Image
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scene.png"
            portrait = root / "portrait.png"
            destination = root / "result.png"
            Image.new("RGB", (1280, 720), (12, 31, 62)).save(source)
            Image.new("RGB", (600, 900), (226, 44, 50)).save(portrait)
            _cover_local_face_composite(source, portrait, destination)
            result = Image.open(destination).convert("RGB")
            self.assertTrue(destination.is_file())
            # The portrait is intentionally anchored at the right edge, while
            # the left half stays free for the text overlay.
            self.assertGreater(result.getpixel((1050, 430))[0], 100)
            self.assertLess(result.getpixel((120, 430))[0], 80)

    def test_cover_face_step_replaces_raw_visible_variant_with_local_composite(self):
        from PIL import Image
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.png"; face = root / "Путин.png"
            Image.new("RGB", (1280, 720), (12, 31, 62)).save(raw)
            Image.new("RGB", (600, 900), (226, 44, 50)).save(face)
            settings = Settings(cover_output_folder=str(root))
            settings.cover_queue = [{
                "title": "Путин сделал заявление", "raw_paths": [str(raw)], "paths": [str(raw)],
                "selected_path": str(raw), "selected_base_path": str(raw),
                "face_reference_path": str(face), "face_reference_label": "Путин",
            }]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}):
                compose_cover_faces({"indices": [0]})
            final = Path(settings.cover_queue[0]["selected_path"])
            self.assertTrue(final.is_file())
            self.assertNotEqual(final, raw)
            self.assertIn(str(final), settings.cover_queue[0]["paths"])

    def test_text_renderer_creates_a_real_final_image_and_replaces_visible_variant(self):
        from PIL import Image, ImageChops
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scene.png"
            Image.new("RGB", (1280, 720), (25, 54, 86)).save(source)
            settings = Settings(cover_output_folder=str(root))
            settings.cover_queue = [{
                "title": "Тегеран усиливает давление на Ормузский пролив",
                "cover_headline": "ОРМУЗ ПОД УГРОЗОЙ",
                "cover_subheadline": "Танкеры ждут решения",
                "paths": [str(source)], "selected_path": str(source), "selected_base_path": str(source),
            }]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}):
                render_cover_text({"indices": [0]})
            final_path = Path(settings.cover_queue[0]["selected_path"])
            self.assertTrue(final_path.is_file())
            self.assertIn(str(final_path), settings.cover_queue[0]["paths"])
            self.assertIsNotNone(ImageChops.difference(Image.open(source).convert("RGB"), Image.open(final_path).convert("RGB")).getbbox())

    def test_face_text_overlay_keeps_all_current_words_inside_the_canvas(self):
        from PIL import Image, ImageDraw

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "face-scene.png"
            Image.new("RGB", (1376, 768), (25, 54, 86)).save(source)
            headline = "ЭНЕРГИЯ ПОД КОНТРОЛЕМ"
            subheadline = "Форум обсуждает безопасность поставок"
            settings = Settings(cover_output_folder=str(root))
            settings.cover_queue = [{
                "title": "Владимир Путин обсуждает энергетическую безопасность",
                "cover_headline": headline,
                "cover_subheadline": subheadline,
                "paths": [str(source)],
                "selected_path": str(source),
                "selected_base_path": str(source),
                "face_composite_paths": [str(source)],
            }]
            drawn = []
            original_text = ImageDraw.ImageDraw.text

            def capture_text(draw, xy, text, *args, **kwargs):
                box = draw.textbbox(
                    xy, text, font=kwargs.get("font"),
                    stroke_width=kwargs.get("stroke_width", 0),
                )
                drawn.append((str(text), box))
                return original_text(draw, xy, text, *args, **kwargs)

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}), \
                 patch.object(ImageDraw.ImageDraw, "text", new=capture_text):
                render_cover_text({"indices": [0]})

        rendered_words = " ".join(text for text, _box in drawn).casefold().split()
        self.assertEqual(rendered_words, f"{headline} {subheadline}".casefold().split())
        self.assertTrue(all(0 <= box[0] and box[2] <= 1376 and 0 <= box[1] and box[3] <= 768
                            for _text, box in drawn))

    def test_face_root_is_saved_as_an_absolute_path(self):
        with TemporaryDirectory() as directory:
            settings = Settings()
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}):
                save_cover_settings({"faceLibraryFolder": directory, "faceLibraryEnabled": True})
            self.assertEqual(settings.cover_face_library_folder, str(Path(directory).resolve()))
            self.assertTrue(settings.cover_face_library_enabled)
            self.assertTrue(settings.cover_face_remove_background)

    def test_prompt_variant_count_accepts_one_through_ten(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}):
            save_cover_settings({"promptVariantCount": 1})
            self.assertEqual(settings.cover_prompt_variant_count, 1)
            save_cover_settings({"promptVariantCount": 10})
            self.assertEqual(settings.cover_prompt_variant_count, 10)

    def test_cover_build_mode_accepts_the_only_my_faces_route(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}):
            save_cover_settings({"buildMode": "fastgen-full-my-face"})
        self.assertEqual(settings.cover_build_mode, "fastgen-full-my-face")

    def test_cover_build_mode_ranges_and_palette_are_persisted(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}):
            save_cover_settings({
                "buildModeRanges": [
                    {"start": 1, "end": 3, "buildMode": "fastgen-full"},
                    {"start": 4, "end": 8, "buildMode": "fastgen-full-my-face"},
                ],
                "allowVariedTextPalette": True,
            })

        self.assertEqual(settings.cover_build_mode_ranges, [
            {"start": 1, "end": 3, "buildMode": "fastgen-full"},
            {"start": 4, "end": 8, "buildMode": "fastgen-full-my-face"},
        ])
        self.assertTrue(settings.cover_allow_varied_text_palette)

    def test_cover_build_mode_ranges_reject_overlaps(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             self.assertRaisesRegex(ValueError, "пересекаются"):
            save_cover_settings({"buildModeRanges": [
                {"start": 1, "end": 5, "buildMode": "fastgen-full"},
                {"start": 5, "end": 9, "buildMode": "fastgen-full-my-face"},
            ]})

    def test_cover_build_mode_ranges_resolve_by_visible_scenario_number(self):
        from scriptor import bridge

        settings = Settings(cover_build_mode="fastgen-full")
        settings.cover_build_mode_ranges = [
            {"start": 2, "end": 4, "buildMode": "fastgen-full-my-face"},
        ]
        self.assertEqual(
            bridge._cover_build_mode_for_item({"scenario_index": 3}, 0, settings),
            "fastgen-full-my-face",
        )
        self.assertEqual(
            bridge._cover_build_mode_for_item({"scenario_index": 7}, 6, settings),
            "fastgen-full",
        )

    def test_ai_reference_settings_are_saved_separately_from_fastgen_references(self):
        settings = Settings()
        with TemporaryDirectory() as directory:
            reference = Path(directory) / "ai.png"
            reference.write_bytes(b"png")
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={}):
                save_cover_settings({"referenceMode": "off", "aiReferenceMode": "all", "aiReferencePaths": [str(reference)]})
        self.assertEqual(settings.cover_reference_mode, "off")
        self.assertEqual(settings.cover_ai_reference_mode, "all")
        self.assertEqual(settings.cover_ai_reference_paths, [str(reference)])

    def test_ai_and_fastgen_reference_resolvers_stay_separate(self):
        settings = Settings()
        with TemporaryDirectory() as directory:
            ai_path = Path(directory) / "ai.png"
            fastgen_path = Path(directory) / "fastgen.png"
            ai_path.write_bytes(b"ai")
            fastgen_path.write_bytes(b"fastgen")
            settings.cover_ai_reference_mode = "all"
            settings.cover_ai_reference_paths = [str(ai_path)]
            settings.cover_reference_mode = "all"
            settings.cover_reference_paths = [str(fastgen_path)]
            item = {"title": "Ормуз", "scenario_index": 1}
            self.assertEqual(_cover_ai_reference_paths_for_item(item, 0, settings), [str(ai_path)])
            self.assertEqual(_cover_reference_paths_for_item(item, 0, settings), [str(fastgen_path)])

    def test_ai_reference_range_can_opt_in_to_fastgen_without_overwriting_fastgen_pack(self):
        from PIL import Image
        with TemporaryDirectory() as directory:
            ai_path = Path(directory) / "ai.png"
            Image.new("RGB", (700, 960), (20, 80, 140)).save(ai_path)
            settings = Settings(cover_reference_mode="off", cover_ai_reference_mode="ranges")
            settings.cover_ai_reference_ranges = [{"start": 7, "end": 8, "paths": [str(ai_path)], "sendToFastgen": True}]
            with patch("scriptor.bridge.app_data_root", return_value=Path(directory) / "app-data"):
                references, _face = _cover_references_for_item({"scenario_index": 7}, settings, position=6)
            self.assertEqual(len(references), 1)
            self.assertNotEqual(references[0], str(ai_path))

    def test_uploaded_visual_reference_is_attached_to_topic_for_prompt_and_render(self):
        from PIL import Image
        settings = Settings()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reference = root / "reference.png"
            Image.new("RGB", (1280, 720), (30, 80, 120)).save(reference)
            settings.cover_queue = [{"title": "Ормуз", "status": "Готово"}]
            with patch("scriptor.bridge.app_data_root", return_value=root / "app-data"), \
                 patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                patch("scriptor.bridge.snapshot", return_value={"ok": True}):
                result = select_cover_visual_reference({"index": 0, "path": str(reference)})
                self.assertTrue(Path(settings.cover_queue[0]["visual_reference_path"]).is_file())
        self.assertEqual(result["ok"], True)

    def test_uploaded_visual_reference_is_normalized_and_sent_to_fastgen_only_when_enabled(self):
        from PIL import Image
        settings = Settings()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "vertical-reference.png"
            Image.new("RGB", (630, 1100), (10, 90, 180)).save(source)
            settings.cover_queue = [{"title": "Ормуз", "status": "Готово"}]
            with patch("scriptor.bridge.app_data_root", return_value=root / "app-data"), \
                 patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={"ok": True}):
                select_cover_visual_reference({"index": 0, "path": str(source)})
                item = settings.cover_queue[0]
                normalized = Path(item["visual_reference_path"])
                self.assertTrue(normalized.is_file())
                with Image.open(normalized) as prepared:
                    self.assertEqual(prepared.size, (1920, 1080))
                self.assertFalse(item["visual_reference_to_fastgen"])
                self.assertNotIn(str(normalized), _cover_references_for_item(item, settings)[0])
                set_cover_visual_reference_target({"index": 0, "sendToFastgen": True})
                self.assertIn(str(normalized), _cover_references_for_item(settings.cover_queue[0], settings)[0])

    def test_every_scene_reference_sent_to_fastgen_is_normalized_without_touching_original(self):
        from PIL import Image
        settings = Settings(cover_reference_mode="all")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tall-channel-reference.png"
            Image.new("RGB", (640, 1200), (150, 60, 20)).save(source)
            settings.cover_reference_paths = [str(source)]
            with patch("scriptor.bridge.app_data_root", return_value=root / "app-data"):
                references, _ = _cover_references_for_item({"title": "Тема"}, settings)
                self.assertEqual(len(references), 1)
                self.assertNotEqual(references[0], str(source))
                prepared = Path(references[0])
                self.assertTrue(source.is_file())
                with Image.open(prepared) as image:
                    self.assertEqual(image.size, (1920, 1080))

    def test_gallery_scene_reference_is_normalized_before_fastgen_rerender(self):
        from PIL import Image
        settings = Settings()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "existing-gallery-cover.png"
            Image.new("RGB", (900, 900), (35, 90, 150)).save(selected)
            with patch("scriptor.bridge.app_data_root", return_value=root / "app-data"):
                references, _ = _cover_references_for_item(
                    {"title": "Тема", "selected_path": str(selected)}, settings,
                    refine=True, face_mode="without",
                )
                self.assertEqual(len(references), 1)
                self.assertNotEqual(references[0], str(selected))
                with Image.open(references[0]) as image:
                    self.assertEqual(image.size, (1920, 1080))

    def test_fastgen_text_rerender_uses_only_topics_with_words_and_prompts(self):
        settings = Settings()
        settings.cover_queue = [
            {"title": "Тегеран и Ормуз", "image_prompt": "scene", "cover_headline": "ОРМУЗ В ОГНЕ"},
            {"title": "Без слов", "image_prompt": "scene", "cover_headline": ""},
        ]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.generate_covers", return_value={"ok": True}) as render:
            self.assertEqual(render_cover_text_fastgen({"indices": [0, 1]}), {"ok": True})
        self.assertEqual(render.call_args.args[0]["indices"], [0])
        self.assertEqual(render.call_args.args[0]["textMode"], "fastgen")
        self.assertTrue(render.call_args.args[0]["localFaceOnly"])

    def test_each_saved_prompt_creates_its_own_cover_variant(self):
        """Two prepared prompts with one picture each are two cover images, not one selected-prompt render."""
        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "title": "Удар по промышленному объекту", "image_prompt": "first real scene",
            "image_prompt_options": ["first real scene", "second real scene"],
            "selected_prompt_index": 0,
        }]
        calls = []

        def render(prompt, *_args, **_kwargs):
            calls.append(prompt)
            return [Path(f"cover-{len(calls)}.png")]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render):
            generate_covers({"indices": [0], "textMode": "fastgen"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(settings.cover_queue[0]["paths"], ["cover-1.png", "cover-2.png"])

    def test_prompt_writer_fills_a_missing_second_prompt_with_a_safe_topic_variant(self):
        """The requested count is a contract even when the text model responds with a single option."""
        settings = Settings(cover_prompt_variant_count=2)
        settings.cover_queue = [{"title": "Ормуз и нефтяные танкеры", "script": ""}]

        async def one_prompt(*_args, **_kwargs):
            return '{"prompts":["Wide real tanker scene with reporters"],"recommended":1}'

        pool = SimpleNamespace(generate=one_prompt)
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=pool):
            generate_cover_prompts({"indices": [0], "provider": "agent"})
        self.assertEqual(len(settings.cover_queue[0]["image_prompt_options"]), 2)
        self.assertTrue(all(prompt.startswith("CORE STYLE:\n")
                            and "NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2." in prompt
                            for prompt in settings.cover_queue[0]["image_prompt_options"]))

    def test_prompt_writer_accepts_a_selected_topic_after_its_visual_prompt_was_deleted(self):
        """Ready headline text must not prevent rebuilding a missing visual prompt."""
        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [{
            "title": "Переговоры по тарифам", "script": "Контекст новости.",
            "cover_headline": "ТРАМП ДАВИТ", "headline_status": "READY",
            "headline_source": "AI", "status": "Промпт очищен",
        }]

        async def one_prompt(*_args, **_kwargs):
            return '{"prompts":["Press conference with tariff documents"],"recommended":1}'

        pool = SimpleNamespace(generate=one_prompt)
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=pool):
            generate_cover_prompts({"indices": [0], "provider": "agent"})

        self.assertTrue(settings.cover_queue[0]["image_prompt"].strip())

    def test_prompt_writer_keeps_an_existing_visual_prompt_without_explicit_regeneration(self):
        """The normal action is missing-only even when a headline is absent."""
        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [{
            "title": "Переговоры по тарифам", "script": "Контекст новости.",
            "image_prompt": "Existing approved visual brief",
            "image_prompt_options": ["Existing approved visual brief"],
        }]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                patch("scriptor.bridge.save_settings"), \
                patch("scriptor.bridge.snapshot", return_value={}), \
                patch("scriptor.bridge.HybridTextPool") as pool:
            result = generate_cover_prompts({"indices": [0], "provider": "agent"})

        pool.assert_not_called()
        self.assertEqual(result["operationResult"]["kind"], "cover-prompts")
        self.assertEqual(result["operationResult"]["count"], 0)

    def test_prompt_writer_dispatches_missing_topics_through_available_text_pool_slots(self):
        """Multiple active keys must make visual-prompt work concurrent, not serial."""
        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [
            {"title": f"Тема {index}", "script": "Контекст новости."}
            for index in range(4)
        ]
        active = maximum = 0

        async def generate(*_args, **_kwargs):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.02)
            active -= 1
            return '{"prompts":["Press conference with documents"],"recommended":1}'

        pool = SimpleNamespace(concurrency=4, generate=generate)
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=pool):
            generate_cover_prompts({"provider": "agent"})

        self.assertGreaterEqual(maximum, 2)

    def test_failed_fastgen_request_does_not_reuse_an_old_local_face_composite(self):
        """A FastGen network failure must remain an error, not turn an old cover into a false success."""
        settings = Settings(cover_auto_overlay_text=False)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "title": "Тегеран и Ормуз", "image_prompt": "scene",
            "face_composite_requested": True, "status": "Готово с текстом",
        }]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.time.sleep"), \
             patch("scriptor.bridge.FastGenPool.generate_media", side_effect=RuntimeError("timeout")), \
             patch("scriptor.bridge.compose_cover_faces") as compose:
            generate_covers({"indices": [0], "textMode": "fastgen"})
        self.assertEqual(settings.cover_queue[0]["status"], "Нужен новый промпт")
        self.assertEqual(settings.cover_queue[0]["generation_prebilling_attempt_count"], 4)
        self.assertIn("FastGen отклонил текущий prompt 4 раза", settings.cover_queue[0]["error"])
        self.assertFalse(settings.cover_queue[0]["face_composite_requested"])
        compose.assert_not_called()

    def test_transient_fastgen_failure_retries_and_finishes(self):
        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{"title": "Ормуз", "image_prompt": "scene"}]
        calls = []

        def render(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("network timeout")
            return [Path("ready.png")]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.time.sleep"), \
             patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render):
            generate_covers({"indices": [0]})
        self.assertEqual(len(calls), 2)
        self.assertEqual(settings.cover_queue[0]["status"], "Готово")
        self.assertEqual(settings.cover_queue[0]["generation_attempt"], 2)

    def test_new_prompts_use_local_fallback_when_provider_safety_filter_blocks(self):
        """A blocked LLM prompt request still produces a safe, renderable new prompt."""
        settings = Settings()
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.openai_api_keys = [OpenAIKey(label="test", secret="test")]
        settings.cover_queue = [{
            "title": "Тегеран усиливает давление на Ормузский пролив",
            "image_prompt": "старый prompt",
            "image_prompt_options": ["старый prompt"],
            "status": "Ошибка FastGen",
            "error": "Request blocked by provider safety filters",
        }]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool.generate", side_effect=RuntimeError("Request blocked by provider safety filters")), \
             patch("scriptor.bridge.generate_covers") as render:
            result = regenerate_covers_new_prompts({"indices": [0], "provider": "agent"})
        self.assertEqual(result["operationResult"]["kind"], "cover-prompts-rewritten")
        self.assertEqual(settings.cover_queue[0]["status"], "Новые промпты созданы")
        self.assertEqual(settings.cover_queue[0]["error"], "")
        self.assertTrue(settings.cover_queue[0]["image_prompt_options"])
        self.assertIn("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2", settings.cover_queue[0]["image_prompt"])
        self.assertNotIn("breaking-news", settings.cover_queue[0]["image_prompt"].casefold())
        render.assert_not_called()

    def test_resume_without_paused_items_returns_a_message_not_a_command_error(self):
        settings = Settings()
        settings.cover_queue = [{"title": "Готовая тема", "status": "Готово"}]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
             patch("scriptor.bridge._release_cover_generation_lock"), \
             patch("scriptor.bridge.snapshot", return_value={"covers": []}):
            result = generate_covers({"resumeOnly": True})
        self.assertEqual(result["operationResult"]["kind"], "cover-resume")
        self.assertEqual(result["operationResult"]["count"], 0)

    def test_select_cover_variant_accepts_a_stale_raw_path_after_face_composition(self):
        """A click rendered before local face composition must not become a remote-command error."""
        settings = Settings()
        raw = "D:/NewsFlow Studio/Обложки/raw.png"
        composite = "D:/NewsFlow Studio/Обложки/С лицами/final.png"
        settings.cover_queue = [{
            "title": "Ормуз", "paths": [composite], "raw_paths": [raw],
            "face_composite_paths": [composite], "selected_path": composite,
        }]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={"ok": True}):
            result = select_cover_variant({"index": 0, "path": raw})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(settings.cover_queue[0]["selected_path"], raw)

    def test_remove_one_stale_raw_variant_after_face_composition(self):
        """One old visible raw variant can be deleted without deleting its composed sibling."""
        with TemporaryDirectory() as directory:
            output = Path(directory)
            raw = output / "raw.png"
            final = output / "final.png"
            raw.write_bytes(b"raw")
            final.write_bytes(b"final")
            settings = Settings(cover_output_folder=str(output))
            settings.cover_queue = [{
                "title": "Ормуз", "paths": [str(final)], "raw_paths": [str(raw)],
                "face_composite_paths": [str(final)], "selected_path": str(final),
            }]
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                 patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                 patch("scriptor.bridge.save_settings"), \
                 patch("scriptor.bridge.snapshot", return_value={"ok": True}):
                result = remove_cover_image({"index": 0, "path": str(raw)})
            self.assertEqual(result["operationResult"]["count"], 1)
            self.assertTrue(final.is_file())
            self.assertFalse(raw.exists())


class CoverBulkTextPromptReliabilityTests(unittest.TestCase):
    @staticmethod
    def _current_row(**values):
        return {
            "production_item_id": "production:0",
            "title": "Порт закрыт из-за кризиса",
            "script": "Контейнеры застряли на терминале и ждут решения.",
            **values,
        }

    def test_complete_scopes_are_successful_no_ops_for_words_and_prompts(self):
        from scriptor import bridge

        cases = (
            (bridge.generate_cover_headlines, self._current_row(
                cover_headline="ПОРТ ЗАКРЫТ", headline_status="READY", headline_source="AI",
            ), "cover-headlines"),
            (bridge.generate_cover_subheadlines, self._current_row(
                cover_headline="ПОРТ ЗАКРЫТ", headline_status="READY",
                cover_subheadline="Контейнеры ждут решения", subheadline_status="READY", subheadline_source="AI",
            ), "cover-subheadlines"),
            (bridge.generate_cover_prompts, self._current_row(
                image_prompt="Existing visual brief", image_prompt_options=["Existing visual brief"],
            ), "cover-prompts"),
        )
        for action, row, result_kind in cases:
            with self.subTest(action=action.__name__):
                settings = Settings()
                settings.cover_queue = [row]
                with patch("scriptor.bridge.load_settings", return_value=settings), \
                     patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                     patch("scriptor.bridge.snapshot", return_value={"covers": []}):
                    result = action({
                        "indices": [0], "productionItemIds": ["production:0"], "provider": "agent",
                    })
                self.assertEqual(result["operationResult"]["kind"], result_kind)
                self.assertEqual(result["operationResult"]["count"], 0)

    def test_blank_current_cover_id_reaches_all_generation_entry_points_selected_and_all(self):
        """Prompt/headline/subheadline actions must not reject the visible current RC row."""
        from scriptor import bridge
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        title = "Ручная текущая тема"
        job = Job(
            ScenarioRequest(0, title, "", "production:current"),
            RunState.DONE,
            "Текущий сценарий",
        )
        cases = (
            (bridge.generate_cover_headlines, {
                "cover_headline": "ПОРТ ЗАКРЫТ",
                "headline_status": "READY",
                "headline_source": "AI",
            }, "cover-headlines"),
            (bridge.generate_cover_subheadlines, {
                "cover_headline": "ПОРТ ЗАКРЫТ",
                "headline_status": "READY",
                "cover_subheadline": "Контейнеры ждут решения",
                "subheadline_status": "READY",
                "subheadline_source": "AI",
            }, "cover-subheadlines"),
            (bridge.generate_cover_prompts, {
                "image_prompt": "Existing visual brief",
                "image_prompt_options": ["Existing visual brief"],
            }, "cover-prompts"),
        )
        scopes = (
            {"indices": [0], "productionItemIds": ["production:current"], "provider": "agent"},
            {"provider": "agent"},
        )

        for action, ready_fields, result_kind in cases:
            for payload in scopes:
                with self.subTest(action=action.__name__, selected=bool(payload.get("indices"))):
                    settings = Settings()
                    settings.cover_queue = [{
                        "title": title,
                        "scenario_index": 1,
                        "script": "Текущий сценарий",
                        "production_item_id": "",
                        **ready_fields,
                    }]

                    def hydrate(current_settings):
                        return bridge._sync_current_scenario_covers(current_settings)

                    with patch("scriptor.bridge.load_settings", return_value=settings), \
                         patch("scriptor.bridge.load_session", return_value=([title], [job])), \
                         patch("scriptor.bridge._hydrate_cover_library", side_effect=hydrate), \
                         patch("scriptor.bridge.snapshot", return_value={"covers": []}):
                        result = action(payload)

                    self.assertEqual(settings.cover_queue[0]["production_item_id"], "production:current")
                    self.assertEqual(result["operationResult"]["kind"], result_kind)
                    self.assertEqual(result["operationResult"]["count"], 0)

    def test_current_session_job_adopts_blank_cover_id_for_selected_and_all_scope(self):
        """Old RC rows without an ID become the current row, not an unselectable ghost."""
        from scriptor import bridge
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        title = "Ручная текущая тема"
        settings = Settings()
        settings.cover_queue = [{
            "title": title,
            "scenario_index": 1,
            "script": "Текущий сценарий",
            "production_item_id": "",
        }]
        job = Job(
            ScenarioRequest(0, title, "", "production:current"),
            RunState.DONE,
            "Текущий сценарий",
        )

        with patch("scriptor.bridge.load_session", return_value=([title], [job])):
            changed = bridge._sync_current_scenario_covers(settings)
            selected = bridge._current_cover_generation_scope(
                settings,
                {"indices": [0], "productionItemIds": ["production:current"]},
                "Выберите сценарии",
            )
            all_rows = bridge._current_cover_generation_scope(
                settings, {}, "Выберите сценарии",
            )

        self.assertTrue(changed)
        self.assertEqual(settings.cover_queue[0]["production_item_id"], "production:current")
        self.assertEqual([index for index, _item in selected], [0])
        self.assertEqual([index for index, _item in all_rows], [0])

    def test_stale_nonempty_cover_id_is_not_reauthorized_by_matching_title(self):
        """A historical ID never becomes current merely because its title matches."""
        from scriptor import bridge
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState

        title = "Повторяющийся заголовок"
        settings = Settings()
        settings.cover_queue = [{
            "title": title,
            "scenario_index": 1,
            "script": "Старый текст",
            "production_item_id": "legacy-cover:old",
        }]
        job = Job(
            ScenarioRequest(0, title, "", "production:new"),
            RunState.DONE,
            "Новый текущий текст",
        )

        with patch("scriptor.bridge.load_session", return_value=([title], [job])):
            bridge._sync_current_scenario_covers(settings)

        self.assertEqual(len(settings.cover_queue), 1)
        self.assertEqual(settings.cover_queue[0]["production_item_id"], "production:new")
        self.assertEqual(settings.cover_queue[0]["script"], "Новый текущий текст")

    def test_partial_stale_selected_scope_is_rejected_before_any_generation(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [
            self._current_row(production_item_id="production:0"),
            self._current_row(production_item_id="production:1", title="Устаревшая тема"),
        ]
        settings.idea_deleted_production_ids = ["production:1"]
        payload = {
            "indices": [0, 1],
            "productionItemIds": ["production:0", "production:1"],
            "provider": "agent",
        }

        with self.assertRaisesRegex(ValueError, "устарела"):
            bridge._current_cover_generation_scope(settings, payload, "Выберите сценарии")

    def test_selected_index_id_mismatch_rejects_prompt_batch_before_provider_call(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [
            self._current_row(production_item_id="production:0"),
            self._current_row(production_item_id="production:1", title="Вторая тема"),
        ]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            raise AssertionError("provider must not be called for stale selected scope")

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)), \
             self.assertRaisesRegex(ValueError, "устарела"):
            bridge.generate_cover_prompts({
                "indices": [0, 1],
                "productionItemIds": ["production:0", "production:wrong"],
                "provider": "agent",
            })

        self.assertEqual(calls, [])

    def test_paired_action_continues_when_headlines_need_no_work_and_reports_summary(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            cover_headline="ПОРТ ЗАКРЫТ", headline_status="READY", headline_source="AI",
        )]

        async def generated(_pool, kind, *_args, **_kwargs):
            self.assertEqual(kind, "subheadline")
            return "Контейнеры ждут решения", {"semantic_slots": ["object"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={"covers": []}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            result = bridge.generate_cover_texts({
                "indices": [0], "productionItemIds": ["production:0"], "provider": "agent",
            })

        self.assertEqual(settings.cover_queue[0]["subheadline_status"], "READY")
        self.assertEqual(result["operationResult"], {
            "kind": "cover-texts", "count": 1, "requested": 1, "current": 1,
            "headlineReady": 1, "subheadlineReady": 1, "failed": 0,
            "message": "Тексты обложек: 1/1 готовы, ошибок: 0.",
        })

    def test_paired_summary_reads_the_state_persisted_by_both_generation_phases(self):
        from copy import deepcopy

        from scriptor import bridge

        stored = [Settings()]
        stored[0].cover_queue = [self._current_row()]

        def load():
            return deepcopy(stored[0])

        def save(settings):
            stored[0] = deepcopy(settings)

        async def generated(_pool, kind, *_args, **_kwargs):
            value = "ПОРТ ЗАКРЫТ" if kind == "headline" else "Контейнеры ждут решения"
            return value, {"semantic_slots": ["object"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", side_effect=load), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state", side_effect=save), \
             patch("scriptor.bridge._save_cover_text_progress", side_effect=save), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            result = bridge.generate_cover_texts({"provider": "agent"})

        self.assertEqual(result["operationResult"]["headlineReady"], 1)
        self.assertEqual(result["operationResult"]["subheadlineReady"], 1)
        self.assertEqual(result["operationResult"]["count"], 1)

    def test_cover_word_transient_failures_retry_twice_then_finish_ready(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row()]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("temporary network timeout")
            return json.dumps({"headline": "ПОРТ ЗАКРЫТ"}, ensure_ascii=False)

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_headlines({"provider": "agent"})

        self.assertEqual(len(calls), 3)
        self.assertEqual(settings.cover_queue[0]["headline_status"], "READY")
        self.assertEqual(settings.cover_queue[0]["headline_provider_attempt_count"], 3)

    def test_cover_word_permanent_failure_is_not_retried(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row()]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            raise RuntimeError("invalid provider request")

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_headlines({"provider": "agent"})

        self.assertEqual(len(calls), 1)
        self.assertEqual(settings.cover_queue[0]["headline_status"], "FAILED")
        self.assertEqual(settings.cover_queue[0]["headline_provider_attempt_count"], 1)
        self.assertIn("invalid provider request", settings.cover_queue[0]["headline_error"])

    def test_cover_word_four_transient_failures_end_explicitly(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row()]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            raise RuntimeError("503 temporary unavailable")

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_headlines({"provider": "agent"})

        self.assertEqual(len(calls), 4)
        self.assertEqual(settings.cover_queue[0]["headline_status"], "FAILED")
        self.assertEqual(settings.cover_queue[0]["headline_provider_attempt_count"], 4)
        self.assertTrue(settings.cover_queue[0]["headline_error"])

    def test_prompt_selected_identity_and_transient_retry_finish_ready(self):
        from scriptor import bridge

        settings = Settings(cover_prompt_variant_count=2)
        settings.cover_queue = [
            self._current_row(production_item_id="production:0", title="Не выбранная тема"),
            self._current_row(production_item_id="production:1", title="Выбранная тема"),
        ]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("429 temporary")
            return '{"prompts":["Real press scene with documents and reporters"],"recommended":1}'

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_prompts({
                "indices": [1], "productionItemIds": ["production:1"], "provider": "agent",
            })

        self.assertEqual(len(calls), 2)
        self.assertNotIn("image_prompt", settings.cover_queue[0])
        self.assertEqual(settings.cover_queue[1]["status"], "Промпты готовы")
        self.assertEqual(len(settings.cover_queue[1]["image_prompt_options"]), 2)
        self.assertEqual(settings.cover_queue[1]["prompt_provider_attempt_count"], 2)

    def test_prompt_batch_uses_each_rows_current_headline_and_subheadline(self):
        from scriptor import bridge

        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [
            self._current_row(
                production_item_id="production:putin",
                title="Владимир Путин обсуждает энергетику",
                cover_headline="ЭНЕРГИЯ ПОД КОНТРОЛЕМ",
                cover_subheadline="Новые решения для рынка",
            ),
            self._current_row(
                production_item_id="production:trump",
                title="Дональд Трамп выступает на форуме",
                cover_headline="ТРАМП МЕНЯЕТ КУРС",
                cover_subheadline="Форум обсуждает новую стратегию",
            ),
        ]
        prompts = []

        async def generate(prompt, **_kwargs):
            prompts.append(prompt)
            return '{"prompts":["Real conference scene with cameras and policy documents"],"recommended":1}'

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_prompts({
                "indices": [0, 1],
                "productionItemIds": ["production:putin", "production:trump"],
                "provider": "agent",
            })

        self.assertEqual(len(prompts), 2)
        putin_prompt = next(prompt for prompt in prompts if "ЭНЕРГИЯ ПОД КОНТРОЛЕМ" in prompt)
        trump_prompt = next(prompt for prompt in prompts if "ТРАМП МЕНЯЕТ КУРС" in prompt)
        self.assertIn("Новые решения для рынка", putin_prompt)
        self.assertNotIn("ТРАМП МЕНЯЕТ КУРС", putin_prompt)
        self.assertNotIn("Форум обсуждает новую стратегию", putin_prompt)
        self.assertIn("Форум обсуждает новую стратегию", trump_prompt)
        self.assertNotIn("ЭНЕРГИЯ ПОД КОНТРОЛЕМ", trump_prompt)
        self.assertNotIn("Новые решения для рынка", trump_prompt)

    def test_changed_cover_text_makes_old_new_prompt_status_stale_until_rewrite(self):
        from scriptor import bridge

        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [self._current_row(
            cover_headline="СТАРЫЙ ЗАГОЛОВОК",
            cover_subheadline="Старая вторая строка",
            image_prompt="Old visual brief",
            image_prompt_options=["Old visual brief"],
            status="Новые промпты созданы",
        )]
        prompts = []

        async def generate(prompt, **_kwargs):
            prompts.append(prompt)
            return '{"prompts":["New press scene with documents and cameras"],"recommended":1}'

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.save_cover_headline({"index": 0, "headline": "НОВЫЙ ЗАГОЛОВОК"})
            bridge.save_cover_subheadline({"index": 0, "subheadline": "Текущая вторая строка"})

            self.assertEqual(settings.cover_queue[0]["status"], "Промпты устарели")

            bridge.generate_cover_prompts({
                "indices": [0],
                "productionItemIds": ["production:0"],
                "provider": "agent",
                "rewrite": True,
            })

        self.assertEqual(len(prompts), 1)
        self.assertIn("НОВЫЙ ЗАГОЛОВОК", prompts[0])
        self.assertIn("Текущая вторая строка", prompts[0])
        self.assertNotIn("СТАРЫЙ ЗАГОЛОВОК", prompts[0])
        self.assertNotIn("Старая вторая строка", prompts[0])
        self.assertTrue(settings.cover_queue[0]["prompt_text_signature"])

    def test_prompt_permanent_failure_is_terminal_after_one_attempt(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row()]
        calls = []

        async def generate(*_args, **_kwargs):
            calls.append(1)
            raise RuntimeError("invalid provider request")

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_prompts({"provider": "agent"})

        self.assertEqual(len(calls), 1)
        self.assertEqual(settings.cover_queue[0]["status"], "Ошибка промпта")
        self.assertEqual(settings.cover_queue[0]["prompt_provider_attempt_count"], 1)
        self.assertTrue(settings.cover_queue[0]["error"])

    def test_fifty_topic_pair_batch_has_no_silent_omissions(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            production_item_id=f"production:{index}", title=f"Тема {index}",
        ) for index in range(50)]

        async def generated(_pool, kind, *_args, **_kwargs):
            value = "ГОТОВЫЙ ЗАГОЛОВОК" if kind == "headline" else "Готовый точный подзаголовок"
            return value, {"semantic_slots": ["subject"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            result = bridge.generate_cover_texts({"provider": "agent"})

        self.assertEqual(result["operationResult"]["headlineReady"], 50)
        self.assertEqual(result["operationResult"]["subheadlineReady"], 50)
        self.assertTrue(all(row.get("cover_headline") and row.get("headline_status") == "READY"
                            for row in settings.cover_queue))
        self.assertTrue(all(row.get("cover_subheadline") and row.get("subheadline_status") == "READY"
                            for row in settings.cover_queue))

    def test_fifty_topic_prompt_batch_has_no_silent_omissions(self):
        from scriptor import bridge

        settings = Settings(cover_prompt_variant_count=2)
        settings.cover_queue = [self._current_row(
            production_item_id=f"production:{index}", title=f"Тема {index}",
        ) for index in range(50)]

        async def generate(*_args, **_kwargs):
            return '{"prompts":["Real press scene with documents and reporters"],"recommended":1}'

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace(generate=generate)):
            bridge.generate_cover_prompts({"provider": "agent"})

        self.assertTrue(all(row.get("image_prompt") and len(row.get("image_prompt_options", [])) == 2
                            and row.get("status") == "Промпты готовы" for row in settings.cover_queue))

    def test_pause_flags_are_persisted_independently(self):
        from scriptor import bridge

        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge.snapshot", return_value={}):
            bridge.set_cover_text_pause({"kind": "headline"}, True)
            self.assertTrue(settings.cover_headlines_paused)
            self.assertFalse(settings.cover_subheadlines_paused)
            bridge.set_cover_text_pause({"kind": "subheadline"}, True)
            bridge.set_cover_text_pause({"kind": "headline"}, False)

        self.assertFalse(settings.cover_headlines_paused)
        self.assertTrue(settings.cover_subheadlines_paused)

    def test_paired_action_preserves_manual_values_without_force(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            cover_headline="РУЧНОЙ ЗАГОЛОВОК", headline_status="MANUAL", headline_source="MANUAL",
            cover_subheadline="Ручной подзаголовок", subheadline_status="MANUAL", subheadline_source="MANUAL",
        )]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool") as pool:
            result = bridge.generate_cover_texts({"provider": "agent"})

        pool.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "РУЧНОЙ ЗАГОЛОВОК")
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "Ручной подзаголовок")
        self.assertEqual(result["operationResult"]["count"], 1)

    def test_force_repair_does_not_replace_manual_cover_text_without_explicit_override(self):
        """A normal retry repairs missing AI text, never words explicitly typed by the operator."""
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            cover_headline="РУЧНОЙ ЗАГОЛОВОК", headline_status="MANUAL", headline_source="MANUAL",
            cover_subheadline="Ручной подзаголовок", subheadline_status="MANUAL", subheadline_source="MANUAL",
        )]
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool") as pool:
            result = bridge.generate_cover_texts({"provider": "agent", "force": True, "regenerate": True})

        pool.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "РУЧНОЙ ЗАГОЛОВОК")
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "Ручной подзаголовок")
        self.assertEqual(result["operationResult"]["count"], 1)

    def test_explicit_replace_manual_action_can_replace_both_manual_fields(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            cover_headline="РУЧНОЙ ЗАГОЛОВОК", headline_status="MANUAL", headline_source="MANUAL",
            cover_subheadline="Ручной подзаголовок", subheadline_status="MANUAL", subheadline_source="MANUAL",
        )]

        async def generated(_pool, kind, *_args, **_kwargs):
            value = "НОВЫЙ ЗАГОЛОВОК" if kind == "headline" else "Новая вторая строка"
            return value, {"semantic_slots": ["subject"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            bridge.generate_cover_texts({"provider": "agent", "replaceManual": True})

        self.assertEqual(settings.cover_queue[0]["cover_headline"], "НОВЫЙ ЗАГОЛОВОК")
        self.assertEqual(settings.cover_queue[0]["headline_source"], "AI")
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "Новая вторая строка")
        self.assertEqual(settings.cover_queue[0]["subheadline_source"], "AI")

    def test_pair_repair_generates_only_the_missing_subheadline(self):
        """Repair must retain the valid neighbouring field and issue one provider request."""
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            cover_headline="РУЧНОЙ ЗАГОЛОВОК", headline_status="MANUAL", headline_source="MANUAL",
        )]
        calls: list[str] = []

        async def generated(_pool, kind, *_args, **_kwargs):
            calls.append(kind)
            return "Новая вторая строка", {"semantic_slots": ["action"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            result = bridge.generate_cover_texts({"provider": "agent"})

        self.assertEqual(calls, ["subheadline"])
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "РУЧНОЙ ЗАГОЛОВОК")
        self.assertEqual(settings.cover_queue[0]["headline_source"], "MANUAL")
        self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "Новая вторая строка")
        self.assertEqual(result["operationResult"]["count"], 1)

    def test_repair_fills_an_explicitly_cleared_manual_field(self):
        """A blank manual field is missing content, not an immutable override."""
        from scriptor import bridge

        item = self._current_row(
            cover_headline="", headline_status="MANUAL", headline_source="MANUAL",
            cover_subheadline="Ручной подзаголовок", subheadline_status="MANUAL", subheadline_source="MANUAL",
        )

        self.assertTrue(bridge._cover_word_should_generate(item, "headline"))
        self.assertFalse(bridge._cover_word_should_generate(item, "subheadline"))

    def test_mass_pair_batch_marks_one_terminal_failure_instead_of_leaving_a_hole(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [self._current_row(
            production_item_id=f"production:{index}", title=f"Тема {index}",
        ) for index in range(50)]

        async def generated(_pool, kind, item, *_args, **_kwargs):
            if kind == "headline" and item["production_item_id"] == "production:17":
                raise RuntimeError("503 temporary unavailable after 4 attempts")
            value = "ГОТОВЫЙ ЗАГОЛОВОК" if kind == "headline" else "Готовый точный подзаголовок"
            return value, {"semantic_slots": ["subject"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            result = bridge.generate_cover_texts({"provider": "agent"})

        failed = settings.cover_queue[17]
        self.assertEqual(failed["headline_status"], "FAILED")
        self.assertTrue(failed["headline_error"])
        self.assertEqual(failed["subheadline_status"], "FAILED")
        self.assertIn("Headline unavailable", failed["subheadline_error"])
        self.assertEqual(result["operationResult"]["failed"], 1)

    def test_paused_word_worker_waits_before_issuing_provider_request(self):
        from scriptor import bridge

        paused = Settings(cover_headlines_paused=True)
        resumed = Settings(cover_headlines_paused=False)
        events = []

        async def no_delay(_seconds):
            events.append("waited")

        class FakePool:
            async def generate(self, _prompt, before_request=None):
                if before_request:
                    await before_request()
                events.append("requested")
                return "ok"

        provider = bridge._BoundedCoverTextProvider(FakePool(), lambda attempt: events.append(attempt))
        with patch("scriptor.bridge.load_settings", side_effect=[paused, resumed]), \
             patch("scriptor.bridge.asyncio.sleep", side_effect=no_delay):
            result = asyncio.run(provider.generate(
                "prompt", before_request=lambda: bridge._wait_for_cover_text_resume("headline"),
            ))

        self.assertEqual(result, "ok")
        self.assertEqual(events, [1, "waited", "requested"])

    def test_resume_only_generates_remaining_headline_rows(self):
        from scriptor import bridge

        settings = Settings()
        settings.cover_queue = [
            self._current_row(production_item_id="production:ready", cover_headline="ГОТОВО",
                              headline_status="READY", headline_source="AI"),
            self._current_row(production_item_id="production:missing", title="Порт снова закрыт"),
        ]
        generated_ids = []

        async def generated(_pool, _kind, item, *_args, **_kwargs):
            generated_ids.append(item["production_item_id"])
            return "ПОРТ ЗАКРЫТ", {"semantic_slots": ["object"], "valid": True}, [{"attempt": 1}]

        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
             patch("scriptor.bridge._save_cover_state"), \
             patch("scriptor.bridge._save_cover_text_progress"), \
             patch("scriptor.bridge.snapshot", return_value={}), \
             patch("scriptor.bridge.HybridTextPool", return_value=SimpleNamespace()), \
             patch("scriptor.bridge._generate_cover_word_v2", side_effect=generated):
            bridge.generate_cover_headlines({"provider": "agent"})

        self.assertEqual(generated_ids, ["production:missing"])
        self.assertEqual(settings.cover_queue[0]["cover_headline"], "ГОТОВО")


class CoverRenderQueueSafetyTests(unittest.TestCase):
    @staticmethod
    def _row(index: int, **values):
        return {
            "production_item_id": f"production:{index}",
            "title": f"Тема {index}",
            "image_prompt": f"Новая сцена {index}",
            **values,
        }

    def test_regenerate_preserves_index_to_production_item_order(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[
            self._row(0, production_item_id="production:z"),
            self._row(1, production_item_id="production:a"),
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "generate_covers", return_value={}) as generate:
            regenerate_covers({
                "indices": [0, 1],
                "productionItemIds": ["production:z", "production:a"],
            })

        self.assertEqual(generate.call_args.args[0]["indices"], [0, 1])
        self.assertEqual(generate.call_args.args[0]["productionItemIds"], ["production:z", "production:a"])

    def test_new_prompt_regeneration_preserves_index_to_production_item_order(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[
            self._row(0, production_item_id="production:z"),
            self._row(1, production_item_id="production:a"),
        ])

        def rewrite(payload):
            for index in payload["indices"]:
                settings.cover_queue[index].update(image_prompt=f"Переписанная сцена {index}", error="")
            return {}

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "generate_cover_prompts", side_effect=rewrite) as generate:
            regenerate_covers_new_prompts({
                "indices": [0, 1],
                "productionItemIds": ["production:z", "production:a"],
                "provider": "agent",
            })

        self.assertEqual(generate.call_args.args[0]["indices"], [0, 1])
        self.assertEqual(generate.call_args.args[0]["productionItemIds"], ["production:z", "production:a"])


    def test_manual_retry_preserves_current_prompt_text_face_and_render_profile(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            old_path = Path(temporary) / "old.png"
            old_path.write_bytes(b"old")
            face_path = Path(temporary) / "same-face.png"
            face_path.write_bytes(b"face")
            settings = Settings(cover_output_folder=temporary, cover_queue=[self._row(
                0,
                status="Нужен новый промпт",
                error="FastGen отклонил текущий prompt 4 раза",
                image_prompt="Keep this exact visual prompt",
                image_prompt_options=["Keep this exact visual prompt"],
                final_provider_prompt="SAVED FINAL PROMPT",
                final_provider_prompt_options=["SAVED FINAL PROMPT"],
                final_provider_reference_paths=[str(face_path)],
                final_provider_face_label="Текущий человек",
                final_provider_face_reference_count=1,
                cover_headline="ТЕКУЩИЙ ЗАГОЛОВОК",
                cover_subheadline="Текущая вторая строка",
                face_reference_path=str(face_path),
                face_reference_label="Текущий человек",
                face_reference_source="auto",
                face_reference_count=1,
                render_profile={
                    "build_mode": "fastgen-full-my-face",
                    "face_mode": "auto",
                    "text_mode": "fastgen",
                    "local_face_only": False,
                    "operation": "reference_image_edit",
                },
                path=str(old_path),
                paths=[str(old_path)],
                selected_path=str(old_path),
                generation_prebilling_attempt_count=4,
                generation_history=[{"status": "failed"}],
            )])

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "generate_covers", return_value={}) as render:
                bridge.retry_cover_generation({
                    "indices": [0], "productionItemIds": ["production:0"],
                })
                self.assertFalse(old_path.exists())

        render.assert_called_once_with({
            "indices": [0],
            "productionItemIds": ["production:0"],
            "buildMode": "fastgen-full-my-face",
            "faceMode": "auto",
            "textMode": "fastgen",
            "localFaceOnly": False,
            "operation": "reference_image_edit",
            "repeatCurrentContract": True,
        })
        row = settings.cover_queue[0]
        self.assertEqual(row["image_prompt"], "Keep this exact visual prompt")
        self.assertEqual(row["final_provider_prompt"], "SAVED FINAL PROMPT")
        self.assertEqual(row["cover_headline"], "ТЕКУЩИЙ ЗАГОЛОВОК")
        self.assertEqual(row["cover_subheadline"], "Текущая вторая строка")
        self.assertEqual(row["face_reference_path"], str(face_path))
        self.assertEqual(row["render_profile"]["operation"], "reference_image_edit")
        self.assertEqual(row["paths"], [])
        self.assertNotIn("generation_prebilling_attempt_count", row)
        self.assertNotIn("generation_history", row)

    def test_manual_retry_rejects_active_or_mixed_selection_without_partial_render(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[
            self._row(0, status="Ошибка FastGen", error="terminal"),
            self._row(1, status="Подготовка запросов", error=""),
            self._row(2, status="Ошибка FastGen", error="polling interrupted",
                      accepted_generation_id="task-1"),
        ])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "regenerate_covers") as render, \
             self.assertRaisesRegex(ValueError, "недоступен"):
            bridge.retry_cover_generation({
                    "indices": [0, 1, 2],
                    "productionItemIds": ["production:0", "production:1", "production:2"],
            })

        render.assert_not_called()

    def test_fastgen_full_batch_sends_each_rows_face_and_exact_text_without_local_compositors(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            faces = [root / "person-a.png", root / "person-b.png"]
            for face in faces:
                face.write_bytes(b"prepared-face")
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=True,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 1, "max": 2},
            }]}
            settings.cover_queue = [
                self._row(
                    0,
                    image_prompt="Current scene A",
                    cover_headline="ТОЧНЫЙ ЗАГОЛОВОК A",
                    cover_subheadline="Точная вторая строка A",
                    face_reference_path=str(faces[0]),
                    face_reference_label="Person A",
                    face_reference_source="manual",
                ),
                self._row(
                    1,
                    image_prompt="Current scene B",
                    cover_headline="ТОЧНЫЙ ЗАГОЛОВОК B",
                    cover_subheadline="Точная вторая строка B",
                    face_reference_path=str(faces[1]),
                    face_reference_label="Person B",
                    face_reference_source="manual",
                ),
            ]
            calls = []

            def render(prompt, _output, stem, operation, _ratio, **kwargs):
                calls.append({
                    "prompt": prompt,
                    "operation": operation,
                    "references": tuple(str(path) for path in kwargs.get("references") or []),
                })
                return [root / f"{stem}.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render), \
                 patch.object(bridge, "compose_cover_faces") as compose, \
                 patch.object(bridge, "render_cover_text") as overlay:
                bridge.generate_covers({
                    "indices": [0, 1],
                    "productionItemIds": ["production:0", "production:1"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "with",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "operation": "reference_image_edit",
                })

        self.assertEqual(len(calls), 2)
        for index, call in enumerate(calls):
            self.assertEqual(call["operation"], "reference_image_edit")
            self.assertEqual(call["references"], (str(faces[index]),))
            self.assertIn(f"HEADLINE:\n<exact-text>ТОЧНЫЙ ЗАГОЛОВОК {'AB'[index]}</exact-text>", call["prompt"])
            self.assertIn(f"SUBHEADLINE:\n<exact-text>Точная вторая строка {'AB'[index]}</exact-text>", call["prompt"])
            self.assertIn("Do not add punctuation", call["prompt"])
            self.assertEqual(settings.cover_queue[index]["status"], "Готово")
        compose.assert_not_called()
        overlay.assert_not_called()

    def test_fastgen_full_transports_explicit_visual_references_and_keeps_them_content_only_guidance(self):
        from PIL import Image

        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            reference = root / "style.png"
            Image.new("RGB", (640, 360), (20, 60, 90)).save(reference)
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
                cover_fastgen_use_references=True,
                cover_fastgen_reference_paths=[str(reference)],
                cover_fastgen_reference_mode_style=True,
                cover_fastgen_reference_mode_composition=True,
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
            }]}
            settings.cover_queue = [self._row(
                0, title="Переговоры в парламенте", image_prompt="Parliament negotiation scene",
                cover_headline="ПЕРЕГОВОРЫ ПОД УГРОЗОЙ", cover_subheadline="Стороны ждут решения",
            )]
            calls = []

            def render(prompt, _output, _stem, _operation, _ratio, **kwargs):
                calls.append((prompt, tuple(str(path) for path in kwargs.get("references") or [])))
                return [root / "provider.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_prepare_cover_visual_reference", side_effect=lambda path: path), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": [0], "productionItemIds": ["production:0"], "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full", "faceMode": "without", "textMode": "fastgen",
                    "localFaceOnly": False, "operation": "reference_image_edit",
                })

        self.assertEqual(calls[0][1], (str(reference),))
        self.assertIn("REFERENCE = VISUAL GUIDANCE ONLY", calls[0][0])
        self.assertIn("PRODUCTIONITEM = SOURCE OF TRUTH FOR CONTENT", calls[0][0])
        self.assertEqual(settings.cover_queue[0]["reference_final_provider_count"], 1)

    def test_two_fastgen_routes_keep_trump_zelensky_cover_words_and_only_my_faces_uploads_portrait(self):
        """The visible routes differ only by one explicit remote face reference."""
        from scriptor import bridge

        rows = (
            {
                "title": "ТРАМП ДАВИТ НА ЗЕЛЕНСКОГО — переговоры по Украине меняют тон — Киеву ставят новые условия",
                "cover_headline": "ТРАМП ДАВИТ",
                "cover_subheadline": "НОВЫЕ УСЛОВИЯ КИЕВУ",
                "build_mode": "fastgen-full",
                "face_label": "Дональд Трамп",
                "expect_reference": False,
            },
            {
                "title": "ЗЕЛЕНСКИЙ НЕ УСТУПАЕТ ТРАМПУ — спор вокруг Украины обостряется — помощь США под вопросом",
                "cover_headline": "ЗЕЛЕНСКИЙ НЕ СДАЁТСЯ",
                "cover_subheadline": "ПОМОЩЬ США ПОД ВОПРОСОМ",
                "build_mode": "fastgen-full-my-face",
                "face_label": "Владимир Зеленский",
                "expect_reference": True,
            },
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            face = root / "zelensky-prepared.png"
            face.write_bytes(b"prepared-face")
            for row in rows:
                settings = Settings(
                    cover_output_folder=temporary,
                    cover_variant_count=1,
                    cover_operation="reference_image_edit",
                )
                settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
                settings.fastgen_capabilities_cache = {"image": [{
                    "id": "reference_image_edit", "inputs": {"min": 0, "max": 2},
                }]}
                settings.cover_queue = [self._row(
                    0,
                    title=row["title"],
                    image_prompt="Topic-accurate editorial news scene",
                    cover_headline=row["cover_headline"],
                    cover_subheadline=row["cover_subheadline"],
                    selected_people=[row["face_label"]],
                    face_reference_path=str(face),
                    face_reference_label=row["face_label"],
                    face_reference_source="manual",
                )]
                calls = []

                def render(prompt, _output, _stem, _operation, _ratio, *, _calls=calls,
                           _root=root, _mode=row["build_mode"], **kwargs):
                    _calls.append((prompt, tuple(str(path) for path in kwargs.get("references") or [])))
                    return [_root / f"{_mode}.png"]

                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                     patch.object(bridge, "_save_cover_state"), \
                     patch.object(bridge, "snapshot", return_value={}), \
                     patch.object(bridge.FastGenPool, "generate_media", side_effect=render), \
                     patch.object(bridge, "compose_cover_faces") as compose:
                    bridge.generate_covers({
                        "indices": [0], "productionItemIds": ["production:0"],
                        "_parallel_cover_worker": True, "buildMode": row["build_mode"],
                        "faceMode": "auto", "textMode": "fastgen", "localFaceOnly": False,
                        "operation": "reference_image_edit",
                    })

                self.assertEqual(len(calls), 1)
                self.assertIn(f"<exact-text>{row['cover_headline']}</exact-text>", calls[0][0])
                self.assertIn(f"<exact-text>{row['cover_subheadline']}</exact-text>", calls[0][0])
                self.assertEqual(calls[0][1], (str(face),) if row["expect_reference"] else ())
                self.assertIn(row["face_label"], calls[0][0])
                compose.assert_not_called()

    def test_fastgen_full_with_selected_face_rejects_operation_without_reference_input(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            face = Path(temporary) / "selected-face.png"
            face.write_bytes(b"prepared-face")
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_operation="flower_image_generate",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "flower_image_generate", "inputs": {"min": 0, "max": 0},
            }]}
            settings.cover_queue = [self._row(
                0,
                cover_headline="ТОЧНЫЙ ЗАГОЛОВОК",
                cover_subheadline="Точная вторая строка",
                face_reference_path=str(face),
                face_reference_label="Selected Person",
                face_reference_source="manual",
            )]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media") as render:
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:0"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "with",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "operation": "flower_image_generate",
                })

        render.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["status"], "Операция FastGen без references")
        self.assertIn("reference", settings.cover_queue[0]["error"].casefold())

    def test_fastgen_full_with_selected_face_rejects_unknown_operation_without_capability_schema(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            face = Path(temporary) / "selected-face.png"
            face.write_bytes(b"prepared-face")
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_operation="unknown_reference_operation",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": []}
            settings.cover_queue = [self._row(
                0,
                cover_headline="ТОЧНЫЙ ЗАГОЛОВОК",
                cover_subheadline="Точная вторая строка",
                face_reference_path=str(face),
                face_reference_label="Selected Person",
                face_reference_source="manual",
            )]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media") as render:
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:0"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "with",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "operation": "unknown_reference_operation",
                })

        render.assert_not_called()
        self.assertEqual(settings.cover_queue[0]["status"], "Операция FastGen без references")
        self.assertIn("не подтверждена поддержка image/reference input", settings.cover_queue[0]["error"].casefold())

    def test_fastgen_full_reserves_max_ten_reference_slot_for_selected_face(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            face = root / "selected-face.png"
            face.write_bytes(b"prepared-face")
            scene_references = []
            for index in range(10):
                path = root / f"scene-{index}.png"
                path.write_bytes(f"scene-{index}".encode())
                scene_references.append(path)
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_operation="max-ten-reference-operation",
                cover_reference_mode="all",
                cover_reference_paths=[str(path) for path in scene_references],
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "max-ten-reference-operation", "inputs": {"min": 0, "max": 10},
            }]}
            settings.cover_queue = [self._row(
                0,
                cover_headline="ТОЧНЫЙ ЗАГОЛОВОК",
                cover_subheadline="Точная вторая строка",
                face_reference_path=str(face),
                face_reference_label="Selected Person",
                face_reference_source="manual",
            )]
            calls = []

            def render(_prompt, _output, _stem, _operation, _ratio, **kwargs):
                calls.append(tuple(str(path) for path in kwargs.get("references") or []))
                return [root / "provider-final.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_prepare_cover_visual_reference", side_effect=lambda path: path), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render), \
                 patch.object(bridge, "compose_cover_faces") as compose, \
                 patch.object(bridge, "render_cover_text") as overlay:
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:0"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "with",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "operation": "max-ten-reference-operation",
                })

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), 10)
        self.assertEqual(calls[0][-1], str(face))
        self.assertEqual(calls[0][:-1], tuple(str(path) for path in scene_references[:9]))
        compose.assert_not_called()
        overlay.assert_not_called()

    def test_fastgen_full_edit_path_sends_base_scene_and_selected_face_to_provider(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "current-base.png"
            face = root / "selected-face.png"
            base.write_bytes(b"base")
            face.write_bytes(b"face")
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 1, "max": 2},
            }]}
            settings.cover_queue = [self._row(
                0,
                cover_headline="ТОЧНЫЙ ЗАГОЛОВОК",
                cover_subheadline="Точная вторая строка",
                selected_path=str(base),
                face_reference_path=str(face),
                face_reference_label="Selected Person",
                face_reference_source="manual",
            )]
            calls = []

            def render(prompt, _output, _stem, _operation, _ratio, **kwargs):
                calls.append((prompt, tuple(str(path) for path in kwargs.get("references") or [])))
                return [root / "edited.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_prepare_cover_visual_reference", side_effect=lambda path: path), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render), \
                 patch.object(bridge, "compose_cover_faces") as compose, \
                 patch.object(bridge, "render_cover_text") as overlay:
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:0"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "with",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "refineWithFace": True,
                    "forceRegenerate": True,
                    "operation": "reference_image_edit",
                })

        self.assertEqual(calls[0][1], (str(base), str(face)))
        self.assertIn("existing composition reference", calls[0][0])
        compose.assert_not_called()
        overlay.assert_not_called()

    def test_fastgen_full_retry_and_new_prompt_keep_exact_text_and_selected_face(self):
        from scriptor import bridge

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            face = root / "selected-face.png"
            face.write_bytes(b"prepared-face")
            settings = Settings(
                cover_output_folder=temporary,
                cover_auto_overlay_text=False,
                cover_prompt_variant_count=1,
                cover_variant_count=1,
                cover_operation="reference_image_edit",
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            settings.fastgen_capabilities_cache = {"image": [{
                "id": "reference_image_edit", "inputs": {"min": 1, "max": 2},
            }]}
            settings.cover_queue = [self._row(
                0,
                status="Нужен новый промпт",
                image_prompt="Old rejected visual prompt",
                image_prompt_options=["Old rejected visual prompt"],
                cover_headline="ТОЧНЫЙ ЗАГОЛОВОК",
                cover_subheadline="Точная вторая строка",
                face_reference_path=str(face),
                face_reference_label="Selected Person",
                face_reference_source="manual",
                render_profile={
                    "build_mode": "fastgen-full-my-face",
                    "face_mode": "auto",
                    "text_mode": "fastgen",
                    "local_face_only": False,
                    "operation": "reference_image_edit",
                },
            )]
            original_prompt = bridge.build_final_provider_prompt(
                "Old rejected visual prompt", settings.cover_queue[0], text_mode="fastgen",
            )
            settings.cover_queue[0].update(
                final_provider_prompt=original_prompt,
                final_provider_prompt_options=[original_prompt],
                final_provider_reference_paths=[str(face)],
                final_provider_face_reference_count=1,
            )
            retry_calls = []

            def retry_render(prompt, _output, _stem, operation, _ratio, **kwargs):
                retry_calls.append((prompt, operation, tuple(str(path) for path in kwargs.get("references") or [])))
                if len(retry_calls) < 2:
                    raise FastGenError("FastGen API (400): prompt rejected", 400)
                return [root / "retried.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.time, "sleep"), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=retry_render):
                bridge.retry_cover_generation({
                    "indices": [0], "productionItemIds": ["production:0"],
                })

            self.assertEqual(len(retry_calls), 2)
            self.assertEqual(retry_calls[0], retry_calls[1])
            self.assertEqual(retry_calls[0][1:], ("reference_image_edit", (str(face),)))
            self.assertIn("HEADLINE:\n<exact-text>ТОЧНЫЙ ЗАГОЛОВОК</exact-text>", retry_calls[0][0])
            self.assertIn("SUBHEADLINE:\n<exact-text>Точная вторая строка</exact-text>", retry_calls[0][0])

            settings.cover_queue[0].update(
                status="Нужен новый промпт",
                error="FastGen отклонил текущий prompt 4 раза",
            )

            def rewrite(payload):
                self.assertEqual(payload["productionItemIds"], ["production:0"])
                settings.cover_queue[0].update(
                    image_prompt="New current visual prompt",
                    image_prompt_options=["New current visual prompt"],
                    error="",
                )
                return {}

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "generate_cover_prompts", side_effect=rewrite), \
                 patch.object(bridge, "generate_covers") as render:
                bridge.regenerate_covers_new_prompts({
                    "indices": [0], "productionItemIds": ["production:0"], "provider": "agent",
                })

            self.assertEqual(settings.cover_queue[0]["image_prompt"], "New current visual prompt")
            self.assertEqual(settings.cover_queue[0]["face_reference_path"], str(face))
            self.assertEqual(settings.cover_queue[0]["cover_headline"], "ТОЧНЫЙ ЗАГОЛОВОК")
            self.assertEqual(settings.cover_queue[0]["cover_subheadline"], "Точная вторая строка")
            render.assert_not_called()

            rewritten_calls = []

            def rewritten_render(prompt, _output, _stem, operation, _ratio, **kwargs):
                rewritten_calls.append((prompt, operation, tuple(str(path) for path in kwargs.get("references") or [])))
                return [root / "rewritten.png"]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=rewritten_render):
                bridge.generate_covers({
                    "indices": [0],
                    "productionItemIds": ["production:0"],
                    "_parallel_cover_worker": True,
                    "buildMode": "fastgen-full-my-face",
                    "faceMode": "auto",
                    "textMode": "fastgen",
                    "localFaceOnly": False,
                    "operation": "reference_image_edit",
                })

            self.assertEqual(len(rewritten_calls), 1)
            self.assertIn("STORY CONTEXT:\nNew current visual prompt", rewritten_calls[0][0])
            self.assertIn("HEADLINE:\n<exact-text>ТОЧНЫЙ ЗАГОЛОВОК</exact-text>", rewritten_calls[0][0])
            self.assertIn("SUBHEADLINE:\n<exact-text>Точная вторая строка</exact-text>", rewritten_calls[0][0])
            self.assertEqual(rewritten_calls[0][1:], ("reference_image_edit", (str(face),)))

    def test_three_prebilling_rejections_then_success_reuse_prompt_and_reference(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(
            0,
            cover_headline="ТЕКУЩИЙ ЗАГОЛОВОК",
            cover_subheadline="Текущая вторая строка",
        )]
        calls = []

        def render(prompt, _output, _stem, operation, _ratio, **kwargs):
            calls.append((prompt, operation, tuple(kwargs.get("references") or [])))
            if len(calls) < 4:
                raise FastGenError("FastGen API (400): prompt rejected", 400)
            return [Path("fresh-success.png")]

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_cover_references_for_item", return_value=([Path("same-face.png")], "")), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.time, "sleep"), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:0"], "_parallel_cover_worker": True,
            })

        row = settings.cover_queue[0]
        self.assertEqual(len(calls), 4)
        self.assertEqual(len({call[0] for call in calls}), 1)
        self.assertEqual(len({call[1] for call in calls}), 1)
        self.assertEqual(len({call[2] for call in calls}), 1)
        self.assertEqual(row["status"], "Готово")
        self.assertEqual(row["paths"], ["fresh-success.png"])
        self.assertEqual(row["generation_prebilling_attempt_count"], 4)
        self.assertEqual(row["generation_history"][-1]["totalAttempt"], 4)
        self.assertTrue(all(not event["rewritten"] for event in row["generation_history"]))

    def test_four_prebilling_rejections_require_new_prompt_without_reusing_old_image(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(
            0,
            cover_headline="ТЕКУЩИЙ ЗАГОЛОВОК",
            cover_subheadline="Текущая вторая строка",
            path="old.png",
            paths=["old.png"],
            raw_paths=["old.png"],
            selected_path="old.png",
        )]
        calls = []

        def render(prompt, _output, _stem, _operation, _ratio, **kwargs):
            calls.append((prompt, tuple(kwargs.get("references") or [])))
            raise FastGenError("FastGen API (400): unsafe token=secret-value", 400)

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_cover_references_for_item", return_value=([Path("same-face.png")], "")), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.time, "sleep"), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:0"],
                "_parallel_cover_worker": True, "forceRegenerate": True,
            })

        row = settings.cover_queue[0]
        self.assertEqual(len(calls), 4)
        self.assertEqual(len({call[0] for call in calls}), 1)
        self.assertEqual(len({call[1] for call in calls}), 1)
        self.assertEqual(row["status"], "Нужен новый промпт")
        self.assertEqual(row["generation_prebilling_attempt_count"], 4)
        self.assertTrue(row["generation_rejected_before_acceptance"])
        self.assertIn("FastGen отклонил текущий prompt 4 раза", row["error"])
        self.assertNotIn("secret-value", row["error"])
        self.assertEqual(row["cover_headline"], "ТЕКУЩИЙ ЗАГОЛОВОК")
        self.assertEqual(row["cover_subheadline"], "Текущая вторая строка")
        self.assertEqual(row["paths"], [])
        self.assertEqual(row["raw_paths"], [])
        self.assertEqual(row["selected_path"], "")

    def test_accepted_generation_id_stops_same_prompt_create_retry(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(0)]
        calls = []
        accepted_error = FastGenError("polling interrupted after acceptance")
        accepted_error.generation_id = "generation-accepted-1"

        def render(*_args, **_kwargs):
            calls.append(1)
            raise accepted_error

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.time, "sleep"), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:0"], "_parallel_cover_worker": True,
            })

        self.assertEqual(len(calls), 1)
        self.assertEqual(settings.cover_queue[0]["status"], "Требуется восстановление FastGen")
        self.assertEqual(settings.cover_queue[0]["accepted_generation_id"], "generation-accepted-1")

    def test_new_prompt_action_after_exhaustion_uses_current_text_without_rendering(self):
        from scriptor import bridge

        settings = Settings(cover_prompt_variant_count=1)
        settings.cover_queue = [self._row(
            0,
            cover_headline="НОВЫЙ КУРС",
            cover_subheadline="Рынок ждёт решений",
            image_prompt="Old rejected visual prompt",
            image_prompt_options=["Old rejected visual prompt"],
            status="Нужен новый промпт",
            error="FastGen отклонил текущий prompt 4 раза",
        )]
        provider_prompts = []

        async def rewrite(prompt, **_kwargs):
            provider_prompts.append(prompt)
            return '{"prompts":["Different current scene with market screens and press cameras"],"recommended":1}'

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "HybridTextPool", return_value=SimpleNamespace(generate=rewrite)), \
             patch.object(bridge, "generate_covers") as render:
            regenerate_covers_new_prompts({
                "indices": [0], "productionItemIds": ["production:0"], "provider": "agent",
            })

        self.assertEqual(len(provider_prompts), 1)
        self.assertIn("НОВЫЙ КУРС", provider_prompts[0])
        self.assertIn("Рынок ждёт решений", provider_prompts[0])
        self.assertNotEqual(settings.cover_queue[0]["image_prompt"], "Old rejected visual prompt")
        self.assertEqual(settings.cover_queue[0]["status"], "Новые промпты созданы")
        self.assertEqual(settings.cover_queue[0]["error"], "")
        render.assert_not_called()

    def test_provider_try_again_later_failure_uses_bounded_retry_contract(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(0)]
        calls = []

        def render(*_args, **_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Generation failed, please try again later")
            return [Path("fresh-success.png")]

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.time, "sleep"), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:0"], "_parallel_cover_worker": True,
            })

        self.assertEqual(len(calls), 2)
        self.assertEqual(settings.cover_queue[0]["status"], "Готово")
        self.assertEqual(settings.cover_queue[0]["paths"], ["fresh-success.png"])

    def test_permanent_fastgen_failure_is_terminal_after_one_call(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(0)]
        calls = []

        def render(*_args, **_kwargs):
            calls.append(1)
            raise RuntimeError("invalid provider request")

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.time, "sleep"), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0], "productionItemIds": ["production:0"], "_parallel_cover_worker": True,
            })

        self.assertEqual(len(calls), 1)
        self.assertEqual(settings.cover_queue[0]["status"], "Ошибка FastGen")
        self.assertIn("invalid provider request", settings.cover_queue[0]["error"])

    def test_pause_finishes_in_flight_row_and_resume_only_processes_remaining_row(self):
        from scriptor import bridge

        settings = Settings(cover_auto_overlay_text=False, cover_variant_count=1)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [self._row(0), self._row(1)]
        calls = []

        def render(_prompt, output, stem, *_args, **_kwargs):
            calls.append(stem)
            if len(calls) == 1:
                settings.cover_generation_paused = True
            return [output / f"{stem}.png"]

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
            bridge.generate_covers({
                "indices": [0, 1],
                "productionItemIds": ["production:0", "production:1"],
                "_parallel_cover_worker": True,
            })
            self.assertEqual(settings.cover_queue[0]["status"], "Готово")
            self.assertEqual(settings.cover_queue[1]["status"], "Приостановлено")
            settings.cover_generation_paused = False
            bridge.generate_covers({"resumeOnly": True, "_parallel_cover_worker": True})

        self.assertEqual(len(calls), 2)
        self.assertEqual(settings.cover_queue[0]["status"], "Готово")
        self.assertEqual(settings.cover_queue[1]["status"], "Готово")

    def test_remove_results_requires_explicit_scope_and_clears_render_metadata(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[self._row(
            0,
            paths=["old.png"], raw_paths=["old.png"], face_composite_paths=["face.png"],
            text_overlay_path="text.png", path="old.png", selected_path="old.png",
            selected_base_path="old.png", prompt_image_paths=[{"paths": ["old.png"]}],
            generation_total_attempt=7, generation_history=[{"status": "success"}],
        )])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}):
            with self.assertRaisesRegex(ValueError, "Выберите"):
                remove_cover_results({})
            remove_cover_results({"indices": [0]})

        row = settings.cover_queue[0]
        for key in ("paths", "raw_paths", "face_composite_paths"):
            self.assertEqual(row[key], [])
        for key in ("text_overlay_path", "path", "selected_path", "selected_base_path"):
            self.assertEqual(row[key], "")
        self.assertNotIn("prompt_image_paths", row)
        self.assertNotIn("generation_history", row)
        self.assertNotIn("generation_total_attempt", row)
        self.assertTrue(row["updatedAt"])

    def test_twenty_selected_rewrites_report_nineteen_ready_and_one_failure_truthfully(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[self._row(index, image_prompt=f"Старая сцена {index}") for index in range(20)])

        def rewrite(payload):
            for index in payload["indices"]:
                row = settings.cover_queue[index]
                if index == 19:
                    row.update(error="provider rejected prompt", status="Ошибка промпта")
                else:
                    row.update(image_prompt=f"Новая сцена {index}", error="", status="Промпты готовы")
            return {}

        selected_ids = [f"production:{index}" for index in range(20)]
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "generate_cover_prompts", side_effect=rewrite):
            regenerate_covers_new_prompts({
                "indices": list(range(20)), "productionItemIds": selected_ids, "provider": "agent",
            })

        self.assertEqual(sum(row["status"] == "Новые промпты созданы" for row in settings.cover_queue), 19)
        self.assertEqual(sum(row["status"] == "Ошибка промпта" for row in settings.cover_queue), 1)
        self.assertEqual(settings.cover_queue[19]["image_prompt"], "Старая сцена 19")

    def test_fifty_topic_render_has_no_omissions_and_stays_within_ten_workers(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(
                cover_output_folder=directory,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_queue=[self._row(index) for index in range(50)],
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            lock = threading.Lock()
            active = maximum = 0

            def render(_prompt, output, stem, *_args, **_kwargs):
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.01)
                path = output / f"{stem}.png"
                path.write_bytes(b"tiny-image")
                with lock:
                    active -= 1
                return [path]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_claim_cover_generation_lock", return_value=Path(directory) / "batch.lock"), \
                 patch.object(bridge, "_release_cover_generation_lock"), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": list(range(50)),
                    "productionItemIds": [f"production:{index}" for index in range(50)],
                })

            paths = [row.get("path") for row in settings.cover_queue]
            self.assertEqual(sum(row.get("status") == "Готово" for row in settings.cover_queue), 50)
            self.assertEqual(len(set(paths)), 50)
            self.assertTrue(all(path and Path(path).is_file() for path in paths))
            self.assertEqual(maximum, 10)

    def test_fifty_topic_render_keeps_forty_nine_successes_when_one_row_fails(self):
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(
                cover_output_folder=directory,
                cover_auto_overlay_text=False,
                cover_variant_count=1,
                cover_queue=[self._row(index) for index in range(50)],
            )
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]

            def render(_prompt, output, stem, *_args, **_kwargs):
                if stem.startswith("018 "):
                    raise RuntimeError("invalid provider request")
                path = output / f"{stem}.png"
                path.write_bytes(b"tiny-image")
                return [path]

            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "_hydrate_cover_library", return_value=False), \
                 patch.object(bridge, "_save_cover_state"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_claim_cover_generation_lock", return_value=Path(directory) / "batch.lock"), \
                 patch.object(bridge, "_release_cover_generation_lock"), \
                 patch.object(bridge.FastGenPool, "generate_media", side_effect=render):
                bridge.generate_covers({
                    "indices": list(range(50)),
                    "productionItemIds": [f"production:{index}" for index in range(50)],
                })

            self.assertEqual(sum(row.get("status") == "Готово" for row in settings.cover_queue), 49)
            self.assertEqual(sum(row.get("status") == "Ошибка FastGen" for row in settings.cover_queue), 1)
            self.assertEqual(settings.cover_queue[17]["status"], "Ошибка FastGen")

    def test_twenty_selected_rewrites_all_finish_in_current_success_state(self):
        from scriptor import bridge

        settings = Settings(cover_queue=[self._row(index, image_prompt=f"Старая сцена {index}") for index in range(20)])

        def rewrite(payload):
            for index in payload["indices"]:
                settings.cover_queue[index].update(image_prompt=f"Новая сцена {index}", error="")
            return {}

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "_save_cover_state"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "generate_cover_prompts", side_effect=rewrite):
            regenerate_covers_new_prompts({
                "indices": list(range(20)),
                "productionItemIds": [f"production:{index}" for index in range(20)],
                "provider": "agent",
            })

        self.assertEqual(sum(row["status"] == "Новые промпты созданы" for row in settings.cover_queue), 20)
        self.assertTrue(all(row["image_prompt"].startswith("Новая сцена") for row in settings.cover_queue))

    def test_duplicate_start_returns_normal_zero_without_provider_call(self):
        from scriptor import bridge

        with patch.object(bridge, "_claim_cover_generation_lock", return_value=None), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge.FastGenPool, "generate_media") as render:
            result = bridge.generate_covers({"indices": [0], "productionItemIds": ["production:0"]})

        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertIn("уже выполняется", result["operationResult"]["message"])
        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
