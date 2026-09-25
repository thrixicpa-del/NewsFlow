"""Non-destructive Publication V2 domain records and legacy migration.

This module deliberately operates on in-memory Settings.  The bridge owns
when data is persisted, so migration can be previewed and tested without
touching a user's actual publication queue.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .timeline import probe_media_duration
from .youtube_api import compose_youtube_description

_STAGES = (
    "AUTH_CHECK", "VIDEO_UPLOAD", "YOUTUBE_PROCESSING", "TITLE", "DESCRIPTION",
    "TAGS", "THUMBNAIL", "ADS", "POST", "CARDS", "END_SCREEN", "SCHEDULE",
)


@dataclass(frozen=True)
class PublicationMigrationReport:
    migrated_items: int
    migrated_jobs: int
    missing_artifacts: int
    ambiguous_jobs: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_fingerprint(path_value: object) -> dict[str, int] | None:
    """Return a cheap immutable-input fingerprint without hashing large media files."""
    path = Path(str(path_value or "").strip())
    try:
        if not path.is_file():
            return None
        stat = path.stat()
    except OSError:
        return None
    return {"sizeBytes": int(stat.st_size), "mtimeNs": int(stat.st_mtime_ns)}


def frozen_artifact_matches(snapshot: dict[str, Any], artifact_name: str, path_value: object) -> bool:
    """Return True for legacy snapshots or when the current file matches the frozen fingerprint."""
    frozen = dict(dict(snapshot.get("artifactFingerprints", {}) or {}).get(artifact_name, {}) or {})
    if not frozen:
        return True
    current = _file_fingerprint(path_value)
    return current is not None and current == frozen


def _oauth_payload_is_structurally_valid(value: object) -> bool:
    """Validate persisted OAuth shape without network access or exposing secrets."""
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    return any(str(payload.get(key) or "").strip() for key in ("token", "refresh_token"))


def _normalise(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def resolve_publication_upload_title(metadata: dict[str, Any]) -> str:
    """Return the frozen YouTube title: SEO title when present, source title otherwise."""
    source = dict(metadata or {})
    return " ".join(str(source.get("seoTitle") or source.get("title") or "").split())


def _legacy_production_id(job: dict[str, Any]) -> str:
    explicit = str(job.get("productionItemId", "")).strip()
    if explicit:
        return explicit
    stable_input = "|".join((str(job.get("videoPath", "")).casefold(), str(job.get("packageFolder", "")).casefold(), str(job.get("id", ""))))
    return f"legacy-{sha256(stable_input.encode('utf-8')).hexdigest()[:24]}"


def _step(status: str = "PENDING") -> dict[str, Any]:
    return {"status": status, "startedAt": None, "finishedAt": None, "durationMs": None,
            "attempts": 0, "error": None, "providerResult": None, "progress": None}


def _execution(snapshot_id: str, production_item_id: str, job: dict[str, Any]) -> dict[str, Any]:
    video_id = str(job.get("videoId", "")).strip()
    steps = {stage: _step() for stage in _STAGES}
    if video_id:
        steps["VIDEO_UPLOAD"] = {**_step("SUCCESS"), "attempts": 1,
                                 "providerResult": {"youtubeVideoId": video_id}}
    return {
        "jobId": f"execution:{snapshot_id}", "snapshotId": snapshot_id,
        "productionItemId": production_item_id,
        "currentStage": "DONE" if video_id and str(job.get("status", "")).lower() in {"done", "scheduled"} else ("VIDEO_UPLOAD" if not video_id else "YOUTUBE_PROCESSING"),
        "overallStatus": "SCHEDULED" if video_id and str(job.get("publishAt", "")).strip() else ("UPLOADED" if video_id else "WAITING"),
        "youtubeVideoId": video_id or None, "youtubeVideoUrl": str(job.get("videoUrl", "")).strip() or None,
        "startedAt": None, "completedAt": None, "plannedPublishAt": str(job.get("publishAt", "")).strip() or None,
        "confirmedPublishAt": None, "actualPublishedAt": None,
        "uploadStartedAt": None, "uploadCompletedAt": None,
        "processingStartedAt": None, "processingCompletedAt": None,
        "steps": steps, "timeline": [], "idempotencyKey": f"snapshot:{snapshot_id}",
        "activeLease": None,
    }


def migrate_legacy_publication_data(settings: Any) -> PublicationMigrationReport:
    """Populate V2 structures without deleting or changing any legacy queue row."""
    items = dict(getattr(settings, "youtube_publication_items", {}) or {})
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    known_by_id = {str(item.get("id") or item.get("production_item_id") or "").strip(): item
                   for item in getattr(settings, "idea_production_items", []) if isinstance(item, dict)
                   and str(item.get("id") or item.get("production_item_id") or "").strip()}
    known_by_title: dict[str, list[str]] = {}
    known_order: dict[str, int] = {}
    for position, (production_id, item) in enumerate(known_by_id.items(), start=1):
        known_by_title.setdefault(_normalise(item.get("title")), []).append(production_id)
        known_order[production_id] = position

    migrated_items = migrated_jobs = missing_artifacts = ambiguous_jobs = 0
    for production_id, production in known_by_id.items():
        if production_id not in items:
            items[production_id] = {
                "productionItemId": production_id, "legacyLinks": {},
                "artifacts": {}, "metadata": {
                    "title": str(production.get("title", "")), "description": "", "tags": [],
                    "index": known_order[production_id],
                    "topic": str(production.get("topic", "")),
                    "direction": str(production.get("direction", "")),
                    "angle": str(production.get("angle", "")),
                    "topicFamily": str(production.get("topic_family", "")),
                    "priority": int(production.get("publication_priority", 0) or 0),
                },
                "readiness": {"state": "DISCOVERED", "reasons": ["VIDEO_MISSING"]}, "jobIds": [], "updatedAt": _now(),
            }
            migrated_items += 1
        else:
            metadata = items[production_id].setdefault("metadata", {})
            metadata.setdefault("index", known_order[production_id])
            metadata.setdefault("topic", str(production.get("topic", "")))
            metadata.setdefault("direction", str(production.get("direction", "")))
            metadata.setdefault("angle", str(production.get("angle", "")))
            metadata.setdefault("topicFamily", str(production.get("topic_family", "")))
            metadata.setdefault("priority", int(production.get("publication_priority", 0) or 0))

    # Older production batches did not have ProductionItems or publication
    # jobs at all: their durable identity lived in the montage queue index.
    # Project those rows into V2 without claiming that a missing MP4 vanished.
    # A later legacy publication job with the same title may enrich this item,
    # but this fallback must already make every recoverable row visible.
    montage_rows = getattr(settings, "montage_task_statuses", {}) or {}
    voice_outputs = getattr(settings, "voice_scenario_outputs", {}) or {}
    if isinstance(montage_rows, dict):
        for raw_index, raw_task in sorted(montage_rows.items(), key=lambda pair: str(pair[0])):
            if not isinstance(raw_task, dict):
                continue
            title = str(raw_task.get("title", "")).strip()
            if not title:
                continue
            matches = known_by_title.get(_normalise(title), [])
            production_id = matches[0] if len(matches) == 1 else f"legacy-montage:{raw_index}"
            item = items.get(production_id)
            if item is None:
                item = {
                    "productionItemId": production_id,
                    "legacyLinks": {},
                    "artifacts": {},
                    "metadata": {"title": title, "description": "", "tags": []},
                    "readiness": {"state": "DISCOVERED", "reasons": ["VIDEO_MISSING"]},
                    "jobIds": [],
                    "updatedAt": _now(),
                }
                items[production_id] = item
                migrated_items += 1
            video_path = str(raw_task.get("outputPath", "")).strip()
            voice_path = str(raw_task.get("voicePath") or voice_outputs.get(str(raw_index), "")).strip()
            video_exists = bool(video_path and Path(video_path).is_file())
            if video_path and not video_exists:
                missing_artifacts += 1
            item.setdefault("legacyLinks", {}).update({
                "legacyMontageIndex": str(raw_index),
                "videoPath": video_path,
            })
            item.setdefault("artifacts", {})["video"] = {
                "path": video_path,
                "exists": video_exists,
                "validatedAt": _now(),
            }
            item["artifacts"]["audio"] = {
                "path": voice_path,
                "exists": bool(voice_path and Path(voice_path).is_file()),
                "validatedAt": _now(),
            }
            item.setdefault("metadata", {}).setdefault("title", title)
            item["readiness"] = {
                "state": "VIDEO_READY" if video_exists else "VIDEO_MISSING",
                "reasons": [] if video_exists else ["VIDEO_MISSING"],
            }
            item["updatedAt"] = _now()

    for legacy in getattr(settings, "youtube_publication_jobs", []) or []:
        if not isinstance(legacy, dict):
            continue
        title_matches = known_by_title.get(_normalise(legacy.get("title")), [])
        production_id = str(legacy.get("productionItemId", "")).strip()
        if not production_id:
            if len(title_matches) == 1:
                production_id = title_matches[0]
            elif len(title_matches) > 1:
                ambiguous_jobs += 1
                continue
            else:
                production_id = _legacy_production_id(legacy)
        item = items.get(production_id)
        if item is None:
            item = {"productionItemId": production_id, "legacyLinks": {}, "artifacts": {},
                    "metadata": {"title": str(legacy.get("title", "")), "description": "", "tags": []},
                    "readiness": {"state": "DISCOVERED", "reasons": []}, "jobIds": [], "updatedAt": _now()}
            items[production_id] = item
            migrated_items += 1
        video_path = str(legacy.get("videoPath", "")).strip()
        thumbnail_path = str(legacy.get("thumbnailPath", "")).strip()
        exists = bool(video_path and Path(video_path).is_file())
        reasons = [] if exists else ["VIDEO_MISSING"]
        if not exists:
            missing_artifacts += 1
        item["legacyLinks"] = {"legacyJobId": str(legacy.get("id", "")).strip(),
                                "packageFolder": str(legacy.get("packageFolder", "")).strip(), "videoPath": video_path}
        item["artifacts"]["video"] = {"path": video_path, "exists": exists, "validatedAt": _now()}
        item["artifacts"]["thumbnail"] = {"path": thumbnail_path, "exists": bool(thumbnail_path and Path(thumbnail_path).is_file()), "validatedAt": _now()}
        item["metadata"].update({"description": str(legacy.get("seoDescription", "")), "tags": [str(value) for value in legacy.get("tags", []) if str(value).strip()]})
        item["readiness"] = {"state": "VIDEO_READY" if exists else "VIDEO_MISSING", "reasons": reasons}
        job_id = str(legacy.get("id", "")).strip()
        if job_id and job_id not in item["jobIds"]:
            item["jobIds"].append(job_id)
        item["updatedAt"] = _now()
        snapshot_id = f"legacy-snapshot:{job_id or production_id}"
        if snapshot_id not in snapshots:
            snapshots[snapshot_id] = {
                "id": snapshot_id, "productionItemId": production_id, "legacyJobId": job_id,
                "videoPath": video_path, "thumbnailPath": thumbnail_path, "channelId": str(legacy.get("channelId", "")).strip(),
                "title": str(legacy.get("title", "")), "privacy": str(legacy.get("privacy", "private")),
                "publishMode": "schedule" if str(legacy.get("publishAt", "")).strip() else "publish_now",
                "requestedPublishAt": str(legacy.get("publishAt", "")).strip() or None,
                "idempotencyKey": f"legacy:{job_id or production_id}", "createdAt": _now(),
            }
        if snapshot_id not in executions:
            executions[snapshot_id] = _execution(snapshot_id, production_id, legacy)
        migrated_jobs += 1

    settings.youtube_publication_items = items
    settings.youtube_publication_snapshots = snapshots
    settings.youtube_publication_executions = executions
    settings.youtube_publication_migration_version = max(int(getattr(settings, "youtube_publication_migration_version", 0) or 0), 2)
    return PublicationMigrationReport(migrated_items, migrated_jobs, missing_artifacts, ambiguous_jobs)


def reconcile_publication_items(settings: Any) -> dict[str, Any]:
    """Refresh Publication V2 from current durable artifacts without title-based identity."""
    migrate_legacy_publication_data(settings)
    items = dict(settings.youtube_publication_items)

    seo_by_id = {
        str(row.get("production_item_id") or row.get("productionItemId") or "").strip(): dict(row)
        for row in getattr(settings, "seo_queue", [])
        if isinstance(row, dict) and str(row.get("production_item_id") or row.get("productionItemId") or "").strip()
    }
    cover_by_id = {
        str(row.get("production_item_id") or row.get("productionItemId") or "").strip(): dict(row)
        for row in getattr(settings, "cover_queue", [])
        if isinstance(row, dict) and str(row.get("production_item_id") or row.get("productionItemId") or "").strip()
    }
    assignments = dict(getattr(settings, "youtube_publication_assignments", {}) or {})
    rules = dict(getattr(settings, "youtube_channel_publication_rules", {}) or {})

    counters = {
        "total": len(items),
        "videoReady": 0,
        "videoMissing": 0,
        "contentReady": 0,
        "publicationReady": 0,
        "needsAttention": 0,
    }

    for production_id, source in items.items():
        item = dict(source)
        artifacts = dict(item.get("artifacts", {}) or {})
        video = dict(artifacts.get("video", {}) or {})
        video_path = str(video.get("path", "")).strip()
        video_exists = bool(video_path and Path(video_path).is_file())
        duration: float | None = None
        if video_exists:
            try:
                duration = float(video.get("durationSeconds") or video.get("duration") or 0) or float(probe_media_duration(Path(video_path)))
            except (OSError, RuntimeError, TypeError, ValueError):
                duration = None
        video.update({
            "path": video_path,
            "exists": video_exists,
            "validatedAt": _now(),
        })
        if duration and duration > 0:
            video["durationSeconds"] = duration
            item["durationSeconds"] = duration
        artifacts["video"] = video

        seo = seo_by_id.get(production_id, {})
        metadata = dict(item.get("metadata", {}) or {})
        if seo:
            if str(seo.get("source_title", "")).strip():
                metadata["title"] = str(seo.get("source_title", "")).strip()
            metadata["seoTitle"] = str(seo.get("title", "")).strip()
            metadata["description"] = str(seo.get("description", "")).strip()
            metadata["tags"] = [str(value).strip() for value in seo.get("tags", []) if str(value).strip()]
            metadata["hashtags"] = [str(value).strip() for value in seo.get("hashtags", []) if str(value).strip()]
            metadata["seoStatus"] = str(seo.get("status", "")).strip()
            metadata["tagsStatus"] = str(seo.get("tags_status", "")).strip()

        cover = cover_by_id.get(production_id, {})
        cover_path = str(cover.get("selected_path") or cover.get("path") or "").strip()
        if not cover_path:
            paths = cover.get("paths")
            if isinstance(paths, list):
                cover_path = next((str(value).strip() for value in paths if str(value).strip()), "")
        thumbnail = dict(artifacts.get("thumbnail", {}) or {})
        if cover_path:
            thumbnail["path"] = cover_path
        thumbnail_path = str(thumbnail.get("path", "")).strip()
        thumbnail.update({
            "path": thumbnail_path,
            "exists": bool(thumbnail_path and Path(thumbnail_path).is_file()),
            "validatedAt": _now(),
        })
        artifacts["thumbnail"] = thumbnail

        reasons: list[str] = []
        if not video_exists:
            reasons.append("VIDEO_MISSING")
        elif duration is None:
            reasons.append("VIDEO_DURATION_UNKNOWN")
        upload_title = resolve_publication_upload_title(metadata)
        if not upload_title:
            reasons.append("TITLE_MISSING")
        elif len(upload_title) > 100:
            reasons.append("TITLE_TOO_LONG")
        if not str(metadata.get("description", "")).strip():
            reasons.append("SEO_DESCRIPTION_MISSING")
        if not [value for value in metadata.get("tags", []) if str(value).strip()]:
            reasons.append("TAGS_MISSING")
        if not thumbnail["exists"]:
            reasons.append("THUMBNAIL_MISSING")

        content_blockers = {
            "VIDEO_MISSING", "VIDEO_DURATION_UNKNOWN", "TITLE_MISSING", "TITLE_TOO_LONG",
            "SEO_DESCRIPTION_MISSING", "TAGS_MISSING", "THUMBNAIL_MISSING",
        }
        content_ready = not any(reason in content_blockers for reason in reasons)
        assignment = dict(assignments.get(production_id, {}) or {})
        channel_id = str(assignment.get("channelId", "")).strip()
        if content_ready and not channel_id:
            reasons.append("ASSIGNMENT_REQUIRED")
        elif content_ready:
            rule = dict(rules.get(channel_id, {}) or {})
            if str(rule.get("publishMode", "")).strip() == "schedule" and not str(assignment.get("publishAt", "")).strip():
                reasons.append("SCHEDULE_REQUIRED")

        publication_ready = content_ready and not any(
            reason in {"ASSIGNMENT_REQUIRED", "SCHEDULE_REQUIRED"} for reason in reasons
        )
        # Preserve the artifact-level state contract: state answers whether
        # the rendered MP4 exists. Content/publication readiness are separate
        # booleans so a missing thumbnail or SEO cannot make a ready video
        # disappear from registry counters/UI.
        state = "VIDEO_READY" if video_exists else "VIDEO_MISSING"

        item["artifacts"] = artifacts
        item["metadata"] = metadata
        item["readiness"] = {
            "state": state,
            "videoReady": video_exists,
            "contentReady": content_ready,
            "publicationReady": publication_ready,
            "reasons": reasons,
        }
        item["updatedAt"] = _now()
        items[production_id] = item

        counters["videoReady"] += int(video_exists)
        counters["videoMissing"] += int(not video_exists)
        counters["contentReady"] += int(content_ready)
        counters["publicationReady"] += int(publication_ready)
        counters["needsAttention"] += int(bool(reasons))

    settings.youtube_publication_items = items
    return {"items": items, "counters": counters}


def _item_duration_seconds(item: dict[str, Any]) -> float | None:
    metadata = dict(item.get("metadata", {}) or {})
    video = dict(dict(item.get("artifacts", {}) or {}).get("video", {}) or {})
    for raw in (
        item.get("durationSeconds"),
        metadata.get("durationSeconds"),
        metadata.get("duration"),
        video.get("durationSeconds"),
        video.get("duration"),
    ):
        if raw in (None, "", 0, "0"):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _item_order(item: dict[str, Any], fallback: int) -> int:
    metadata = dict(item.get("metadata", {}) or {})
    for raw in (metadata.get("index"), item.get("productionOrder"), item.get("index")):
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return fallback


def _rule_allows_item(rule: dict[str, Any], item: dict[str, Any], fallback_order: int) -> bool:
    duration = _item_duration_seconds(item)
    minimum = max(0.0, float(rule.get("minDurationSeconds", 0) or 0))
    maximum = max(0.0, float(rule.get("maxDurationSeconds", 0) or 0))
    if minimum and (duration is None or duration < minimum):
        return False
    if maximum and (duration is None or duration > maximum):
        return False

    order = _item_order(item, fallback_order)
    order_start = max(0, int(rule.get("orderStart", 0) or 0))
    order_end = max(0, int(rule.get("orderEnd", 0) or 0))
    if order_start and order < order_start:
        return False
    if order_end and order > order_end:
        return False

    metadata = dict(item.get("metadata", {}) or {})
    routing_text = " ".join(
        str(metadata.get(field, ""))
        for field in ("topic", "direction", "angle", "topicFamily")
    ).casefold()
    includes = [
        str(value).casefold()
        for value in rule.get("includeKeywords", [])
        if str(value).strip()
    ] if isinstance(rule.get("includeKeywords"), list) else []
    excludes = [
        str(value).casefold()
        for value in rule.get("excludeKeywords", [])
        if str(value).strip()
    ] if isinstance(rule.get("excludeKeywords"), list) else []
    if includes and not any(value in routing_text for value in includes):
        return False
    if excludes and any(value in routing_text for value in excludes):
        return False
    return True


def _item_priority(item: dict[str, Any]) -> int:
    metadata = dict(item.get("metadata", {}) or {})
    try:
        return int(metadata.get("priority", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _fill_ratio(rule: dict[str, Any], used: dict[str, int]) -> float:
    channel_id = str(rule.get("channelId", "")).strip()
    quota = max(1, int(rule.get("quota", 0) or 0))
    return used.get(channel_id, 0) / quota


def _schedule_conflict_message(kind: str) -> str:
    return {
        "quarter_hour_required": "Время должно попадать на сетку :00 / :15 / :30 / :45.",
        "duplicate_slot": "На этом канале уже занят тот же временной слот.",
        "disabled_weekday": "Выбран день, в который канал не публикует.",
        "outside_window": "Время находится вне разрешённого окна публикации канала.",
        "daily_cap_exceeded": "Превышен дневной лимит публикаций канала.",
        "max_videos_per_hour": "Превышен лимит публикаций канала за один час.",
        "topic_cooldown": "Два ролика одной темы стоят слишком близко друг к другу.",
        "blackout_period": "Время попадает в blackout-период канала.",
        "invalid_blackout_period": "В правилах канала есть некорректный blackout-период.",
        "invalid_timezone_or_time": "Некорректное время или timezone.",
    }.get(str(kind), str(kind))


def _schedule_conflict_suggestion(kind: str) -> str:
    return {
        "quarter_hour_required": "Округлите время до ближайшего 15-минутного слота.",
        "duplicate_slot": "Сдвиньте один ролик минимум на 15 минут.",
        "disabled_weekday": "Перенесите ролик на следующий разрешённый день.",
        "outside_window": "Перенесите ролик внутрь окна публикации канала.",
        "daily_cap_exceeded": "Перенесите лишний ролик на следующий день или увеличьте дневной лимит.",
        "max_videos_per_hour": "Сдвиньте лишний ролик за пределы текущего 60-минутного окна или увеличьте лимит в час.",
        "topic_cooldown": "Разнесите ролики одной темы на заданный cooldown или уменьшите cooldown в правилах канала.",
        "blackout_period": "Перенесите ролик за пределы blackout-периода.",
        "invalid_blackout_period": "Исправьте начало/конец blackout в настройках канала.",
        "invalid_timezone_or_time": "Проверьте timezone и дату/время назначения.",
    }.get(str(kind), "Измените правило или время и пересчитайте preview.")


def build_distribution_preview(items: dict[str, dict], rules: list[dict], assignments: dict[str, dict]) -> dict[str, Any]:
    """Return a deterministic, non-mutating smart allocation preview.

    Manual/locked/confirmed assignments are immutable inputs. Auto allocation
    respects auth, quotas, duration/order eligibility and the selected strategy.
    """
    active_rules: list[dict[str, Any]] = []
    for raw_rule in rules:
        rule = dict(raw_rule)
        channel_id = str(rule.get("channelId", "")).strip()
        quota = max(0, int(rule.get("quota", 0) or 0))
        if not channel_id or not bool(rule.get("enabled", True)) or quota <= 0:
            continue
        if rule.get("oauthConnected") is False:
            continue
        if str(rule.get("distributionStrategy", "balanced")).strip() == "manual":
            continue
        rule["quota"] = quota
        active_rules.append(rule)

    by_channel = {str(rule["channelId"]): rule for rule in active_rules}
    rule_order = {str(rule["channelId"]): index for index, rule in enumerate(active_rules)}
    used = {channel_id: 0 for channel_id in by_channel}
    rows: list[dict[str, Any]] = []
    assigned_ids: set[str] = set()

    ordered_items = sorted(
        items.items(),
        key=lambda pair: (_item_order(pair[1], 10**9), pair[0]),
    )
    item_order = {production_id: position + 1 for position, (production_id, _item) in enumerate(ordered_items)}

    for production_id, _item in ordered_items:
        assignment = dict(assignments.get(production_id, {}) or {})
        channel_id = str(assignment.get("channelId", "")).strip()
        source = str(assignment.get("source", "")).strip()
        locked = bool(assignment.get("locked", False)) or source in {"manual", "confirmed_snapshot"}
        if channel_id and locked:
            if channel_id in used:
                used[channel_id] += 1
            rows.append({
                "productionItemId": production_id,
                "channelId": channel_id,
                "source": source or "manual",
                "locked": True,
                "reason": "confirmed_snapshot" if source == "confirmed_snapshot" else "manual_locked",
                "publishAt": str(assignment.get("publishAt", "") or ""),
            })
            assigned_ids.add(production_id)

    candidates = []
    for production_id, item in ordered_items:
        if production_id in assigned_ids:
            continue
        readiness = dict(item.get("readiness", {}) or {})
        # Current reconciled records have an explicit contentReady flag and
        # must satisfy it. Legacy/synthetic records created before that field
        # existed retain the historical VIDEO_READY fallback.
        if "contentReady" in readiness:
            eligible = bool(readiness.get("contentReady"))
        else:
            eligible = str(readiness.get("state", "")) == "VIDEO_READY"
        if eligible:
            candidates.append((production_id, item))

    # Longest-to-monetized is a first pass, not a global candidate sort.
    # Once monetized capacity is filled, all remaining items must return to
    # their normal priority/batch order so regular channels keep deterministic
    # ordered/balanced semantics.
    candidates.sort(key=lambda pair: (-_item_priority(pair[1]), item_order[pair[0]], pair[0]))
    longest_rules = [
        rule for rule in active_rules
        if bool(rule.get("monetized"))
        and str(rule.get("distributionStrategy", "")) == "longest_monetized"
    ]
    allocated_ids: set[str] = set()
    for production_id, item in sorted(
        candidates,
        key=lambda pair: (
            -(_item_duration_seconds(pair[1]) or 0.0),
            -_item_priority(pair[1]),
            item_order[pair[0]],
            pair[0],
        ),
    ):
        available_longest = [
            rule for rule in longest_rules
            if used[str(rule["channelId"])] < int(rule["quota"])
            and _rule_allows_item(rule, item, item_order[production_id])
        ]
        if not available_longest:
            continue
        chosen = min(
            available_longest,
            key=lambda rule: (
                _fill_ratio(rule, used),
                -int(rule.get("channelPriority", 0) or 0),
                rule_order[str(rule["channelId"])],
            ),
        )
        channel_id = str(chosen["channelId"])
        used[channel_id] += 1
        allocated_ids.add(production_id)
        rows.append({
            "productionItemId": production_id,
            "channelId": channel_id,
            "source": "auto",
            "locked": False,
            "reason": "longest_monetized",
        })

    for production_id, item in candidates:
        if production_id in allocated_ids:
            continue
        available = [
            rule for rule in active_rules
            if used[str(rule["channelId"])] < int(rule["quota"])
            and _rule_allows_item(rule, item, item_order[production_id])
        ]
        if not available:
            has_capacity = any(used[str(rule["channelId"])] < int(rule["quota"]) for rule in active_rules)
            rows.append({
                "productionItemId": production_id,
                "channelId": "",
                "source": "",
                "locked": False,
                "reason": "eligibility_mismatch" if has_capacity else "quota_exhausted",
            })
            continue

        balanced = [rule for rule in available if str(rule.get("distributionStrategy", "balanced")) == "balanced"]
        pool = balanced or available
        reason = "balanced" if balanced else "ordered"
        chosen = min(
            pool,
            key=lambda rule: (
                _fill_ratio(rule, used),
                -int(rule.get("channelPriority", 0) or 0),
                rule_order[str(rule["channelId"])],
            ),
        )
        channel_id = str(chosen["channelId"])
        used[channel_id] += 1
        rows.append({
            "productionItemId": production_id,
            "channelId": channel_id,
            "source": "auto",
            "locked": False,
            "reason": reason,
        })

    schedule_warnings: list[dict[str, str]] = []
    for channel_id, rule in by_channel.items():
        if str(rule.get("publishMode", "")).strip() != "schedule":
            continue
        channel_rows = [row for row in rows if row.get("channelId") == channel_id]
        if not channel_rows:
            continue
        manual_slots = {
            str(row["productionItemId"]): str((assignments.get(str(row["productionItemId"]), {}) or {}).get("publishAt", "") or row.get("publishAt", "") or "").strip()
            for row in channel_rows if bool(row.get("locked", False))
        }
        try:
            slots = build_channel_schedule(
                [str(row["productionItemId"]) for row in channel_rows],
                rule,
                manual_slots,
                item_topics={
                    str(row["productionItemId"]): str(
                        dict(items.get(str(row["productionItemId"]), {}).get("metadata", {}) or {}).get("topicFamily")
                        or dict(items.get(str(row["productionItemId"]), {}).get("metadata", {}) or {}).get("topic")
                        or ""
                    ).strip()
                    for row in channel_rows
                },
            )
        except ValueError as error:
            schedule_warnings.append({"channelId": channel_id, "message": str(error)})
            for row in channel_rows:
                row["scheduleWarning"] = str(error)
            continue
        by_production_id = {slot["productionItemId"]: slot for slot in slots}
        for row in channel_rows:
            slot = by_production_id[str(row["productionItemId"])]
            row["publishAt"] = slot["publishAt"]
            row["timezone"] = slot["timezone"]
    validation_rules = {
        str(rule.get("channelId", "")).strip(): dict(rule)
        for rule in rules
        if str(rule.get("channelId", "")).strip()
    }
    item_topics = {
        str(production_id): str(
            dict(item.get("metadata", {}) or {}).get("topicFamily")
            or dict(item.get("metadata", {}) or {}).get("topic")
            or ""
        ).strip()
        for production_id, item in items.items()
    }
    validation_conflicts = validate_publication_schedule(rows, validation_rules, item_topics=item_topics)
    conflicts_by_item: dict[str, list[str]] = {}
    suggestions_by_item: dict[str, list[str]] = {}
    for conflict in validation_conflicts:
        production_id = str(conflict.get("productionItemId", "")).strip()
        if not production_id:
            continue
        kind = str(conflict.get("kind", "")).strip()
        conflicts_by_item.setdefault(production_id, []).append(_schedule_conflict_message(kind))
        suggestions_by_item.setdefault(production_id, []).append(_schedule_conflict_suggestion(kind))
    for row in rows:
        production_id = str(row.get("productionItemId", "")).strip()
        existing = str(row.get("scheduleWarning", "")).strip()
        messages = conflicts_by_item.get(production_id, [])
        if existing:
            messages = [existing, *messages]
        if messages:
            row["scheduleWarning"] = " ".join(dict.fromkeys(messages))
            row["scheduleSuggestion"] = " ".join(dict.fromkeys(suggestions_by_item.get(production_id, []))) or "Исправьте конфликт и пересчитайте preview."

    return {
        "assignments": rows,
        "channelUsage": used,
        "scheduleWarnings": [
            *schedule_warnings,
            *validation_conflicts,
        ],
    }

def _clock(value: object) -> time | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    return time.fromisoformat(clean)


def _is_quarter_hour(value: datetime) -> bool:
    return value.minute % 15 == 0 and value.second == 0 and value.microsecond == 0


def _validate_quarter_hour_clock(value: time | None, label: str) -> None:
    if value is not None and (value.minute % 15 != 0 or value.second != 0 or value.microsecond != 0):
        raise ValueError(f"{label} должно быть кратно 15 минутам (:00/:15/:30/:45).")

def _blackout_ranges(rule: dict[str, Any], zone: ZoneInfo) -> list[tuple[datetime, datetime, str]]:
    result: list[tuple[datetime, datetime, str]] = []
    raw_periods = rule.get("blackoutPeriods", [])
    if raw_periods in (None, ""):
        return result
    if not isinstance(raw_periods, list):
        raise ValueError("blackoutPeriods должен быть списком")
    for raw in raw_periods:
        if not isinstance(raw, dict):
            raise ValueError("Каждый blackout-период должен быть объектом")
        start_raw = str(raw.get("start", "")).strip()
        end_raw = str(raw.get("end", "")).strip()
        if not start_raw or not end_raw:
            raise ValueError("Для blackout укажите начало и конец")
        try:
            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)
        except ValueError as error:
            raise ValueError("Некорректный blackout-период") from error
        start = start.replace(tzinfo=zone) if start.tzinfo is None else start.astimezone(zone)
        end = end.replace(tzinfo=zone) if end.tzinfo is None else end.astimezone(zone)
        if not _is_quarter_hour(start) or not _is_quarter_hour(end):
            raise ValueError("blackout-период должен быть кратен 15 минутам")
        if end <= start:
            raise ValueError("Конец blackout-периода должен быть позже начала")
        result.append((start, end, " ".join(str(raw.get("label", "")).split())))
    return sorted(result, key=lambda value: value[0])


def _blackout_end_for_slot(slot: datetime, rule: dict[str, Any], zone: ZoneInfo) -> datetime | None:
    local = slot.astimezone(zone)
    for start, end, _label in _blackout_ranges(rule, zone):
        if start <= local < end:
            return end
    return None


def normalize_channel_publication_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one persisted channel rule at the write boundary."""

    source = dict(rule or {})
    channel_id = str(source.get("channelId", "")).strip()
    if not channel_id:
        raise ValueError("Правило публикации требует channelId")
    try:
        quota = int(source.get("quota", 0) or 0)
        interval = int(source.get("intervalMinutes", 180) or 180)
        daily_cap = int(source.get("dailyCap", 0) or 0)
        minimum = float(source.get("minDurationSeconds", 0) or 0)
        maximum = float(source.get("maxDurationSeconds", 0) or 0)
        order_start = int(source.get("orderStart", 0) or 0)
        order_end = int(source.get("orderEnd", 0) or 0)
        channel_priority = int(source.get("channelPriority", 0) or 0)
        max_per_hour = int(source.get("maxVideosPerHour", 0) or 0)
        topic_cooldown = int(source.get("topicCooldownMinutes", 0) or 0)
    except (TypeError, ValueError) as error:
        raise ValueError("Квоты, интервалы и диапазоны должны быть числами") from error
    if (quota < 0 or daily_cap < 0 or minimum < 0 or maximum < 0 or order_start < 0 or order_end < 0
            or max_per_hour < 0 or topic_cooldown < 0):
        raise ValueError("Квоты и диапазоны не могут быть отрицательными")
    if maximum and maximum < minimum:
        raise ValueError("Некорректный диапазон длительности канала")
    if order_start and order_end and order_end < order_start:
        raise ValueError("Некорректный диапазон номеров роликов")
    if interval < 15 or interval % 15 != 0:
        raise ValueError("Интервал публикации должен быть кратен 15 минутам")

    timezone_name = str(source.get("timezone", "")).strip() or "UTC"
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Неизвестный timezone канала") from error

    first_publish = str(source.get("firstPublishAt", "")).strip()
    if first_publish:
        try:
            first_point = datetime.fromisoformat(first_publish)
        except ValueError as error:
            raise ValueError("Некорректное время первого выхода") from error
        if not _is_quarter_hour(first_point):
            raise ValueError("Первый выход должен быть кратен 15 минутам")

    window_start = _clock(source.get("publishWindowStart"))
    window_end = _clock(source.get("publishWindowEnd"))
    _validate_quarter_hour_clock(window_start, "Начало окна публикации")
    _validate_quarter_hour_clock(window_end, "Конец окна публикации")

    strategy = str(source.get("distributionStrategy", "balanced")).strip()
    if strategy not in {"balanced", "longest_monetized", "ordered", "manual"}:
        raise ValueError("Неизвестная стратегия распределения")
    privacy = str(source.get("privacy", "private")).strip()
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Некорректный privacy режим")
    publish_mode = str(source.get("publishMode", "publish_now")).strip()
    if publish_mode not in {"schedule", "publish_now"}:
        raise ValueError("Некорректный режим публикации")

    allowed_weekdays = source.get("allowedWeekdays")
    if isinstance(allowed_weekdays, list):
        weekdays = sorted({int(day) for day in allowed_weekdays if 0 <= int(day) <= 6})
    else:
        weekdays = list(range(7))
    include_keywords = [
        " ".join(str(value).split()).casefold()
        for value in source.get("includeKeywords", [])
        if str(value).strip()
    ] if isinstance(source.get("includeKeywords"), list) else []
    exclude_keywords = [
        " ".join(str(value).split()).casefold()
        for value in source.get("excludeKeywords", [])
        if str(value).strip()
    ] if isinstance(source.get("excludeKeywords"), list) else []
    blackout_periods = [
        {"start": start.isoformat(), "end": end.isoformat(), **({"label": label} if label else {})}
        for start, end, label in _blackout_ranges(source, ZoneInfo(timezone_name))
    ]
    automation_source = dict(source.get("automation", {}) or {})
    automation = {
        "upload": True,
        "metadata": True,
        "thumbnail": bool(automation_source.get("thumbnail", True)),
        "ads": True,
        "post": bool(automation_source.get("post", True)),
        "cards": bool(automation_source.get("cards", True)),
        "endScreen": bool(automation_source.get("endScreen", True)),
    }
    return {
        **source,
        "channelId": channel_id,
        "enabled": bool(source.get("enabled", True)),
        "quota": quota,
        "monetized": bool(source.get("monetized", False)),
        "distributionStrategy": strategy,
        "privacy": privacy,
        "publishMode": publish_mode,
        "timezone": timezone_name,
        "firstPublishAt": first_publish,
        "intervalMinutes": interval,
        "allowedWeekdays": weekdays,
        "publishWindowStart": window_start.isoformat(timespec="minutes") if window_start else "",
        "publishWindowEnd": window_end.isoformat(timespec="minutes") if window_end else "",
        "dailyCap": daily_cap,
        "minDurationSeconds": minimum,
        "maxDurationSeconds": maximum,
        "orderStart": order_start,
        "orderEnd": order_end,
        "channelPriority": channel_priority,
        "includeKeywords": include_keywords,
        "excludeKeywords": exclude_keywords,
        "maxVideosPerHour": max_per_hour,
        "topicCooldownMinutes": topic_cooldown,
        "blackoutPeriods": blackout_periods,
        "automation": automation,
    }


