"""Non-destructive Publication V2 domain records and legacy migration.

This module deliberately operates on in-memory Settings.  The bridge owns
when data is persisted, so migration can be previewed and tested without
touching a user's actual publication queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_STAGES = (
    "AUTH_CHECK", "VIDEO_UPLOAD", "YOUTUBE_PROCESSING", "TITLE", "DESCRIPTION",
    "TAGS", "THUMBNAIL", "POST", "CARDS", "END_SCREEN", "SCHEDULE",
)


@dataclass(frozen=True)
class PublicationMigrationReport:
    migrated_items: int
    migrated_jobs: int
    missing_artifacts: int
    ambiguous_jobs: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


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
    for production_id, item in known_by_id.items():
        known_by_title.setdefault(_normalise(item.get("title")), []).append(production_id)

    migrated_items = migrated_jobs = missing_artifacts = ambiguous_jobs = 0
    for production_id, production in known_by_id.items():
        if production_id not in items:
            items[production_id] = {
                "productionItemId": production_id, "legacyLinks": {},
                "artifacts": {}, "metadata": {"title": str(production.get("title", "")), "description": "", "tags": []},
                "readiness": {"state": "DISCOVERED", "reasons": ["VIDEO_MISSING"]}, "jobIds": [], "updatedAt": _now(),
            }
            migrated_items += 1

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
    """Refresh non-destructive artifact state and return the V2 registry projection."""
    migrate_legacy_publication_data(settings)
    items = dict(settings.youtube_publication_items)
    ready = missing = 0
    for production_id, item in items.items():
        artifact = dict(item.get("artifacts", {}).get("video", {}) or {})
        path = str(artifact.get("path", "")).strip()
        exists = bool(path and Path(path).is_file())
        artifact.update({"path": path, "exists": exists, "validatedAt": _now()})
        item.setdefault("artifacts", {})["video"] = artifact
        item["readiness"] = {"state": "VIDEO_READY" if exists else "VIDEO_MISSING",
                             "reasons": [] if exists else ["VIDEO_MISSING"]}
        item["updatedAt"] = _now()
        if exists:
            ready += 1
        else:
            missing += 1
        items[production_id] = item
    settings.youtube_publication_items = items
    return {"items": items, "counters": {"total": len(items), "videoReady": ready, "videoMissing": missing}}


def build_distribution_preview(items: dict[str, dict], rules: list[dict], assignments: dict[str, dict]) -> dict[str, Any]:
    """Return a deterministic non-mutating allocation preview.

    Locked/manual assignments consume only their own channel quota.  All
    remaining rows are sorted by production ID unless a channel explicitly
    asks for longest-first.
    """
    enabled = [dict(rule) for rule in rules if bool(rule.get("enabled", True)) and int(rule.get("quota", 0) or 0) > 0]
    by_channel = {str(rule.get("channelId", "")).strip(): rule for rule in enabled if str(rule.get("channelId", "")).strip()}
    used = {channel_id: 0 for channel_id in by_channel}
    rows: list[dict[str, Any]] = []
    assigned_ids: set[str] = set()
    for production_id in sorted(items):
        assignment = dict(assignments.get(production_id, {}) or {})
        channel_id = str(assignment.get("channelId", "")).strip()
        locked = bool(assignment.get("locked", False)) or str(assignment.get("source", "")) == "manual"
        if channel_id and locked:
            if channel_id in used:
                used[channel_id] += 1
            rows.append({"productionItemId": production_id, "channelId": channel_id, "source": assignment.get("source", "manual"),
                         "locked": True, "reason": "manual_locked"})
            assigned_ids.add(production_id)

    candidates = [
        (production_id, item) for production_id, item in items.items()
        if production_id not in assigned_ids and str(item.get("readiness", {}).get("state", "")) == "VIDEO_READY"
    ]
    if any(str(rule.get("distributionStrategy", "")) == "longest_monetized" for rule in enabled):
        candidates.sort(key=lambda pair: (-float(pair[1].get("durationSeconds", 0) or 0), pair[0]))
    else:
        candidates.sort(key=lambda pair: pair[0])
    for production_id, _item in candidates:
        chosen = next((rule for rule in enabled if used[str(rule["channelId"])] < int(rule["quota"])), None)
        if chosen is None:
            rows.append({"productionItemId": production_id, "channelId": "", "source": "", "locked": False, "reason": "quota_exhausted"})
            continue
        channel_id = str(chosen["channelId"])
        used[channel_id] += 1
        rows.append({"productionItemId": production_id, "channelId": channel_id, "source": "auto", "locked": False, "reason": "auto"})
    schedule_warnings: list[dict[str, str]] = []
    for channel_id, rule in by_channel.items():
        if str(rule.get("publishMode", "")).strip() != "schedule":
            continue
        channel_rows = [row for row in rows if row.get("channelId") == channel_id]
        if not channel_rows:
            continue
        manual_slots = {
            str(row["productionItemId"]): str((assignments.get(str(row["productionItemId"]), {}) or {}).get("publishAt", "") or "").strip()
            for row in channel_rows if bool(row.get("locked", False))
        }
        try:
            slots = build_channel_schedule([str(row["productionItemId"]) for row in channel_rows], rule, manual_slots)
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
    return {"assignments": rows, "channelUsage": used, "scheduleWarnings": schedule_warnings}


def _clock(value: object) -> time | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    return time.fromisoformat(clean)


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
        return current


def build_channel_schedule(production_item_ids: list[str], rule: dict[str, Any], manual_slots: dict[str, str] | None = None) -> list[dict[str, str]]:
    """Build a timezone-aware schedule for exactly one channel without mutation."""
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
    interval = int(rule.get("intervalMinutes", 0) or 0)
    if interval < 1:
        raise ValueError("Интервал между роликами должен быть положительным")
    result: list[dict[str, str]] = []
    overrides = dict(manual_slots or {})
    daily_cap = max(0, int(rule.get("dailyCap", 0) or 0))
    daily_counts: dict[str, int] = {}
    for production_item_id in production_item_ids:
        manual = str(overrides.get(production_item_id, "")).strip()
        if manual:
            slot = datetime.fromisoformat(manual)
            if slot.tzinfo is None:
                slot = slot.replace(tzinfo=zone)
            else:
                slot = slot.astimezone(zone)
            source = "manual"
        else:
            slot = _next_allowed_slot(candidate, rule, zone)
            while daily_cap and daily_counts.get(slot.date().isoformat(), 0) >= daily_cap:
                candidate = datetime.combine((slot + timedelta(days=1)).date(), _clock(rule.get("publishWindowStart")) or time.min, tzinfo=zone)
                slot = _next_allowed_slot(candidate, rule, zone)
            source = "auto"
        result.append({"productionItemId": str(production_item_id), "publishAt": slot.isoformat(), "source": source,
                       "timezone": zone.key})
        daily_key = slot.date().isoformat()
        daily_counts[daily_key] = daily_counts.get(daily_key, 0) + 1
        candidate = slot + timedelta(minutes=interval)
    return result


def apply_bulk_schedule_range(assignments: list[dict], schedule: dict[str, Any]) -> list[dict]:
    """Return a non-mutating, evenly-spaced preview inside one operator range.

    This is deliberately a preview helper: it never saves assignments, creates
    snapshots, or starts a provider call.  Confirmation remains the only
    persistent publication action.
    """
    date_value = str(schedule.get("date", "")).strip()
    start_value = str(schedule.get("startTime", "")).strip()
    end_value = str(schedule.get("endTime", "")).strip()
    zone_name = str(schedule.get("timezone", "")).strip() or "UTC"
    try:
        zone = ZoneInfo(zone_name)
        start = datetime.fromisoformat(f"{date_value}T{start_value}").replace(tzinfo=zone)
        end = datetime.fromisoformat(f"{date_value}T{end_value}").replace(tzinfo=zone)
    except Exception as error:
        raise ValueError("Укажите корректные дату, начало, конец и часовой пояс диапазона.") from error
    if end < start:
        raise ValueError("Конец диапазона должен быть не раньше начала.")

    result = [dict(row) for row in assignments]
    scheduled_positions = [index for index, row in enumerate(result) if str(row.get("channelId", "")).strip()]
    if not scheduled_positions:
        return result
    if len(scheduled_positions) == 1:
        result[scheduled_positions[0]].update({"publishAt": start.isoformat(), "timezone": zone.key, "source": "bulk_range"})
        return result

    total_seconds = int((end - start).total_seconds())
    denominator = len(scheduled_positions) - 1
    for offset, position in enumerate(scheduled_positions):
        seconds = round(total_seconds * offset / denominator)
        result[position].update({"publishAt": (start + timedelta(seconds=seconds)).isoformat(), "timezone": zone.key,
                                 "source": "bulk_range"})
    return result


def validate_publication_schedule(assignments: list[dict], channel_rules: dict[str, dict]) -> list[dict[str, str]]:
    """Return conflicts without correcting any explicit assignment in place."""
    conflicts: list[dict[str, str]] = []
    seen_slots: dict[tuple[str, str], str] = {}
    daily_counts: dict[tuple[str, str], int] = {}
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
        if not within_window and bool(assignment.get("locked", False)):
            conflicts.append({"kind": "manual_outside_window", "productionItemId": production_id, "channelId": channel_id})
        daily_key = (channel_id, local_slot.date().isoformat())
        daily_counts[daily_key] = daily_counts.get(daily_key, 0) + 1
        daily_cap = max(0, int(rule.get("dailyCap", 0) or 0))
        if daily_cap and daily_counts[daily_key] > daily_cap:
            conflicts.append({"kind": "daily_cap_exceeded", "productionItemId": production_id, "channelId": channel_id})
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
    if not video_path or not Path(video_path).is_file():
        reasons.append({"kind": "VIDEO_MISSING", "message": "MP4 из snapshot не найден. Связь с роликом сохранена для восстановления."})
    metadata = dict(snapshot.get("metadata", {}) or {})
    title = str(metadata.get("title", "")).strip()
    if not title or len(title) > 100:
        reasons.append({"kind": "TITLE_INVALID", "message": "Заголовок YouTube должен содержать от 1 до 100 символов."})
    channel_id = str(snapshot.get("channelId", "")).strip()
    tokens = dict(getattr(settings, "youtube_oauth_tokens", {}) or {})
    if not channel_id or not str(tokens.get(channel_id, "")).strip():
        reasons.append({"kind": "AUTH_REQUIRED", "message": "Для канала требуется OAuth-вход."})
    return {
        "ok": not reasons,
        "snapshotId": snapshot_id,
        "reasons": reasons,
        "uploadAlreadyExists": bool(str(execution.get("youtubeVideoId") or "").strip()),
        "videoPath": video_path,
    }


def confirm_publication_snapshots(settings: Any, assignments: list[dict], channel_rules: dict[str, dict]) -> list[str]:
    """Freeze explicit valid assignments once; repeat confirmation is idempotent."""
    conflicts = validate_publication_schedule(assignments, channel_rules)
    if conflicts:
        kinds = ", ".join(sorted({str(conflict["kind"]) for conflict in conflicts}))
        raise ValueError(f"Расписание содержит конфликты: {kinds}")
    snapshots = dict(getattr(settings, "youtube_publication_snapshots", {}) or {})
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    items = dict(getattr(settings, "youtube_publication_items", {}) or {})
    created: list[str] = []
    existing_by_item = {str(snapshot.get("productionItemId", "")): snapshot_id for snapshot_id, snapshot in snapshots.items()}
    for assignment in assignments:
        production_id = str(assignment.get("productionItemId", "")).strip()
        channel_id = str(assignment.get("channelId", "")).strip()
        item = items.get(production_id)
        if not production_id or not channel_id or not item:
            raise ValueError("Подтверждение требует существующий ролик и канал")
        if str(item.get("readiness", {}).get("state", "")) != "VIDEO_READY":
            raise ValueError(f"Ролик {production_id} не готов к публикации")
        snapshot_id = existing_by_item.get(production_id)
        if snapshot_id:
            created.append(snapshot_id)
            continue
        rule = dict(channel_rules.get(channel_id, {}) or {})
        publish_at = str(assignment.get("publishAt", "")).strip() or None
        mode = str(rule.get("publishMode", "")).strip() or ("schedule" if publish_at else "publish_now")
        if mode == "schedule" and not publish_at:
            raise ValueError(f"Для scheduled публикации {production_id} требуется время")
        privacy = str(rule.get("privacy", "private")).strip()
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Некорректный privacy режим")
        if mode == "schedule" and privacy != "private":
            raise ValueError("Для публикации по расписанию YouTube требует initial privacy private")
        snapshot_id = f"snapshot:{production_id}:{channel_id}"
        artifact = dict(item.get("artifacts", {}).get("video", {}) or {})
        thumbnail = dict(item.get("artifacts", {}).get("thumbnail", {}) or {})
        metadata = dict(item.get("metadata", {}) or {})
        snapshot = {
            "id": snapshot_id, "productionItemId": production_id, "channelId": channel_id,
            "videoPath": str(artifact.get("path", "")), "thumbnailPath": str(thumbnail.get("path", "")), "metadata": metadata,
            "privacy": privacy, "publishMode": mode, "requestedPublishAt": publish_at,
            "idempotencyKey": sha256(f"{production_id}|{channel_id}".encode()).hexdigest(), "createdAt": _now(),
        }
        snapshots[snapshot_id] = snapshot
        executions[snapshot_id] = _execution(snapshot_id, production_id, {"publishAt": publish_at or ""})
        executions[snapshot_id]["overallStatus"] = "SCHEDULED" if mode == "schedule" else "READY"
        executions[snapshot_id]["plannedPublishAt"] = publish_at
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
    result.update({"status": "RETRYING", "error": None, "nextRetryAt": None})
    steps[normalized] = result
    execution["steps"] = steps
    execution["currentStage"] = normalized
    execution["overallStatus"] = "RETRYING"
    execution.setdefault("timeline", []).append({"at": _now(), "stage": normalized, "status": "RETRYING", "detail": "Повтор этапа"})
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
    allowed = {"WAITING", "READY", "RETRYING", "RETRYABLE"}
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
    upload = dict(steps.get("VIDEO_UPLOAD", {}) or _step())
    if str(upload.get("status", "")).upper() not in {"PENDING", "RETRYING", "FAILED"}:
        release_execution(settings, snapshot_id, worker_id)
        raise ValueError("Загрузка MP4 не находится в состоянии запуска")
    now = _now()
    upload.update({"status": "RUNNING", "startedAt": now, "finishedAt": None, "error": None,
                   "attempts": int(upload.get("attempts", 0) or 0) + 1, "progress": {"state": "starting"}})
    steps["VIDEO_UPLOAD"] = upload
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
    execution.update({"steps": steps, "youtubeVideoId": video_id, "youtubeVideoUrl": str(provider_result.get("videoUrl", "")).strip() or None,
                      "currentStage": "YOUTUBE_PROCESSING", "overallStatus": "PROCESSING", "uploadCompletedAt": now})
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
    expected = dict(snapshot.get("metadata", {}) or {})
    steps = dict(execution.get("steps", {}) or {})
    now = _now()

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

    checks = {
        "TITLE": _normalise(snippet.get("title")) == _normalise(expected.get("title")),
        "DESCRIPTION": str(snippet.get("description", "")).strip() == str(expected.get("description", "")).strip(),
        "TAGS": { _normalise(value) for value in expected.get("tags", []) if _normalise(value) }.issubset({ _normalise(value) for value in snippet.get("tags", []) if _normalise(value) }),
    }
    for stage, matches in checks.items():
        step = dict(steps.get(stage, {}) or _step())
        step.update({"status": "SUCCESS" if matches else "UNVERIFIED", "finishedAt": now,
                     "providerResult": {"verified": bool(matches)}})
        steps[stage] = step
    execution["steps"] = steps
    execution["currentStage"] = "THUMBNAIL"
    execution["overallStatus"] = "FORMATTING" if processing_step["status"] == "SUCCESS" else "PROCESSING"
    execution.setdefault("timeline", []).append({"at": now, "stage": "YOUTUBE_PROCESSING", "status": processing_step["status"], "detail": "Состояние YouTube подтверждено через API."})
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
    terminal = {"SUCCESS", "SKIPPED", "NOT_REQUIRED"}
    execution["steps"] = steps
    execution["currentStage"] = next_stage
    execution["overallStatus"] = "DONE" if all(str(dict(value or {}).get("status", "PENDING")).upper() in terminal for value in steps.values()) else "FORMATTING"
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
    step.update({"status": "FAILED" if classification not in {"AUTH_REQUIRED", "QUOTA_BLOCKED", "USER_ACTION_REQUIRED"} else classification,
                 "finishedAt": now, "error": {"category": classification, "message": str(message)}, "progress": None})
    steps[normalized] = step
    execution["steps"] = steps
    execution["currentStage"] = normalized
    execution["overallStatus"] = "PARTIAL" if str(execution.get("youtubeVideoId") or "").strip() else step["status"]
    execution.setdefault("timeline", []).append({"at": now, "stage": normalized, "status": step["status"], "detail": str(message)})
    executions[snapshot_id] = execution
    settings.youtube_publication_executions = executions


def cancel_publication_execution(settings: Any, snapshot_id: str) -> None:
    """Stop a job without deleting a remotely known YouTube video."""
    executions = dict(getattr(settings, "youtube_publication_executions", {}) or {})
    execution = executions.get(snapshot_id)
    if not execution:
        raise ValueError("Publication execution не найден")
    has_video = bool(str(execution.get("youtubeVideoId") or "").strip())
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
            upload.update({
                "status": "USER_ACTION_REQUIRED",
                "error": {"category": "USER_ACTION_REQUIRED", "message": "Загрузка была прервана до подтверждения YouTube ID. Автоповтор отключён, чтобы не создать дубликат."},
                "finishedAt": _now(),
            })
            steps["VIDEO_UPLOAD"] = upload
            execution.update({"steps": steps, "currentStage": "VIDEO_UPLOAD", "overallStatus": "USER_ACTION_REQUIRED"})
            execution.setdefault("timeline", []).append({"at": _now(), "stage": "VIDEO_UPLOAD", "status": "USER_ACTION_REQUIRED", "detail": "Нужна безопасная сверка прерванной загрузки."})
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
    final_status = "PARTIAL" if has_failure or incomplete else str(execution.get("overallStatus", "DONE")).upper()
    if final_status not in {"DONE", "SCHEDULED", "PARTIAL", "NEEDS_ATTENTION", "AUTOMATION_CANCELLED", "CANCELLED"}:
        final_status = "PARTIAL"
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
            "completion": {"completed": completed, "total": total}, "steps": steps,
            "timeline": list(execution.get("timeline", []) or [])[-100:],
            "active": bool(execution.get("activeLease")),
        })
    return {"items": items, "queue": rows, "counters": {"total": len(rows), **status_counts},
            "paused": bool(getattr(settings, "youtube_publication_queue_paused", False)),
            "uploadConcurrency": int(getattr(settings, "youtube_publication_upload_concurrency", 1) or 1),
            "channelRules": dict(getattr(settings, "youtube_channel_publication_rules", {}) or {}),
            "assignments": dict(getattr(settings, "youtube_publication_assignments", {}) or {}),
            "receipts": dict(getattr(settings, "youtube_publication_receipts", {}) or {})}
