from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"


class ImmutableRcTests(unittest.TestCase):
    def test_packaging_wrapper_executes_windows_pnpm_shims_through_cmd(self):
        wrapper = (APP / "scripts" / "package-immutable-rc.mjs").read_text(encoding="utf-8")

        self.assertIn('command.toLowerCase().endsWith(".cmd")', wrapper)
        self.assertIn('shell: process.platform === "win32"', wrapper)

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
            prepared = subprocess.run(
                ["node", "scripts/prepare-immutable-rc.mjs", "--output-root", directory, "--type", "TEST", "--rc", "04"],
                cwd=APP,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, prepared.returncode, prepared.stdout + prepared.stderr)
            artifact_root = Path(prepared.stdout.strip().splitlines()[-1])
            exe = artifact_root / "NewsFlow Studio.exe"
            exe.write_bytes(b"verified portable artifact")
            subprocess.run(
                ["node", "scripts/finalize-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=APP,
                text=True,
                capture_output=True,
                check=True,
            )
            verified = subprocess.run(
                ["node", "scripts/verify-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=APP,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr)
            exe.write_bytes(b"tampered portable artifact")
            rejected = subprocess.run(
                ["node", "scripts/verify-immutable-rc.mjs", "--directory", str(artifact_root)],
                cwd=APP,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(0, rejected.returncode)
