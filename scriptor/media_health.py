"""Bounded media validation and identity-scoped, non-destructive quarantine."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

_PATH_LOCKS = [threading.Lock() for _ in range(64)]
_INVALID = re.compile(r"moov atom not found|invalid data found|error while decoding|invalid nal|no frames", re.IGNORECASE)
_UNAVAILABLE = re.compile(r"permission denied|access is denied|resource temporarily|cannot allocate|decoder.*not found|unknown decoder|no such file", re.IGNORECASE)


@dataclass(frozen=True)
class MediaHealth:
    state: str
    reason: str = ""
    duration: float = 0.0
    identity: tuple[int, int] | None = None


def signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def inspect_video(path: Path) -> MediaHealth:
    try:
        before = signature(path)
        result = _inspect_video(path)
        if signature(path) != before:
            return MediaHealth("unavailable", "Файл изменился во время проверки")
        return replace(result, identity=before)
    except OSError as error:
        return MediaHealth("unavailable", str(error)[-500:])


def _inspect_video(path: Path) -> MediaHealth:
    """Read headers and decode one frame at each end, never the whole video."""
    from .timeline import ffmpeg_executable
    try:
        before = signature(path)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        options = {"capture_output": True, "text": True, "encoding": "utf-8", "errors": "replace",
                   "timeout": 12, "creationflags": flags}
        binary = ffmpeg_executable()
        probe = subprocess.run([binary, "-hide_banner", "-i", str(path)], check=False, **options)
        details = probe.stderr or ""
        if _UNAVAILABLE.search(details):
            return MediaHealth("unavailable", details[-500:])
        if _INVALID.search(details):
            return MediaHealth("invalid", details[-500:])
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
        if not re.search(r"\bVideo:\s", details):
            # A parsed audio-only container is a definite no-video result;
            # an unexplained probe failure is not evidence of corruption.
            state = "invalid" if match or "Audio:" in details else "unavailable"
            return MediaHealth(state, "Нет читаемого видеопотока: " + details[-350:])
        if not match:
            return MediaHealth("unavailable", "Не определена длительность видео")
        h, m, s = map(float, match.groups())
        duration = h * 3600 + m * 60 + s
        if not math.isfinite(duration) or duration <= .05:
            return MediaHealth("invalid", "Нулевая длительность видео")
        # Container duration can include a longer audio track. Header-only
        # video metadata supplies a frame-aware endpoint without decoding all
        # frames or requiring an unbundled ffprobe executable.
        import cv2
        capture = cv2.VideoCapture(str(path))
        try:
            fps = capture.get(cv2.CAP_PROP_FPS)
            count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        finally:
            capture.release()
        if all(math.isfinite(value) and value > 0 for value in (fps, count)):
            duration = count / fps
        else:
            return MediaHealth("unavailable", "Не определена длительность видеопотока")
        # Matroska/WebM frame counts may be inferred from the *container*
        # duration. Prefer the first video stream's own duration tag, never
        # an audio stream tag or the container's Duration field.
        video = re.search(r"(?m)^\s*Stream #0:\d+[^\n]*Video:[\s\S]*?(?=\n\s*Stream #|\Z)", details)
        video_duration = re.search(r"(?i)\bDURATION\s*:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", video.group() if video else "")
        if video_duration:
            hours, minutes, seconds = map(float, video_duration.groups())
            stream_duration = hours * 3600 + minutes * 60 + seconds
            if math.isfinite(stream_duration) and stream_duration > .05:
                duration = stream_duration
        tail = max(0.0, duration - max(.2, 1.0 / fps))
        for start in dict.fromkeys((0.0, tail)):
            decoded = subprocess.run([
                binary, "-hide_banner", "-v", "error", "-xerror", "-ss", str(start),
                "-i", str(path), "-map", "0:v:0", "-frames:v", "1", "-an",
                "-progress", "pipe:1", "-f", "null", "-",
            ], check=False, **options)
            error = decoded.stderr or ""
            if _UNAVAILABLE.search(error):
                return MediaHealth("unavailable", error[-500:])
            if decoded.returncode:
                return MediaHealth("invalid" if _INVALID.search(error) else "unavailable", error[-500:])
            frames = re.findall(r"(?m)^frame=(\d+)", decoded.stdout or "")
            if not frames or max(map(int, frames)) < 1:
                # Inaccurate/VFR endpoint metadata is not proof of corruption.
                if start == 0.0:
                    return MediaHealth("invalid", "Не найден первый декодируемый кадр видео")
                return _find_video_endpoint(binary, path, duration, fps, options)
        if signature(path) != before:
            return MediaHealth("unavailable", "Файл изменился во время проверки")
        return MediaHealth("valid", duration=duration)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        return MediaHealth("unavailable", str(error)[-500:])


def _find_video_endpoint(binary: str, path: Path, upper: float, fps: float, options: dict) -> MediaHealth:
    """Resolve an audio-tail overestimate using bounded video-only windows.

    Optional stream duration tags and OpenCV frame counts are not always
    available/reliable. Inspect at most twelve 2-second windows (240 frames
    each), with a shared 12-second time budget; never scan an entire long
    source. Ambiguous EOF/timeout remains retryable, not corruption.
    """
    deadline = time.monotonic() + 12
    lower, start = 0.0, 0.0
    for _ in range(12):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        decoded = subprocess.run([
            binary, "-hide_banner", "-v", "info", "-xerror", "-copyts", "-ss", str(start),
            "-i", str(path), "-map", "0:v:0", "-an", "-t", "2", "-frames:v", "240",
            "-vf", "showinfo,setpts=PTS-STARTPTS", "-f", "null", "-",
        ], check=False, **{**options, "timeout": min(remaining, 12)})
        details = decoded.stderr or ""
        if decoded.returncode:
            state = "invalid" if _INVALID.search(details) and not _UNAVAILABLE.search(details) else "unavailable"
            return MediaHealth(state, details[-500:])
        stamps = [float(value) for value in re.findall(r"\bpts_time:([\d.eE+-]+)", details)]
        if stamps:
            endpoint = max(stamps) + 1.0 / fps
            if len(stamps) < 240 and endpoint < start + 2 - max(.05, 1.0 / fps):
                return MediaHealth("valid", duration=endpoint)
            lower = max(lower, start)
        else:
            upper = start
        start = (lower + upper) / 2
    return MediaHealth("unavailable", "Не удалось достоверно определить конец видеопотока за ограниченное время")


class MediaHealthStore:
    """Separate DB: health writes never invalidate the large embedding matrix."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS health (
                path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER,
                state TEXT, reason TEXT, duration REAL, version INTEGER)""")
            db.execute("CREATE INDEX IF NOT EXISTS health_state ON health(state)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            with db:
                yield db
        finally:
            db.close()

    def cached(self, path: Path) -> MediaHealth | None:
        try:
            size, modified = signature(path)
        except OSError:
            return None
        with self._connect() as db:
            row = db.execute("SELECT state,reason,duration FROM health WHERE path=? AND size=? AND mtime_ns=? AND version=1",
                             (_key(path), size, modified)).fetchone()
        return MediaHealth(*row, identity=(size, modified)) if row else None

    def cached_many(self, paths: list[Path]) -> dict[Path, MediaHealth]:
        """One DB read for incremental scans; stat still invalidates repairs."""
        with self._connect() as db:
            rows = {row[0]: row[1:] for row in db.execute(
                "SELECT path,size,mtime_ns,state,reason,duration FROM health WHERE version=1"
            )}
        result = {}
        for path in paths:
            row = rows.get(_key(path))
            if row is None:
                continue
            try:
                if signature(path) == tuple(row[:2]):
                    result[path] = MediaHealth(*row[2:], identity=tuple(row[:2]))
            except OSError:
                continue
        return result

    def record(self, path: Path, result: MediaHealth, expected: tuple[int, int] | None = None) -> None:
        if result.state == "unavailable":
            return  # A timeout/sharing failure must be retried, never quarantined.
        try:
            size, modified = signature(path)
        except OSError:
            return
        if expected is not None and expected != (size, modified):
            return
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO health VALUES(?,?,?,?,?,?,1)",
                       (_key(path), size, modified, result.state, result.reason, result.duration))

    def check(self, path: Path) -> MediaHealth:
        lock = _PATH_LOCKS[hash(_key(path)) % len(_PATH_LOCKS)]
        with lock:
            result = self.cached(path)
            if result:
                return result
            try:
                before = signature(path)
            except OSError as error:
                return MediaHealth("unavailable", str(error))
            result = inspect_video(path)
            try:
                if signature(path) != before:
                    return MediaHealth("unavailable", "Файл изменился во время проверки")
            except OSError as error:
                return MediaHealth("unavailable", str(error))
            self.record(path, result, before)
            return result

    def quarantined_paths(self) -> set[str]:
        return {item["path"].casefold() for item in self.quarantined_entries()}

    def quarantined_entries(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute("SELECT path,size,mtime_ns,reason FROM health WHERE state='invalid' AND version=1").fetchall()
        result = []
        for path, size, modified, reason in rows:
            try:
                if signature(Path(path)) == (size, modified):
                    result.append({"path": path, "reason": reason})
            except OSError:
                continue
        return result


def default_health_store() -> MediaHealthStore:
    from .config import app_data_root
    return MediaHealthStore(app_data_root() / "media-health.sqlite3")


def quarantine_cache(path: Path, cache_root: Path, result: MediaHealth, source: Path) -> Path | None:
    """Only managed caches move; originals are always logical quarantine only."""
    try:
        if (result.state != "invalid" or result.identity is None or path.is_symlink()
                or path.resolve() == source.resolve() or path.resolve().parent != cache_root.resolve()):
            return None
        before = signature(path)
        if before != result.identity:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if signature(path) != before:
            return None
        source_size, source_modified = signature(source)
        folder = cache_root / "ProxyQuarantine" / uuid.uuid4().hex
        folder.mkdir(parents=True, exist_ok=False)
        target = folder / (path.stem + ".invalid-mp4")
        with (folder / "manifest.json").open("x", encoding="utf-8") as handle:
            json.dump({"cachePath": str(path), "sourcePath": str(source), "reason": result.reason,
                       "sha256": digest.hexdigest(), "size": before[0],
                       "sourceIdentity": {"size": source_size, "mtimeNs": source_modified}}, handle, ensure_ascii=False)
        path.rename(target)
        return target
    except OSError:
        # Failure to relocate a bad cache is not permission to consume it.
        return None
