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
    "scriptor/ai_index.py",
    "scriptor/onnx_clip.py",
    "scriptor/scene_intent.py",
    "scriptor/visual_evidence.py",
    "scriptor/config.py",
    "scriptor/core.py",
    "scriptor/runner.py",
    "scriptor/story_planner.py",
    "scriptor/openai_client.py",
    "scriptor/timeline.py",
    "scriptor/media_health.py",
    "scriptor/thumbnail_prompt_v2.py",
    "scriptor/observability.py",
    "scriptor/footage_block_bridge.py",
    "scriptor/footage_blocks.py",
    "scriptor/montage_blocks.py",
    "scriptor/montage_continuity.py",
    "scriptor/stock_credits.py",
    "scriptor/stock_downloads.py",
    "scriptor/stock_history.py",
    "scriptor/stock_media.py",
    "scriptor/stock_selection.py",
    "scriptor/stock_sources.py",
    "scriptor/overlay_library.py",
    "scriptor/overlays.py",
    "bridge_main.py",
    "Scriptor.spec",
)


def _git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
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

        shutil.copy2(
            APP_ROOT / "scripts" / "verify-core-assets.mjs",
            fixture_app / "scripts" / "verify-core-assets.mjs",
        )
        # Structural fixture for hash validation, not a Windows execution smoke.
        asset_bytes = bytearray(512)
        asset_bytes[:2] = b"MZ"
        asset_bytes[60:64] = (128).to_bytes(4, "little")
        asset_bytes[128:132] = b"PE\0\0"
        asset = fixture_core / "_internal" / "assets" / "ffmpeg.exe"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(asset_bytes)
        (fixture_app / "core-assets-lock.json").write_text(json.dumps({
            "format": 1,
            "ffmpeg": {"size": len(asset_bytes), "sha256": hashlib.sha256(asset_bytes).hexdigest()},
        }), encoding="utf-8")

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
            content = f"# fixture {index}\n".encode()
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

    def test_guard_rejects_changed_stock_download_queue_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _executable = self._fixture(temporary)
            relative = "scriptor/stock_downloads.py"
            source = fixture_root / relative
            source.write_bytes(b"# stock queue included in the built core\n")
            lock_path = fixture_app / "core-runtime-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["sourceGitBlobs"][relative] = _git_blob_sha(source.read_bytes())
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            matching = self._run(fixture_app)
            self.assertEqual(matching.returncode, 0, matching.stdout + matching.stderr)

            source.write_bytes(b"# queue implementation changed after the core build\n")
            stale = self._run(fixture_app)
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn(relative, stale.stdout + stale.stderr)

    def test_guard_requires_stock_download_queue_identity(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            _fixture_root, fixture_app, _executable = self._fixture(temporary)
            lock_path = fixture_app / "core-runtime-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["sourceGitBlobs"].pop("scriptor/stock_downloads.py", None)
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            result = self._run(fixture_app)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("scriptor/stock_downloads.py", result.stdout + result.stderr)

    def test_repository_lock_matches_current_source_and_package_revision(self):
        lock = json.loads((APP_ROOT / "core-runtime-lock.json").read_text(encoding="utf-8"))
        package = json.loads((APP_ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(lock["appVersion"], package["version"])
        self.assertEqual(lock["coreRevision"], ".core-bin-2.1.152-stock-r53")
        self.assertEqual(
            lock["coreExeSha256"],
            "9b94eaf4bbb6405e92c84b1e011bded93fc59afe3a258e21c5584053ca9e6400",
        )
        self.assertEqual(lock["coreExeSize"], 21798863)
        self.assertEqual(
            lock["builtFromGitSha"],
            "a8fd3e98498ccdce554747eae07368087e7b4bec",
        )
        self.assertEqual(
            set(lock["sourceGitBlobs"]),
            set(REQUIRED_SOURCES),
            "Frozen Core lock must identify every source covered by the runtime guard",
        )

        resources = package["build"]["extraResources"]
        core_resource = next(resource for resource in resources if resource.get("to") == "core-bin")
        tcl_resource = next(resource for resource in resources if resource.get("to") == "core-tcl-data")
        normalized_core = str(core_resource["from"]).replace("\\", "/")
        normalized_tcl = str(tcl_resource["from"]).replace("\\", "/")
        self.assertIn(lock["coreRevision"], normalized_core.split("/"))
        self.assertIn(lock["coreRevision"], normalized_tcl.split("/"))

        for relative in REQUIRED_SOURCES:
            actual = _git_blob_sha((ROOT / relative).read_bytes())
            self.assertEqual(
                actual,
                lock["sourceGitBlobs"][relative],
                f"tracked Frozen Core lock is stale for {relative}",
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

    def test_guard_rejects_changed_footage_semantic_runtime(self):
        for relative in ("scriptor/scene_intent.py", "scriptor/visual_evidence.py"):
            with self.subTest(source=relative), tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
                fixture_root, fixture_app, _ = self._fixture(temporary)
                source = fixture_root / relative
                original = b"# semantic runtime fixture\n"
                lock_path = fixture_app / "core-runtime-lock.json"
                lock = json.loads(lock_path.read_text(encoding="utf-8"))
                lock["sourceGitBlobs"][relative] = _git_blob_sha(original)
                lock_path.write_text(json.dumps(lock), encoding="utf-8")
                source.write_bytes(b"# changed semantic runtime\n")
                result = self._run(fixture_app)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(relative, result.stderr)

    def test_guard_rejects_changed_scenario_runtime_support_content(self):
        for relative in ("scriptor/config.py", "scriptor/runner.py", "scriptor/story_planner.py"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
                fixture_root, fixture_app, _ = self._fixture(temporary)
                (fixture_root / relative).write_text("# changed scenario runtime support\n", encoding="utf-8")

                result = self._run(fixture_app)

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(relative, result.stderr)
                self.assertIn("Пересоберите core-bin", result.stderr)

    def test_guard_rejects_changed_frozen_core_build_spec(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "Scriptor.spec").write_text(
                "# changed frozen core build specification\n", encoding="utf-8"
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Scriptor.spec", result.stderr)

    def test_guard_rejects_changed_openai_client_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "scriptor" / "openai_client.py").write_text(
                "# changed OpenAI runtime transport\n",
                encoding="utf-8",
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scriptor/openai_client.py", result.stderr)
            self.assertIn("Пересоберите core-bin", result.stderr)

    def test_guard_rejects_changed_footage_index_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            (fixture_root / "scriptor" / "ai_index.py").write_text(
                "# changed footage index\n",
                encoding="utf-8",
            )

            result = self._run(fixture_app)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("scriptor/ai_index.py", result.stderr)
            self.assertIn("Пересоберите core-bin", result.stderr)

    def test_guard_rejects_changed_media_health_content(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-core-runtime-guard-") as temporary:
            fixture_root, fixture_app, _ = self._fixture(temporary)
            relative = "scriptor/media_health.py"
            source = fixture_root / relative
            original = b"# built media validator\n"
            source.write_bytes(original)
            lock_path = fixture_app / "core-runtime-lock.json"
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            lock["sourceGitBlobs"][relative] = _git_blob_sha(original)
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            source.write_bytes(b"# changed quarantine policy\n")
            result = self._run(fixture_app)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(relative, result.stderr)

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
