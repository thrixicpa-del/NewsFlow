# -*- mode: python ; coding: utf-8 -*-
import hashlib
import json
from pathlib import Path

# Validate build inputs BEFORE collect_all/import hooks can start the build.
# Hydrating a later Electron checkout cannot repair an existing Frozen Core.
asset_contract = json.loads(
    (Path(SPECPATH) / "studio-ui-remotion-verify" / "frozen-core-assets.json").read_text(encoding="utf-8")
)
asset = asset_contract["ffmpeg"]
if (asset_contract.get("format") != 1 or asset.get("sourcePath") != "assets/ffmpeg.exe"
        or asset.get("bundledPath") != "_internal/assets/ffmpeg.exe"):
    raise RuntimeError("Invalid frozen-core-assets.json FFmpeg contract")
ffmpeg_path = Path(SPECPATH) / asset["sourcePath"]
if not ffmpeg_path.is_file():
    raise RuntimeError(f"FFmpeg payload missing: {ffmpeg_path}; hydrate Git LFS before building Core")
ffmpeg_bytes = ffmpeg_path.read_bytes()
if ffmpeg_bytes.startswith(b"version https://git-lfs.github.com/spec/v1"):
    raise RuntimeError("Git LFS pointer in assets/ffmpeg.exe; run Git LFS preparation before building Core")
if len(ffmpeg_bytes) != asset["size"]:
    raise RuntimeError("FFmpeg size mismatch; hydrate Git LFS before building Core")
pe_offset = int.from_bytes(ffmpeg_bytes[60:64], "little")
if (len(ffmpeg_bytes) < 64 or ffmpeg_bytes[:2] != b"MZ" or pe_offset < 64
        or ffmpeg_bytes[pe_offset:pe_offset + 4] != b"PE\0\0"):
    raise RuntimeError("FFmpeg is not a PE executable")
if hashlib.sha256(ffmpeg_bytes).hexdigest() != asset["sha256"]:
    raise RuntimeError("FFmpeg SHA-256 mismatch; hydrate Git LFS before building Core")
del ffmpeg_bytes

from PyInstaller.utils.hooks import collect_all

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
