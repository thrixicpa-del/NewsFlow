"""Frozen-resource regressions: inventory consistency is not runtime validity."""
from __future__ import annotations

import hashlib
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_core_runtime_guard as core_tests

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"
BUNDLED = "_internal/assets/ffmpeg.exe"
PACKAGED = f"win-unpacked/resources/core-bin/{BUNDLED}"
POINTER = (
    "version https://git-lfs.github.com/spec/v1\n"
    "oid sha256:2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3\n"
    "size 87638016\n"
).encode("ascii")


def pe_fixture() -> bytes:
    """Structural PE fixture only; not presented as an executable smoke."""
    data = bytearray(512)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    return bytes(data)


def write_asset_lock(app: Path, payload: bytes) -> None:
    (app / "core-assets-lock.json").write_text(json.dumps({
        "format": 1,
        "ffmpeg": {"size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
    }), encoding="utf-8")


class AnalysisReached(Exception):
    pass


class CoreAssetGuardTests(unittest.TestCase):
    def _fixture(self, temporary):
        root, app, executable = core_tests.CoreRuntimeGuardTests()._fixture(temporary)
        shutil.copy2(APP_ROOT / "scripts/verify-immutable-rc.mjs", app / "scripts/verify-immutable-rc.mjs")
        helper = APP_ROOT / "scripts/verify-core-assets.mjs"
        if helper.exists():  # Allows the exact negative tests to run against Base.
            shutil.copy2(helper, app / "scripts" / helper.name)
        asset = executable.parent / BUNDLED
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(pe_fixture())
        write_asset_lock(app, pe_fixture())
        return root, app, executable, asset

    def _run(self, app, script, *args):
        return subprocess.run(
            ["node", f"scripts/{script}", *map(str, args)], cwd=app,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20, check=False,
        )

    def _spec_result(self, root, app, payload):
        asset = root / "assets/ffmpeg.exe"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(payload)
        write_asset_lock(app, pe_fixture())
        modules = {name: types.ModuleType(name) for name in (
            "PyInstaller", "PyInstaller.utils", "PyInstaller.utils.hooks",
        )}

        def stop_before_analysis(*_args, **_kwargs):
            raise AnalysisReached("dependency collection reached")

        modules["PyInstaller.utils.hooks"].collect_all = stop_before_analysis
        with patch.dict(sys.modules, modules):
            try:
                runpy.run_path(str(ROOT / "Scriptor.spec"), init_globals={
                    "SPEC": str(root / "Scriptor.spec"), "SPECPATH": str(root),
                })
            except (RuntimeError, AnalysisReached) as error:
                return error
        self.fail("spec neither rejected the asset nor reached dependency collection")

    def _candidate(self, root, payload, *, omit_inventory=False, omit_asset=False):
        candidate = root / "candidate"
        candidate.mkdir()
        core = candidate / "win-unpacked/resources/core-bin/NewsFlowCore.exe"
        core.parent.mkdir(parents=True)
        core.write_bytes(b"fixture-core")
        asset = candidate / PACKAGED
        if not omit_asset:
            asset.parent.mkdir(parents=True)
            asset.write_bytes(payload)
        identity = {"gitSha": "1" * 40, "coreBinSha256": hashlib.sha256(core.read_bytes()).hexdigest()}
        (candidate / "build-manifest.json").write_text(json.dumps({**identity, "buildType": "RC"}))
        files = [core] + ([] if omit_inventory or omit_asset else [asset])
        entries = [{"path": file.relative_to(candidate).as_posix(),
                    "size": file.stat().st_size,
                    "sha256": hashlib.sha256(file.read_bytes()).hexdigest()} for file in files]
        (candidate / "artifact-hashes.json").write_text(json.dumps({**identity, "artifacts": entries}))
        return candidate

    def test_spec_rejects_pointer_before_dependency_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            result = self._spec_result(root, app, POINTER)
            self.assertIsInstance(result, RuntimeError, "PyInstaller accepted an LFS-pointer input")
            self.assertIn("LFS pointer", str(result))

    def test_spec_accepts_locked_pe_before_dependency_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            self.assertIsInstance(self._spec_result(root, app, pe_fixture()), AnalysisReached)

    def test_core_rejects_pointer_despite_matching_main_exe_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, app, _, asset = self._fixture(temporary)
            asset.write_bytes(POINTER)
            result = self._run(app, "verify-core-runtime.mjs")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LFS pointer", result.stderr)

    def test_core_rejects_missing_resource(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, app, _, asset = self._fixture(temporary)
            asset.unlink()
            result = self._run(app, "verify-core-runtime.mjs")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CORE_ASSET_INVALID", result.stderr)

    def test_core_rejects_wrong_bytes_even_when_size_and_pe_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, app, _, asset = self._fixture(temporary)
            data = bytearray(pe_fixture())
            data[-1] = 1
            asset.write_bytes(data)
            result = self._run(app, "verify-core-runtime.mjs")
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SHA-256", result.stderr)

    def test_core_accepts_locked_asset(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, app, _, _ = self._fixture(temporary)
            result = self._run(app, "verify-core-runtime.mjs")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rc_rejects_pointer_even_with_self_consistent_artifact_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            candidate = self._candidate(root, POINTER)
            result = self._run(app, "verify-immutable-rc.mjs", "--directory", candidate)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("LFS pointer", result.stderr)

    def test_rc_rejects_missing_asset_even_when_inventory_omits_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            candidate = self._candidate(root, pe_fixture(), omit_asset=True)
            result = self._run(app, "verify-immutable-rc.mjs", "--directory", candidate)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CORE_ASSET_INVALID", result.stderr)

    def test_rc_requires_asset_in_hash_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            candidate = self._candidate(root, pe_fixture(), omit_inventory=True)
            result = self._run(app, "verify-immutable-rc.mjs", "--directory", candidate)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("required FFmpeg", result.stderr)

    def test_rc_accepts_matching_resource_and_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, app, _, _ = self._fixture(temporary)
            candidate = self._candidate(root, pe_fixture())
            result = self._run(app, "verify-immutable-rc.mjs", "--directory", candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("CORE_MEDIA_SMOKE=PASS", result.stdout)

    def test_gate_requires_packaged_media_smoke(self):
        script = (ROOT / "scripts/release-gate.ps1").read_text(encoding="utf-8")
        invocation = next(line for line in script.splitlines() if "Invoke-GateStep -Name 'artifact-manifest'" in line)
        self.assertIn("'--media-smoke'", invocation)
        self.assertIn("$candidateRoot", invocation)

    def _smoke_harness(self, mode):
        helper = (APP_ROOT / "scripts/verify-core-assets.mjs").as_uri()
        source = r'''
import {runCoreMediaSmoke} from HELPER;
import fs from 'node:fs';
import path from 'node:path';
const calls = [];
const executable = path.resolve('fixture core', 'ffmpeg.exe');
const mode = MODE;
const runner = (exe, args, options) => {
  calls.push({exe, args, cwd: options.cwd, shell: options.shell});
  if (args.includes('libx264')) {
    if (mode === 'exit') return {status: 1, stderr: 'encoder failed'};
    if (mode !== 'missing') fs.writeFileSync(args.at(-1), 'fixture MP4');
  }
  return {status: 0, stdout: 'ffmpeg version fixture', stderr: ''};
};
try {
  runCoreMediaSmoke(executable, runner);
  console.log(JSON.stringify({calls, cleaned: !fs.existsSync(calls[0].cwd)}));
} catch (error) {
  console.error(String(error));
  process.exitCode = 1;
}
'''.replace("HELPER", json.dumps(helper)).replace("MODE", json.dumps(mode))
        return subprocess.run(["node", "--input-type=module", "-e", source],
                              capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)

    def test_media_smoke_uses_exact_executable_for_encode_and_decode(self):
        result = self._smoke_harness("ok")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(len(report["calls"]), 3)
        self.assertEqual(len({call["exe"] for call in report["calls"]}), 1)
        self.assertIn("libx264", report["calls"][1]["args"])
        self.assertIn("null", report["calls"][2]["args"])
        self.assertTrue(all(call["shell"] is False for call in report["calls"]))
        self.assertTrue(report["cleaned"])

    def test_media_smoke_rejects_encoder_failure(self):
        result = self._smoke_harness("exit")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CORE_MEDIA_SMOKE=FAIL", result.stderr)
        self.assertNotIn("CORE_MEDIA_SMOKE=PASS", result.stdout)

    def test_media_smoke_rejects_exit_zero_without_output(self):
        result = self._smoke_harness("missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CORE_MEDIA_SMOKE=FAIL", result.stderr)
        self.assertNotIn("CORE_MEDIA_SMOKE=PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
