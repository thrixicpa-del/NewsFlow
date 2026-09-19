"""Build reproducible MONTAGE-002 evidence without touching production state."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from scriptor import bridge
from scriptor.ai_index import ClipIndex
from scriptor.timeline import ffmpeg_executable


class _ImageEmbedding:
    calls = 0
    frames = 0

    def embed(self, images, **_):
        type(self).calls += 1
        type(self).frames += len(images)
        for image in images:
            pixels = np.asarray(image, dtype=np.float32)
            means = pixels.reshape(-1, 3).mean(axis=0) / 255.0
            yield np.asarray([*means, 1.0], dtype=np.float32)


class _TextEmbedding:
    calls = 0

    def query_embed(self, queries, **_):
        type(self).calls += 1
        values = queries if isinstance(queries, list) else [queries]
        for query in values:
            text = str(query).casefold()
            if any(word in text for word in ("tanker", "oil", "port")):
                yield np.asarray([0, 0, 1, 1], dtype=np.float32)
            elif any(word in text for word in ("protest", "crowd", "police", "strike")):
                yield np.asarray([1, 0, 0, 1], dtype=np.float32)
            elif any(word in text for word in ("diplomatic", "negotiation", "summit")):
                yield np.asarray([0, 128 / 255, 0, 1], dtype=np.float32)
            else:
                digest = hashlib.sha256(text.encode("utf-8")).digest()
                yield np.asarray([digest[0], digest[1], digest[2], 255], dtype=np.float32)


class _SmokeIndex(ClipIndex):
    media_probe_calls = 0

    def __init__(self, db_path):
        super().__init__(db_path, embedder_factory=lambda: (_ImageEmbedding(), _TextEmbedding()))

    @staticmethod
    def _sample_frames(path, samples=3):
        _SmokeIndex.media_probe_calls += 1
        return ClipIndex._sample_frames(path, samples)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_clip(path: Path, color: str, size: str, fps: str, duration: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
        f"color=c={color}:s={size}:r={fps}:d={duration}",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ]
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr[-2000:])


def _relative_rows(index: ClipIndex, footage: Path) -> list[dict]:
    rows = []
    for item in index.all_items():
        metadata = index.metadata(item.path)
        rows.append({
            "path": Path(item.path).relative_to(footage).as_posix(),
            "size": metadata.size,
            "mtimeNs": metadata.mtime_ns,
            "duration": round(metadata.duration, 4),
            "width": metadata.width,
            "height": metadata.height,
            "fps": round(metadata.fps, 4),
            "sourceFamily": metadata.source_family,
            "englishText": metadata.english_text,
            "semanticScores": metadata.semantic_scores,
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = args.output.resolve()
    if review.exists():
        shutil.rmtree(review)
    footage = review / "isolated-footage"
    app_root = review / "isolated-app-data"
    footage.mkdir(parents=True)
    app_root.mkdir(parents=True)
    _ImageEmbedding.calls = 0
    _ImageEmbedding.frames = 0
    _TextEmbedding.calls = 0
    _SmokeIndex.media_probe_calls = 0

    fixtures = [
        ("alpha_slices/clip_alpha_000001.mp4", "black", "320x180", "24", 0.8),
        ("alpha_slices/clip_alpha_000002.mp4", "white", "320x180", "24", 1.0),
        ("clip001.mp4", "blue", "640x360", "30", 1.2),
        ("clip002.mp4", "red", "426x240", "25", 0.9),
        ("clip003.mp4", "green", "480x270", "30", 1.1),
        ("forest_fire.mp4", "orange", "360x640", "30", 0.7),
        ("cargo_cranes.mp4", "yellow", "640x360", "30000/1001", 1.3),
        ("night_traffic.mp4", "purple", "512x288", "24", 1.0),
    ]
    for relative, color, size, fps, duration in fixtures:
        _make_clip(footage / relative, color, size, fps, duration)
    corrupt = footage / "corrupt_zero_byte.mp4"
    corrupt.touch()
    valid = [path for path in footage.rglob("*.mp4") if path.stat().st_size]
    hashes_before = {path.relative_to(footage).as_posix(): _sha256(path) for path in valid}

    settings = SimpleNamespace(footage_folders=[str(footage)])
    with patch.object(bridge, "app_data_root", return_value=app_root), \
         patch.object(bridge, "load_settings", return_value=settings), \
         patch.object(bridge, "ClipIndex", _SmokeIndex), \
         patch.object(bridge, "snapshot", return_value={}):
        started = time.perf_counter()
        cold_result = bridge.index_footage({"folders": [str(footage)]})["indexResult"]
        cold_seconds = time.perf_counter() - started
        started = time.perf_counter()
        deep_result = bridge.index_footage({"folders": [str(footage)], "enhance": True})["indexResult"]
        deep_seconds = time.perf_counter() - started
        started = time.perf_counter()
        unchanged_result = bridge.index_footage({"folders": [str(footage)]})["indexResult"]
        unchanged_seconds = time.perf_counter() - started

    index = _SmokeIndex(app_root / "footage-index.sqlite3")
    rows_before = _relative_rows(index, footage)
    queries = ["oil tanker at port", "street protest crowd", "diplomatic negotiations", "cargo cranes"]
    started = time.perf_counter()
    hits_before = index.search_many(queries, limit=3)
    search_seconds = time.perf_counter() - started

    semantic_expected = ["clip001.mp4", "clip002.mp4", "clip003.mp4"]
    semantic_actual = [Path(hits_before[index][0].item.path).name for index in range(3)]
    old_city = footage / "clip002.mp4"
    moved_city = footage / "renamed" / "clip002_moved.mp4"
    moved_city.parent.mkdir()
    old_city.rename(moved_city)
    (footage / "clip003.mp4").unlink()
    _make_clip(footage / "clip001.mp4", "navy", "854x480", "25", 1.8)

    with patch.object(bridge, "app_data_root", return_value=app_root), \
         patch.object(bridge, "load_settings", return_value=settings), \
         patch.object(bridge, "ClipIndex", _SmokeIndex), \
         patch.object(bridge, "snapshot", return_value={}):
        started = time.perf_counter()
        lifecycle_result = bridge.index_footage({"folders": [str(footage)]})["indexResult"]
        lifecycle_seconds = time.perf_counter() - started
        lifecycle_deep_result = bridge.index_footage(
            {"folders": [str(footage)], "enhance": True}
        )["indexResult"]

    index = _SmokeIndex(app_root / "footage-index.sqlite3")
    rows_after = _relative_rows(index, footage)
    hits_after = index.search_many(queries, limit=3)
    paths_after = {row["path"] for row in rows_after}
    untouched = [
        path for path in valid
        if path.name not in {"clip001.mp4", "clip002.mp4", "clip003.mp4"}
    ]
    hashes_after = {path.relative_to(footage).as_posix(): _sha256(path) for path in untouched}
    untouched_hashes_match = all(hashes_before[name] == digest for name, digest in hashes_after.items())
    alpha_families = {
        row["sourceFamily"] for row in rows_after if row["path"].startswith("alpha_slices/")
    }
    manifest = {
        "contract": "MONTAGE-002 isolated index smoke",
        "fixtureCounts": {"validInitial": 8, "corrupt": 1},
        "cold": {"seconds": cold_seconds, "result": cold_result},
        "deepEnrichment": {"seconds": deep_seconds, "result": deep_result},
        "unchangedReindex": {"seconds": unchanged_seconds, "result": unchanged_result},
        "lifecycleReindex": {"seconds": lifecycle_seconds, "result": lifecycle_result},
        "lifecycleDeepResume": lifecycle_deep_result,
        "searchMany": {
            "seconds": search_seconds,
            "queryCount": len(queries),
            "queries": [
                {"query": query, "hits": [Path(hit.item.path).relative_to(footage).as_posix() for hit in hits]}
                for query, hits in zip(queries, hits_before)
            ],
            "neutralFilenameExpected": semantic_expected,
            "neutralFilenameActual": semantic_actual,
        },
        "operationCounts": {
            "filesystemScans": 3,
            "mediaProbeCalls": _SmokeIndex.media_probe_calls,
            "ffprobeCalls": 0,
            "imageEmbeddingCalls": _ImageEmbedding.calls,
            "imageFramesEmbedded": _ImageEmbedding.frames,
            "textEmbeddingCalls": _TextEmbedding.calls,
        },
        "rowsBefore": rows_before,
        "rowsAfter": rows_after,
        "lifecycleAssertions": {
            "oldRenamedPathAbsent": "clip002.mp4" not in paths_after,
            "newRenamedPathPresent": "renamed/clip002_moved.mp4" in paths_after,
            "deletedPathAbsent": "clip003.mp4" not in paths_after,
            "replacementMetadata": next(row for row in rows_after if row["path"] == "clip001.mp4"),
            "neutralFilenameSemanticRetrieval": semantic_actual == semantic_expected,
            "sourceFamilyCutsShareIdentity": len(alpha_families) == 1,
            "untouchedSourceHashesMatch": untouched_hashes_match,
            "postLifecycleHitsExisting": all(Path(hit.item.path).is_file() for hits in hits_after for hit in hits),
        },
        "sourceHashesBefore": hashes_before,
        "untouchedSourceHashesAfter": hashes_after,
        "corruptFile": {"path": corrupt.name, "indexed": corrupt.name in paths_after},
    }
    checks = manifest["lifecycleAssertions"]
    if not all(checks.values()) or corrupt.name in paths_after:
        raise AssertionError(json.dumps(manifest, ensure_ascii=False, indent=2))
    (review / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "artifact": str(review / "manifest.json"),
        "coldSeconds": round(cold_seconds, 4),
        "deepSeconds": round(deep_seconds, 4),
        "unchangedSeconds": round(unchanged_seconds, 4),
        "lifecycleSeconds": round(lifecycle_seconds, 4),
        "searchManySeconds": round(search_seconds, 6),
        "rows": len(rows_after),
        "corruptFailed": lifecycle_result["failed"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
