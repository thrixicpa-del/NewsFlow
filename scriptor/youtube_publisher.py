"""Local publication queue primitives for NewsFlow's YouTube workspace.

This first layer deliberately has no Google dependency.  It keeps production
packages, user-facing scheduling and queue state deterministic and testable;
the OAuth/API client is added on top of these objects later.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
import re
from uuid import uuid4

from .timeline import probe_media_duration


PublicationPrivacy = str
PublicationStatus = str


@dataclass(frozen=True)
class PublicationJob:
    """A ready NewsFlow package waiting to be uploaded to one YouTube channel."""

    id: str
    video_path: str
    package_folder: str
    title: str
    status: PublicationStatus = "ready"
    privacy: PublicationPrivacy = "private"
    publish_at: datetime | None = None
    channel_id: str = ""
    script_name: str = ""
    seo_title: str = ""
    seo_description: str = ""
    seo_phrases: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    thumbnail_path: str = ""
    duration_seconds: float | None = None
    title_rewrite_instruction: str = ""


@dataclass(frozen=True)
class AnalyticsMetricPoint:
    """One factual YouTube Analytics bucket returned for a channel.

    ``views`` and ``subscribers`` are period values, not guessed lifetime
    counters. Revenue is absent (``None``) until the channel grants the
    monetary OAuth scope; zero is therefore a meaningful, reported value.
    """

    channel_id: str
    at: datetime
    views: int
    subscribers: int
    publications: int
    estimated_revenue: float | None = None


def aggregate_analytics_metrics(
    points: list[AnalyticsMetricPoint],
    *,
    channel_ids: list[str],
    start_at: datetime,
    end_at: datetime,
) -> dict:
    """Aggregate one channel, a group, or a whole channel set for charts.

    The function preserves revenue coverage explicitly so the UI can never
    present a partial monetary total as the income of every selected channel.
    """

    if start_at.tzinfo is None or end_at.tzinfo is None:
        raise ValueError("Период аналитики должен содержать часовой пояс")
    if end_at <= start_at:
        raise ValueError("Конец периода аналитики должен быть позже начала")
    selected = {str(channel).strip() for channel in channel_ids if str(channel).strip()}
    relevant = [
        point for point in points
        if (not selected or point.channel_id in selected) and start_at <= point.at < end_at
    ]
    revenue_channels = {point.channel_id for point in relevant if point.estimated_revenue is not None}
    target_channels = selected or {point.channel_id for point in relevant}
    totals = {
        "views": sum(point.views for point in relevant),
        "subscribers": sum(point.subscribers for point in relevant),
        "publications": sum(point.publications for point in relevant),
        "revenue": round(sum(point.estimated_revenue or 0.0 for point in relevant), 2),
    }
    buckets: dict[datetime, list[AnalyticsMetricPoint]] = {}
    for point in relevant:
        buckets.setdefault(point.at, []).append(point)
    series = [
        {
            "at": at.isoformat(),
            "views": sum(point.views for point in bucket),
            "subscribers": sum(point.subscribers for point in bucket),
            "publications": sum(point.publications for point in bucket),
            "revenue": round(sum(point.estimated_revenue or 0.0 for point in bucket), 2),
        }
        for at, bucket in sorted(buckets.items())
    ]
    return {
        "totals": totals,
        "series": series,
        "revenueCoverage": {
            "availableChannels": sorted(revenue_channels),
            "missingChannels": sorted(target_channels - revenue_channels),
        },
    }


def create_publication_job(
    *,
    video_path: str,
    package_folder: str,
    title: str,
    script_name: str = "",
    seo_title: str = "",
    seo_description: str = "",
    seo_phrases: list[str] | None = None,
    tags: list[str] | None = None,
    hashtags: list[str] | None = None,
    thumbnail_path: str = "",
    duration_seconds: float | None = None,
) -> PublicationJob:
    """Create a safe private draft from a completed NewsFlow output package."""

    clean_title = " ".join(str(title).split())
    if not clean_title:
        raise ValueError("Укажите название ролика для публикации")
    if not str(video_path).strip():
        raise ValueError("Укажите готовый MP4 для публикации")
    needs_title_rewrite = len(clean_title) > 100
    rewrite_instruction = (
        "Перефразируй исходное название ролика до 100 символов включительно. "
        "Сохрани его новостную структуру, ключевой смысл и фактическую точность. "
        "Верни только один заголовок без кавычек."
        if needs_title_rewrite else ""
    )
    return PublicationJob(
        id=uuid4().hex,
        video_path=str(video_path),
        package_folder=str(package_folder),
        title=clean_title,
        status="needs-title-rewrite" if needs_title_rewrite else "ready",
        script_name=str(script_name),
        seo_title=str(seo_title),
        seo_description=str(seo_description),
        seo_phrases=list(seo_phrases or []),
        tags=list(tags or []),
        hashtags=list(hashtags or []),
        thumbnail_path=str(thumbnail_path),
        duration_seconds=(float(duration_seconds) if duration_seconds is not None and float(duration_seconds) > 0 else None),
        title_rewrite_instruction=rewrite_instruction,
    )


def _without_hashtags(value: str) -> str:
    """Remove hashtag tokens while preserving a readable SEO text."""

    without_tags = re.sub(r"(?<!\w)#[^\s#]+", "", str(value or ""))
    lines = [" ".join(line.split()) for line in without_tags.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def build_linked_community_post(
    job: PublicationJob,
    *,
    video_url: str = "",
    call_to_action: str = "Смотрите новый выпуск и напишите своё мнение в комментариях.",
) -> dict:
    """Prepare, but never publish, a Community post paired with one video.

    The public YouTube Data API has no endpoint for publishing Community
    posts.  NewsFlow therefore preserves the exact text, URL and matching
    date for a Chrome/Studio hand-off and requires the operator's final
    confirmation instead of pretending that a post was sent.
    """

    parts = [_without_hashtags(job.seo_description), _without_hashtags(call_to_action), str(video_url).strip()]
    text = "\n\n".join(part for part in parts if part)
    return {
        "text": text,
        "status": "prepared" if text else "needs-text",
        "publishAt": job.publish_at.isoformat() if job.publish_at else "",
        "videoUrl": str(video_url).strip(),
        "requiresManualConfirmation": True,
    }


def manual_ad_break_checklist(duration_seconds: int | float, *, interval_seconds: int = 39) -> list[str]:
    """Return safe manual Studio ad-marker suggestions for an uploaded video.

    Mid-roll placement for ordinary uploads is not exposed by the public
    YouTube API.  The list is deliberately a checklist for Studio, leaving a
    15-second tail so no suggestion is placed at the very end of a video.
    """

    duration = int(duration_seconds)
    interval = int(interval_seconds)
    if duration < 1 or interval < 1:
        raise ValueError("Длительность и интервал рекламных пауз должны быть положительными")
    markers = [seconds for seconds in range(interval, duration, interval) if seconds + 15 <= duration]
    return [f"{seconds // 60:02d}:{seconds % 60:02d}" for seconds in markers]


def can_upload(job: PublicationJob) -> bool:
    """Return whether a task has a valid title and is ready for YouTube upload."""

    return job.status in {"ready", "scheduled"} and 0 < len(job.title) <= 100


def suggest_youtube_title(job: PublicationJob, *, limit: int = 100) -> str:
    """Return a safe first rewrite suggestion without calling an external model.

    A ready SEO heading normally contains the same news event in a shorter,
    search-friendly form, so it is the least destructive automatic option.
    When it cannot be used, retain whole words from the original title rather
    than silently cutting one in half.  The operator can always edit the
    suggestion before upload.
    """

    if limit < 1:
        raise ValueError("Лимит заголовка должен быть положительным")
    seo_title = " ".join(str(job.seo_title or "").split())
    if seo_title and len(seo_title) <= limit:
        return seo_title
    source = " ".join(str(job.title or "").split())
    if len(source) <= limit:
        return source
    words: list[str] = []
    size = 0
    for word in source.split():
        candidate = len(word) if not words else size + 1 + len(word)
        if candidate > limit:
            break
        words.append(word)
        size = candidate
    return " ".join(words) or source[:limit]


def apply_rewritten_title(job: PublicationJob, title: str) -> PublicationJob:
    """Accept a reviewed agent rewrite only when it satisfies YouTube's limit."""

    clean_title = " ".join(str(title).split())
    if not clean_title:
        raise ValueError("Перефразированный заголовок не может быть пустым")
    if len(clean_title) > 100:
        raise ValueError("Перефразированный заголовок длиннее 100 символов")
    next_status = "scheduled" if job.publish_at else "ready"
    return replace(job, title=clean_title, status=next_status, title_rewrite_instruction="")


