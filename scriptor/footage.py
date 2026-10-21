from __future__ import annotations

import json
import logging
import re
import tempfile
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from yt_dlp.utils import DownloadError

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ogv"}


@dataclass
class FootageItem:
    path: str
    name: str
    source: str = "local"
    source_url: str = ""
    license: str = "user-owned"
    tags: list[str] | None = None


def tokenize(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[\w-]{3,}", value, re.UNICODE)}


def scan_folders(folders: list[str]) -> list[FootageItem]:
    items: list[FootageItem] = []
    seen: set[str] = set()
    for raw in folders:
        folder = Path(raw).expanduser()
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS:
                continue
            resolved = str(path.resolve())
            if resolved.casefold() in seen:
                continue
            seen.add(resolved.casefold())
            tags = sorted(tokenize(" ".join(path.parts[-3:])))
            items.append(FootageItem(resolved, path.name, tags=tags))
    return items


def rank_items(query: str, items: list[FootageItem]) -> list[FootageItem]:
    wanted = tokenize(query)
    return sorted(
        items,
        key=lambda item: len(wanted & (set(item.tags or []) | tokenize(item.name))),
        reverse=True,
    )


def save_index(path: Path, items: list[FootageItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(path: Path) -> list[FootageItem]:
    if not path.exists():
        return []
    return [FootageItem(**item) for item in json.loads(path.read_text(encoding="utf-8"))]


def search_wikimedia_videos(query: str, limit: int = 12) -> list[dict]:
    """Search freely licensed videos and return provenance before any download."""
    params = urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:video",
        "gsrnamespace": "6", "gsrlimit": str(limit), "prop": "imageinfo",
        "iiprop": "url|extmetadata", "format": "json", "origin": "*",
    })
    request = urllib.request.Request(
        f"https://commons.wikimedia.org/w/api.php?{params}",
        headers={"User-Agent": "NewsFlow/0.2 (footage research tool)"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    results = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        metadata = info.get("extmetadata") or {}
        url = info.get("url", "")
        if not url:
            continue
        results.append({
            "title": page.get("title", "").removeprefix("File:"),
            "download_url": url,
            "source_url": info.get("descriptionurl", ""),
            "license": (metadata.get("LicenseShortName") or {}).get("value", "Check source"),
            "artist": re.sub("<[^>]+>", "", (metadata.get("Artist") or {}).get("value", "")),
        })
    return results


def download_footage(result: dict, folder: Path) -> FootageItem:
    folder.mkdir(parents=True, exist_ok=True)
    suffix = Path(urllib.parse.urlparse(result["download_url"]).path).suffix or ".webm"
    filename = re.sub(r"[^\w .()-]", "_", result["title"]).strip()[:120] + suffix
    target = folder / filename
    request = urllib.request.Request(result["download_url"], headers={"User-Agent": "NewsFlow/0.2"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    return FootageItem(str(target), target.name, "wikimedia", result.get("source_url", ""),
                       result.get("license", "Check source"), sorted(tokenize(result["title"])))


def search_youtube_videos(query: str, limit: int = 10) -> list[dict]:
    """Metadata-only YouTube search. Download remains an explicit separate action."""
    from yt_dlp import YoutubeDL
    options = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    with YoutubeDL(options) as client:
        payload = client.extract_info(f"ytsearch{limit}:{query}", download=False)
    results = []
    for item in payload.get("entries", []) if payload else []:
        video_id = item.get("id", "")
        if not video_id:
            continue
        results.append({
            "title": item.get("title", "Без названия"),
            "source_url": item.get("url") if str(item.get("url", "")).startswith("http")
                          else f"https://www.youtube.com/watch?v={video_id}",
            "download_url": item.get("url", ""),
            "license": "Проверьте разрешение правообладателя",
            "artist": item.get("channel") or item.get("uploader") or "",
            "duration": item.get("duration") or 0,
            "source": "youtube",
        })
    return results


def search_all_available_videos(query: str, limit_per_source: int = 10) -> list[dict]:
    """Search every external source integrated in NewsFlow, preserving its origin."""
    results: list[dict] = []
    seen: set[str] = set()
    for finder in (search_wikimedia_videos, search_youtube_videos):
        for item in finder(query, limit_per_source):
            item = dict(item)
            item.setdefault("source", "wikimedia" if finder is search_wikimedia_videos else "youtube")
            key = item.get("source_url") or item.get("download_url") or item.get("title", "")
            if key and key not in seen:
                seen.add(key)
                results.append(item)
    return results


def download_youtube_segment(result: dict, folder: Path, start: float = 0.0, duration: float = 6.0) -> FootageItem:
    """Download only a short selected interval instead of retaining the entire source video."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import download_range_func

    from .timeline import ffmpeg_executable
    folder.mkdir(parents=True, exist_ok=True)
    safe_title = re.sub(r"[^\w .()-]", "_", result["title"]).strip()[:100]
    output_template = str(folder / f"{safe_title}__%(id)s__{int(start):06d}.%(ext)s")
    completed = []

    def hook(data):
        if data.get("status") == "finished" and data.get("filename"):
            completed.append(data["filename"])

    options = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "download_ranges": download_range_func(None, [(max(0.0, start), max(0.1, start + duration))]),
        "force_keyframes_at_cuts": True,
        "ffmpeg_location": str(Path(ffmpeg_executable()).parent),
        "progress_hooks": [hook],
    }
    with YoutubeDL(options) as client:
        info = client.extract_info(result["source_url"], download=True)
        expected = Path(client.prepare_filename(info)).with_suffix(".mp4")
    candidates = [Path(value) for value in completed] + [expected]
    target = next((path for path in candidates if path.exists()), None)
    if target is None:
        matches = sorted(folder.glob(f"{safe_title}__*"), key=lambda path: path.stat().st_mtime, reverse=True)
        target = matches[0] if matches else None
    if target is None:
        raise RuntimeError("yt-dlp не вернул скачанный фрагмент")
    return FootageItem(str(target.resolve()), target.name, "youtube", result.get("source_url", ""),
                       result.get("license", "Проверьте разрешение правообладателя"),
                       sorted(tokenize(result["title"])))


def download_best_youtube_segment(result: dict, folder: Path, visual_query_en: str, scorer,
                                  duration: float = 6.0, probes: int = 5) -> FootageItem:
    """Visually sample a source and retain the six-second interval closest to the scene query."""
    source_duration = float(result.get("duration") or 0.0)
    if source_duration <= duration:
        try:
            from yt_dlp import YoutubeDL
            with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as client:
                metadata = client.extract_info(result["source_url"], download=False)
            source_duration = float((metadata or {}).get("duration") or 0.0)
        except (DownloadError, OSError, RuntimeError, ValueError, KeyError, TypeError):
            source_duration = 0.0
    source_duration = max(duration, source_duration)
    latest_start = max(0.0, source_duration - duration)
    if latest_start <= 0.0:
        return download_youtube_segment(result, folder, 0.0, duration)
    count = max(2, min(7, int(probes)))
    starts = [latest_start * index / (count - 1) for index in range(count)]
    scored: list[tuple[float, float]] = []
    with tempfile.TemporaryDirectory(prefix="newsflow-youtube-probes-") as temporary:
        preview_folder = Path(temporary)
        for start in starts:
            try:
                preview = download_youtube_segment(result, preview_folder, start, min(2.0, duration))
                scored.append((float(scorer(preview.path, visual_query_en)), start))
            except (DownloadError, OSError, RuntimeError, ValueError, KeyError, TypeError) as error:
                logging.getLogger(__name__).debug("Optional footage preview failed: %s", type(error).__name__)
    best_start = max(scored, default=(-1.0, 0.0))[1]
    return download_youtube_segment(result, folder, best_start, duration)
