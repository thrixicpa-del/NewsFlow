# -*- mode: python ; coding: utf-8 -*-
# Validate the real payload before collect_all/Analysis can copy an LFS pointer.
import hashlib
import json
from pathlib import Path

_spec_root = Path(SPEC).resolve().parent
_asset = _spec_root / "assets" / "ffmpeg.exe"
_asset_lock = json.loads((_spec_root / "studio-ui-remotion-verify" / "core-assets-lock.json").read_text(encoding="utf-8"))
_expected = _asset_lock.get("ffmpeg", {})
if (_asset_lock.get("format") != 1 or not isinstance(_expected.get("size"), int)
        or _expected["size"] < 64 or len(str(_expected.get("sha256", ""))) != 64):
    raise RuntimeError("CORE_ASSET_INVALID: invalid core-assets-lock.json")
if not _asset.is_file():
    raise RuntimeError("CORE_ASSET_INVALID: assets/ffmpeg.exe missing; hydrate Git LFS before building Core")
_payload = _asset.read_bytes()
if _payload.startswith(b"version https://git-lfs.github.com/spec/v1"):
    raise RuntimeError("CORE_ASSET_INVALID: assets/ffmpeg.exe is an LFS pointer; hydrate Git LFS before building Core")
_pe_offset = int.from_bytes(_payload[60:64], "little") if len(_payload) >= 64 else -1
if (_payload[:2] != b"MZ" or _pe_offset < 64 or _pe_offset > len(_payload) - 4
        or _payload[_pe_offset:_pe_offset + 4] != b"PE\0\0"):
    raise RuntimeError("CORE_ASSET_INVALID: assets/ffmpeg.exe is not a Windows PE executable")
if len(_payload) != _expected["size"] or hashlib.sha256(_payload).hexdigest() != _expected["sha256"]:
    raise RuntimeError("CORE_ASSET_INVALID: assets/ffmpeg.exe size/SHA-256 differs from the asset lock")
del _payload

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("assets", "assets")]
binaries = []
hiddenimports = []
for package in (
    "tkinterdnd2",
    "playwright",
    "fastembed",
    "onnxruntime",
    "cv2",
    "PIL",
    "numpy",
    "googleapiclient",
    "google_auth_oauthlib",
    "tzdata",
    "yt_dlp",
):
    collected = collect_all(package)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

# ``ai_index`` imports FastEmbed only when footage semantic search is used.
# PyInstaller cannot discover that deferred import from static analysis; data
# collection alone leaves ``fastembed`` files on disk but no importable module
# in PYZ, which makes Montage fail at runtime.
hiddenimports += collect_submodules("fastembed")

a = Analysis(
    ["bridge_main.py"],
    pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="NewsFlowCore",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None, console=True,
    disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None, icon=["assets/scriptor.ico"],
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[], name="NewsFlowCore",
)
