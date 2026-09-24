"""Executable regression tests for the pre-package FAST NEWS Montage gate."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


class BuildMontageRuntimeGuardTests(unittest.TestCase):
    def _run_guard(self, *, timeline_source: str | None = None, bridge_source: str | None = None):
        with tempfile.TemporaryDirectory(prefix="newsflow-build-montage-guard-") as temporary:
            fixture_root = Path(temporary)
            fixture_app = fixture_root / "studio-ui-remotion-verify"
            fixture_scriptor = fixture_root / "scriptor"
            (fixture_app / "scripts").mkdir(parents=True)
            (fixture_app / "electron").mkdir(parents=True)
            fixture_scriptor.mkdir()

            for filename in ("package.json", "pnpm-lock.yaml"):
                shutil.copy2(APP_ROOT / filename, fixture_app / filename)
            shutil.copy2(
                APP_ROOT / "scripts" / "verify-build-runtime.mjs",
                fixture_app / "scripts" / "verify-build-runtime.mjs",
            )
            shutil.copy2(APP_ROOT / "electron" / "main.ts", fixture_app / "electron" / "main.ts")
            shutil.copy2(ROOT / "Scriptor.spec", fixture_root / "Scriptor.spec")
            for filename in ("config.py", "session.py", "thumbnail_prompt_v2.py"):
                shutil.copy2(ROOT / "scriptor" / filename, fixture_scriptor / filename)

            (fixture_scriptor / "bridge.py").write_text(
                bridge_source if bridge_source is not None
                else (ROOT / "scriptor" / "bridge.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (fixture_scriptor / "timeline.py").write_text(
                timeline_source if timeline_source is not None
                else (ROOT / "scriptor" / "timeline.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            return subprocess.run(
                ["node", "scripts/verify-build-runtime.mjs"],
                cwd=fixture_app,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

    def test_guard_accepts_current_montage_queue_wiring(self):
        """The package guard must accept the queue/render call shipped by current source."""
        result = self._run_guard()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Build runtime protection passed", result.stdout)

    def test_guard_rejects_a_stale_implicit_remotion_renderer(self):
        """A package check must reject an old slow default before it can ship."""
        timeline_source = (ROOT / "scriptor" / "timeline.py").read_text(encoding="utf-8").replace(
            'renderer: str = "ffmpeg"', 'renderer: str = "remotion"', 1,
        )
        self.assertIn('renderer: str = "remotion"', timeline_source)

        result = self._run_guard(timeline_source=timeline_source)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FAST NEWS Montage is missing the current FFmpeg default", result.stderr)

    def test_guard_rejects_queue_that_bypasses_the_saved_renderer(self):
        """The queue must pass its saved renderer explicitly to render_project."""
        bridge_source = (ROOT / "scriptor" / "bridge.py").read_text(encoding="utf-8")
        current_call = (
            "render_project(project, staged_output, progress=progress, "
            "renderer=settings.montage_renderer,"
        )
        stale_call = (
            "render_project(project, staged_output, progress=progress, "
            'renderer="remotion",'
        )
        self.assertIn(current_call, bridge_source)
        bridge_source = bridge_source.replace(current_call, stale_call, 1)

        result = self._run_guard(bridge_source=bridge_source)

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("FAST NEWS Montage queue is not wired to the current bridge and render service", result.stderr)


if __name__ == "__main__":
    unittest.main()
