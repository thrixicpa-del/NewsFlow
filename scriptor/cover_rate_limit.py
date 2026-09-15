"""Local FastGen image-rate accounting for a resumable cover queue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CoverRateLimitDecision:
    allowed: bool
    used: int
    resume_at: datetime | None = None


def next_fastgen_resume_at(now: datetime | None = None) -> datetime:
    """FastGen quotas reset on the hour; reserve one minute for the reset."""
    moment = now or datetime.now().astimezone()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    next_hour = (moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return next_hour + timedelta(minutes=1)


def _event_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def cover_rate_limit_decision(
    events: Sequence[Mapping[str, object]], *, requested: int, limit_per_hour: int, now: datetime | None = None,
) -> CoverRateLimitDecision:
    """Tell the caller whether an image batch fits in the preceding hour.

    The stored events describe only successfully received images.  Bad or old
    rows are ignored, so the queue recovers safely after an interrupted run.
    """
    if limit_per_hour <= 0:
        return CoverRateLimitDecision(True, 0)
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    window_start = moment - timedelta(hours=1)
    usable: list[tuple[datetime, int]] = []
    for event in events:
        at = _event_time(event.get("at"))
        try:
            count = max(0, int(event.get("count", 0) or 0))
        except (TypeError, ValueError):
            continue
        if at is not None and at > window_start and count:
            usable.append((at, count))
    usable.sort(key=lambda item: item[0])
    used = sum(count for _, count in usable)
    if requested <= 0 or used + requested <= limit_per_hour:
        return CoverRateLimitDecision(True, used)
    remaining = used
    for at, count in usable:
        remaining -= count
        if remaining + requested <= limit_per_hour:
            return CoverRateLimitDecision(False, used, at + timedelta(hours=1))
    # A manually selected limit may be smaller than one requested batch.
    # Waiting cannot make that batch legal, so expose a deterministic next
    # window instead of reporting a misleading immediate retry.
    return CoverRateLimitDecision(False, used, moment + timedelta(hours=1))
