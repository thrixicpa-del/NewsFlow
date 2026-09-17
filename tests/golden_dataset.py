"""Generate the small, non-production fixture set shared by NewsFlow tests."""
from __future__ import annotations

import json
import os
import struct
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

from scriptor.timeline import ffmpeg_executable


class GoldenDatasetError(RuntimeError):
    """Raised when a fixture would be generated outside disposable test storage."""


@dataclass(frozen=True)
class GoldenDataset:
    root: Path
    manifest: dict[str, object]


_MANIFEST: dict[str, object] = {
    "format": 1,
    "name": "newsflow-golden-v1",
    "topics": [{
        "id": "golden-topic-ormuz",
        "title": "Ормуз: давление на нефтяные маршруты",
        "directionId": "golden-direction-energy",
    }],
    "scripts": [{
        "id": "golden-script-ormuz",
        "topicId": "golden-topic-ormuz",
        "headline": "Ормуз на грани",
        "subheadline": "Танкеры под давлением",
        "body": "Тестовый сценарий для изолированного NewsFlow regression flow.",
    }],
    "assets": {
        "voice": "audio/voice.mp3",
        "faceReferences": {"iranian-official": "faces/iranian-official.png"},
        "cover": "covers/ormuz-cover.png",
        "footage": ["footage/tanker.mp4"],
    },
    "expectedMappings": {
        "topicToProduction": {"golden-topic-ormuz": "golden-production-ormuz"},
        "scriptToVoice": {"golden-script-ormuz": "audio/voice.mp3"},
        "productionToCover": {"golden-production-ormuz": "covers/ormuz-cover.png"},
    },
    "expectedTimeline": {
        "productionItemId": "golden-production-ormuz",
        "voice": "audio/voice.mp3",
        "durationSeconds": 1.0,
        "clips": ["footage/tanker.mp4"],
    },
    "publication": {
        "channels": [{"id": "golden-channel-news", "title": "Golden News"}],
        "jobs": [{
            "id": "golden-publication-ormuz",
            "productionItemId": "golden-production-ormuz",
            "channelId": "golden-channel-news",
            "status": "ready",
        }],
    },
}


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _write_solid_png(path: Path, rgb: tuple[int, int, int]) -> None:
    width = height = 24
    row = bytes((0,)) + bytes(rgb) * width
    pixels = row * height
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(pixels, level=9))
        + _png_chunk(b"IEND", b"")
    )


def _run_ffmpeg(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        raise GoldenDatasetError(f"golden fixture ffmpeg failed: {result.stderr[-1000:]}")


def _write_media(root: Path) -> None:
    ffmpeg = ffmpeg_executable()
    voice = root / "audio" / "voice.mp3"
    footage = root / "footage" / "tanker.mp4"
    _run_ffmpeg([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=48000:duration=1", "-c:a", "libmp3lame",
        "-b:a", "64k", "-metadata", "title=NewsFlow golden voice", str(voice),
    ])
    _run_ffmpeg([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=navy:s=320x180:r=25:d=1", "-an", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-metadata", "title=NewsFlow golden footage", str(footage),
    ])


def materialize_golden_dataset(root: Path) -> GoldenDataset:
    """Materialize fixed, synthetic assets under an explicit disposable test root."""
    test_root_raw = os.environ.get("NEWSFLOW_TEST_ROOT", "").strip()
    if os.environ.get("NEWSFLOW_TEST_MODE") != "1" or not test_root_raw:
        raise GoldenDatasetError("golden dataset requires NEWSFLOW_TEST_MODE=1 and NEWSFLOW_TEST_ROOT")
    test_root = Path(test_root_raw)
    if not _is_within(root, test_root):
        raise GoldenDatasetError("golden dataset target must be inside NEWSFLOW_TEST_ROOT")

    root.mkdir(parents=True, exist_ok=True)
    for name in ("audio", "faces", "covers", "footage"):
        (root / name).mkdir(exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(_MANIFEST, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_solid_png(root / "faces" / "iranian-official.png", (62, 92, 124))
    _write_solid_png(root / "covers" / "ormuz-cover.png", (180, 41, 47))
    _write_media(root)
    return GoldenDataset(root=root, manifest=_MANIFEST)
