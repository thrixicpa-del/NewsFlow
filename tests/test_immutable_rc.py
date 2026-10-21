from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_core_runtime_guard as core_tests

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"


class ImmutableRcTests(unittest.TestCase):
    def _windows_packaging_invocation(self):
        """Execute the real wrapper with process/filesystem side effects stubbed."""
        script = r"""
import fs from 'node:fs';
import child from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
const calls = [];
Object.defineProperty(process, 'platform', { value: 'win32' });
process.argv = [process.execPath, 'fixture', '--output-root', 'fixture-output', '--type', 'TEST', '--rc', '03'];
process.env.NEWSFLOW_PACKAGING_SENTINEL = 'preserved';
process.env.ELECTRON_BUILDER_7Z_FILTER = 'ARM';
child.execFileSync = (command, args, options = {}) => {
  calls.push({ command, args, cwd: options.cwd, shell: options.shell,
    filter: options.env?.ELECTRON_BUILDER_7Z_FILTER,
    sentinel: options.env?.NEWSFLOW_PACKAGING_SENTINEL });
  return args[0] === 'scripts/prepare-immutable-rc.mjs' ? 'fixture-candidate\n' : Buffer.alloc(0);
};
fs.existsSync = () => false;
fs.mkdirSync = fs.cpSync = fs.rmSync = () => {};
syncBuiltinESMExports();
await import('./scripts/package-immutable-rc.mjs');
console.log(JSON.stringify({ calls, originalFilter: process.env.ELECTRON_BUILDER_7Z_FILTER }));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=APP, text=True, capture_output=True, check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_packaging_wrapper_executes_windows_pnpm_shims_through_cmd(self):
        wrapper = (APP / "scripts" / "package-immutable-rc.mjs").read_text(encoding="utf-8")

        self.assertIn('command.toLowerCase().endsWith(".cmd")', wrapper)
        self.assertIn('shell: process.platform === "win32"', wrapper)
        self.assertIn('`--config.directories.output="${stagingRoot}"`', wrapper)

    def test_windows_packaging_uses_a_short_subst_workdir_for_nsis_templates(self):
        calls = self._windows_packaging_invocation()["calls"]
        mapping = next(call for call in calls if call["command"] == "subst.exe")
        builder = next(call for call in calls if call["args"][:2] == ["exec", "electron-builder"])
        self.assertEqual(str(ROOT), mapping["args"][1])
        self.assertEqual(f'{mapping["args"][0]}\\{APP.name}', builder["cwd"])
        self.assertEqual([mapping["args"][0], "/D"], calls[-1]["args"])

    def test_windows_builder_receives_compatible_filter_and_inherited_environment(self):
        invocation = self._windows_packaging_invocation()
        builder = next(call for call in invocation["calls"] if call["args"][:2] == ["exec", "electron-builder"])
        self.assertEqual("BCJ", builder["filter"])
        self.assertEqual("preserved", builder["sentinel"])
        self.assertEqual("ARM", invocation["originalFilter"])
        self.assertEqual("pnpm.cmd", builder["command"])
        self.assertTrue(builder["shell"])

    def test_windows_subst_keeps_declared_parent_resources_available(self):
        """The short drive must include ../scriptor used by electron-builder."""
        wrapper = (APP / "scripts" / "package-immutable-rc.mjs").read_text(encoding="utf-8")

        self.assertIn('const repositoryRoot = path.resolve(appRoot, "..");', wrapper)
        self.assertIn('execFileSync("subst.exe", [drive, repositoryRoot]', wrapper)
        self.assertIn('cwd: `${drive}\\\\${path.basename(appRoot)}`', wrapper)

    def test_rc_directory_is_commit_addressed_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            command = ["node", "scripts/prepare-immutable-rc.mjs", "--output-root", directory, "--type", "TEST", "--rc", "01"]
            first = subprocess.run(command, cwd=APP, text=True, capture_output=True, check=False)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            created = Path(first.stdout.strip().splitlines()[-1])
            manifest = json.loads((created / "build-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("TEST", manifest["buildType"])
            second = subprocess.run(command, cwd=APP, text=True, capture_output=True, check=False)
            self.assertNotEqual(0, second.returncode)

    def test_rc_finalization_records_the_actual_packaged_exe_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = subprocess.run(
                ["node", "scripts/prepare-immutable-rc.mjs", "--output-root", directory, "--type", "TEST", "--rc", "02"],
                cwd=APP,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, prepared.returncode, prepared.stdout + prepared.stderr)
            artifact_root = Path(prepared.stdout.strip().splitlines()[-1])
            exe = artifact_root / "NewsFlow Studio.exe"
            exe.write_bytes(b"portable test artifact")
            finalized = subprocess.run(
                ["node", "scripts/finalize-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=APP,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, finalized.returncode, finalized.stdout + finalized.stderr)
            hashes = json.loads((artifact_root / "artifact-hashes.json").read_text(encoding="utf-8"))
            entries = {entry["path"]: entry for entry in hashes["artifacts"]}
            self.assertEqual(hashlib.sha256(exe.read_bytes()).hexdigest(), entries["NewsFlow Studio.exe"]["sha256"])

    def test_packaging_wrapper_reserves_a_unique_immutable_target_before_building(self):
        with tempfile.TemporaryDirectory() as directory:
            command = [
                "node",
                "scripts/package-immutable-rc.mjs",
                "--output-root",
                directory,
                "--type",
                "TEST",
                "--rc",
                "03",
                "--dry-run",
            ]
            first = subprocess.run(command, cwd=APP, text=True, capture_output=True, check=False)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            target = Path(first.stdout.strip().splitlines()[-1])
            self.assertTrue((target / "build-manifest.json").is_file())
            second = subprocess.run(command, cwd=APP, text=True, capture_output=True, check=False)
            self.assertNotEqual(0, second.returncode)

    def test_rc_verifier_rejects_a_tampered_packaged_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            # Hash verification uses structural fixtures, not a claimed EXE smoke.
            _, fixture_app, fixture_core = core_tests.CoreRuntimeGuardTests()._fixture(directory)
            for name in ("finalize-immutable-rc.mjs", "verify-immutable-rc.mjs"):
                shutil.copy2(APP / "scripts" / name, fixture_app / "scripts" / name)
            artifact_root = Path(directory) / "candidate"
            core_root = artifact_root / "win-unpacked/resources/core-bin"
            shutil.copytree(fixture_core.parent, core_root)
            source_root = artifact_root / "win-unpacked/resources/core/scriptor"
            source_root.mkdir(parents=True)
            for name in ("__init__.py", "bridge.py"):
                (source_root / name).write_text("# packaged source fixture\n", encoding="utf-8")
            (artifact_root / "build-manifest.json").write_text(json.dumps({
                "gitSha": "1" * 40,
                "coreBinSha256": hashlib.sha256(fixture_core.read_bytes()).hexdigest(),
                "buildType": "TEST",
            }), encoding="utf-8")
            exe = artifact_root / "NewsFlow Studio.exe"
            exe.write_bytes(b"verified portable artifact")
            subprocess.run(
                ["node", "scripts/finalize-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=fixture_app,
                text=True,
                capture_output=True,
                check=True,
            )
            verified = subprocess.run(
                ["node", "scripts/verify-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=fixture_app,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            exe.write_bytes(b"tampered portable artifact")
            rejected = subprocess.run(
                ["node", "scripts/verify-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=fixture_app,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("Artifact hash mismatch", rejected.stderr)
