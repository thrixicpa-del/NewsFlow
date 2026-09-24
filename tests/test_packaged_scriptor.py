"""Execute package validators against disposable Scriptor payload fixtures.

These are structural regression tests, not a Windows EXE or media smoke.
Every negative fixture has a freshly generated, internally consistent hash
inventory, reproducing files omitted during packaging rather than tampering.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "studio-ui-remotion-verify"


class PackagedScriptorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="newsflow-package-scriptor-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "app"
        scripts = self.app / "scripts"
        scripts.mkdir(parents=True)
        for name in (
            "verify-portable.mjs",
            "verify-immutable-rc.mjs",
            "verify-core-assets.mjs",
            "finalize-immutable-rc.mjs",
        ):
            shutil.copy2(APP / "scripts" / name, scripts / name)
        (self.app / "package.json").write_text(
            json.dumps({"version": "2.1.152", "build": {}}), encoding="utf-8"
        )
        self.candidate = self.root / "candidate"
        self.resources = self.candidate / "win-unpacked" / "resources"
        for relative in (
            "app.asar",
            "app.asar.unpacked/remotion/render.mjs",
            "app.asar.unpacked/remotion-bundle/index.html",
            "remotion-binaries/ffmpeg.exe",
            "remotion-binaries/ffprobe.exe",
            "core-tcl-data/init.tcl",
            "core-bin/NewsFlowCore.exe",
            "core-bin/_internal/_tcl_data/init.tcl",
            "core/scriptor/__init__.py",
            "core/scriptor/bridge.py",
        ):
            target = self.resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"# structural fixture\n")
        # A synthetic PE header for the structural verifier; never executed.
        ffmpeg = bytearray(512)
        ffmpeg[:2] = b"MZ"
        ffmpeg[60:64] = (128).to_bytes(4, "little")
        ffmpeg[128:132] = b"PE\0\0"
        asset = self.resources / "core-bin/_internal/assets/ffmpeg.exe"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(ffmpeg)
        (self.app / "core-assets-lock.json").write_text(json.dumps({
            "format": 1,
            "ffmpeg": {"size": len(ffmpeg), "sha256": hashlib.sha256(ffmpeg).hexdigest()},
        }), encoding="utf-8")
        (self.candidate / "NewsFlow Studio.exe").write_bytes(b"structural portable fixture")
        (self.candidate / "build-manifest.json").write_text(json.dumps({
            "gitSha": "1" * 40,
            "coreBinSha256": "2" * 64,
            "buildType": "TEST",
        }), encoding="utf-8")
        self.scriptor = self.resources / "core/scriptor"

    def _run(self, script):
        arguments = [str(self.candidate)] if script == "verify-portable.mjs" else [
            "--directory", str(self.candidate)
        ]
        return subprocess.run(
            ["node", f"scripts/{script}", *arguments], cwd=self.app,
            text=True, encoding="utf-8", errors="replace", capture_output=True,
            timeout=30, check=False,
        )

    def _finalize(self):
        result = self._run("finalize-immutable-rc.mjs")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def _assert_rejected_by_both(self):
        self._finalize()
        for script in ("verify-portable.mjs", "verify-immutable-rc.mjs"):
            with self.subTest(script=script):
                result = self._run(script)
                self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertIn("scriptor", result.stderr.lower())

    def test_complete_scriptor_payload_is_accepted(self):
        self._finalize()
        for script in ("verify-portable.mjs", "verify-immutable-rc.mjs"):
            with self.subTest(script=script):
                result = self._run(script)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_omitted_scriptor_is_rejected_with_consistent_hash_inventory(self):
        shutil.rmtree(self.scriptor)
        self._assert_rejected_by_both()

    def test_empty_scriptor_directory_is_rejected(self):
        shutil.rmtree(self.scriptor)
        self.scriptor.mkdir()
        self._assert_rejected_by_both()

    def test_initializer_without_bridge_is_rejected(self):
        (self.scriptor / "bridge.py").unlink()
        self._assert_rejected_by_both()

    def test_directory_instead_of_bridge_file_is_rejected(self):
        (self.scriptor / "bridge.py").unlink()
        (self.scriptor / "bridge.py").mkdir()
        self._assert_rejected_by_both()

    def test_empty_bridge_file_is_rejected(self):
        (self.scriptor / "bridge.py").write_bytes(b"")
        self._assert_rejected_by_both()

    def test_file_instead_of_scriptor_directory_is_rejected(self):
        shutil.rmtree(self.scriptor)
        self.scriptor.write_bytes(b"not a source directory")
        self._assert_rejected_by_both()

    def test_rc_inventory_must_include_required_scriptor_files(self):
        self._finalize()
        inventory = self.candidate / "artifact-hashes.json"
        hashes = json.loads(inventory.read_text(encoding="utf-8"))
        hashes["artifacts"] = [
            entry for entry in hashes["artifacts"]
            if entry["path"] != "win-unpacked/resources/core/scriptor/bridge.py"
        ]
        inventory.write_text(json.dumps(hashes), encoding="utf-8")
        result = self._run("verify-immutable-rc.mjs")
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("scriptor", result.stderr.lower())
