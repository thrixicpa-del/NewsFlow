from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


@unittest.skipUnless(os.environ.get("NEWSFLOW_RUN_ELECTRON_E2E") == "1", "set NEWSFLOW_RUN_ELECTRON_E2E=1")
class ElectronE2ESmokeTests(unittest.TestCase):
    """CDP/Playwright smoke for a real Electron process; providers are never invoked."""

    def setUp(self):
        boundary = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.test_root = Path(tempfile.mkdtemp(prefix="electron-e2e-", dir=boundary))
        self.test_root.mkdir(parents=True, exist_ok=True)
        environment = patch.dict(os.environ, {
            "NEWSFLOW_TEST_ROOT": str(self.test_root),
            "LOCALAPPDATA": str(self.test_root),
            "NEWSFLOW_RENDER_TEMP_ROOT": str(self.test_root / "render-workspace"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.process: subprocess.Popen[str] | None = None

    def tearDown(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _launch(self) -> None:
        target = os.environ.get("NEWSFLOW_E2E_TARGET", "source")
        if target == "packaged":
            executable = Path(os.environ.get("NEWSFLOW_PACKAGED_EXE", ""))
            if not executable.is_file():
                self.skipTest("NEWSFLOW_PACKAGED_EXE must point to a release-candidate EXE")
            command = [str(executable), f"--remote-debugging-port={self.port}"]
            cwd = executable.parent
        elif target == "source":
            if not (APP_ROOT / "dist" / "index.html").is_file() or not (APP_ROOT / "dist-electron" / "main.js").is_file():
                self.skipTest("build source Electron first: pnpm --dir studio-ui-remotion-verify build:web && pnpm --dir studio-ui-remotion-verify build:desktop")
            electron = APP_ROOT / "node_modules" / "electron" / "dist" / ("electron.exe" if os.name == "nt" else "electron")
            if not electron.is_file():
                self.skipTest("install the pinned Electron dependency before source E2E")
            command = [str(electron), f"--remote-debugging-port={self.port}", "."]
            cwd = APP_ROOT
        else:
            self.fail(f"Unknown NEWSFLOW_E2E_TARGET: {target}")

        environment = os.environ.copy()
        environment["NEWSFLOW_TEST_MODE"] = "1"
        environment["LOCALAPPDATA"] = str(self.test_root)
        self.process = subprocess.Popen(command, cwd=cwd, env=environment, text=True)

    def _wait_for_cdp(self) -> None:
        endpoint = f"http://127.0.0.1:{self.port}/json/version"
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                self.fail(f"Electron ended before CDP became available: {self.process.returncode}")
            try:
                with urlopen(endpoint, timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.2)
        self.fail("Electron CDP endpoint did not become available")

    def test_launch_navigation_and_test_identity(self):
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        artifact_root = Path(os.environ.get("NEWSFLOW_TEST_ARTIFACTS_DIR", self.test_root / "artifacts")).resolve()
        artifact = artifact_root / "electron-e2e.png"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.get_by_role("button", name="Генерация идей").click()
            self.assertIn("Генерация идей", page.locator(".nf-page-header h1").inner_text())
            page.screenshot(path=str(artifact))
            self.assertTrue(artifact.is_file())
            browser.close()

    @unittest.skipUnless(os.name == "nt", "native Windows window-title regression")
    def test_test_window_identity_survives_renderer_title_changes(self):
        """HTML title updates must not disguise an isolated TEST window as production."""
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.evaluate("document.title = 'Renderer title update'")
            page.wait_for_timeout(250)
            self.assertIsNotNone(self.process)
            observed = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Process -Id {self.process.pid}).MainWindowTitle"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, check=True,
            )
            self.assertEqual("NewsFlow Studio [TEST]", observed.stdout.strip())
            page.reload()
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            observed = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Process -Id {self.process.pid}).MainWindowTitle"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=10, check=True,
            )
            self.assertEqual("NewsFlow Studio [TEST]", observed.stdout.strip())
            browser.close()

    def test_covers_poll_completed_files_by_production_id_without_provider_calls(self):
        """Real source Electron/IPC/Core refreshes a synthetic 84-topic queue."""
        if os.environ.get("NEWSFLOW_E2E_TARGET", "source") != "source":
            self.skipTest("source-only bug regression; do not modify immutable packages")
        from PIL import Image

        from scriptor import config

        settings = config.Settings(montage_renderer="ffmpeg", cover_rate_auto_resume=False)
        settings.cover_queue = [
            {"production_item_id": f"e2e-cover:{i}", "title": f"Offline cover topic {i}",
             "status": "FastGen генерирует", "paths": [], "image_prompt": "Manual scene",
             "prompt_provider": "manual"} for i in range(1, 85)
        ]
        config.save_settings(settings)
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.get_by_role("button", name="ОБЛОЖКИ И ГЕНЕРАЦИИ", exact=True).click()
            page.get_by_role("button", name="Обложки YouTube", exact=True).click()
            row = page.get_by_role("button", name="1. Offline cover topic 1", exact=True).locator("xpath=ancestor::tr")
            row.wait_for(timeout=20_000)
            settings = config.load_settings()
            output = Path(settings.cover_output_folder)
            output.mkdir(parents=True, exist_ok=True)
            for i, item in enumerate(settings.cover_queue, 1):
                if i <= 78:
                    image = output / f"offline-{i}.png"
                    Image.new("RGB", (8, 8), "blue").save(image)
                    item.update(status="Готово", progress=100, paths=[str(image)])
                elif i == 79:
                    item.update(status="Ожидает лимит FastGen", progress=5, rate_limit_wait_until="2099-01-01T00:00:00Z")
                else:
                    item.update(status="Требуется восстановление FastGen", progress=100,
                                accepted_generation_id=f"offline-accepted-{i}")
            config.save_settings(settings)
            page.wait_for_function("""() => document.querySelectorAll('tr').length > 78
                && [...document.querySelectorAll('tr')].filter(row => row.innerText.includes('1 картинок')).length === 78""",
                                   timeout=30_000)
            self.assertIn("Готово", row.inner_text())
            snapshot = page.evaluate("async () => window.newsflowDesktop.snapshot()")
            self.assertEqual(len(snapshot["covers"]), 84)
            self.assertEqual(sum(bool(item.get("paths")) for item in snapshot["covers"]), 78)
            self.assertEqual(sum(item.get("status") == "Требуется восстановление FastGen"
                                 for item in snapshot["covers"]), 5)
            self.assertEqual(sum(item.get("status") == "Ожидает лимит FastGen"
                                 for item in snapshot["covers"]), 1)
            self.assertEqual(snapshot["covers"][0]["production_item_id"], "e2e-cover:1")
            self.assertFalse(snapshot.get("safeMode", False))
            artifact_root = Path(os.environ.get("NEWSFLOW_TEST_ARTIFACTS_DIR", self.test_root / "artifacts"))
            artifact = artifact_root / "issue-375-covers-refresh.png"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(artifact))
            page.get_by_role("button", name="Галерея обложек", exact=True).click()
            gallery_row = page.get_by_role("button", name="79. Offline cover topic 79", exact=True).locator("xpath=ancestor::tr")
            gallery_row.get_by_text("Нет файлов", exact=True).wait_for(timeout=20_000)
            image = output / "offline-79.png"
            Image.new("RGB", (8, 8), "blue").save(image)
            settings.cover_queue[78].update(status="Готово", progress=100, paths=[str(image)])
            config.save_settings(settings)
            gallery_row.get_by_text("1 готово", exact=True).wait_for(timeout=30_000)
            page.screenshot(path=str(artifact.with_name("issue-375-gallery-refresh.png")))
            browser.close()

    def test_preload_bridge_and_safe_core_command_round_trip(self):
        """A packaged renderer must expose preload IPC and persist one local command."""
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)

            bridge_types = page.evaluate("""() => ({
                desktop: typeof window.newsflowDesktop,
                snapshot: typeof window.newsflowDesktop?.snapshot,
                command: typeof window.newsflowDesktop?.command,
            })""")
            self.assertEqual(
                {"desktop": "object", "snapshot": "function", "command": "function"},
                bridge_types,
            )

            plan = page.evaluate("""async () => {
                const state = await window.newsflowDesktop.command("add-topics-to-plan", {
                    topics: ["E2E preload bridge"],
                    count: 2,
                    provider: "agent",
                    requirements: "",
                });
                return state.ideaPlan;
            }""")
            self.assertTrue(
                any(item.get("topic") == "E2E preload bridge" and item.get("count") == 2 for item in plan),
                plan,
            )

            refreshed = page.evaluate("""async () => {
                const state = await window.newsflowDesktop.snapshot();
                return state.ideaPlan;
            }""")
            self.assertTrue(
                any(item.get("topic") == "E2E preload bridge" and item.get("count") == 2 for item in refreshed),
                refreshed,
            )

            generated = page.evaluate("""async () => {
                const state = await window.newsflowDesktop.command("generate-ideas", {
                    topics: ["E2E preload bridge"],
                    count: 1,
                    provider: "agent",
                    requirements: "",
                    titleFormulaOnly: true,
                });
                return {
                    operation: state.operationResult,
                    ideas: state.ideaResults,
                };
            }""")
            self.assertEqual("ideas", generated["operation"]["kind"])
            self.assertGreaterEqual(generated["operation"]["generation"]["generated"], 1)
            self.assertTrue(generated["ideas"], generated)
            self.assertTrue(all(len(idea.split(" — ")) == 3 for idea in generated["ideas"]), generated)
            browser.close()

    def test_preload_persists_a_large_template_without_using_the_command_line(self):
        """Long template text crosses Electron → Core through the short payload transport."""
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        template = "E2E large template {title}. " + ("Keep this exact editorial context. " * 4_000)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            response = page.evaluate(
                """async (template) => window.newsflowDesktop.command("save-template", { template })""",
                template,
            )
            self.assertIsInstance(response, dict)
            browser.close()

        settings = self.test_root / "NewsFlow" / "settings.json"
        persisted = json.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(template.strip(), persisted["template"])

    def test_api_key_edit_reveal_and_reload_through_real_ui_ipc_storage(self):
        """Synthetic secrets cross the real source runtime; no providers invoked."""
        if os.environ.get("NEWSFLOW_E2E_TARGET", "source") != "source":
            self.skipTest("new credential command requires updated source runtime")
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.get_by_role("button", name="НАСТРОЙКИ", exact=True).click()
            page.get_by_role("button", name="API-ключи", exact=True).click()
            page.get_by_role("button", name="Добавить ключ", exact=True).click()
            page.get_by_label("Название ключа", exact=True).fill("E2E synthetic")
            page.get_by_label("API-ключ", exact=True).fill("e2e-synthetic-old")
            page.get_by_role("button", name="Сохранить ключ", exact=True).click()
            page.get_by_role("button", name="Редактировать ключ E2E synthetic", exact=True).click()
            expect(page.get_by_label("API-ключ", exact=True)).to_have_value("e2e-synthetic-old")
            self.assertEqual(page.get_by_label("API-ключ", exact=True).get_attribute("type"), "password")
            page.get_by_role("button", name="Показать ключ", exact=True).click()
            self.assertEqual(page.get_by_label("API-ключ", exact=True).get_attribute("type"), "text")
            page.get_by_label("API-ключ", exact=True).fill("e2e-synthetic-new")
            page.get_by_label("Название ключа", exact=True).fill("E2E updated")
            page.get_by_role("button", name="Сохранить ключ", exact=True).click()
            expect(page.get_by_label("API-ключ", exact=True)).to_have_count(0)
            page.reload()
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            if page.get_by_role("button", name="API-ключи", exact=True).count() == 0:
                page.get_by_role("button", name="НАСТРОЙКИ", exact=True).click()
            page.get_by_role("button", name="API-ключи", exact=True).click()
            page.get_by_role("button", name="Редактировать ключ E2E updated", exact=True).click()
            expect(page.get_by_label("API-ключ", exact=True)).to_have_value("e2e-synthetic-new")
            safe = page.evaluate("async () => JSON.stringify(await window.newsflowDesktop.snapshot())")
            self.assertNotIn("e2e-synthetic-new", safe)
            self.assertNotIn("e2e-synthetic-old", safe)
            page.get_by_role("button", name="Отмена", exact=True).click()
            browser.close()

    def test_screen_text_maintenance_round_trip_does_not_require_footage_roots(self):
        """The existing-vector maintenance action remains safe for an empty library."""
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            result = page.evaluate("""async () => {
                const state = await window.newsflowDesktop.command("index-footage", { screenText: true });
                return {
                    kind: state.operationResult?.kind,
                    result: state.indexResult,
                    folders: state.footageFolders,
                };
            }""")
            self.assertEqual("screen-text", result["kind"])
            self.assertEqual([], result["folders"])
            self.assertEqual(0, result["result"]["processed"])
            browser.close()

    def test_footage_v3_named_person_context_switch_renders_through_montage_ui(self):
        """Actual UI/IPC/queue/source render; synthetic imagery is not face QA."""
        import numpy as np

        from scriptor.ai_index import SCREEN_TEXT_CLASSIFIER_VERSION, ClipIndex
        from scriptor.config import Settings, app_data_root, save_settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState
        from scriptor.session import save_session
        from scriptor.timeline import (
            TimelineProject,
            ffmpeg_executable,
            probe_media_duration,
        )

        fixture = self.test_root / "footage-v3-ui"
        fixture.mkdir(exist_ok=True)
        library = fixture / "library"
        library.mkdir(exist_ok=True)
        index = ClipIndex(app_data_root() / "footage-index.sqlite3")
        for number, tag in enumerate(("parliament-government", "oil-tanker-port")):
            path = library / f"pattern_{number}.mp4"
            subprocess.run([ffmpeg_executable(), "-y", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=30:d=7",
                            "-an", "-c:v", "libx264", str(path)], check=True, capture_output=True)
            stat = path.stat()
            with index._connect() as connection:
                connection.execute(
                    "INSERT INTO clips(path,name,size,mtime_ns,embedding,tags,duration,width,height,fps,"
                    "english_text,english_text_version) VALUES(?,?,?,?,?,?,7,320,180,30,-1,?)",
                    (str(path), path.name, stat.st_size, stat.st_mtime_ns,
                     np.full(8, 1 / np.sqrt(8), dtype=np.float32).tobytes(),
                     json.dumps([tag]), SCREEN_TEXT_CLASSIFIER_VERSION),
                )
        voice = fixture / "tone.wav"
        subprocess.run([ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=12", str(voice)],
                       check=True, capture_output=True)
        title = "Footage V3 source UI"
        settings = Settings(
            footage_folders=[str(library)], montage_project_folder=str(fixture / "projects"),
            montage_output_folder=str(fixture / "outputs"), montage_renderer="ffmpeg",
            montage_export_davinci_xml=False, montage_auto_web=False, montage_scene_planner="local",
            montage_intro_enabled=False, montage_overlay_enabled=False, montage_transition_style="cut",
            montage_transition_frames=0, montage_fast_reuse_enabled=True, montage_unique_footage_percent=50,
            voice_scenario_outputs={"1": str(voice)},
        )
        save_settings(settings)
        save_session([title], [Job(ScenarioRequest(0, title, ""), RunState.DONE,
                                  "Путин выступил с заявлением. Танкер прибыл в порт.", "")])
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.get_by_role("button", name="ПРОИЗВОДСТВО", exact=True).click()
            page.get_by_role("button", name="Монтаж", exact=True).first.click()
            page.get_by_role("button", name="Собрать незавершённые", exact=True).click()
            deadline = time.monotonic() + 120
            task = None
            while time.monotonic() < deadline:
                state = page.evaluate("async () => await window.newsflowDesktop.snapshot()")
                task = next((item for item in state["montageTasks"] if item["status"] == "Готово"), None)
                if task:
                    break
                failures = [item for item in state["montageTasks"] if item["status"] == "Ошибка"]
                self.assertEqual([], failures)
                page.wait_for_timeout(1000)
            self.assertIsNotNone(task, "montage queue did not produce a completed task")
            project_path = Path(task.get("projectPath", ""))
            self.assertTrue(project_path.is_file(), task)
            project = TimelineProject.load(project_path)
            self.assertIn("Putin", project.clips[0].visual_query_en)
            self.assertIn("tanker", project.clips[1].visual_query_en)
            self.assertNotEqual(project.clips[0].path, project.clips[1].path)
            self.assertNotEqual(project.clips[0].selection_diagnostics["person"]["status"], "confirmed")
            mp4 = Path(task["outputPath"])
            self.assertAlmostEqual(probe_media_duration(mp4), 12, delta=.25)
            prepared = [(clip.path, clip.source_start, clip.duration) for clip in project.clips]
            page.reload()
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            reloaded = TimelineProject.load(project_path)
            self.assertEqual(prepared, [(clip.path, clip.source_start, clip.duration) for clip in reloaded.clips])
            browser.close()

    def test_production_reset_uses_in_app_dialog(self):
        """The desktop must not depend on unsupported browser prompt() dialogs."""
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.get_by_role("button", name="Генерация идей").click()
            page.get_by_role("button", name="Удалить всё производство").click()

            dialog = page.get_by_role("dialog", name="Удалить всё производство")
            dialog.wait_for(timeout=10_000)
            self.assertEqual("", page.get_by_label("Контрольная фраза").input_value())
            page.get_by_role("button", name="Отмена").click()
            dialog.wait_for(state="detached", timeout=10_000)
            browser.close()

    def test_accessibility_and_ux_guards(self):
        self._launch()
        self._wait_for_cdp()
        from playwright.sync_api import sync_playwright

        axe_source = APP_ROOT / "node_modules" / "axe-core" / "axe.min.js"
        self.assertTrue(axe_source.is_file(), "install the pinned axe-core test dependency")

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            page = next(page for context in browser.contexts for page in context.pages)
            page.locator(".nf-page-header h1").wait_for(timeout=20_000)
            page.add_script_tag(url=axe_source.as_uri())
            report = page.evaluate("""async () => (await axe.run(document, {
                runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
            })).violations.map(({ id, impact, nodes }) => ({
                id,
                impact,
                targets: nodes.map(({ target, html }) => ({ target, html })),
            }))""")
            self.assertEqual([], report, f"axe violations: {report}")

            page.get_by_role("button", name="ОБЛОЖКИ И ГЕНЕРАЦИИ").click()
            page.get_by_role("button", name="Обложки YouTube").click()
            page.get_by_role("button", name="Настроить студию").click()
            dialog = page.get_by_role("dialog", name="Настройки Visual Production Studio")
            dialog.wait_for(timeout=10_000)
            page.keyboard.press("Tab")
            focus_is_trapped = dialog.evaluate("node => node.contains(document.activeElement)")
            self.assertTrue(focus_is_trapped, "Sheet focus escaped its modal dialog")

            geometry = dialog.evaluate("""node => {
                const rect = node.getBoundingClientRect();
                return {
                    clientWidth: node.clientWidth,
                    scrollWidth: node.scrollWidth,
                    left: rect.left,
                    right: rect.right,
                    top: rect.top,
                    bottom: rect.bottom,
                    viewportWidth: window.innerWidth,
                    viewportHeight: window.innerHeight,
                    documentClientWidth: document.documentElement.clientWidth,
                    documentScrollWidth: document.documentElement.scrollWidth,
                };
            }""")
            self.assertLessEqual(
                geometry["documentScrollWidth"],
                geometry["documentClientWidth"],
                f"Page has horizontal overflow: {geometry}",
            )
            self.assertLessEqual(geometry["scrollWidth"], geometry["clientWidth"], "Sheet content overflows horizontally")
            self.assertGreaterEqual(geometry["left"], 0, "Sheet starts outside the viewport")
            # Electron on Windows reports the usable document width without the
            # native scrollbar gutter, while a fixed Sheet can legitimately
            # occupy that visible gutter. A larger excursion is off-screen.
            self.assertLessEqual(geometry["right"], geometry["viewportWidth"] + 20, "Sheet extends past the viewport")
            self.assertGreaterEqual(geometry["top"], 0, "Sheet starts above the viewport")
            self.assertLessEqual(geometry["bottom"], geometry["viewportHeight"], "Sheet extends below the viewport")
            browser.close()
