"""Create isolated MONTAGE-004 VoiceMap-to-render evidence with synthetic media."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scriptor import bridge
from scriptor.ai_index import ClipIndex
from scriptor.config import Settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.timeline import TimelineProject, ffmpeg_executable, probe_media_duration
from scriptor.voice_map import (
    AlignmentResult,
    TimedObservation,
    VoiceMapContext,
    ensure_voice_map,
)

SCRIPT = (
    "Танкеры проходят через Ормузский пролив утром. "
    "Нефтяные терминалы готовят грузы для международных рынков. "
    "Портовые службы контролируют движение судов и безопасность."
)
DURATION_SECONDS = 15.0


class _ImageEmbedding:
    def embed(self, images, **_):
        for image in images:
            pixels = np.asarray(image, dtype=np.float32)
            means = pixels.reshape(-1, 3).mean(axis=0) / 255.0
            yield np.asarray([*means, 1.0], dtype=np.float32)


class _TextEmbedding:
    def query_embed(self, queries, **_):
        values = queries if isinstance(queries, list) else [queries]
        for _query in values:
            yield np.asarray([0.0, 0.0, 1.0, 1.0], dtype=np.float32)


class _SmokeIndex(ClipIndex):
    def __init__(self, db_path):
        super().__init__(db_path, embedder_factory=lambda: (_ImageEmbedding(), _TextEmbedding()))

    def screen_text_safe(self, _path):
        return True


class _KnownSyntheticAlignment:
    name = "deterministic-isolated-audio-timing-v1"

    def __init__(self, duration: float):
        self.duration = duration

    def availability(self) -> tuple[bool, str]:
        return True, ""

    def align(self, _context: VoiceMapContext) -> AlignmentResult:
        words = SCRIPT.split()
        step = self.duration / len(words)
        observations = [
            TimedObservation(
                text=word,
                start=round(index * step, 3),
                end=round((index + 1) * step, 3),
                confidence=1.0,
                kind="word",
            )
            for index, word in enumerate(words)
        ]
        return AlignmentResult(self.name, observations, 1.0)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-3000:])
    return result


def _make_video(path: Path, color: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
        f"color=c={color}:s=640x360:r=30:d=20",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
    ])


def _make_voice(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_executable(), "-y", "-f", "lavfi", "-i",
        f"sine=frequency=440:sample_rate=44100:duration={DURATION_SECONDS}",
        "-c:a", "libmp3lame", "-q:a", "7", str(path),
    ])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict:
    executable = shutil.which("ffprobe")
    if not executable:
        raise RuntimeError("ffprobe is required for the isolated acceptance smoke")
    result = _run([
        executable, "-v", "error", "-show_streams", "-show_format",
        "-of", "json", str(path),
    ])
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    review = args.output.resolve()
    if review.exists():
        raise FileExistsError(f"Refusing to overwrite existing review set: {review}")
    footage = review / "isolated-footage"
    app_root = review / "isolated-app-data"
    projects = review / "projects"
    outputs = review / "outputs"
    voice_path = review / "isolated-voice" / "voice.mp3"
    for folder in (footage, app_root, projects, outputs):
        folder.mkdir(parents=True, exist_ok=True)
    os.environ["NEWSFLOW_TEST_MODE"] = "1"
    os.environ["NEWSFLOW_TEST_ROOT"] = str(review / "test-storage")

    sources = {
        "hormuz_tanker_convoy.mp4": "blue",
        "oil_terminal_loading.mp4": "navy",
        "port_security_patrol.mp4": "royalblue",
        "cargo_ship_navigation.mp4": "deepskyblue",
    }
    for name, color in sources.items():
        _make_video(footage / name, color)
    _make_voice(voice_path)
    audio_duration = probe_media_duration(voice_path)
    source_hashes_before = {name: _sha256(footage / name) for name in sources}

    title = "Ормузский пролив и нефтяные танкеры"
    production_item_id = "smoke:montage-004:voice-map"
    job = Job(
        ScenarioRequest(0, title, "", production_item_id),
        RunState.DONE,
        SCRIPT,
        "",
    )
    settings = Settings(
        footage_folders=[str(footage)],
        montage_project_folder=str(projects),
        montage_output_folder=str(outputs),
        montage_renderer="ffmpeg",
        montage_export_davinci_xml=False,
        montage_auto_web=False,
        montage_external_only=False,
        montage_use_script_text=True,
        montage_exclude_english_text=False,
        montage_match_threshold=0.22,
        voice_scenario_outputs={"1": str(voice_path)},
        voice_task_statuses={"1": {"durationSeconds": audio_duration}},
    )
    index = _SmokeIndex(app_root / "footage-index.sqlite3")
    index_result = index.index_folders([str(footage)])
    context = VoiceMapContext(
        production_item_id=production_item_id,
        scenario_index=0,
        title=title,
        script=SCRIPT,
        audio_path=voice_path,
        audio_duration=audio_duration,
        storage_root=app_root / "voice-maps",
    )

    started = time.perf_counter()
    voice_map_status = ensure_voice_map(
        context,
        engine=_KnownSyntheticAlignment(audio_duration),
        current_context=lambda: context,
    )
    alignment_seconds = time.perf_counter() - started
    progress_events: list[dict] = []
    with (
        patch.object(bridge, "app_data_root", return_value=app_root),
        patch.object(bridge, "ClipIndex", _SmokeIndex),
        patch.object(bridge, "load_settings", return_value=settings),
        patch.object(bridge, "save_settings", return_value=None),
        patch.object(bridge, "load_session", return_value=([title], [job])),
        patch.object(bridge, "snapshot", return_value={}),
    ):
        preparation_started = time.perf_counter()
        prepared = bridge.prepare_montage({
            "scenarioIndex": 0,
            "_progress": lambda stage, detail: progress_events.append({
                "stage": stage,
                "detail": detail,
            }),
        })["preparedProject"]
        preparation_seconds = time.perf_counter() - preparation_started
        render_started = time.perf_counter()
        bridge.render_montage({"projectPath": prepared["path"]})
        render_seconds = time.perf_counter() - render_started

    project_path = Path(prepared["path"])
    project = TimelineProject.load(project_path)
    output_path = outputs / f"{bridge.safe_filename(title)}.mp4"
    probe = _ffprobe(output_path)
    probe_path = review / "ffprobe.json"
    probe_path.write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
    map_path = Path(voice_map_status.path)
    map_payload = json.loads(map_path.read_text(encoding="utf-8"))
    source_hashes_after = {name: _sha256(footage / name) for name in sources}
    output_duration = probe_media_duration(output_path)
    stream_types = {str(item.get("codec_type")) for item in probe.get("streams", [])}
    map_segments = map_payload["segments"]
    expected_visual_duration = audio_duration + len(map_segments) / 30.0 + 0.05
    clip_evidence = [{
        "voiceSegmentId": clip.voice_segment_id,
        "narrationStart": clip.narration_start,
        "narrationEnd": clip.narration_end,
        "duration": clip.duration,
        "footage": Path(clip.path).name,
        "sourceStart": clip.source_start,
        "sourceDuration": probe_media_duration(Path(clip.path)),
        "query": clip.visual_query_en,
    } for clip in project.clips]
    assertions = {
        "alignedVoiceMap": voice_map_status.state == "ready" and map_payload["timingMode"] == "aligned",
        "canonicalTextPreserved": " ".join(item["text"] for item in map_segments) == SCRIPT,
        "timestampsPositiveMonotonic": all(
            float(item["end"]) > float(item["start"]) >= 0.0
            for item in map_segments
        ),
        "audioEndpointCovered": abs(float(map_segments[-1]["end"]) - audio_duration) <= 0.05,
        "projectUsesVoiceMap": project.voice_map_provenance.get("voiceMapPath") == str(map_path),
        "projectHashesMatchVoiceMap": (
            project.voice_map_provenance.get("scriptSha256") == map_payload["scriptSha256"]
            and project.voice_map_provenance.get("audioSha256") == map_payload["audioSha256"]
        ),
        "clipsLinkEveryVoiceSegment": (
            [clip.voice_segment_id for clip in project.clips]
            == [int(item["id"]) for item in map_segments]
        ),
        "clipNarrationTimingMatches": all(
            abs(clip.narration_start - float(segment["start"])) <= 0.01
            and abs(clip.narration_end - float(segment["end"])) <= 0.01
            for clip, segment in zip(project.clips, map_segments, strict=True)
        ),
        "visualTailComplete": abs(project.duration - expected_visual_duration) <= 0.05,
        "sourceStartsBounded": all(
            0.0 <= row["sourceStart"] <= row["sourceDuration"] - row["duration"] + 0.05
            for row in clip_evidence
        ),
        "renderHasAudioAndVideo": stream_types >= {"audio", "video"},
        "renderDurationMatchesVoice": abs(output_duration - audio_duration) <= 0.35,
        "sourceMediaUnchanged": source_hashes_before == source_hashes_after,
    }
    manifest = {
        "contract": "MONTAGE-004 isolated VoiceMap alignment smoke",
        "productionItemId": production_item_id,
        "indexResult": asdict(index_result),
        "voiceMap": {
            "path": str(map_path),
            "sha256": _sha256(map_path),
            "timingMode": map_payload["timingMode"],
            "alignmentEngine": map_payload["alignmentEngine"],
            "alignmentConfidence": map_payload["alignmentConfidence"],
            "scriptSha256": map_payload["scriptSha256"],
            "audioSha256": map_payload["audioSha256"],
            "segments": map_segments,
        },
        "project": {
            "path": str(project_path),
            "sha256": _sha256(project_path),
            "duration": project.duration,
            "voiceMapProvenance": project.voice_map_provenance,
            "clips": clip_evidence,
        },
        "render": {
            "path": str(output_path),
            "sha256": _sha256(output_path),
            "duration": output_duration,
            "ffprobe": str(probe_path),
        },
        "timingsSeconds": {
            "alignment": round(alignment_seconds, 3),
            "preparation": round(preparation_seconds, 3),
            "render": round(render_seconds, 3),
        },
        "progressEvents": progress_events,
        "sourceHashesBefore": source_hashes_before,
        "sourceHashesAfter": source_hashes_after,
        "assertions": assertions,
    }
    if not all(assertions.values()):
        raise AssertionError(json.dumps(manifest, ensure_ascii=False, indent=2))
    manifest_path = review / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "voiceMap": str(map_path),
        "project": str(project_path),
        "render": str(output_path),
        "timingsSeconds": manifest["timingsSeconds"],
        "assertions": assertions,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
