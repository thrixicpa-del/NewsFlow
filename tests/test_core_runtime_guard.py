"""Executable checks for deterministic Frozen Core content identity."""

from __future__ import annotations

import hashlib
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

REQUIRED_SOURCES = (
    "scriptor/bridge.py",
    "scriptor/timeline.py",
    "scriptor/core.py",
    "scriptor/thumbnail_prompt_v2.py",
    "scriptor/observability.py",
    "bridge_main.py",
)


def _git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("utf-8")
    return hashlib.sha1(header + content).hexdigest()


class CoreRuntimeGuardTests(unittest.TestCase):
    def _fixture(self, temporary: str):
        fixture_root = Path(temporary)
        fixture_app = fixture_root / "studio-ui-remotion-verify"
        fixture_core = fixture_root / "core-bin-test" / "NewsFlowCore"
        (fixture_app / "scripts").mkdir(parents=True)
        fixture_core.mkdir(parents=True)

        shutil.copy2(
            APP_ROOT / "scripts" / "verify-core-runtime.mjs",
            fixture_app / "scripts" / "verify-core-runtime.mjs",
        )

        package = {
            "version": "2.1.152",
            "build": {
                "extraResources": [
                    {"from": "../core-bin-test/NewsFlowCore", "to": "core-bin"},
                ],
            },
        }
        (fixture_app / "package.json").write_text(json.dumps(package), encoding="utf-8")

        source_bytes = {}
        for index, relative in enumerate(REQUIRED_SOURCES, start=1):
            content = f"# fixture {index}\n".encode("utf-8")
            source_bytes[relative] = content
            target = fixture_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        core_bytes = b"fixture-core-binary"
        executable = fixture_core / "NewsFlowCore.exe"
        executable.write_bytes(core_bytes)

        lock = {
            "format": 1,
            "appVersion": "2.1.152",
            "coreRevision": "core-bin-test",
            "coreExeSha256": hashlib.sha256(core_bytes).hexdigest(),
            "coreExeSize": len(core_bytes),
            "builtFromGitSha": "0" * 40,
            "sourceGitBlobs": {
                relative: _git_blob_sha(content)
                for relative, content in source_bytes.items()
            },
        }
        (fixture_app / "core-runtime-lock.json").write_text(
            json.dumps(lock),
            encoding="utf-8",
        )
        return fixture_root, fixture_app, executable

    def _run(self, fixture_app: Path):
        return subprocess.run(
            ["node", "scripts/verify-core-runtime.mjs"],
            cwd=fixture_app,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_guard_accepts_matching_content_even_when_checkout_mtimes_are_newer(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, executable = self._fixture(temporary)

            now = time.time()
            os.utime(executable, (now - 3600, now - 3600))
            for relative in REQUIRED_SOURCES:
                source = fixture_root / relative
                os.utime(source, (now, now))

            result = self._run(fixture_app)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("актуально по содержимому", result.stdout)

    def test_guard_rejects_changed_montage_timeline_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "scriptor" / "timeline.py").write_text(
                "# changed timeline\n",
                encoding="utf-8",
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scriptor/timeline.py", result.stderr)
            self.assertIn("Пересоберите core-bin", result.stderr)

    def test_guard_rejects_changed_scenario_core_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "scriptor" / "core.py").write_text(
                "# changed scenario core\n",
                encoding="utf-8",
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scriptor/core.py", result.stderr)

    def test_guard_rejects_changed_observability_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "scriptor" / "observability.py").write_text(
                "# changed observability\n",
                encoding="utf-8",
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scriptor/observability.py", result.stderr)

    def test_guard_rejects_core_binary_hash_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            _, fixture_app, executable = self._fixture(temporary)
            executable.write_bytes(b"different-core-binary")

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Frozen Core SHA-256", result.stderr)


if __name__ == "__main__":
    unittest.main()