def publication_job_record(job: PublicationJob) -> dict:
    """Return the stable JSON form consumed by the Electron snapshot."""

    record = asdict(job)
    record["videoPath"] = record.pop("video_path")
    record["packageFolder"] = record.pop("package_folder")
    record["channelId"] = record.pop("channel_id")
    record["scriptName"] = record.pop("script_name")
    record["seoTitle"] = record.pop("seo_title")
    record["seoDescription"] = record.pop("seo_description")
    record["seoPhrases"] = record.pop("seo_phrases")
    record["thumbnailPath"] = record.pop("thumbnail_path")
    record["durationSeconds"] = record.pop("duration_seconds")
    record["titleRewriteInstruction"] = record.pop("title_rewrite_instruction")
    publish_at = record.pop("publish_at")
    record["publishAt"] = publish_at.isoformat() if publish_at else ""
    return record


def _read_package_text(folder: Path, name: str) -> str:
    path = folder / name
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _split_package_values(value: str, separators: str = ",\n") -> list[str]:
    values = [value]
    for separator in separators:
        values = [part for item in values for part in item.split(separator)]
    return [" ".join(item.split()) for item in values if item.strip()]


def create_publication_job_from_package(source_video: str, package_folder: str) -> PublicationJob:
    """Read the NewsFlow result files without guessing or losing metadata."""

    folder = Path(package_folder)
    if not folder.is_dir():
        raise ValueError("Папка результата для публикации не найдена")
    packaged_video = next((path for path in sorted(folder.glob("*.mp4")) if path.is_file()), Path(source_video))
    if not packaged_video.is_file():
        raise ValueError("В готовом пакете не найден MP4")
    scenario_title = _read_package_text(folder, "Название сценария.txt") or _read_package_text(folder, "Заголовок.txt")
    if not scenario_title:
        scenario_title = packaged_video.stem
    thumbnail = next((path for path in sorted(folder.glob("Обложка.*")) if path.is_file()), None)
    try:
        duration_seconds = probe_media_duration(packaged_video)
    except (OSError, ValueError, RuntimeError):
        duration_seconds = None
    return create_publication_job(
        video_path=str(packaged_video),
        package_folder=str(folder),
        title=scenario_title,
        script_name=scenario_title,
        seo_title=_read_package_text(folder, "SEO-заголовок.txt"),
        seo_description=_read_package_text(folder, "Описание.txt"),
        seo_phrases=_split_package_values(_read_package_text(folder, "SEO-фразы.txt")),
        tags=_split_package_values(_read_package_text(folder, "Теги.txt")),
        hashtags=_split_package_values(_read_package_text(folder, "Хештеги.txt"), " \n"),
        thumbnail_path=str(thumbnail) if thumbnail else "",
        duration_seconds=duration_seconds,
    )


