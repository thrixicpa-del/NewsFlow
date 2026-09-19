"""Create isolated MONTAGE-003 prepare/render evidence with synthetic media."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriptor import bridge
from scriptor.ai_index import ClipIndex
from scriptor.config import Settings
from scriptor.timeline import TimelineProject, ffmpeg_executable, probe_media_duration


class _ImageEmbedding:
    def embed(self, images, **_):
        for image in images:
            pixels = np.asarray(image, dtype=np.float32)
            means = pixels.reshape(-1, 3).mean(axis=0) / 255.0
            yield np.asarray([*means, 1.0], dtype=np.float32)


class _TextEmbedding:
    def query_embed(self, queries, **_):
        values = queries if isinstance(queries, list) else [queries]
        for query in values:
            text = str(query).casefold()
            if any(word in text for word in ("tanker", "oil", "port", "hormuz")):
                yield np.asarray([0.0, 0.0, 1.0, 1.0], dtype=np.float32)
            else:
                yield np.asarray([0.2, 0.2, 0.2, 1.0], dtype=np.float32)


class _SmokeIndex(ClipIndex):
    def __init__(self, db_path):
        super().__init__(db_path, embedder_factory=lambda: (_ImageEmbedding(), _TextEmbedding()))


def _run(command: list[str]) -> None:
    result = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])


def _make_video(path: Path, color: str, duration: float = 18.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
        f"color=c={color}:s=640x360:r=30:d={duration}",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ])


def _make_voice(path: Path, frequency: int, duration: float = 18.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
        f"sine=frequency={frequency}:sample_rate=44100:duration={duration}",
        "-c:a", "libmp3lame", "-q:a", "7", str(path),
    ])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = args.output.resolve()
    if review.exists():
        shutil.rmtree(review)
    footage = review / "isolated-footage"
    voices = review / "isolated-voices"
    app_root = review / "isolated-app-data"
    projects = review / "projects"
    outputs = review / "outputs"
    for folder in (footage, voices, app_root, projects, outputs):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ["NEWSFLOW_TEST_ROOT"] = str(review / "test-storage")

    colors = ["blue", "navy", "cyan", "royalblue", "steelblue", "deepskyblue"]
    sources = []
    for number, color in enumerate(colors, 1):
        path = footage / f"oil_tanker_family_{number}.mp4"
        _make_video(path, color)
        sources.append(path)
    unsafe = footage / "ukraine_oil_tanker_wrong_country.mp4"
    _make_video(unsafe, "red")
    all_sources = [*sources, unsafe]
    source_hashes_before = {path.name: _sha256(path) for path in all_sources}

    titles = [
        "Иран и Ормузский пролив: движение нефтяных танкеров",
        "Ормузский пролив: риски для нефтяных танкеров",
        "Танкеры в Ормузском проливе и мировая нефть",
    ]
    voice_paths = []
    for index, frequency in enumerate((430, 510, 590), 1):
        path = voices / f"voice-{index}.mp3"
        _make_voice(path, frequency)
        voice_paths.append(path)

    index = _SmokeIndex(app_root / "footage-index.sqlite3")
    index_result = index.index_folders([str(footage)])
    settings = Settings()
    settings.footage_folders = [str(footage)]
    settings.footage_download_folder = str(review / "downloads")
    settings.cutter_output_folder = str(review / "cuts")
    settings.montage_project_folder = str(projects)
    settings.montage_output_folder = str(outputs)
    settings.montage_renderer = "ffmpeg"
    settings.montage_export_davinci_xml = False
    settings.montage_auto_web = False
    settings.montage_external_only = False
    settings.montage_use_script_text = False
    settings.montage_exclude_english_text = False
    settings.montage_match_threshold = 0.22
    settings.montage_recent_clip_paths = []
    settings.voice_scenario_outputs = {
        str(index + 1): str(path) for index, path in enumerate(voice_paths)
    }
    batch_usage = {
        "lock": threading.RLock(), "paths": {}, "families": {},
        "placements": {}, "windows": {},
    }

    prepared = []
    rendered = []
    progress_events = []
    started = time.perf_counter()
    with patch.object(bridge, "app_data_root", return_value=app_root), \
         patch.object(bridge, "ClipIndex", _SmokeIndex), \
         patch.object(bridge, "load_settings", return_value=settings), \
         patch.object(bridge, "save_settings", return_value=None), \
         patch.object(bridge, "load_session", return_value=(titles, [])), \
         patch.object(bridge, "snapshot", return_value={}):
        for scenario_index in range(len(titles)):
            result = bridge.prepare_montage({
                "scenarioIndex": scenario_index,
                "_batchFootageUsage": batch_usage,
                "_progress": lambda stage, detail, row=scenario_index: progress_events.append({
                    "row": row, "stage": stage, "detail": detail,
                }),
            })["preparedProject"]
            prepared.append(result)
            bridge.render_montage({"projectPath": result["path"]})
            output = outputs / f"{bridge.safe_filename(titles[scenario_index])}.mp4"
            rendered.append({
                "path": str(output), "sha256": _sha256(output),
                "duration": round(probe_media_duration(output), 3),
            })
    total_seconds = time.perf_counter() - started

    project_rows = []
    openings = []
    starts_by_family: dict[str, list[float]] = {}
    for item in prepared:
        project = TimelineProject.load(Path(item["path"]))
        clips = []
        for clip in project.clips:
            openings.append(clip.source_family) if not clips else None
            starts_by_family.setdefault(clip.source_family, []).append(clip.source_start)
            clips.append({
                "file": Path(clip.path).name,
                "family": clip.source_family,
                "fallbackLevel": clip.fallback_level,
                "positionBucket": clip.position_bucket,
                "sourceStart": clip.source_start,
                "reused": clip.reused,
                "rotationReason": clip.position_rotation_reason,
            })
        project_rows.append({
            "title": project.title,
            "path": str(item["path"]),
            "summary": project.selection_summary,
            "summaryText": item["summaryText"],
            "timingsMs": project.preparation_metrics_ms,
            "clips": clips,
        })

    source_hashes_after = {path.name: _sha256(path) for path in all_sources}
    reused_windows = {
        family: starts for family, starts in starts_by_family.items()
        if len(starts) > 1
    }
    assertions = {
        "threeProjectsRendered": len(rendered) == 3 and all(Path(row["path"]).is_file() for row in rendered),
        "threeDistinctOpeningFamilies": len(set(openings)) == 3,
        "safeReuseOccurred": any(
            clip["fallbackLevel"] == "SAFE_REUSE"
            for project in project_rows for clip in project["clips"]
        ),
        "reusedLongSourcesUseDifferentWindows": bool(reused_windows) and all(
            len(set(starts)) > 1 for starts in reused_windows.values()
        ),
        "wrongCountrySourceRejected": all(
            clip["file"] != unsafe.name for project in project_rows for clip in project["clips"]
        ),
        "sourceMediaUnchanged": source_hashes_before == source_hashes_after,
        "renderDurationsMatchVoice": all(abs(row["duration"] - 18.0) <= 0.35 for row in rendered),
        "timingsPersisted": all(project["timingsMs"].get("total", 0) > 0 for project in project_rows),
    }
    manifest = {
        "contract": "MONTAGE-003 isolated semantic diversity smoke",
        "indexResult": asdict(index_result),
        "elapsedSeconds": round(total_seconds, 3),
        "projects": project_rows,
        "rendered": rendered,
        "openingFamilies": openings,
        "reusedSourceWindows": reused_windows,
        "sourceHashesBefore": source_hashes_before,
        "sourceHashesAfter": source_hashes_after,
        "progressEvents": progress_events,
        "assertions": assertions,
    }
    if not all(assertions.values()):
        raise AssertionError(json.dumps(manifest, ensure_ascii=False, indent=2))
    manifest_path = review / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "artifact": str(manifest_path),
        "outputs": len(rendered),
        "openingFamilies": openings,
        "reuseFamilies": list(reused_windows),
        "elapsedSeconds": round(total_seconds, 3),
        "assertions": assertions,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
