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
    def test_guard_rejects_a_stale_implicit_remotion_renderer(self):
        """A package check must reject an old slow default before it can ship."""
        with tempfile.TemporaryDirectory(prefix="newsflow-build-montage-guard-") as temporary:
            fixture_root = Path(temporary)
            fixture_app = fixture_root / "studio-ui-remotion-verify"
            fixture_scriptor = fixture_root / "scriptor"
            (fixture_app / "scripts").mkdir(parents=True)
            (fixture_app / "electron").mkdir(parents=True)
            fixture_scriptor.mkdir()

            for filename in ("package.json", "pnpm-lock.yaml"):
                shutil.copy2(APP_ROOT / filename, fixture_app / filename)
            shutil.copy2(APP_ROOT / "scripts" / "verify-build-runtime.mjs", fixture_app / "scripts" / "verify-build-runtime.mjs")
            shutil.copy2(APP_ROOT / "electron" / "main.ts", fixture_app / "electron" / "main.ts")
            shutil.copy2(ROOT / "Scriptor.spec", fixture_root / "Scriptor.spec")
            for filename in ("config.py", "bridge.py", "session.py", "thumbnail_prompt_v2.py"):
                shutil.copy2(ROOT / "scriptor" / filename, fixture_scriptor / filename)

            stale_timeline = (ROOT / "scriptor" / "timeline.py").read_text(encoding="utf-8").replace(
                'renderer: str = "ffmpeg"', 'renderer: str = "remotion"', 1,
            )
            self.assertIn('renderer: str = "remotion"', stale_timeline)
            (fixture_scriptor / "timeline.py").write_text(stale_timeline, encoding="utf-8")

            result = subprocess.run(
                ["node", "scripts/verify-build-runtime.mjs"], cwd=fixture_app,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("FAST NEWS Montage", result.stderr)


if __name__ == "__main__":
    unittest.main()