def schedule_publication(job: PublicationJob, publish_at: datetime) -> PublicationJob:
    """Return a private task waiting for a specific YouTube publication time."""

    if publish_at.tzinfo is None:
        raise ValueError("Укажите время публикации с часовым поясом")
    return replace(job, status="scheduled", privacy="private", publish_at=publish_at)


def build_staggered_publication_grid(
    channel_ids: list[str],
    first_cycle_at: datetime,
    cycles: int,
    interval_hours: int | None = None,
    *,
    interval_minutes: int | None = None,
    distribution: str = "spread",
    slot_minutes: int = 15,
    batch_capacity: int = 1,
) -> dict[str, list[datetime]]:
    """Build deterministic operator-selected points for each publication cycle.

    ``spread`` gives each channel a stable offset. ``aligned`` deliberately
    allows shared moments, for example when the operator wants every channel
    to publish at 04:00, 05:00 and so on. The grid never imposes a hidden
    cross-channel uniqueness policy.
    """

    if first_cycle_at.tzinfo is None:
        raise ValueError("Укажите начало сетки с часовым поясом")
    if cycles < 1:
        raise ValueError("Укажите хотя бы один цикл публикации")
    if interval_minutes is not None and interval_hours is not None:
        raise ValueError("Укажите интервал либо в часах, либо в минутах")
    minutes = interval_minutes if interval_minutes is not None else (interval_hours or 0) * 60
    if minutes < 1:
        raise ValueError("Интервал публикации должен быть не меньше минуты")
    if distribution not in {"spread", "aligned", "allow-overlap", "first-then-batches", "always-batches", "stretch-cycle"}:
        raise ValueError("Неизвестный метод распределения публикаций")
    if slot_minutes < 1:
        raise ValueError("Шаг слотов должен быть не меньше одной минуты")
    if batch_capacity < 1:
        raise ValueError("Вместимость пачки должна быть не меньше одного канала")
    normalized = [str(channel).strip() for channel in channel_ids]
    if not normalized or any(not channel for channel in normalized):
        raise ValueError("Выберите хотя бы один канал")
    if len(set(normalized)) != len(normalized):
        raise ValueError("В сетке есть повторяющиеся каналы")

    cycle_seconds = minutes * 60
    ordered = list(normalized)
    if distribution == "first-then-batches":
        # Cover every 15-minute slot first. If there are more channels than
        # slots in one cadence, the next layer intentionally reuses a slot;
        # this is surfaced as a batch in the UI rather than silently moving a
        # channel away from its requested repeat interval.
        slots_per_cycle = max(1, (minutes + slot_minutes - 1) // slot_minutes)
        offsets = {
            channel: (((position // batch_capacity) % slots_per_cycle) * slot_minutes * 60)
            for position, channel in enumerate(ordered)
        }
    elif distribution == "always-batches":
        offsets = {
            channel: ((position // batch_capacity) * slot_minutes * 60)
            for position, channel in enumerate(ordered)
        }
    elif distribution == "stretch-cycle":
        slots_needed = (len(ordered) + batch_capacity - 1) // batch_capacity
        cycle_seconds = max(minutes, slots_needed * slot_minutes) * 60
        offsets = {
            channel: ((position // batch_capacity) * slot_minutes * 60)
            for position, channel in enumerate(ordered)
        }
    elif distribution == "aligned":
        offsets = {channel: 0 for channel in ordered}
    else:
        offsets = {
            channel: (position * cycle_seconds) // len(ordered)
            for position, channel in enumerate(ordered)
        }
    return {
        channel: [
            first_cycle_at + timedelta(seconds=offsets[channel] + cycle_index * cycle_seconds)
            for cycle_index in range(cycles)
        ]
        for channel in normalized
    }


def plan_jobs_on_publication_grid(
    jobs: list[PublicationJob],
    *,
    channel_ids: list[str],
    first_cycle_at: datetime,
    interval_minutes: int,
    distribution: str = "spread",
    slot_minutes: int = 15,
    batch_capacity: int = 1,
) -> list[PublicationJob]:
    """Assign ready tasks to a repeatable channel/time grid without uploading."""

    if not jobs:
        raise ValueError("Выберите хотя бы один ролик для расписания")
    if not channel_ids:
        raise ValueError("Выберите хотя бы один канал")
    editable_statuses = {"ready", "needs-title-rewrite"}
    if any(job.status not in editable_statuses for job in jobs):
        raise ValueError("В расписание можно добавлять только новые задачи или задачи с заголовком на проверке")
    cycles = (len(jobs) + len(channel_ids) - 1) // len(channel_ids)
    grid = build_staggered_publication_grid(
        channel_ids,
        first_cycle_at,
        cycles,
        interval_minutes=interval_minutes,
        distribution=distribution,
        slot_minutes=slot_minutes,
        batch_capacity=batch_capacity,
    )
    slots = sorted(
        ((moment, channel) for channel, moments in grid.items() for moment in moments),
        key=lambda value: (value[0], value[1]),
    )
    planned: list[PublicationJob] = []
    for job, (publish_at, channel_id) in zip(jobs, slots):
        status = "scheduled" if job.status == "ready" else "needs-title-rewrite"
        planned.append(replace(job, channel_id=channel_id, publish_at=publish_at, status=status))
    return planned
