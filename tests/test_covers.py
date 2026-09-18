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
    _match_cover_face_reference,
    _migrate_legacy_cover_photo_prompts,
    _normalize_cover_photo_prompt,
    compose_cover_faces,
    generate_cover_headlines,
    generate_cover_prompts,
    generate_cover_subheadlines,
    generate_covers,
    prepare_cover_face_library,
    regenerate_covers,
    regenerate_covers_new_prompts,
    remove_cover_image,
    render_cover_text,
    render_cover_text_fastgen,
    save_cover_settings,
    select_cover_variant,
    select_cover_visual_reference,
    set_cover_visual_reference_target,
)
from scriptor.config import FastGenKey, OpenAIKey, Settings
from scriptor.cover_rate_limit import cover_rate_limit_decision, next_fastgen_resume_at
from scriptor.covers import (
    FastGenClient,
    FastGenError,
    FastGenPool,
    reference_mime_type,
)


class CoverGalleryFileStateTests(unittest.TestCase):
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
            output = Path(directory) / "generated.png"
            output.write_bytes(b"generated")
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge._save_cover_state"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media", return_value=[output]) as render:
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
            output = Path(directory) / "generated.png"
            output.write_bytes(b"generated")
            payloads = []
            def render(prompt, *_args, **_kwargs):
                payloads.append(prompt)
                return [output]
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
        self.assertIn("thin vivid red graphical edge accents", payloads[0])
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

    def test_provider_payload_equals_final_prompt(self):
        """No adapter, retry or render guard is allowed to append provider text."""
        from scriptor import bridge

        with TemporaryDirectory() as directory:
            settings = Settings(cover_output_folder=directory, cover_auto_overlay_text=False)
            settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
            item = {
                "title": "Ормуз на грани! Иран давит на танкеры! Нефтяной рынок ждёт шок!",
                "image_prompt": "Wide tanker scene. Photorealistic, 16:9, breaking-news image.",
                "cover_headline": "ОРМУЗ НА ГРАНИ",
                "cover_subheadline": "ТАНКЕРЫ ПОД ДАВЛЕНИЕМ",
            }
            settings.cover_queue = [item]
            output = Path(directory) / "generated.png"
            output.write_bytes(b"generated")
            payloads = []

            def render(prompt, *_args, **_kwargs):
                payloads.append(prompt)
                return [output]

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge._hydrate_cover_library", return_value=False), \
                    patch("scriptor.bridge._claim_cover_generation_lock", return_value=Path("test.lock")), \
                    patch("scriptor.bridge._release_cover_generation_lock"), \
                    patch("scriptor.bridge._save_cover_state"), \
                    patch("scriptor.bridge.snapshot", return_value={}), \
                    patch("scriptor.bridge.FastGenPool.generate_media", side_effect=render):
                bridge.generate_covers({"indices": [0], "textMode": "fastgen"})

            self.assertEqual(payloads, [bridge._normalize_cover_photo_prompt(item["image_prompt"], item)])
            self.assertIn("MAIN SUBJECT:\nIranian pressure on oil shipping routes", payloads[0])
            self.assertIn("VISIBLE ACTION:\nOil tankers affected near Strait of Hormuz", payloads[0])
            self.assertIn("VISUAL EVIDENCE:\nTankers, maritime tension, naval presence, crisis atmosphere", payloads[0])
            self.assertEqual(settings.cover_queue[0]["prompt_sources"], {
                "CORE STYLE": "Universal V2",
                "SCENE": "Topic Planner",
                "PEOPLE": "Reference Resolver",
                "TEXT": "Thumbnail Text Engine",
                "NEGATIVE": "Universal V2",
            })

    def test_semantic_scene_planner_resolves_concrete_values_for_supported_news_topics(self):
        """V2 receives scene facts, never planner instructions or generic placeholders."""
        from scriptor.thumbnail_prompt_v2 import build_final_provider_prompt

        samples = (
            {
                "title": "Цены на нефть растут после сокращения поставок",
                "expected": ("oil price movement", "trading screens", "energy-market"),
            },
            {
                "title": "Президент заявил о новых переговорах с Европой",
                "expected": ("president", "speaks", "press"),
            },
            {
                "title": "Порт Новороссийска приостановил отгрузку контейнеров",
                "expected": ("port", "container", "terminal"),
            },
            {
                "title": "ЕС обсуждает новые санкции против Ирана",
                "expected": ("eu", "officials", "consultation"),
            },
            {
                "title": "Мэр объявил о ремонте повреждённого моста",
                "expected": ("mayor", "briefing", "bridge"),
            },
        )
        blocked = (
            "a concrete topic-grounded", "a coherent real-world", "relevant evidence",
            "suitable environment", "dynamic action", "implied by the topic",
            "clear urgency and high stakes",
        )

        for sample in samples:
            with self.subTest(title=sample["title"]):
                prompt = build_final_provider_prompt("", {"title": sample["title"]})
                body = prompt.casefold()
                self.assertTrue(all(term in body for term in sample["expected"]), prompt)
                self.assertTrue(all(term not in body for term in blocked), prompt)

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
        self.assertTrue(all(len(row["cover_headline"].split()) <= 3 for row in settings.cover_queue))
        self.assertTrue(all(3 <= len(row["cover_subheadline"].split()) <= 7 for row in settings.cover_queue))
        self.assertTrue(all(not _cover_lines_repeat_meaningful_words(row["cover_headline"], row["cover_subheadline"])
                            for row in settings.cover_queue))

    def test_word_engine_repairs_an_overlong_headline_instead_of_silently_truncating_it(self):
        """A valid READY line must be authored, not the first three words of a bad response."""
        from scriptor import bridge

        item = {"title": "Порт закрыт из-за кризиса", "script": "Контейнеры застряли на терминале."}
        calls: list[str] = []

        async def generate(prompt, **_kwargs):
            calls.append(prompt)
            return json.dumps({"headline": "ПОРТ ЗАКРЫТ" if len(calls) > 1 else "ПОРТ ЗАКРЫТ ПРЯМО СЕЙЧАС"}, ensure_ascii=False)

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
            ("Трамп усиливает давление на поставки нефти", "ТРАМП ДАВИТ", "Танкеры ждут решения"),
            ("Путин и Макрон обсуждают переговоры", "ПУТИН ДАВИТ", "Макрон требует гарантий"),
            ("Цены на нефть могут вырасти", "НЕФТЬ РВАНЁТ?", "Рынок ждёт дефицита"),
            ("Порт закрыт из-за кризиса", "ПОРТ ЗАКРЫТ", "Контейнеры застряли на терминале"),
            ("Поставки газа могут сократиться", "ПОСТАВКИ ПОД РИСКОМ?", "Заводы сокращают выпуск"),
        ]
        settings.cover_queue = [
            {"title": title, "script": f"Контекст: {title}", "cover_headline": headline,
             "cover_subheadline": subheadline, "headline_status": "READY", "subheadline_status": "READY"}
            for title, headline, subheadline in rows
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
        for _title, headline, subheadline in rows:
            matching = [payload for payload in payloads if f"HEADLINE:\n{headline}." in payload]
            self.assertEqual(len(matching), 1)
            payload = matching[0]
            self.assertEqual(payload.count("NEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2"), 1)
            self.assertIn("CLICKABILITY = HIGH.", payload)
            self.assertIn("PHOTOREALISM = MAXIMUM.", payload)
            self.assertIn("SELECTED COMPOSITION:\n", payload)
            self.assertIn("Use thin vivid red graphical edge accents", payload)
            self.assertIn(f"HEADLINE:\n{headline}.", payload)
            self.assertIn(f"SUBHEADLINE:\n{subheadline}.", payload)
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
    def test_headline_is_limited_to_three_words(self):
        self.assertEqual(_clean_cover_headline("ОРМУЗ ПОД УГРОЗОЙ ПРЯМО СЕЙЧАС"), "ОРМУЗ ПОД УГРОЗОЙ")

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

    def test_matches_regional_leader_when_the_topic_names_country_but_not_person(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            portrait = folder / "Хаменеи" / "portrait.jpg"
            portrait.parent.mkdir()
            portrait.write_bytes(b"test")
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)
            path, label, source = _match_cover_face_reference({"title": "Тегеран усиливает давление"}, settings)
            self.assertEqual(Path(path), portrait)
            self.assertEqual(label, "Хаменеи")
            self.assertEqual(source, "auto")

    def test_ormuz_prefers_trump_when_both_topic_appropriate_folders_exist(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            trump = folder / "Трамп" / "portrait.jpg"
            khamenei = folder / "Хаменеи" / "portrait.jpg"
            trump.parent.mkdir(); khamenei.parent.mkdir()
            trump.write_bytes(b"trump"); khamenei.write_bytes(b"khamenei")
            settings = Settings(cover_face_library_folder=str(folder), cover_face_library_enabled=True)
            path, label, source = _match_cover_face_reference({"title": "Иран — кризис на Ормузе"}, settings)
            self.assertEqual(Path(path), trump)
            self.assertEqual(label, "Трамп")
            self.assertEqual(source, "auto")

    def test_remembers_composition_profile_for_the_same_face(self):
        settings = Settings()
        item = {"title": "Путин сделал заявление"}
        first = _cover_face_layout(item, settings, "C:/faces/Путин/portrait.png", "Путин")
        second = _cover_face_layout(item, settings, "C:/faces/Путин/portrait.png", "Путин")
        self.assertEqual(first, second)
        self.assertTrue(item["face_layout"].startswith("крупный план героя"))

    def test_reserves_a_text_safe_zone_when_overlay_is_enabled(self):
        settings = Settings(cover_auto_overlay_text=True, cover_text_mode="overlay")
        item = {"title": "Путин сделал заявление"}
        instruction = _cover_face_layout(item, settings, "C:/faces/Путин/portrait.png", "Путин")
        self.assertIn("RIGHT side", instruction)
        self.assertIn("lower-left 52%", instruction)
        self.assertIn("зона текста свободна", item["face_layout"])

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
            with patch("scriptor.bridge.random.choice", side_effect=lambda values: values[-1]):
                path, _label, source = _match_cover_face_reference({"title": "Путин сделал заявление"}, settings)
            self.assertEqual(Path(path), portraits[-1])
            self.assertEqual(source, "auto")
            # Auto matches are allowed to change on the next render, while a
            # reference explicitly marked manual is not randomized.
            with patch("scriptor.bridge.random.choice", side_effect=lambda values: values[0]):
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
        self.assertIn("ПЛАН ИНЦИДЕНТА", instruction)
        self.assertNotIn("ACTION = HIGH.", instruction)

    def test_visual_prompt_requires_a_real_press_photograph_not_an_illustration(self):
        instruction = _cover_instruction({"title": "Удар по промышленному объекту", "script": ""}, 0, Settings())
        prompt = _normalize_cover_photo_prompt("Wide view of a damaged factory with responders", {"title": "Удар по промышленному объекту"})
        self.assertIn("Не добавляй style prompt", instruction)
        self.assertIn("CORE STYLE:\nNEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2.", prompt)
        self.assertIn("PHOTOREALISM = MAXIMUM.", prompt)
        self.assertIn("No artwork, illustration", prompt)

    def test_every_new_saved_fastgen_prompt_carries_the_universal_v2_contract_once(self):
        prompt = _normalize_cover_photo_prompt("Wide view of a damaged factory with responders")
        self.assertTrue(prompt.startswith("CORE STYLE:\nNEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2."))
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

    def test_prompt_builder_owns_the_realistic_newsroom_treatment(self):
        prompt = _normalize_cover_photo_prompt("Officials and cameras at a consultation", {"title": "НАТО и Россия — риск новой эскалации"})
        self.assertNotIn("breaking-news", prompt.casefold())
        self.assertIn("CORE STYLE:\nNEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2.", prompt)
        self.assertIn("Official NATO and EU fabric flags", prompt)

    def test_topic_plan_uses_ormuz_specific_scene_not_a_generic_soldier_map(self):
        plan = _cover_topic_visual_plan({"title": "Иран — кризис на Ормузе (нефть и танкеры)"})
        self.assertIn("танкер", plan)
        self.assertIn("Трампа", plan)
        self.assertIn("случайного военного у карты", plan)

    def test_default_topic_plan_does_not_invent_a_generic_event(self):
        plan = _cover_topic_visual_plan({"title": "Новые изменения в правилах"})
        self.assertIn("не придумывай отдельное событие", plan.casefold())
        self.assertIn("только конкретные объекты", plan.casefold())

    def test_nato_russia_plan_requires_real_symbols_not_an_invented_ai_war_room(self):
        plan = _cover_topic_visual_plan({"title": "НАТО и Россия — риск новой эскалации"})
        self.assertIn("официальные флаги НАТО и ЕС", plan)
        self.assertIn("саммит", plan)
        self.assertIn("ракетный пуск", plan)
        self.assertIn("не рисуй выдуманного седого генерала", plan.casefold())
        self.assertIn("не показывай бункер", plan.casefold())


class CoverLocalCompositorTests(unittest.TestCase):
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
                    "indices": [0], "buildMode": "fastgen-text-auto-face",
                    "faceMode": "auto", "textMode": "fastgen", "localFaceOnly": True,
                })
        self.assertEqual(settings.cover_queue[0]["render_profile"], {
            "build_mode": "fastgen-text-auto-face", "face_mode": "auto",
            "text_mode": "fastgen", "local_face_only": True,
            "operation": "flower_image_generate",
        })

    def test_repeat_current_uses_saved_render_profile_instead_of_new_defaults(self):
        """A retry must not turn an automatic text+face cover into a different route."""
        settings = Settings()
        settings.cover_queue = [{
            "title": "Ормуз", "image_prompt": "scene",
            "render_profile": {
                "build_mode": "fastgen-text-auto-face", "face_mode": "auto",
                "text_mode": "fastgen", "local_face_only": True,
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
            "indices": [0], "buildMode": "fastgen-text-auto-face", "faceMode": "auto",
            "textMode": "fastgen", "localFaceOnly": True,
            "operation": "flower_image_generate",
        })
        self.assertEqual(len(payload["productionItemIds"]), 1)
        self.assertTrue(payload["productionItemIds"][0].startswith("production:manual:"))

    def test_nato_cover_request_uses_topic_semantics_without_a_legacy_render_tail(self):
        """The builder owns the final prompt; NATO scene values remain semantic and topic-grounded."""
        settings = Settings(cover_auto_overlay_text=False)
        settings.cover_api_keys = [FastGenKey(label="test", secret="test")]
        settings.cover_queue = [{
            "title": "НАТО и ЕС обсуждают риск эскалации", "image_prompt": "dramatic breaking news scene",
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
        self.assertIn("official nato and eu fabric flags", captured[0].casefold())
        self.assertIn("press", captured[0].casefold())
        self.assertEqual(captured[0].count("CORE STYLE:"), 1)
        self.assertEqual(captured[0].count("FINAL NEGATIVE RULES:"), 1)
        self.assertNotIn("structured production context", captured[0].casefold())

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

    def test_cover_build_mode_accepts_additional_automatic_text_face_route(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
             patch("scriptor.bridge.save_settings"), \
             patch("scriptor.bridge.snapshot", return_value={}):
            save_cover_settings({"buildMode": "fastgen-text-auto-face"})
        self.assertEqual(settings.cover_build_mode, "fastgen-text-auto-face")

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
        self.assertTrue(all(prompt.startswith("CORE STYLE:\nNEWSFLOW FASTGEN UNIVERSAL THUMBNAIL CORE V2.")
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
        self.assertEqual(settings.cover_queue[0]["status"], "Ошибка FastGen")
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


if __name__ == "__main__":
    unittest.main()
