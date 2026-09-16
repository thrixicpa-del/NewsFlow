from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import unittest
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


@unittest.skipUnless(os.environ.get("NEWSFLOW_RUN_ELECTRON_E2E") == "1", "set NEWSFLOW_RUN_ELECTRON_E2E=1")
class ElectronE2ESmokeTests(unittest.TestCase):
    """CDP/Playwright smoke for a real Electron process; providers are never invoked."""

    def setUp(self):
        self.test_root = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.test_root.mkdir(parents=True, exist_ok=True)
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
            pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
            if not pnpm:
                self.skipTest("pnpm is required to launch source Electron E2E")
            command = [pnpm, "exec", "electron", f"--remote-debugging-port={self.port}", "."]
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

        artifact = self.test_root / "artifacts" / "electron-e2e.png"
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
