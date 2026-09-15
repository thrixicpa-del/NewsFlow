"""Pure, non-secret records for channel-scoped public-source research."""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any


_EXPORT_FIELDS = ("title", "url", "publisher", "publishedAt", "topic", "summary", "hook", "idea", "status")
_ALLOWED_TRANSITIONS = {
    "waiting": {"running", "paused", "skipped"},
    "running": {"paused", "stopping", "completed", "failed", "skipped"},
    "paused": {"waiting", "stopping"},
    "stopping": {"completed", "failed", "skipped"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_source_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Нужна HTTP(S)-ссылка")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc.casefold(), parsed.path.rstrip("/"), parsed.query, ""))


def dedupe_sources(urls: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        normalized = normalize_source_url(raw)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def parse_txt_sources(text: str) -> tuple[list[str], list[dict[str, str]]]:
    sources: list[str] = []
    errors: list[dict[str, str]] = []
    for number, raw in enumerate(str(text).splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            sources.append(normalize_source_url(raw))
        except ValueError as exc:
            errors.append({"line": str(number), "message": str(exc)})
    return dedupe_sources(sources), errors


def recover_research_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a durable queue to a safe paused state after an app restart."""

    tasks = []
    for item in state.get("tasks", []) if isinstance(state.get("tasks", []), list) else []:
        if not isinstance(item, dict):
            continue
        restored = dict(item)
        if restored.get("status") == "running":
            restored.update({"status": "waiting", "detail": "Повтор после перезапуска", "updatedAt": _now_iso()})
        tasks.append(restored)
    status = dict(state.get("status", {})) if isinstance(state.get("status"), dict) else {}
    if status.get("state") in {"running", "stopping"}:
        status.update({"state": "paused", "message": "Очередь восстановлена после перезапуска", "updatedAt": _now_iso()})
    return {**state, "tasks": tasks, "status": status}


def channel_research_state(settings: Any, profile_id: str) -> dict[str, Any]:
    """Create or return one non-secret, isolated state record per profile."""

    key = str(profile_id).strip()
    if not key:
        raise ValueError("Не задан профиль канала")
    return settings.channel_research.setdefault(key, {
        "config": {"queries": [], "languages": ["ru", "en"], "regions": [], "manualUrls": []},
        "tasks": [],
        "results": [],
        "status": {"state": "idle", "processed": 0, "skipped": 0, "message": "Не запускался", "updatedAt": _now_iso()},
        "updatedAt": _now_iso(),
    })


def new_task(channel_id: str, url: str, origin: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "channelId": str(channel_id),
        "url": normalize_source_url(url),
        "origin": str(origin),
        "status": "waiting",
        "detail": "Ожидает анализа",
        "updatedAt": _now_iso(),
    }


def transition_task(task: dict[str, Any], target: str, *, detail: str = "") -> dict[str, Any]:
    current = str(task.get("status", "waiting"))
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Недопустимый переход очереди: {current} → {target}")
    return {**task, "status": target, "detail": detail, "updatedAt": _now_iso()}


def public_result(task: dict[str, Any], *, title: str, summary: str, topic: str, hook: str, idea: str,
                  publisher: str = "", published_at: str = "") -> dict[str, str]:
    return {
        "title": str(title), "url": normalize_source_url(str(task.get("url", ""))),
        "publisher": str(publisher), "publishedAt": str(published_at), "topic": str(topic),
        "summary": str(summary), "hook": str(hook), "idea": str(idea), "status": str(task.get("status", "")),
    }


def serialize_results(results: list[dict[str, str]], format_name: str) -> tuple[str, str]:
    rows = [{field: str(item.get(field, "")) for field in _EXPORT_FIELDS} for item in results]
    if format_name == "json":
        return "application/json", json.dumps(rows, ensure_ascii=False, indent=2)
    if format_name == "csv":
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=_EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        return "text/csv", stream.getvalue()
    if format_name == "markdown":
        header = "| " + " | ".join(_EXPORT_FIELDS) + " |\n|" + "|".join(["---"] * len(_EXPORT_FIELDS)) + "|"
        body = ["| " + " | ".join(row[field].replace("|", "\\|").replace("\n", " ") for field in _EXPORT_FIELDS) + " |" for row in rows]
        return "text/markdown", "\n".join([header, *body])
    raise ValueError("Неподдерживаемый формат экспорта")