def _next_allowed_slot(candidate: datetime, rule: dict[str, Any], zone: ZoneInfo) -> datetime:
    allowed = rule.get("allowedWeekdays")
    weekdays = {int(value) for value in allowed} if isinstance(allowed, list) and allowed else set(range(7))
    start, end = _clock(rule.get("publishWindowStart")), _clock(rule.get("publishWindowEnd"))
    current = candidate.astimezone(zone)
    while True:
        if current.weekday() not in weekdays:
            current = datetime.combine((current + timedelta(days=1)).date(), start or time.min, tzinfo=zone)
            continue
        if start and current.timetz().replace(tzinfo=None) < start:
            current = datetime.combine(current.date(), start, tzinfo=zone)
            continue
        current_time = current.timetz().replace(tzinfo=None)
        within_window = not start or not end or (start <= end and start <= current_time <= end) or (start > end and (current_time >= start or current_time <= end))
        if not within_window:
            next_day = current.date() if start and current_time < start else (current + timedelta(days=1)).date()
            current = datetime.combine(next_day, start or time.min, tzinfo=zone)
            continue
        blackout_end = _blackout_end_for_slot(current, rule, zone)
        if blackout_end is not None:
            current = blackout_end
            continue
        return current


def build_channel_schedule(
    production_item_ids: list[str],
    rule: dict[str, Any],
    manual_slots: dict[str, str] | None = None,
    item_topics: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Build one independent channel schedule on the canonical 15-minute grid."""
    zone_name = str(rule.get("timezone", "")).strip() or "UTC"
    zone = ZoneInfo(zone_name)
    first = str(rule.get("firstPublishAt", "")).strip()
    if not first:
        raise ValueError("Укажите первый выход канала")
    try:
        candidate = datetime.fromisoformat(first)
    except ValueError as error:
        raise ValueError("Некорректное время первого выхода") from error
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=zone)
    else:
        candidate = candidate.astimezone(zone)
    if not _is_quarter_hour(candidate):
        raise ValueError("Первый выход должен быть кратен 15 минутам (:00/:15/:30/:45).")

    interval = int(rule.get("intervalMinutes", 0) or 0)
    if interval < 15 or interval % 15 != 0:
        raise ValueError("Интервал между роликами должен быть положительным и кратным 15 минутам.")

    _validate_quarter_hour_clock(_clock(rule.get("publishWindowStart")), "Начало окна публикации")
    _validate_quarter_hour_clock(_clock(rule.get("publishWindowEnd")), "Конец окна публикации")

    result: list[dict[str, str]] = []
    overrides = dict(manual_slots or {})
    daily_cap = max(0, int(rule.get("dailyCap", 0) or 0))
    max_per_hour = max(0, int(rule.get("maxVideosPerHour", 0) or 0))
    topic_cooldown = max(0, int(rule.get("topicCooldownMinutes", 0) or 0))
    topics = {str(key): str(value).strip().casefold() for key, value in dict(item_topics or {}).items()}
    daily_counts: dict[str, int] = {}
    scheduled_points: list[datetime] = []
    last_topic_slot: dict[str, datetime] = {}
    for production_item_id in production_item_ids:
        manual = str(overrides.get(production_item_id, "")).strip()
        if manual:
            slot = datetime.fromisoformat(manual)
            if slot.tzinfo is None:
                slot = slot.replace(tzinfo=zone)
            else:
                slot = slot.astimezone(zone)
            if not _is_quarter_hour(slot):
                raise ValueError("Ручное время должно быть кратно 15 минутам (:00/:15/:30/:45).")
            source = "manual"
        else:
            slot = _next_allowed_slot(candidate, rule, zone)
            while True:
                if daily_cap and daily_counts.get(slot.date().isoformat(), 0) >= daily_cap:
                    candidate = datetime.combine(
                        (slot + timedelta(days=1)).date(),
                        _clock(rule.get("publishWindowStart")) or time.min,
                        tzinfo=zone,
                    )
                    slot = _next_allowed_slot(candidate, rule, zone)
                    continue

                if max_per_hour:
                    recent = [point for point in scheduled_points if timedelta(0) <= slot - point < timedelta(hours=1)]
                    if len(recent) >= max_per_hour:
                        candidate = min(recent) + timedelta(hours=1)
                        slot = _next_allowed_slot(candidate, rule, zone)
                        continue

                topic = topics.get(str(production_item_id), "")
                previous_topic_slot = last_topic_slot.get(topic) if topic else None
                if topic and topic_cooldown and previous_topic_slot:
                    earliest = previous_topic_slot + timedelta(minutes=topic_cooldown)
                    if slot < earliest:
                        candidate = earliest
                        # Keep the canonical 15-minute grid when a cooldown is
                        # not itself a multiple of 15.
                        remainder = candidate.minute % 15
                        if remainder or candidate.second or candidate.microsecond:
                            candidate = candidate.replace(second=0, microsecond=0) + timedelta(minutes=(15 - remainder) % 15)
                        slot = _next_allowed_slot(candidate, rule, zone)
                        continue
                break
            if not _is_quarter_hour(slot):
                raise ValueError("Расчётное время вышло за 15-минутную сетку.")
            source = "auto"
        result.append({
            "productionItemId": str(production_item_id),
            "publishAt": slot.isoformat(),
            "source": source,
            "timezone": zone.key,
        })
        daily_key = slot.date().isoformat()
        daily_counts[daily_key] = daily_counts.get(daily_key, 0) + 1
        scheduled_points.append(slot)
        topic = topics.get(str(production_item_id), "")
        if topic:
            last_topic_slot[topic] = slot
        candidate = slot + timedelta(minutes=interval)
    return result


def _adaptive_bulk_slots(
    production_item_ids: list[str],
    *,
    start: datetime,
    end: datetime,
    channel_id: str,
    occupied: set[datetime],
    can_use: Any = None,
    on_choose: Any = None,
) -> dict[str, datetime | None]:
    """Spread one channel across a selected day window without synchronising channels.

    The offsets are deterministic: rebuilding the same preview must not move
    the operator's plan, but the schedule should not look like a metronome.
    """
    slots: list[datetime] = []
    current = start
    while current <= end:
        slots.append(current)
        current += timedelta(minutes=15)
    if not slots:
        return {production_item_id: None for production_item_id in production_item_ids}

    result: dict[str, datetime | None] = {}
    count = len(production_item_ids)
    for position, production_item_id in enumerate(production_item_ids):
        if count == 1:
            ideal = (len(slots) - 1) // 2
        else:
            ideal = round(position * (len(slots) - 1) / (count - 1))
        # Keep the variation modest enough that the per-channel plan remains
        # visibly spread.  One grid point is enough to avoid a metronome
        # without turning a five-item day plan into visible bursts.
        neighbour_span = min(1, max(0, (len(slots) - 1) // max(1, count - 1) // 3))
        seed = int(sha256(f"{channel_id}|{production_item_id}|{start.isoformat()}".encode()).hexdigest()[:8], 16)
        jitter = (seed % (neighbour_span * 2 + 1)) - neighbour_span if neighbour_span else 0
        target = min(len(slots) - 1, max(0, ideal + jitter))
        candidates = sorted(
            range(len(slots)),
            key=lambda index: (
                abs(index - target),
                abs(index - ideal),
                (seed + index * 17) % 97,
            ),
        )
        chosen = next((
            slots[index]
            for index in candidates
            if slots[index].astimezone(timezone.utc) not in occupied
            and (can_use is None or bool(can_use(slots[index], production_item_id)))
        ), None)
        if chosen is None:
            result[production_item_id] = None
            continue
        occupied.add(chosen.astimezone(timezone.utc))
        if on_choose is not None:
            on_choose(chosen, production_item_id)
        result[production_item_id] = chosen
    return result


def _apply_adaptive_bulk_schedule_range(
    assignments: list[dict],
    schedule: dict[str, Any],
    channel_rules: dict[str, dict],
    item_topics: dict[str, str] | None = None,
) -> list[dict]:
    """Apply a date-only adaptive schedule on a shared 15-minute grid.

    Every channel receives its own evenly-spaced sequence, with a stable
    jitter and no duplicate instant across channels.  Locked rows are never
    moved and reserve their existing instant when it belongs to the preview.
    """
    date_value = str(schedule.get("date", "")).strip()
    start_value = str(schedule.get("startTime", "")).strip()
    end_value = str(schedule.get("endTime", "")).strip()
    fallback_zone_name = str(schedule.get("timezone", "")).strip() or "UTC"
    if not date_value or not start_value or not end_value:
        raise ValueError("Укажите дату, начало и конец массового диапазона.")

    result = [dict(row) for row in assignments]
    topics = {
        str(production_item_id): str(topic or "").strip().casefold()
        for production_item_id, topic in dict(item_topics or {}).items()
    }
    occupied: set[datetime] = set()
    channel_slots: dict[str, list[tuple[datetime, str]]] = {}
    for row in result:
        raw = str(row.get("publishAt", "")).strip()
        if not raw or not bool(row.get("locked", False)):
            continue
        try:
            instant = datetime.fromisoformat(raw)
        except ValueError:
            continue
        channel_id = str(row.get("channelId", "")).strip()
        rule = dict(channel_rules.get(channel_id, {}) or {})
        zone_name = str(rule.get("timezone", "")).strip() or fallback_zone_name
        try:
            zone = ZoneInfo(zone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Некорректный часовой пояс канала {channel_id or 'публикации'}.") from error
        local_instant = instant.replace(tzinfo=zone) if instant.tzinfo is None else instant.astimezone(zone)
        occupied.add(local_instant.astimezone(timezone.utc))
        if channel_id:
            channel_slots.setdefault(channel_id, []).append((local_instant, str(row.get("productionItemId", "")).strip()))

    positions_by_channel: dict[str, list[int]] = {}
    for index, row in enumerate(result):
        channel_id = str(row.get("channelId", "")).strip()
        if channel_id and not bool(row.get("locked", False)):
            positions_by_channel.setdefault(channel_id, []).append(index)

    def schedule_positions(window_positions: list[int], start_value: str, end_value: str) -> None:
        positions_by_window_channel: dict[str, list[int]] = {}
        for position in window_positions:
            channel_id = str(result[position].get("channelId", "")).strip()
            if channel_id:
                positions_by_window_channel.setdefault(channel_id, []).append(position)
        for channel_id in sorted(positions_by_window_channel):
            positions = positions_by_window_channel[channel_id]
            rule = dict(channel_rules.get(channel_id, {}) or {})
            zone_name = str(rule.get("timezone", "")).strip() or fallback_zone_name
            try:
                zone = ZoneInfo(zone_name)
                start = datetime.fromisoformat(f"{date_value}T{start_value}").replace(tzinfo=zone)
                end = datetime.fromisoformat(f"{date_value}T{end_value}").replace(tzinfo=zone)
            except Exception as error:
                raise ValueError("Укажите корректные дату, начало, конец и часовой пояс диапазона.") from error
            if end < start:
                raise ValueError("Конец диапазона должен быть не раньше начала.")
            if not _is_quarter_hour(start) or not _is_quarter_hour(end):
                raise ValueError("Начало и конец массового диапазона должны быть кратны 15 минутам.")

            minimum_interval_minutes = max(
                180,
                max(15, int(rule.get("intervalMinutes", 180) or 180)),
            )

            def can_use(
                candidate: datetime,
                production_item_id: str,
                rule_for_channel: dict = rule,
                channel_zone: ZoneInfo = zone,
                channel_key: str = channel_id,
                *,
                enforce_interval: bool = True,
            ) -> bool:
                allowed = rule_for_channel.get("allowedWeekdays")
                weekdays = {int(value) for value in allowed} if isinstance(allowed, list) and allowed else set(range(7))
                if candidate.weekday() not in weekdays:
                    return False
                rule_start, rule_end = _clock(rule_for_channel.get("publishWindowStart")), _clock(rule_for_channel.get("publishWindowEnd"))
                candidate_time = candidate.timetz().replace(tzinfo=None)
                within_channel_window = (
                    not rule_start or not rule_end
                    or (rule_start <= rule_end and rule_start <= candidate_time <= rule_end)
                    or (rule_start > rule_end and (candidate_time >= rule_start or candidate_time <= rule_end))
                )
                if not within_channel_window:
                    return False
                try:
                    if _blackout_end_for_slot(candidate, rule_for_channel, channel_zone) is not None:
                        return False
                except ValueError:
                    return False
                existing = channel_slots.get(channel_key, [])
                if enforce_interval and any(
                    abs(candidate - point) < timedelta(minutes=minimum_interval_minutes)
                    for point, _value in existing
                ):
                    return False
                daily_cap = max(0, int(rule_for_channel.get("dailyCap", 0) or 0))
                if daily_cap and sum(point.date() == candidate.date() for point, _value in existing) >= daily_cap:
                    return False
                max_per_hour = max(0, int(rule_for_channel.get("maxVideosPerHour", 0) or 0))
                if max_per_hour and sum(abs(candidate - point) < timedelta(hours=1) for point, _value in existing) >= max_per_hour:
                    return False
                topic_cooldown = max(0, int(rule_for_channel.get("topicCooldownMinutes", 0) or 0))
                topic = topics.get(production_item_id, "")
                return not (
                    topic and topic_cooldown and any(
                        topics.get(existing_id, "") == topic and abs(candidate - point) < timedelta(minutes=topic_cooldown)
                        for point, existing_id in existing
                    )
                )

            def remember(candidate: datetime, production_item_id: str, channel_key: str = channel_id) -> None:
                channel_slots.setdefault(channel_key, []).append((candidate, production_item_id))

            production_item_ids = [str(result[position]["productionItemId"]) for position in positions]
            slots_by_id = _adaptive_bulk_slots(
                production_item_ids,
                start=start,
                end=end,
                channel_id=channel_id,
                occupied=occupied,
                can_use=can_use,
                on_choose=remember,
            )
            for position in positions:
                row = result[position]
                slot = slots_by_id[str(row["productionItemId"])]
                if slot is None:
                    candidate = start
                    rule_compatible_without_interval = False
                    while candidate <= end:
                        if (
                            candidate.astimezone(timezone.utc) not in occupied
                            and can_use(candidate, str(row["productionItemId"]), enforce_interval=False)
                        ):
                            rule_compatible_without_interval = True
                            break
                        candidate += timedelta(minutes=15)
                    if rule_compatible_without_interval:
                        row["scheduleWarning"] = (
                            f"Не удаётся выдержать минимальный интервал {minimum_interval_minutes} минут "
                            "между роликами этого канала."
                        )
                        row["scheduleSuggestion"] = (
                            "Расширьте временное окно, уменьшите квоту канала или перенесите часть роликов "
                            "на другой канал."
                        )
                    else:
                        row["scheduleWarning"] = (
                            "В выбранном окне нет свободного времени, совместимого с правилами канала."
                        )
                        row["scheduleSuggestion"] = (
                            "Проверьте окно публикации, blackout, дневную квоту и ограничения канала."
                        )
                    row.pop("publishAt", None)
                    continue
                row.pop("scheduleWarning", None)
                row.pop("scheduleSuggestion", None)
                row.update({
                    "publishAt": slot.isoformat(),
                    "timezone": zone.key,
                    "source": "bulk_range_adaptive",
                })

    raw_windows = schedule.get("timeWindows")
    if isinstance(raw_windows, list):
        windows: list[tuple[str, str, int]] = []
        for raw_window in raw_windows:
            if not isinstance(raw_window, dict) or not bool(raw_window.get("enabled", False)):
                continue
            try:
                quota = max(0, int(raw_window.get("quota", 0) or 0))
            except (TypeError, ValueError) as error:
                raise ValueError("Квота окна публикации должна быть числом.") from error
            start_value = str(raw_window.get("startTime", "")).strip()
            end_value = str(raw_window.get("endTime", "")).strip()
            if start_value and end_value:
                windows.append((start_value, end_value, quota))

        # Interleave channels before applying a window quota so one channel
        # cannot consume an entire preferred period merely because its rows
        # happened to arrive first in the production registry.
        channel_queues = {channel_id: list(positions) for channel_id, positions in sorted(positions_by_channel.items())}
        ordered_positions: list[int] = []
        while any(channel_queues.values()):
            for channel_id in sorted(channel_queues):
                if channel_queues[channel_id]:
                    ordered_positions.append(channel_queues[channel_id].pop(0))

        explicit_quota = sum(quota for _start, _end, quota in windows if quota > 0)
        automatic_indexes = [index for index, (_start, _end, quota) in enumerate(windows) if quota == 0]
        remaining_for_automatic = max(0, len(ordered_positions) - explicit_quota)
        automatic_base, automatic_extra = divmod(remaining_for_automatic, len(automatic_indexes) or 1)

        cursor = 0
        for index, (start_value, end_value, quota) in enumerate(windows):
            effective_quota = quota
            if quota == 0:
                automatic_position = automatic_indexes.index(index)
                effective_quota = automatic_base + (1 if automatic_position < automatic_extra else 0)
            window_positions = ordered_positions[cursor:cursor + effective_quota]
            cursor += len(window_positions)
            if not window_positions:
                continue
            # Adjacent preference windows share a textual boundary (12:00,
            # 17:00). Reserve it for the following window to keep one global
            # no-collision grid.
            effective_end = end_value
            if index + 1 < len(windows) and end_value == windows[index + 1][0]:
                end_point = datetime.fromisoformat(f"{date_value}T{end_value}") - timedelta(minutes=15)
                effective_end = end_point.time().isoformat(timespec="minutes")
            schedule_positions(window_positions, start_value, effective_end)

        for position in ordered_positions[cursor:]:
            result[position]["scheduleWarning"] = "В выбранных окнах не хватает квоты для ролика."
            result[position]["scheduleSuggestion"] = "Увеличьте квоту окна, включите другое окно или уменьшите квоту канала."
            result[position].pop("publishAt", None)
        return result

    schedule_positions(
        [position for positions in positions_by_channel.values() for position in positions],
        start_value,
        end_value,
    )
    return result


def apply_bulk_schedule_range(
    assignments: list[dict],
    schedule: dict[str, Any],
    channel_rules: dict[str, dict] | None = None,
    item_topics: dict[str, str] | None = None,
) -> list[dict]:
    """Apply one bulk window independently inside every selected channel.

    The window limits each channel; it never flattens all channels into one
    shared global sequence. Channel interval/timezone/window/day rules remain
    authoritative, while explicit locked/manual slots are preserved.
    """
    if str(schedule.get("spacingStrategy", "")).strip() == "adaptive_jittered":
        return _apply_adaptive_bulk_schedule_range(
            assignments,
            schedule,
            dict(channel_rules or {}),
            dict(item_topics or {}),
        )
    date_value = str(schedule.get("date", "")).strip()
    start_value = str(schedule.get("startTime", "")).strip()
    end_value = str(schedule.get("endTime", "")).strip()
    fallback_zone_name = str(schedule.get("timezone", "")).strip() or "UTC"
    if not date_value or not start_value or not end_value:
        raise ValueError("Укажите дату, начало и конец массового диапазона.")

    result = [dict(row) for row in assignments]
    rules = dict(channel_rules or {})
    positions_by_channel: dict[str, list[int]] = {}
    for index, row in enumerate(result):
        channel_id = str(row.get("channelId", "")).strip()
        if channel_id and not bool(row.get("locked", False)):
            positions_by_channel.setdefault(channel_id, []).append(index)

    for channel_id, positions in positions_by_channel.items():
        rule = dict(rules.get(channel_id, {}) or {})
        zone_name = str(rule.get("timezone", "")).strip() or fallback_zone_name
        try:
            zone = ZoneInfo(zone_name)
            start = datetime.fromisoformat(f"{date_value}T{start_value}").replace(tzinfo=zone)
            end = datetime.fromisoformat(f"{date_value}T{end_value}").replace(tzinfo=zone)
        except Exception as error:
            raise ValueError("Укажите корректные дату, начало, конец и часовой пояс диапазона.") from error
        if end < start:
            raise ValueError("Конец диапазона должен быть не раньше начала.")
        if not _is_quarter_hour(start) or not _is_quarter_hour(end):
            raise ValueError("Начало и конец массового диапазона должны быть кратны 15 минутам.")

        interval = int(rule.get("intervalMinutes", 15) or 15)
        if interval < 15 or interval % 15 != 0:
            raise ValueError(f"Интервал канала {channel_id} должен быть кратен 15 минутам.")

        bounded_rule = {
            **rule,
            "channelId": channel_id,
            "timezone": zone.key,
            "firstPublishAt": start.isoformat(),
            "intervalMinutes": interval,
        }
        channel_item_ids = [str(result[position]["productionItemId"]) for position in positions]
        topics = dict(item_topics or {})
        slots = build_channel_schedule(
            channel_item_ids,
            bounded_rule,
            item_topics={production_id: str(topics.get(production_id, "")) for production_id in channel_item_ids},
        )
        slots_by_id = {slot["productionItemId"]: slot for slot in slots}
        for position in positions:
            row = result[position]
            slot = slots_by_id[str(row["productionItemId"])]
            slot_time = datetime.fromisoformat(slot["publishAt"]).astimezone(zone)
            if slot_time > end:
                row["scheduleWarning"] = "Ролик не помещается в выбранный диапазон этого канала."
                row.pop("publishAt", None)
                continue
            row.update({
                "publishAt": slot["publishAt"],
                "timezone": zone.key,
                "source": "bulk_range",
            })
    return result

def validate_publication_schedule(
    assignments: list[dict],
    channel_rules: dict[str, dict],
    item_topics: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Return schedule conflicts without mutating explicit operator choices."""
    conflicts: list[dict[str, str]] = []
    seen_slots: dict[tuple[str, str], str] = {}
    daily_counts: dict[tuple[str, str], int] = {}
    valid_slots_by_channel: dict[str, list[tuple[datetime, str]]] = {}
    topics = {
        str(production_id): str(topic or "").strip().casefold()
        for production_id, topic in dict(item_topics or {}).items()
    }

    for assignment in assignments:
        production_id = str(assignment.get("productionItemId", "")).strip()
        channel_id = str(assignment.get("channelId", "")).strip()
        raw_slot = str(assignment.get("publishAt", "")).strip()
        if not production_id or not channel_id or not raw_slot:
            continue
        rule = dict(channel_rules.get(channel_id, {}) or {})
        try:
            zone = ZoneInfo(str(rule.get("timezone", "") or "UTC"))
            slot = datetime.fromisoformat(raw_slot)
        except (ValueError, ZoneInfoNotFoundError):
            conflicts.append({"kind": "invalid_timezone_or_time", "productionItemId": production_id, "channelId": channel_id})
            continue
        local_slot = slot.replace(tzinfo=zone) if slot.tzinfo is None else slot.astimezone(zone)
        valid_slots_by_channel.setdefault(channel_id, []).append((local_slot, production_id))
        if not _is_quarter_hour(local_slot):
            conflicts.append({"kind": "quarter_hour_required", "productionItemId": production_id, "channelId": channel_id})
        slot_key = (channel_id, local_slot.isoformat())
        if slot_key in seen_slots:
            conflicts.append({"kind": "duplicate_slot", "productionItemId": production_id, "channelId": channel_id})
        else:
            seen_slots[slot_key] = production_id
        allowed = rule.get("allowedWeekdays")
        weekdays = {int(value) for value in allowed} if isinstance(allowed, list) and allowed else set(range(7))
        if local_slot.weekday() not in weekdays:
            conflicts.append({"kind": "disabled_weekday", "productionItemId": production_id, "channelId": channel_id})
        start, end = _clock(rule.get("publishWindowStart")), _clock(rule.get("publishWindowEnd"))
        local_time = local_slot.timetz().replace(tzinfo=None)
        within_window = not start or not end or (start <= end and start <= local_time <= end) or (start > end and (local_time >= start or local_time <= end))
        if not within_window:
            conflicts.append({"kind": "outside_window", "productionItemId": production_id, "channelId": channel_id})
        try:
            blackout_end = _blackout_end_for_slot(local_slot, rule, zone)
        except ValueError:
            conflicts.append({"kind": "invalid_blackout_period", "productionItemId": production_id, "channelId": channel_id})
            blackout_end = None
        if blackout_end is not None:
            conflicts.append({"kind": "blackout_period", "productionItemId": production_id, "channelId": channel_id})
        daily_key = (channel_id, local_slot.date().isoformat())
        daily_counts[daily_key] = daily_counts.get(daily_key, 0) + 1
        daily_cap = max(0, int(rule.get("dailyCap", 0) or 0))
        if daily_cap and daily_counts[daily_key] > daily_cap:
            conflicts.append({"kind": "daily_cap_exceeded", "productionItemId": production_id, "channelId": channel_id})

    # These constraints are rolling/order-dependent, so validate them after
    # sorting by the channel-local timestamp. Manual row order in the UI must
    # not change whether a conflict is detected.
    for channel_id, slot_rows in valid_slots_by_channel.items():
        rule = dict(channel_rules.get(channel_id, {}) or {})
        ordered = sorted(slot_rows, key=lambda pair: (pair[0], pair[1]))
        max_per_hour = max(0, int(rule.get("maxVideosPerHour", 0) or 0))
        topic_cooldown = max(0, int(rule.get("topicCooldownMinutes", 0) or 0))
        previous_points: list[datetime] = []
        last_topic_slot: dict[str, datetime] = {}

        for slot, production_id in ordered:
            if max_per_hour:
                previous_points = [
                    point for point in previous_points
                    if timedelta(0) <= slot - point < timedelta(hours=1)
                ]
                if len(previous_points) >= max_per_hour:
                    conflicts.append({
                        "kind": "max_videos_per_hour",
                        "productionItemId": production_id,
                        "channelId": channel_id,
                    })
            previous_points.append(slot)

            topic = topics.get(production_id, "")
            previous_topic = last_topic_slot.get(topic) if topic else None
            if topic and topic_cooldown and previous_topic is not None:
                if slot - previous_topic < timedelta(minutes=topic_cooldown):
                    conflicts.append({
                        "kind": "topic_cooldown",
                        "productionItemId": production_id,
                        "channelId": channel_id,
                    })
            if topic:
                last_topic_slot[topic] = slot

    return conflicts


def validate_publication_snapshot(settings: Any, snapshot_id: str) -> dict[str, Any]:
    """Preflight one frozen snapshot without modifying its source data."""
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    snapshot = dict(snapshots.get(snapshot_id, {}) or {})
    if not snapshot:
        raise ValueError("Publication snapshot не найден")
    execution = dict(executions.get(snapshot_id, {}) or {})
    reasons: list[dict[str, str]] = []
    video_path = str(snapshot.get("videoPath", "")).strip()
    current_video_fingerprint = _file_fingerprint(video_path)
    if not video_path or current_video_fingerprint is None:
        reasons.append({"kind": "VIDEO_MISSING", "message": "MP4 из snapshot не найден. Связь с роликом сохранена для восстановления."})
    elif not frozen_artifact_matches(snapshot, "video", video_path):
        reasons.append({
            "kind": "VIDEO_STALE",
            "message": "MP4 изменился после подтверждения snapshot. Переподтвердите назначение перед загрузкой.",
        })
    metadata = dict(snapshot.get("metadata", {}) or {})
    upload_title = resolve_publication_upload_title(metadata)
    if not upload_title or len(upload_title) > 100:
        reasons.append({"kind": "TITLE_INVALID", "message": "Заголовок YouTube должен содержать от 1 до 100 символов."})
    channel_id = str(snapshot.get("channelId", "")).strip()
    tokens = dict(getattr(settings, "youtube_oauth_tokens", {}) or {})
    if not channel_id or not _oauth_payload_is_structurally_valid(tokens.get(channel_id, "")):
        reasons.append({"kind": "AUTH_REQUIRED", "message": "OAuth канала отсутствует или повреждён. Выполните повторный вход."})
    return {
        "ok": not reasons,
        "snapshotId": snapshot_id,
        "reasons": reasons,
        "uploadAlreadyExists": bool(str(execution.get("youtubeVideoId") or "").strip()),
        "videoPath": video_path,
    }


def _normalize_publish_at(value: object, rule: dict[str, Any]) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    zone_name = str(rule.get("timezone", "") or "").strip()
    try:
        point = datetime.fromisoformat(raw)
        zone = ZoneInfo(zone_name or "UTC")
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("Некорректное время публикации или timezone канала") from error
    if point.tzinfo is None:
        point = point.replace(tzinfo=zone)
    elif zone_name:
        point = point.astimezone(zone)
    # When the rule has no explicit timezone, preserve the operator-provided
    # offset instead of silently rewriting the immutable audit snapshot to UTC.
    if not _is_quarter_hour(point):
        raise ValueError("Время публикации должно быть кратно 15 минутам")
    return point.isoformat()


def _refresh_execution_overall_status(settings: Any, snapshot_id: str, execution: dict[str, Any]) -> None:
    """Derive the row status from all persisted stages without hiding failures."""

    steps = dict(execution.get("steps", {}) or {})
    statuses = {
        stage: str(dict(steps.get(stage, {}) or {}).get("status", "PENDING")).upper()
        for stage in _STAGES
    }
    failures = {"FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"}
    terminal = {"SUCCESS", "SKIPPED", "NOT_REQUIRED"}
    if any(status in failures for status in statuses.values()):
        execution["overallStatus"] = "PARTIAL" if str(execution.get("youtubeVideoId") or "").strip() else next(
            status for status in statuses.values() if status in failures
        )
        return
    if statuses.get("VIDEO_UPLOAD") == "RUNNING":
        execution["overallStatus"] = "UPLOADING"
        return
    if statuses.get("YOUTUBE_PROCESSING") == "RUNNING":
        execution["overallStatus"] = "PROCESSING"
        return
    if all(status in terminal for status in statuses.values()):
        snapshot = dict((getattr(settings, "youtube_publication_snapshots", {}) or {}).get(snapshot_id, {}) or {})
        execution["currentStage"] = "DONE"
        execution["completedAt"] = execution.get("completedAt") or _now()
        execution["overallStatus"] = (
            "SCHEDULED"
            if str(snapshot.get("publishMode", "")) == "schedule" and str(snapshot.get("requestedPublishAt") or "").strip()
            else "DONE"
        )
        return
    execution["overallStatus"] = "FORMATTING" if str(execution.get("youtubeVideoId") or "").strip() else "WAITING"


def confirm_publication_snapshots(settings: Any, assignments: list[dict], channel_rules: dict[str, dict]) -> list[str]:
    """Freeze explicit valid assignments once; repeat confirmation is idempotent."""
    items = dict(getattr(settings, "youtube_publication_items", {}) or {})
    item_topics = {
        str(production_id): str(
            dict(item.get("metadata", {}) or {}).get("topicFamily")
            or dict(item.get("metadata", {}) or {}).get("topic")
            or ""
        ).strip()
        for production_id, item in items.items()
    }
    conflicts = validate_publication_schedule(assignments, channel_rules, item_topics=item_topics)
    if conflicts:
        kinds = ", ".join(sorted({str(conflict["kind"]) for conflict in conflicts}))
        raise ValueError(f"Расписание содержит конфликты: {kinds}")
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    created: list[str] = []
    existing_by_item: dict[str, str] = {}
    for existing_snapshot_id, existing_snapshot in snapshots.items():
        production_id = str(dict(existing_snapshot or {}).get("productionItemId", "")).strip()
        if not production_id:
            continue
        existing_execution = dict(executions.get(existing_snapshot_id, {}) or {})
        status = str(existing_execution.get("overallStatus", "")).upper()
        has_video = bool(str(existing_execution.get("youtubeVideoId") or "").strip())
        # A pre-upload cancellation explicitly releases the item for a new
        # confirmation. Once YouTube identity exists, even cancelled
        # downstream automation must continue to protect the frozen snapshot.
        if status == "CANCELLED" and not has_video:
            continue
        existing_by_item[production_id] = existing_snapshot_id
    for assignment in assignments:
        production_id = str(assignment.get("productionItemId", "")).strip()
        channel_id = str(assignment.get("channelId", "")).strip()
        item = items.get(production_id)
        if not production_id or not channel_id or not item:
            raise ValueError("Подтверждение требует существующий ролик и канал")
        readiness = dict(item.get("readiness", {}) or {})
        content_ready = (
            bool(readiness.get("contentReady"))
            if "contentReady" in readiness
            else str(readiness.get("state", "")) == "VIDEO_READY"
        )
        if not content_ready:
            raise ValueError(f"Ролик {production_id} не готов к публикации")
        snapshot_id = existing_by_item.get(production_id)
        if snapshot_id:
            created.append(snapshot_id)
            continue
        rule = dict(channel_rules.get(channel_id, {}) or {})
        publish_at = _normalize_publish_at(assignment.get("publishAt"), rule)
        mode = str(rule.get("publishMode", "")).strip() or ("schedule" if publish_at else "publish_now")
        if mode == "schedule" and not publish_at:
            raise ValueError(f"Для scheduled публикации {production_id} требуется время")
        privacy = str(rule.get("privacy", "private")).strip()
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Некорректный privacy режим")
        if mode == "schedule" and privacy != "private":
            raise ValueError("Для публикации по расписанию YouTube требует initial privacy private")
        base_snapshot_id = f"snapshot:{production_id}:{channel_id}"
        snapshot_id = base_snapshot_id
        revision = 2
        while snapshot_id in snapshots:
            snapshot_id = f"{base_snapshot_id}:r{revision}"
            revision += 1
        artifact = dict(item.get("artifacts", {}).get("video", {}) or {})
        thumbnail = dict(item.get("artifacts", {}).get("thumbnail", {}) or {})
        metadata = dict(item.get("metadata", {}) or {})
        automation = dict(rule.get("automation", {}) or {})
        frozen_automation = {
            "upload": bool(automation.get("upload", True)),
            "metadata": bool(automation.get("metadata", True)),
            "thumbnail": bool(automation.get("thumbnail", True)),
            "ads": bool(automation.get("ads", True)),
            "post": bool(automation.get("post", True)),
            "cards": bool(automation.get("cards", True)),
            "endScreen": bool(automation.get("endScreen", True)),
        }
        duration_seconds = _item_duration_seconds(item)
        monetized = bool(rule.get("monetized", False))
        artifact_fingerprints: dict[str, dict[str, int]] = {}
        video_fingerprint = _file_fingerprint(artifact.get("path", ""))
        if video_fingerprint is not None:
            artifact_fingerprints["video"] = video_fingerprint
        thumbnail_fingerprint = _file_fingerprint(thumbnail.get("path", ""))
        if thumbnail_fingerprint is not None:
            artifact_fingerprints["thumbnail"] = thumbnail_fingerprint
        snapshot = {
            "id": snapshot_id, "productionItemId": production_id, "channelId": channel_id,
            "videoPath": str(artifact.get("path", "")), "thumbnailPath": str(thumbnail.get("path", "")), "metadata": metadata,
            "artifactFingerprints": artifact_fingerprints,
            "durationSeconds": duration_seconds, "monetized": monetized,
            "adPolicy": {
                "enabled": monetized,
                "manualIntervalSeconds": 39,
                "automaticSlotsEnabled": True,
            },
            "communityPost": {
                "callToAction": str(getattr(settings, "seo_call_to_action", "") or "").strip(),
            },
            "automation": frozen_automation,
            "privacy": privacy, "publishMode": mode, "requestedPublishAt": publish_at,
            "idempotencyKey": sha256(f"{snapshot_id}|{channel_id}".encode()).hexdigest(), "createdAt": _now(),
        }
        snapshots[snapshot_id] = snapshot
        execution = _execution(snapshot_id, production_id, {"publishAt": publish_at or ""})
        execution["overallStatus"] = "SCHEDULED" if mode == "schedule" else "READY"
        execution["plannedPublishAt"] = publish_at
        if not frozen_automation["thumbnail"]:
            execution["steps"]["THUMBNAIL"] = {**_step("NOT_REQUIRED"), "providerResult": {"reason": "channel_policy"}}
        if not monetized:
            execution["steps"]["ADS"] = {
                **_step("NOT_REQUIRED"),
                "providerResult": {"mode": "NONE", "reason": "channel_not_monetized"},
            }
        if not frozen_automation["post"]:
            execution["steps"]["POST"] = {**_step("NOT_REQUIRED"), "providerResult": {"reason": "channel_policy"}}
        if not frozen_automation["cards"]:
            execution["steps"]["CARDS"] = {**_step("NOT_REQUIRED"), "providerResult": {"reason": "channel_policy"}}
        if not frozen_automation["endScreen"]:
            execution["steps"]["END_SCREEN"] = {**_step("NOT_REQUIRED"), "providerResult": {"reason": "channel_policy"}}
        if mode != "schedule":
            execution["steps"]["SCHEDULE"] = {**_step("NOT_REQUIRED"), "providerResult": {"reason": "publish_now"}}
        executions[snapshot_id] = execution
        created.append(snapshot_id)
    settings.youtube_publication_snapshots = snapshots
    settings.youtube_publication_executions = executions
    return created


def claim_execution(settings: Any, snapshot_id: str, worker_id: str) -> bool:
    """Atomically reserve one active execution in the in-memory settings model."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    active = execution.get("activeLease")
    if active and str(active.get("workerId", "")) != str(worker_id):
        return False
    execution["activeLease"] = {"workerId": str(worker_id), "claimedAt": _now()}
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions
    return True


def retry_publication_stage(settings: Any, snapshot_id: str, stage: str) -> None:
    """Retry only an unfinished/failed stage; completed upload remains immutable."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    normalized = str(stage).strip().upper()
    steps = dict(execution.get("steps", {}) or {})
    result = dict(steps.get(normalized, {}) or {})
    if not result:
        raise ValueError("Этап публикации не найден")
    if str(result.get("status", "")) in {"SUCCESS", "SKIPPED", "NOT_REQUIRED"}:
        raise ValueError("Готовый этап нельзя повторить без явного force")
    if normalized == "VIDEO_UPLOAD" and str(execution.get("youtubeVideoId") or "").strip():
        raise ValueError("MP4 уже загружен на YouTube; повторная загрузка запрещена")
    if normalized == "VIDEO_UPLOAD" and str(result.get("status", "")).upper() == "USER_ACTION_REQUIRED":
        raise ValueError("Прерванная загрузка требует безопасной сверки перед повтором; обычный retry запрещён")
    result.update({"status": "RETRYING", "error": None, "nextRetryAt": None})
    steps[normalized] = result
    execution["steps"] = steps
    execution["currentStage"] = normalized
    execution["overallStatus"] = "RETRYING"
    execution.setdefault("timeline", []).append({"at": _now(), "stage": normalized, "status": "RETRYING", "detail": "Повтор этапа"})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def queue_publication_reupload(
    settings: Any,
    snapshot_id: str,
    reason: str,
    *,
    metadata_confirmed: bool = False,
) -> None:
    """Queue one explicit private replacement upload and preserve the old identity."""
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    snapshot = dict(snapshots.get(snapshot_id, {}) or {})
    execution = dict(executions.get(snapshot_id, {}) or {})
    if not snapshot or not execution:
        raise ValueError("Publication snapshot или execution не найден")
    if not metadata_confirmed:
        raise ValueError("Перед перезаливом подтвердите актуальность frozen metadata.")
    if execution.get("activeLease"):
        raise ValueError("Нельзя перезалить ролик: текущая попытка ещё выполняется")

    current_reupload = dict(execution.get("reupload", {}) or {})
    if str(current_reupload.get("status", "")).upper() in {
        "QUEUED", "RUNNING", "RETRYABLE", "UPLOADED", "PROCESSING",
    }:
        raise ValueError("Этот ролик уже находится в активном перезаливе")

    old_video_id = str(execution.get("youtubeVideoId") or "").strip()
    old_video_url = str(execution.get("youtubeVideoUrl") or "").strip()
    if not old_video_id:
        raise ValueError("Перезалив доступен только после подтверждённого YouTube ID")
    clean_reason = " ".join(str(reason or "").split())
    if not clean_reason:
        raise ValueError("Укажите причину перезалива")

    now = _now()
    previous_reupload = dict(current_reupload)
    reupload_history = list(execution.get("reuploadHistory", []) or [])
    if previous_reupload:
        reupload_history.append(previous_reupload)

    steps = dict(execution.get("steps", {}) or {})
    reset_steps: dict[str, dict[str, Any]] = {}
    for stage in _STAGES:
        previous = dict(steps.get(stage, {}) or {})
        if stage == "AUTH_CHECK":
            reset_steps[stage] = _step("PENDING")
        elif stage == "VIDEO_UPLOAD":
            reset_steps[stage] = {
                **_step("PENDING"),
                "attempts": 0,
                "detail": "Оператор подтвердил новый private upload; прежний ролик сохранён.",
            }
        elif str(previous.get("status", "")).upper() == "NOT_REQUIRED":
            # Channel policy remains immutable for this frozen snapshot.
            reset_steps[stage] = previous
        else:
            reset_steps[stage] = _step("PENDING")

    execution.update({
        "youtubeVideoId": None,
        "youtubeVideoUrl": None,
        "steps": reset_steps,
        "currentStage": "VIDEO_UPLOAD",
        "overallStatus": "REUPLOAD_QUEUED",
        "activeLease": None,
        "resumableUpload": None,
        "reuploadHistory": reupload_history[-20:],
        "reupload": {
            "status": "QUEUED",
            "oldVideoId": old_video_id,
            "oldVideoUrl": old_video_url or None,
            "reason": clean_reason,
            "requestedAt": now,
            "lastCheckedAt": now,
            "originalPrivacy": snapshot.get("privacy", "private"),
            "originalPublishMode": snapshot.get("publishMode", "publish_now"),
            "originalPublishAt": snapshot.get("requestedPublishAt"),
            "metadataConfirmedAt": now,
            "replacementPrivacy": "private",
            "scheduleApplied": False,
        },
    })
    execution.setdefault("timeline", []).append({
        "at": now,
        "stage": "VIDEO_UPLOAD",
        "status": "REUPLOAD_QUEUED",
        "detail": (
            "Новый private upload поставлен в очередь. Старый YouTube ID сохранён; "
            "исходное расписание автоматически не применяется."
        ),
    })
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def release_execution(settings: Any, snapshot_id: str, worker_id: str) -> bool:
    """Release only the worker's own lease; another worker cannot unlock it."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    active = dict(execution.get("activeLease") or {})
    if active and str(active.get("workerId", "")) != str(worker_id):
        return False
    execution["activeLease"] = None
    execution.setdefault("timeline", []).append({"at": _now(), "status": "LEASE_RELEASED", "detail": "Worker освобождён"})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions
    return True


def next_upload_candidates(settings: Any) -> list[str]:
    """Return only safe new uploads without counting YouTube processing as transport.

    This is intentionally a read-only scheduling decision.  The caller must
    claim each returned execution before it starts a transport request.
    """
    if bool(getattr(settings, "youtube_publication_queue_paused", False)):
        return []
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    limit = max(1, int(getattr(settings, "youtube_publication_upload_concurrency", 1) or 1))
    active_uploads = 0
    for execution in executions.values():
        steps = dict(execution.get("steps", {}) or {})
        upload = dict(steps.get("VIDEO_UPLOAD", {}) or {})
        if str(upload.get("status", "")).upper() == "RUNNING":
            active_uploads += 1
    available = max(0, limit - active_uploads)
    if not available:
        return []
    allowed = {"WAITING", "READY", "RETRYING", "RETRYABLE", "REUPLOAD_QUEUED"}
    candidates: list[str] = []
    for snapshot_id in sorted(executions):
        execution = dict(executions[snapshot_id] or {})
        if str(execution.get("youtubeVideoId") or "").strip():
            continue
        if execution.get("activeLease"):
            continue
        status = str(execution.get("overallStatus", "WAITING")).upper()
        upload_status = str((execution.get("steps", {}).get("VIDEO_UPLOAD", {}) or {}).get("status", "PENDING")).upper()
        if status in allowed and upload_status in {"PENDING", "RETRYING", "FAILED"}:
            candidates.append(snapshot_id)
            if len(candidates) >= available:
                break
    return candidates


def begin_upload_attempt(settings: Any, snapshot_id: str, worker_id: str) -> None:
    """Persist the exclusive lease and running transport state before network I/O."""
    if bool(getattr(settings, "youtube_publication_queue_paused", False)):
        raise ValueError("Очередь публикаций приостановлена")
    if not claim_execution(settings, snapshot_id, worker_id):
        raise ValueError("Этот publication snapshot уже выполняется другим worker")
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions[snapshot_id]
    if str(execution.get("youtubeVideoId") or "").strip():
        release_execution(settings, snapshot_id, worker_id)
        raise ValueError("MP4 уже загружен на YouTube; повторная загрузка запрещена")
    steps = dict(execution.get("steps", {}) or {})
    auth = dict(steps.get("AUTH_CHECK", {}) or _step())
    auth.update({"status": "SUCCESS", "finishedAt": _now(), "providerResult": {"validated": True}})
    steps["AUTH_CHECK"] = auth
    upload = dict(steps.get("VIDEO_UPLOAD", {}) or _step())
    if str(upload.get("status", "")).upper() not in {"PENDING", "RETRYING", "FAILED"}:
        release_execution(settings, snapshot_id, worker_id)
        raise ValueError("Загрузка MP4 не находится в состоянии запуска")
    now = _now()
    upload.update({"status": "RUNNING", "startedAt": now, "finishedAt": None, "error": None,
                   "attempts": int(upload.get("attempts", 0) or 0) + 1, "progress": {"state": "starting"}})
    steps["VIDEO_UPLOAD"] = upload
    reupload = dict(execution.get("reupload", {}) or {})
    if str(reupload.get("status", "")).upper() == "QUEUED":
        reupload.update({"status": "RUNNING", "startedAt": now, "lastCheckedAt": now})
        execution["reupload"] = reupload
    execution.update({"steps": steps, "currentStage": "VIDEO_UPLOAD", "overallStatus": "UPLOADING",
                      "startedAt": execution.get("startedAt") or now, "uploadStartedAt": now})
    execution.setdefault("timeline", []).append({"at": now, "stage": "VIDEO_UPLOAD", "status": "RUNNING", "detail": "Передача MP4 начата"})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def complete_upload_attempt(settings: Any, snapshot_id: str, worker_id: str, provider_result: dict[str, Any]) -> None:
    """Commit the returned YouTube identity before allowing downstream stages."""
    video_id = str(provider_result.get("videoId") or "").strip()
    if not video_id:
        raise ValueError("YouTube не вернул ID после загрузки ролика")
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    active = dict(execution.get("activeLease") or {})
    if str(active.get("workerId", "")) != str(worker_id):
        raise ValueError("Этот worker не владеет publication execution")
    now = _now()
    steps = dict(execution.get("steps", {}) or {})
    upload = dict(steps.get("VIDEO_UPLOAD", {}) or _step())
    upload.update({"status": "SUCCESS", "finishedAt": now, "providerResult": dict(provider_result), "progress": {"state": "complete"}})
    steps["VIDEO_UPLOAD"] = upload
    reupload = dict(execution.get("reupload", {}) or {})
    if str(reupload.get("status", "")).upper() in {"QUEUED", "RUNNING"}:
        reupload.update({
            "status": "UPLOADED",
            "newVideoId": video_id,
            "newVideoUrl": str(provider_result.get("videoUrl", "")).strip() or None,
            "uploadedAt": now,
            "lastCheckedAt": now,
        })
        execution["reupload"] = reupload
    execution.update({"steps": steps, "youtubeVideoId": video_id, "youtubeVideoUrl": str(provider_result.get("videoUrl", "")).strip() or None,
                      "currentStage": "YOUTUBE_PROCESSING", "overallStatus": "PROCESSING", "uploadCompletedAt": now,
                      "resumableUpload": None})
    execution.setdefault("timeline", []).append({"at": now, "stage": "VIDEO_UPLOAD", "status": "SUCCESS", "detail": f"YouTube ID: {video_id}"})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions
    release_execution(settings, snapshot_id, worker_id)


def reconcile_youtube_video_state(settings: Any, snapshot_id: str, video: dict[str, Any]) -> None:
    """Apply only confirmed YouTube readback to granular execution stages."""
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    snapshot = dict(snapshots.get(snapshot_id, {}) or {})
    execution = executions.get(snapshot_id)
    if not snapshot or not execution:
        raise ValueError("Publication snapshot или execution не найден")
    snippet = dict(video.get("snippet", {}) or {})
    processing = dict(video.get("processingDetails", {}) or {})
    remote_status = dict(video.get("status", {}) or {})
    expected = dict(snapshot.get("metadata", {}) or {})
    steps = dict(execution.get("steps", {}) or {})
    now = _now()
    execution["youtubePrivacyStatus"] = str(remote_status.get("privacyStatus", "")).strip() or execution.get("youtubePrivacyStatus")
    execution["actualPublishedAt"] = str(snippet.get("publishedAt", "")).strip() or execution.get("actualPublishedAt")

    processing_status = str(processing.get("processingStatus", "")).casefold()
    processing_step = dict(steps.get("YOUTUBE_PROCESSING", {}) or _step())
    if processing_status == "succeeded":
        processing_step.update({"status": "SUCCESS", "finishedAt": now, "providerResult": {"processingStatus": processing_status}})
        execution["processingCompletedAt"] = now
    elif processing_status in {"failed", "terminated"}:
        processing_step.update({"status": "FAILED", "finishedAt": now, "error": {"category": "PERMANENT_FAILED", "message": "YouTube не завершил обработку ролика."}})
    else:
        processing_step.update({"status": "RUNNING", "providerResult": {"processingStatus": processing_status or "unknown"}})
    steps["YOUTUBE_PROCESSING"] = processing_step
    reupload = dict(execution.get("reupload", {}) or {})
    if reupload:
        reupload["lastCheckedAt"] = now
        if processing_status == "succeeded":
            reupload.update({"status": "SUCCEEDED", "completedAt": now})
        elif processing_status in {"failed", "terminated"}:
            reupload.update({"status": "FAILED", "failedAt": now})
        elif str(reupload.get("status", "")).upper() in {"UPLOADED", "PROCESSING"}:
            reupload["status"] = "PROCESSING"
        execution["reupload"] = reupload

    expected_description = compose_youtube_description(
        str(expected.get("description", "")),
        expected.get("hashtags", []) if isinstance(expected.get("hashtags"), list) else [],
    )
    checks = {
        "TITLE": _normalise(snippet.get("title")) == _normalise(resolve_publication_upload_title(expected)),
        "DESCRIPTION": str(snippet.get("description", "")).strip() == expected_description.strip(),
        "TAGS": { _normalise(value) for value in expected.get("tags", []) if _normalise(value) }.issubset({ _normalise(value) for value in snippet.get("tags", []) if _normalise(value) }),
    }
    for stage, matches in checks.items():
        step = dict(steps.get(stage, {}) or _step())
        step.update({"status": "SUCCESS" if matches else "UNVERIFIED", "finishedAt": now,
                     "providerResult": {"verified": bool(matches)}})
        steps[stage] = step

    schedule_step = dict(steps.get("SCHEDULE", {}) or _step())
    expected_publish_at = str(snapshot.get("requestedPublishAt") or "").strip()
    if str(snapshot.get("publishMode", "")) != "schedule":
        schedule_step.update({"status": "NOT_REQUIRED", "finishedAt": now, "providerResult": {"mode": "publish_now"}})
    elif expected_publish_at:
        remote_publish_at = str(remote_status.get("publishAt") or "").strip()
        matches = False
        try:
            expected_point = datetime.fromisoformat(expected_publish_at.replace("Z", "+00:00"))
            remote_point = datetime.fromisoformat(remote_publish_at.replace("Z", "+00:00")) if remote_publish_at else None
            matches = bool(remote_point and expected_point.astimezone(timezone.utc) == remote_point.astimezone(timezone.utc))
        except ValueError:
            matches = False
        schedule_step.update({
            "status": "SUCCESS" if matches else "UNVERIFIED",
            "finishedAt": now,
            "providerResult": {"verified": matches, "publishAt": remote_publish_at or None},
        })
        if matches:
            execution["confirmedPublishAt"] = remote_publish_at
    steps["SCHEDULE"] = schedule_step

    execution["steps"] = steps
    execution["currentStage"] = "THUMBNAIL"
    _refresh_execution_overall_status(settings, snapshot_id, execution)
    execution.setdefault("timeline", []).append({"at": now, "stage": "YOUTUBE_PROCESSING", "status": processing_step["status"], "detail": "Состояние YouTube подтверждено через API."})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def begin_publication_stage(settings: Any, snapshot_id: str, worker_id: str, stage: str) -> None:
    """Lease and mark one downstream stage RUNNING before a side effect starts."""

    normalized = str(stage).strip().upper()
    if normalized not in _STAGES or normalized in {"AUTH_CHECK", "VIDEO_UPLOAD", "YOUTUBE_PROCESSING", "TITLE", "DESCRIPTION", "TAGS"}:
        raise ValueError("Этот этап нельзя запускать через Studio stage helper")
    if not claim_execution(settings, snapshot_id, worker_id):
        raise ValueError("Этот publication snapshot уже выполняется другим worker")
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions[snapshot_id]
    steps = dict(execution.get("steps", {}) or {})
    step = dict(steps.get(normalized, {}) or _step())
    if str(step.get("status", "")).upper() in {"SUCCESS", "SKIPPED", "NOT_REQUIRED"}:
        release_execution(settings, snapshot_id, worker_id)
        raise ValueError("Готовый этап нельзя запускать повторно без явного reset")
    now = _now()
    step.update({
        "status": "RUNNING",
        "startedAt": now,
        "finishedAt": None,
        "attempts": int(step.get("attempts", 0) or 0) + 1,
        "error": None,
    })
    steps[normalized] = step
    reupload = dict(execution.get("reupload", {}) or {})
    if normalized == "VIDEO_UPLOAD" and str(reupload.get("status", "")).upper() in {"QUEUED", "RUNNING", "RETRYABLE"}:
        reupload.update({
            "status": "RETRYABLE" if classification == "RETRYABLE" else "FAILED",
            "failedAt": now,
            "lastCheckedAt": now,
            "error": {"category": classification, "message": str(message)},
        })
        execution["reupload"] = reupload
    execution["steps"] = steps
    execution["currentStage"] = normalized
    execution["overallStatus"] = "FORMATTING"
    execution.setdefault("timeline", []).append({
        "at": now, "stage": normalized, "status": "RUNNING", "detail": "Этап начат",
    })
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def mark_publication_stage_not_required(
    settings: Any,
    snapshot_id: str,
    stage: str,
    reason: str,
    provider_result: dict[str, Any] | None = None,
) -> None:
    """Persist an explicit non-action so completion counters remain truthful."""

    normalized = str(stage).strip().upper()
    if normalized not in _STAGES:
        raise ValueError("Этап публикации не найден")
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    steps = dict(execution.get("steps", {}) or {})
    step = dict(steps.get(normalized, {}) or _step())
    now = _now()
    step.update({
        "status": "NOT_REQUIRED",
        "finishedAt": now,
        "error": None,
        "providerResult": {"reason": str(reason), **dict(provider_result or {})},
    })
    steps[normalized] = step
    execution["steps"] = steps
    _refresh_execution_overall_status(settings, snapshot_id, execution)
    execution.setdefault("timeline", []).append({
        "at": now, "stage": normalized, "status": "NOT_REQUIRED", "detail": str(reason),
    })
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def complete_publication_stage(settings: Any, snapshot_id: str, worker_id: str, stage: str, provider_result: dict[str, Any] | None = None) -> None:
    """Complete a leased downstream stage without reopening any previous stage."""
    normalized = str(stage).strip().upper()
    if normalized not in _STAGES or normalized == "VIDEO_UPLOAD":
        raise ValueError("Для этого этапа используйте специализированный обработчик публикации")
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    active = dict(execution.get("activeLease") or {})
    if str(active.get("workerId", "")) != str(worker_id):
        raise ValueError("Этот worker не владеет publication execution")
    steps = dict(execution.get("steps", {}) or {})
    step = dict(steps.get(normalized, {}) or _step())
    now = _now()
    step.update({"status": "SUCCESS", "finishedAt": now, "error": None, "providerResult": dict(provider_result or {})})
    steps[normalized] = step
    index = _STAGES.index(normalized)
    next_stage = next((candidate for candidate in _STAGES[index + 1:] if str(dict(steps.get(candidate, {}) or {}).get("status", "PENDING")).upper() not in {"SUCCESS", "SKIPPED", "NOT_REQUIRED"}), "DONE")
    execution["steps"] = steps
    execution["currentStage"] = next_stage
    _refresh_execution_overall_status(settings, snapshot_id, execution)
    execution.setdefault("timeline", []).append({"at": now, "stage": normalized, "status": "SUCCESS", "detail": "Этап подтверждён"})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions
    release_execution(settings, snapshot_id, worker_id)


def classify_publication_error(error: BaseException | str) -> str:
    """Map transport/provider failures into a finite, user-safe retry model."""
    detail = str(error).casefold()
    if any(token in detail for token in ("quota", "daily limit", "ratelimit", "rate limit")):
        return "QUOTA_BLOCKED"
    if any(token in detail for token in ("oauth", "unauthorized", "invalid_grant", "login", "401", "403")):
        return "AUTH_REQUIRED"
    if any(token in detail for token in ("timeout", "temporar", "connection", "503", "502", "504", "reset by peer")):
        return "RETRYABLE"
    if any(token in detail for token in ("missing", "not found", "no such file")):
        return "USER_ACTION_REQUIRED"
    return "PERMANENT_FAILED"


def fail_publication_stage(settings: Any, snapshot_id: str, stage: str, category: str, message: str) -> None:
    """Record one failed stage while preserving all completed irreversible work."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    normalized = str(stage).strip().upper()
    if normalized not in _STAGES:
        raise ValueError("Этап публикации не найден")
    steps = dict(execution.get("steps", {}) or {})
    step = dict(steps.get(normalized, {}) or _step())
    classification = str(category).strip().upper() or "PERMANENT_FAILED"
    now = _now()
    if classification == "STUDIO_IDENTITY_REQUIRED":
        step_status = "USER_ACTION_REQUIRED"
    elif classification in {"AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"}:
        step_status = classification
    else:
        step_status = "FAILED"
    step.update({
        "status": step_status,
        "finishedAt": now,
        "error": {"category": classification, "message": str(message)},
        "progress": None,
    })
    steps[normalized] = step
    execution["steps"] = steps
    execution["currentStage"] = normalized
    execution["overallStatus"] = "PARTIAL" if str(execution.get("youtubeVideoId") or "").strip() else step["status"]
    execution.setdefault("timeline", []).append({"at": now, "stage": normalized, "status": step["status"], "detail": str(message)})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def resolve_uncertain_upload(
    settings: Any,
    snapshot_id: str,
    outcome: str,
    youtube_video_id: str = "",
) -> None:
    """Resolve an upload whose remote insert outcome could not be proven automatically."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    if str(execution.get("youtubeVideoId") or "").strip():
        raise ValueError("YouTube ID уже сохранён; неопределённая загрузка уже разрешена")

    steps = dict(execution.get("steps", {}) or {})
    upload = dict(steps.get("VIDEO_UPLOAD", {}) or {})
    if str(upload.get("status", "")).upper() != "USER_ACTION_REQUIRED":
        raise ValueError("Явная сверка доступна только для неопределённой загрузки MP4")

    normalized = str(outcome or "").strip().lower()
    now = _now()
    if normalized == "found":
        video_id = str(youtube_video_id or "").strip()
        if not video_id:
            raise ValueError("Укажите YouTube video ID найденного ролика")
        upload.update({
            "status": "SUCCESS",
            "finishedAt": now,
            "error": None,
            "providerResult": {"youtubeVideoId": video_id, "reconciledManually": True},
            "progress": {"state": "complete"},
        })
        steps["VIDEO_UPLOAD"] = upload
        execution.update({
            "steps": steps,
            "youtubeVideoId": video_id,
            "youtubeVideoUrl": f"https://www.youtube.com/watch?v={video_id}",
            "currentStage": "YOUTUBE_PROCESSING",
            "overallStatus": "PROCESSING",
            "uploadCompletedAt": execution.get("uploadCompletedAt") or now,
            "activeLease": None,
        })
        execution.setdefault("timeline", []).append({
            "at": now,
            "stage": "VIDEO_UPLOAD",
            "status": "SUCCESS",
            "detail": f"Оператор подтвердил существующий YouTube ID: {video_id}",
        })
    elif normalized == "not_found":
        upload.update({
            "status": "RETRYING",
            "finishedAt": now,
            "error": None,
            "providerResult": {"operatorConfirmedAbsent": True},
            "progress": None,
            "nextRetryAt": None,
        })
        steps["VIDEO_UPLOAD"] = upload
        execution.update({
            "steps": steps,
            "currentStage": "VIDEO_UPLOAD",
            "overallStatus": "RETRYING",
            "activeLease": None,
            "resumableUpload": None,
        })
        execution.setdefault("timeline", []).append({
            "at": now,
            "stage": "VIDEO_UPLOAD",
            "status": "RETRYING",
            "detail": "Оператор проверил канал и подтвердил отсутствие ролика; повтор MP4 разрешён.",
        })
    else:
        raise ValueError("Неизвестный результат сверки загрузки")

    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def cancel_publication_execution(settings: Any, snapshot_id: str) -> None:
    """Stop a job without deleting a remotely known YouTube video."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    has_video = bool(str(execution.get("youtubeVideoId") or "").strip())
    upload_status = str(dict(execution.get("steps", {}) or {}).get("VIDEO_UPLOAD", {}).get("status", "")).upper()
    if not has_video and upload_status == "USER_ACTION_REQUIRED":
        raise ValueError("Неопределённую загрузку нельзя отменить до явной сверки YouTube")
    execution["activeLease"] = None
    execution["overallStatus"] = "AUTOMATION_CANCELLED" if has_video else "CANCELLED"
    execution["currentStage"] = "AUTOMATION_CANCELLED" if has_video else "CANCELLED"
    execution.setdefault("timeline", []).append({
        "at": _now(), "status": execution["overallStatus"],
        "detail": "Остановлена дальнейшая автоматизация; видео на YouTube не удаляется." if has_video else "Задача отменена до загрузки MP4.",
    })
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def reconcile_publication_executions(settings: Any) -> dict[str, int]:
    """Recover persisted queue state after restart without creating duplicate uploads.

    A transport that ended before it yielded ``youtubeVideoId`` is deliberately
    *not* retried automatically: the only safe outcome is a visible operator
    reconciliation state.  Once the ID is known, downstream failures resume
    from their own stage and the upload stays immutable.
    """
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    interrupted = partial = unchanged = 0
    for snapshot_id, raw_execution in executions.items():
        execution = dict(raw_execution or {})
        had_lease = bool(execution.get("activeLease"))
        if not had_lease:
            unchanged += 1
            continue
        execution["activeLease"] = None
        steps = dict(execution.get("steps", {}) or {})
        video_id = str(execution.get("youtubeVideoId") or "").strip()
        upload = dict(steps.get("VIDEO_UPLOAD", {}) or {})
        if not video_id and str(upload.get("status", "")).upper() == "RUNNING":
            resume = dict(execution.get("resumableUpload", {}) or {})
            if str(resume.get("sessionUri", "")).strip():
                upload.update({
                    "status": "RETRYING",
                    "error": None,
                    "finishedAt": None,
                    "progress": {
                        "state": "resumable",
                        "bytesSent": int(resume.get("bytesSent", 0) or 0),
                        "totalBytes": int(resume.get("totalBytes", 0) or 0),
                    },
                })
                steps["VIDEO_UPLOAD"] = upload
                execution.update({
                    "steps": steps,
                    "currentStage": "VIDEO_UPLOAD",
                    "overallStatus": "RETRYING",
                })
                execution.setdefault("timeline", []).append({
                    "at": _now(), "stage": "VIDEO_UPLOAD", "status": "RETRYING",
                    "detail": "Перезапуск: сохранена resumable session, будет продолжена без нового videos.insert.",
                })
            else:
                upload.update({
                    "status": "USER_ACTION_REQUIRED",
                    "error": {
                        "category": "USER_ACTION_REQUIRED",
                        "message": "Загрузка прервана до сохранения resumable session/YouTube ID. Нужна сверка канала.",
                    },
                    "finishedAt": _now(),
                })
                steps["VIDEO_UPLOAD"] = upload
                execution.update({
                    "steps": steps,
                    "currentStage": "VIDEO_UPLOAD",
                    "overallStatus": "USER_ACTION_REQUIRED",
                })
                execution.setdefault("timeline", []).append({
                    "at": _now(), "stage": "VIDEO_UPLOAD", "status": "USER_ACTION_REQUIRED",
                    "detail": "Нужна безопасная сверка прерванной загрузки.",
                })
            interrupted += 1
        elif video_id:
            failed_downstream = any(
                stage != "VIDEO_UPLOAD" and str(dict(step or {}).get("status", "")).upper() in {"FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"}
                for stage, step in steps.items()
            )
            execution["overallStatus"] = "PARTIAL" if failed_downstream else str(execution.get("overallStatus", "UPLOADED"))
            execution.setdefault("timeline", []).append({"at": _now(), "status": "RECONCILED", "detail": "Перезапуск: YouTube ID сохранён, MP4 не будет загружен повторно."})
            partial += 1
        else:
            execution["overallStatus"] = "WAITING"
            unchanged += 1
        executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions
    return {"interrupted": interrupted, "partial": partial, "unchanged": unchanged}


def publication_receipt(settings: Any, snapshot_id: str) -> dict[str, Any]:
    """Create an honest, persistent-data-only final receipt for one snapshot."""
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    snapshot = dict(snapshots.get(snapshot_id, {}) or {})
    execution = dict(executions.get(snapshot_id, {}) or {})
    if not snapshot or not execution:
        raise ValueError("Publication snapshot или execution не найден")
    steps = dict(execution.get("steps", {}) or {})
    statuses = {stage: str(dict(value or {}).get("status", "PENDING")).upper() for stage, value in steps.items()}
    has_failure = any(status in {"FAILED", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"} for status in statuses.values())
    incomplete = any(status in {"PENDING", "RUNNING", "RETRYING", "UNVERIFIED"} for status in statuses.values())
    overall_status = str(execution.get("overallStatus", "DONE")).upper()
    if overall_status in {"CANCELLED", "AUTOMATION_CANCELLED"}:
        final_status = overall_status
    else:
        final_status = "PARTIAL" if has_failure or incomplete else overall_status
    if final_status not in {"DONE", "SCHEDULED", "PARTIAL", "NEEDS_ATTENTION", "AUTOMATION_CANCELLED", "CANCELLED"}:
        final_status = "PARTIAL"
    ads_step = dict(steps.get("ADS", {}) or {})
    ads_result = dict(ads_step.get("providerResult", {}) or {})
    return {
        "snapshotId": snapshot_id,
        "productionItemId": snapshot.get("productionItemId", ""),
        "channelId": snapshot.get("channelId", ""),
        "title": dict(snapshot.get("metadata", {}) or {}).get("title", ""),
        "youtubeVideoId": execution.get("youtubeVideoId"),
        "youtubeVideoUrl": execution.get("youtubeVideoUrl"),
        "privacy": snapshot.get("privacy", "private"),
        "publishMode": snapshot.get("publishMode", "publish_now"),
        "requestedPublishAt": snapshot.get("requestedPublishAt"),
        "confirmedPublishAt": execution.get("confirmedPublishAt"),
        "reupload": dict(execution.get("reupload", {}) or {}),
        "ads": {
            "status": str(ads_step.get("status", "PENDING")).upper(),
            "mode": str(ads_result.get("mode", "NONE" if str(ads_step.get("status", "")).upper() in {"NOT_REQUIRED", "SKIPPED"} else "")),
            "automatic": bool(ads_result.get("automaticSlotsEnabled")),
            "manualSlotsSeconds": list(ads_result.get("manualSlotsSeconds") or []),
            "confirmedManualSlotsSeconds": list(ads_result.get("confirmedManualSlotsSeconds") or []),
            "midRollEligible": bool(ads_result.get("midRollEligible")),
        },
        "stages": statuses,
        "finalStatus": final_status,
    }


def persist_publication_receipt(settings: Any, snapshot_id: str) -> dict[str, Any]:
    """Store a receipt as execution history without ever editing the snapshot."""
    receipt = publication_receipt(settings, snapshot_id)
    receipts = dict(getattr(settings, "youtube_publication_receipts", {}) or {})
    receipts[snapshot_id] = {**receipt, "recordedAt": _now()}
    settings.youtube_publication_receipts = receipts
    return receipt


def publication_queue_projection(settings: Any) -> dict[str, Any]:
    """Build the UI read model without exposing credentials or raw errors."""
    items = dict(getattr(settings, "youtube_publication_items", {}) or {})
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    assignments = dict(getattr(settings, "youtube_publication_assignments", {}) or {})
    rules = dict(getattr(settings, "youtube_channel_publication_rules", {}) or {})
    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for snapshot_id, snapshot in snapshots.items():
        execution = dict(executions.get(snapshot_id, {}) or {})
        steps = dict(execution.get("steps", {}) or {})
        completed = sum(1 for step in steps.values() if str(step.get("status", "")) in {"SUCCESS", "SKIPPED", "NOT_REQUIRED"})
        total = len(steps)
        status = str(execution.get("overallStatus", "WAITING"))
        status_counts[status] = status_counts.get(status, 0) + 1
        rows.append({
            "snapshotId": snapshot_id, "productionItemId": snapshot.get("productionItemId", ""),
            "title": snapshot.get("metadata", {}).get("title") or items.get(snapshot.get("productionItemId", ""), {}).get("metadata", {}).get("title", ""),
            "channelId": snapshot.get("channelId", ""), "publishAt": execution.get("confirmedPublishAt") or snapshot.get("requestedPublishAt"),
            "privacy": snapshot.get("privacy", "private"), "publishMode": snapshot.get("publishMode", "publish_now"),
            "youtubeVideoId": execution.get("youtubeVideoId"), "youtubeVideoUrl": execution.get("youtubeVideoUrl"),
            "currentStage": execution.get("currentStage", "WAITING"), "status": status,
            "ads": {
                "status": str(dict(steps.get("ADS", {}) or {}).get("status", "PENDING")).upper(),
                "mode": str(
                    dict(dict(steps.get("ADS", {}) or {}).get("providerResult", {}) or {}).get(
                        "mode",
                        "NONE" if str(dict(steps.get("ADS", {}) or {}).get("status", "")).upper() in {"NOT_REQUIRED", "SKIPPED"} else "",
                    )
                ),
                "automatic": bool(dict(dict(steps.get("ADS", {}) or {}).get("providerResult", {}) or {}).get("automaticSlotsEnabled")),
                "manualSlotsSeconds": list(dict(dict(steps.get("ADS", {}) or {}).get("providerResult", {}) or {}).get("manualSlotsSeconds", []) or []),
                "confirmedManualSlotsSeconds": list(dict(dict(steps.get("ADS", {}) or {}).get("providerResult", {}) or {}).get("confirmedManualSlotsSeconds", []) or []),
            },
            "completion": {"completed": completed, "total": total}, "steps": steps,
            "timeline": list(execution.get("timeline", []) or [])[-100:],
            "active": bool(execution.get("activeLease")),
            "reupload": dict(execution.get("reupload", {}) or {}),
        })
    assigned_channels: dict[str, str] = {}
    for production_id, assignment in assignments.items():
        production_key = str(production_id)
        if production_key not in items:
            continue
        channel_id = str(dict(assignment or {}).get("channelId", "")).strip()
        if channel_id:
            assigned_channels[production_key] = channel_id
    for snapshot_id, snapshot in snapshots.items():
        production_id = str(dict(snapshot or {}).get("productionItemId", "")).strip()
        channel_id = str(dict(snapshot or {}).get("channelId", "")).strip()
        if not production_id or production_id not in items or not channel_id or production_id in assigned_channels:
            continue
        execution = dict(executions.get(snapshot_id, {}) or {})
        status = str(execution.get("overallStatus", "")).upper()
        has_video = bool(str(execution.get("youtubeVideoId") or "").strip())
        if status == "CANCELLED" and not has_video:
            continue
        assigned_channels[production_id] = channel_id

    used_by_channel: dict[str, int] = {}
    for channel_id in assigned_channels.values():
        used_by_channel[channel_id] = used_by_channel.get(channel_id, 0) + 1

    video_ready = publication_ready = unassigned = 0
    for production_id, item in items.items():
        readiness = dict(dict(item or {}).get("readiness", {}) or {})
        is_video_ready = bool(readiness.get("videoReady")) if "videoReady" in readiness else str(readiness.get("state", "")).upper() == "VIDEO_READY"
        is_publication_ready = bool(readiness.get("publicationReady"))
        is_content_ready = bool(readiness.get("contentReady")) if "contentReady" in readiness else is_video_ready
        video_ready += int(is_video_ready)
        publication_ready += int(is_publication_ready)
        unassigned += int(is_content_ready and str(production_id) not in assigned_channels)

    quota_slots_remaining = 0
    for channel_id, rule in rules.items():
        source = dict(rule or {})
        if source.get("enabled") is False:
            continue
        try:
            quota = max(0, int(source.get("quota", 0) or 0))
        except (TypeError, ValueError):
            quota = 0
        quota_slots_remaining += max(0, quota - used_by_channel.get(str(channel_id), 0))

    semantic_counters = {
        "total": len(items),
        "videoReady": video_ready,
        "publicationReady": publication_ready,
        "assigned": len(assigned_channels),
        "unassigned": unassigned,
        "scheduled": sum(1 for execution in executions.values() if str(dict(execution or {}).get("overallStatus", "")).upper() == "SCHEDULED"),
        "uploading": sum(1 for execution in executions.values() if str(dict(execution or {}).get("overallStatus", "")).upper() == "UPLOADING"),
        "done": sum(1 for execution in executions.values() if str(dict(execution or {}).get("overallStatus", "")).upper() == "DONE"),
        "failed": sum(1 for execution in executions.values() if str(dict(execution or {}).get("overallStatus", "")).upper() in {"FAILED", "PARTIAL", "AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"}),
        "quotaSlotsRemaining": quota_slots_remaining,
    }
    return {"items": items, "queue": rows, "counters": {**semantic_counters, **status_counts},
            "paused": bool(getattr(settings, "youtube_publication_queue_paused", False)),
            "uploadConcurrency": int(getattr(settings, "youtube_publication_upload_concurrency", 1) or 1),
            "channelRules": dict(getattr(settings, "youtube_channel_publication_rules", {}) or {}),
            "rulePresets": list(getattr(settings, "youtube_publication_v2_rule_presets", []) or []),
            "planVersions": list(getattr(settings, "youtube_publication_plan_versions", []) or []),
            "assignments": dict(getattr(settings, "youtube_publication_assignments", {}) or {}),
            "receipts": dict(getattr(settings, "youtube_publication_receipts", {}) or {})}
