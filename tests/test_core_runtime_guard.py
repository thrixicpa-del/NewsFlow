"""Executable checks for the pre-package Python-core freshness gate."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


class CoreRuntimeGuardTests(unittest.TestCase):
    def test_guard_rejects_a_core_older_than_current_montage_timeline(self):
        """A rebuilt bridge alone must not hide stale FFmpeg montage code."""
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root = Path(temporary)
            fixture_app = fixture_root / "studio-ui-remotion-verify"
            fixture_scriptor = fixture_root / "scriptor"
            fixture_core = fixture_root / ".core-bin-current" / "NewsFlowCore"
            (fixture_app / "scripts").mkdir(parents=True)
            fixture_scriptor.mkdir()
            fixture_core.mkdir(parents=True)

            package = {
                "build": {"extraResources": [{"from": "../.core-bin-current/NewsFlowCore", "to": "core-bin"}]},
            }
            (fixture_app / "package.json").write_text(json.dumps(package), encoding="utf-8")
            shutil.copy2(APP_ROOT / "scripts" / "verify-core-runtime.mjs", fixture_app / "scripts" / "verify-core-runtime.mjs")
            for filename in ("bridge.py", "timeline.py"):
                (fixture_scriptor / filename).write_text("# fixture\n", encoding="utf-8")
            (fixture_root / "bridge_main.py").write_text("# fixture\n", encoding="utf-8")
            executable = fixture_core / "NewsFlowCore.exe"
            executable.write_bytes(b"fixture")

            now = time.time()
            for source in (fixture_scriptor / "bridge.py", fixture_root / "bridge_main.py"):
                os.utime(source, (now - 20, now - 20))
            os.utime(executable, (now - 10, now - 10))
            os.utime(fixture_scriptor / "timeline.py", (now, now))

            result = subprocess.run(
                ["node", "scripts/verify-core-runtime.mjs"], cwd=fixture_app,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("timeline.py", result.stderr)

    def test_guard_rejects_a_core_older_than_current_scenario_core(self):
        """Prompt-contract fixes in core.py must be frozen into the packaged engine."""
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root = Path(temporary)
            fixture_app = fixture_root / "studio-ui-remotion-verify"
            fixture_scriptor = fixture_root / "scriptor"
            fixture_core = fixture_root / ".core-bin-current" / "NewsFlowCore"
            (fixture_app / "scripts").mkdir(parents=True)
            fixture_scriptor.mkdir()
            fixture_core.mkdir(parents=True)

            package = {
                "build": {"extraResources": [{"from": "../.core-bin-current/NewsFlowCore", "to": "core-bin"}]},
            }
            (fixture_app / "package.json").write_text(json.dumps(package), encoding="utf-8")
            shutil.copy2(APP_ROOT / "scripts" / "verify-core-runtime.mjs", fixture_app / "scripts" / "verify-core-runtime.mjs")
            for filename in ("bridge.py", "timeline.py", "core.py"):
                (fixture_scriptor / filename).write_text("# fixture\n", encoding="utf-8")
            (fixture_root / "bridge_main.py").write_text("# fixture\n", encoding="utf-8")
            executable = fixture_core / "NewsFlowCore.exe"
            executable.write_bytes(b"fixture")

            now = time.time()
            for source in (fixture_scriptor / "bridge.py", fixture_scriptor / "timeline.py", fixture_root / "bridge_main.py"):
                os.utime(source, (now - 20, now - 20))
            os.utime(executable, (now - 10, now - 10))
            os.utime(fixture_scriptor / "core.py", (now, now))

            result = subprocess.run(
                ["node", "scripts/verify-core-runtime.mjs"], cwd=fixture_app,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("core.py", result.stderr)

    def test_guard_rejects_a_core_older_than_the_imported_observability_runtime(self):
        """A bridge import must be frozen even when bridge.py itself is unchanged."""
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root = Path(temporary)
            fixture_app = fixture_root / "studio-ui-remotion-verify"
            fixture_scriptor = fixture_root / "scriptor"
            fixture_core = fixture_root / ".core-bin-current" / "NewsFlowCore"
            (fixture_app / "scripts").mkdir(parents=True)
            fixture_scriptor.mkdir()
            fixture_core.mkdir(parents=True)

            package = {
                "build": {"extraResources": [{"from": "../.core-bin-current/NewsFlowCore", "to": "core-bin"}]},
            }
            (fixture_app / "package.json").write_text(json.dumps(package), encoding="utf-8")
            shutil.copy2(APP_ROOT / "scripts" / "verify-core-runtime.mjs", fixture_app / "scripts" / "verify-core-runtime.mjs")
            for filename in ("bridge.py", "timeline.py", "core.py", "thumbnail_prompt_v2.py", "observability.py"):
                (fixture_scriptor / filename).write_text("# fixture\n", encoding="utf-8")
            (fixture_root / "bridge_main.py").write_text("# fixture\n", encoding="utf-8")
            executable = fixture_core / "NewsFlowCore.exe"
            executable.write_bytes(b"fixture")

            now = time.time()
            for source in (
                fixture_scriptor / "bridge.py", fixture_scriptor / "timeline.py", fixture_scriptor / "core.py",
                fixture_scriptor / "thumbnail_prompt_v2.py", fixture_root / "bridge_main.py",
            ):
                os.utime(source, (now - 20, now - 20))
            os.utime(executable, (now - 10, now - 10))
            os.utime(fixture_scriptor / "observability.py", (now, now))

            result = subprocess.run(
                ["node", "scripts/verify-core-runtime.mjs"], cwd=fixture_app,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=False,
            )

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("observability.py", result.stderr)


if __name__ == "__main__":
    unittest.main()
