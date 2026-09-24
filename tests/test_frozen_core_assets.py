"""Executable release regressions for the exact FFmpeg selected by frozen Core.

Small PE fixtures exercise validation, never pretend to be executable FFmpeg.
Only their disposable copy of the asset contract uses fixture hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"
SOURCES = (
    "scriptor/bridge.py", "scriptor/timeline.py", "scriptor/core.py",
    "scriptor/thumbnail_prompt_v2.py", "scriptor/observability.py", "bridge_main.py",
)
POINTER = (
    b"version https://git-lfs.github.com/spec/v1\n"
    b"oid sha256:2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3\n"
    b"size 87638016\n"
)
BUNDLED_PATH = "_internal/assets/ffmpeg.exe"
PACKAGED_CORE = "win-unpacked/resources/core-bin"


def pe_fixture() -> bytes:
    data = bytearray(256)
    data[:2] = b"MZ"
    data[60:64] = (128).to_bytes(4, "little")
    data[128:132] = b"PE\0\0"
    return bytes(data)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def install_fixture_asset(app: Path, core: Path):
    module = APP / "scripts/verify-frozen-core-assets.mjs"
    if module.exists():
        shutil.copy2(module, app / "scripts/verify-frozen-core-assets.mjs")
    payload = pe_fixture()
    write_json(app / "frozen-core-assets.json", {"format": 1, "ffmpeg": {
        "sourcePath": "assets/ffmpeg.exe", "bundledPath": BUNDLED_PATH,
        "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(),
    }})
    asset = core / BUNDLED_PATH
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(payload)


def create_asset_fixture(root: Path):
    app = root / "studio-ui-remotion-verify"
    scripts = app / "scripts"
    scripts.mkdir(parents=True)
    for name in ("verify-core-runtime.mjs", "verify-immutable-rc.mjs", "verify-frozen-core-assets.mjs"):
        source = APP / "scripts" / name
        if source.exists():
            shutil.copy2(source, scripts / name)
    core = root / "core-bin-fixture" / "NewsFlowCore"
    install_fixture_asset(app, core)
    asset = core / BUNDLED_PATH
    exe = core / "NewsFlowCore.exe"
    exe.write_bytes(b"fixture core executable")
    blobs = {}
    for relative in SOURCES:
        content = f"# {relative}\n".encode()
        source = root / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(content)
        blobs[relative] = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
    core_sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    write_json(app / "core-runtime-lock.json", {
        "format": 1, "appVersion": "2.1.152", "coreRevision": "core-bin-fixture",
        "coreExeSha256": core_sha, "coreExeSize": exe.stat().st_size,
        "builtFromGitSha": "a" * 40, "sourceGitBlobs": blobs,
    })
    write_json(app / "package.json", {"version": "2.1.152", "build": {"extraResources": [
        {"from": "../core-bin-fixture/NewsFlowCore", "to": "core-bin"},
    ]}})
    candidate = root / "candidate"
    packaged = candidate / PACKAGED_CORE
    shutil.copytree(core, packaged)
    (candidate / "NewsFlow Studio.exe").write_bytes(b"fixture portable executable")
    write_json(candidate / "build-manifest.json", {
        "gitSha": "a" * 40, "coreBinSha256": core_sha, "buildType": "RC",
    })
    fixture = SimpleNamespace(root=root, app=app, core=core, asset=asset,
                              candidate=candidate, packaged=packaged, core_sha=core_sha)
    record_inventory(fixture)
    return fixture


def record_inventory(fixture):
    entries = []
    for file in sorted(fixture.candidate.rglob("*")):
        if file.is_file() and file.name != "artifact-hashes.json":
            entries.append({"path": file.relative_to(fixture.candidate).as_posix(),
                            "size": file.stat().st_size,
                            "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
    write_json(fixture.candidate / "artifact-hashes.json", {
        "gitSha": "a" * 40, "coreBinSha256": fixture.core_sha, "artifacts": entries,
    })


def run_node(app: Path, script: str, *args):
    return subprocess.run(["node", f"scripts/{script}", *map(str, args)], cwd=app,
                          text=True, encoding="utf-8", errors="replace",
                          capture_output=True, timeout=40, check=False)


class FrozenCoreAssetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="newsflow-frozen-assets-")
        self.addCleanup(temporary.cleanup)
        self.fixture = create_asset_fixture(Path(temporary.name))

    def assert_rejected(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)

    def core_guard(self):
        return run_node(self.fixture.app, "verify-core-runtime.mjs")

    def rc_guard(self):
        return run_node(self.fixture.app, "verify-immutable-rc.mjs",
                        "--directory", self.fixture.candidate)

    def test_core_guard_rejects_bundled_pointer_despite_matching_exe(self):
        self.fixture.asset.write_bytes(POINTER)
        self.assert_rejected(self.core_guard(), "Git LFS pointer")

    def test_rc_rejects_pointer_even_when_inventory_hash_matches(self):
        (self.fixture.packaged / BUNDLED_PATH).write_bytes(POINTER)
        record_inventory(self.fixture)
        self.assert_rejected(self.rc_guard(), "Git LFS pointer")

    def test_matching_asset_passes_core_and_rc_guards(self):
        for result in (self.core_guard(), self.rc_guard()):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_core_rejects_missing_asset(self):
        self.fixture.asset.unlink()
        self.assert_rejected(self.core_guard(), "FFmpeg payload missing")

    def test_core_rejects_wrong_size(self):
        self.fixture.asset.write_bytes(pe_fixture() + b"extra")
        self.assert_rejected(self.core_guard(), "FFmpeg size mismatch")

    def test_core_rejects_wrong_hash_with_valid_pe_header_and_size(self):
        content = bytearray(pe_fixture())
        content[-1] = 1
        self.fixture.asset.write_bytes(content)
        self.assert_rejected(self.core_guard(), "FFmpeg SHA-256 mismatch")

    def test_non_pe_payload_cannot_be_approved_by_rehashing_contract(self):
        payload = b"not an executable" * 16
        self.fixture.asset.write_bytes(payload)
        contract_file = self.fixture.app / "frozen-core-assets.json"
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
        contract["ffmpeg"].update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
        write_json(contract_file, contract)
        self.assert_rejected(self.core_guard(), "FFmpeg is not a PE executable")

    def test_rc_rejects_missing_packaged_asset_after_inventory_is_rebuilt(self):
        (self.fixture.packaged / BUNDLED_PATH).unlink()
        record_inventory(self.fixture)
        self.assert_rejected(self.rc_guard(), "Required Core artifact absent from inventory")

    def test_rc_rejects_omitted_asset_entry_even_when_file_exists(self):
        inventory_file = self.fixture.candidate / "artifact-hashes.json"
        inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
        inventory["artifacts"] = [item for item in inventory["artifacts"]
                                  if item["path"] != f"{PACKAGED_CORE}/{BUNDLED_PATH}"]
        write_json(inventory_file, inventory)
        self.assert_rejected(self.rc_guard(), "Required Core artifact absent from inventory")

    def test_rc_rejects_rehashed_wrong_core_exe(self):
        (self.fixture.packaged / "NewsFlowCore.exe").write_bytes(b"different core")
        record_inventory(self.fixture)
        self.assert_rejected(self.rc_guard(), "Packaged Core identity mismatch")

    def test_canonical_gate_requires_exact_packaged_media_smoke(self):
        gate = (ROOT / "scripts/release-gate.ps1").read_text(encoding="utf-8")
        self.assertIn(
            "@('scripts/verify-immutable-rc.mjs', '--directory', $candidateRoot, '--media-smoke')",
            gate,
        )

    def test_media_smoke_does_not_fall_back_when_supplied_binary_is_missing(self):
        module = (self.fixture.app / "scripts/verify-frozen-core-assets.mjs").as_uri()
        missing = str(self.fixture.root / "missing-ffmpeg.exe")
        code = f"import {{smokeFfmpeg}} from {json.dumps(module)}; smokeFfmpeg({json.dumps(missing)});"
        result = subprocess.run(["node", "--input-type=module", "-e", code],
                                text=True, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=10, check=False)
        self.assert_rejected(result, "Packaged FFmpeg smoke failed")

    def run_spec(self, payload):
        source = self.fixture.root / "assets/ffmpeg.exe"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        shutil.copy2(ROOT / "Scriptor.spec", self.fixture.root / "Scriptor.spec")
        hooks = self.fixture.root / "PyInstaller/utils/hooks.py"
        hooks.parent.mkdir(parents=True, exist_ok=True)
        for parent in (hooks.parent, hooks.parent.parent):
            (parent / "__init__.py").touch()
        hooks.write_text('def collect_all(package):\n    print("DEPENDENCY_COLLECTION_REACHED")\n    raise SystemExit(0)\n',
                         encoding="utf-8")
        runner = "import runpy; from pathlib import Path; runpy.run_path('Scriptor.spec', init_globals={'SPECPATH': str(Path.cwd())})"
        return subprocess.run([sys.executable, "-c", runner], cwd=self.fixture.root,
                              env={**os.environ, "PYTHONPATH": str(self.fixture.root)},
                              text=True, encoding="utf-8", errors="replace",
                              capture_output=True, timeout=10, check=False)

    def test_build_rejects_lfs_pointer_before_dependency_collection(self):
        result = self.run_spec(POINTER)
        self.assert_rejected(result, "Git LFS pointer")
        self.assertNotIn("DEPENDENCY_COLLECTION_REACHED", result.stdout)

    def test_build_accepts_matching_asset_before_dependency_collection(self):
        result = self.run_spec(pe_fixture())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DEPENDENCY_COLLECTION_REACHED", result.stdout)

    def test_build_rejects_wrong_asset_hash(self):
        payload = bytearray(pe_fixture())
        payload[-1] = 1
        self.assert_rejected(self.run_spec(payload), "FFmpeg SHA-256 mismatch")


if __name__ == "__main__":
    unittest.main()
