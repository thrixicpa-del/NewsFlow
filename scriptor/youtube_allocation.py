"""Deterministic, local allocation rules for the YouTube publication queue.

The module deliberately knows nothing about Google, files, or Settings. It turns
plain queue records and channel profiles into a reviewable recommendation so the
desktop bridge can persist only an operator-approved change.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import inf
from typing import Mapping, Sequence


_EDITABLE_STATUSES = {"ready", "needs-title-rewrite"}
_DURATION_REASON = "Нужно определить длительность ролика"
_RANGE_REASON = "Длительность не входит в диапазон канала"


@dataclass(frozen=True)
class ChannelAllocationProfile:
    channel_id: str
    monetized: bool = False
    growth_signal: bool = False
    quota: int | None = None
    quota_locked: bool = False
    min_duration_seconds: float = 0.0
    max_duration_seconds: float = inf

    @classmethod
    def from_record(cls, value: Mapping[str, object], *, require_channel: bool = True) -> "ChannelAllocationProfile":
        channel_id = str(value.get("channelId", value.get("id", ""))).strip()
        if require_channel and not channel_id:
            raise ValueError("Для профиля распределения нужен канал")
        minimum = max(0.0, float(value.get("minDurationSeconds", 0) or 0))
        maximum = float(value.get("maxDurationSeconds", inf) or inf)
        if maximum < minimum:
            raise ValueError("Максимальная длительность не может быть меньше минимальной")
        raw_quota = value.get("quota")
        quota = None if raw_quota in (None, "") else max(0, int(raw_quota))
        return cls(
            channel_id=channel_id,
            monetized=bool(value.get("monetized", False)),
            growth_signal=bool(value.get("growthSignal", False)),
            quota=quota,
            quota_locked=bool(value.get("quotaLocked", False)),
            min_duration_seconds=minimum,
            max_duration_seconds=maximum,
        )

    def record(self) -> dict:
        record = asdict(self)
        return {
            "channelId": record["channel_id"],
            "monetized": record["monetized"],
            "growthSignal": record["growth_signal"],
            "quota": record["quota"],
            "quotaLocked": record["quota_locked"],
            "minDurationSeconds": record["min_duration_seconds"],
            "maxDurationSeconds": record["max_duration_seconds"] if record["max_duration_seconds"] != inf else 0,
        }


def recommend_quota(profile: Mapping[str, object] | ChannelAllocationProfile) -> int:
    """Return the user-agreed 3/2/1 quota without changing persisted data."""

    normalized = profile if isinstance(profile, ChannelAllocationProfile) else ChannelAllocationProfile.from_record(profile, require_channel=False)
    if normalized.quota_locked:
        return normalized.quota if normalized.quota is not None else 0
    if normalized.monetized:
        return 3
    if normalized.growth_signal:
        return 2
    return 1


def _is_ready(value: Mapping[str, object]) -> bool:
    return str(value.get("status", "ready")) in _EDITABLE_STATUSES


def _duration(value: Mapping[str, object]) -> float | None:
    raw = value.get("durationSeconds")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        parsed = float(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def duration_matches(job: Mapping[str, object], profile: Mapping[str, object] | ChannelAllocationProfile) -> bool:
    """Whether a real measured duration fits one selected channel profile."""

    duration = _duration(job)
    normalized = profile if isinstance(profile, ChannelAllocationProfile) else ChannelAllocationProfile.from_record(profile)
    return duration is not None and normalized.min_duration_seconds <= duration <= normalized.max_duration_seconds


def _profiles(values: Sequence[Mapping[str, object]]) -> list[ChannelAllocationProfile]:
    unique: set[str] = set()
    profiles: list[ChannelAllocationProfile] = []
    for value in values:
        profile = ChannelAllocationProfile.from_record(value)
        if profile.channel_id in unique:
            raise ValueError(f"Канал «{profile.channel_id}» повторён в конструкторе")
        unique.add(profile.channel_id)
        profiles.append(profile)
    return profiles


def _assigned_by_channel(jobs: Sequence[Mapping[str, object]]) -> dict[str, list[str]]:
    assigned: dict[str, list[str]] = {}
    for job in jobs:
        channel = str(job.get("channelId", "")).strip()
        job_id = str(job.get("id", "")).strip()
        if channel and job_id:
            assigned.setdefault(channel, []).append(job_id)
    return assigned


def build_allocation_summary(
    profiles: Sequence[Mapping[str, object]],
    jobs: Sequence[Mapping[str, object]],
) -> dict:
    """Build review data and counters without moving any publication job."""

    normalized = _profiles(profiles)
    assigned = _assigned_by_channel(jobs)
    ready = [job for job in jobs if _is_ready(job)]
    unassigned_ready = [job for job in ready if not str(job.get("channelId", "")).strip()]
    missing_duration_ids = [
        str(job.get("id", "")) for job in unassigned_ready
        if str(job.get("id", "")).strip() and _duration(job) is None
    ]
    channels = []
    for profile in normalized:
        recommended = recommend_quota(profile)
        channels.append({
            "channelId": profile.channel_id,
            "monetized": profile.monetized,
            "growthSignal": profile.growth_signal,
            "recommendedQuota": recommended,
            "quota": profile.quota if profile.quota is not None else recommended,
            "quotaLocked": profile.quota_locked,
            "minDurationSeconds": profile.min_duration_seconds,
            "maxDurationSeconds": profile.max_duration_seconds if profile.max_duration_seconds != inf else 0,
            "assignedJobIds": assigned.get(profile.channel_id, []),
        })
    required = sum(int(channel["quota"]) for channel in channels)
    assigned_count = sum(len(channel["assignedJobIds"]) for channel in channels)
    return {
        "channels": channels,
        "counters": {
            "required": required,
            "ready": len(ready),
            "assigned": assigned_count,
            "missing": max(required - assigned_count, 0),
            "reserve": len(unassigned_ready),
        },
        "missingDurationJobIds": missing_duration_ids,
    }


def allocate_ready_jobs(
    profiles: Sequence[Mapping[str, object]],
    jobs: Sequence[Mapping[str, object]],
) -> dict:
    """Propose only compatible, currently unassigned ready-job allocations.

    Existing assignments stay untouched. A caller must explicitly apply the
    returned assignments to Settings; this function is pure and non-destructive.
    """

    normalized = _profiles(profiles)
    candidates = [
        job for job in jobs
        if _is_ready(job) and not str(job.get("channelId", "")).strip() and str(job.get("id", "")).strip()
    ]
    assignments: dict[str, list[str]] = {profile.channel_id: [] for profile in normalized}
    consumed: set[str] = set()
    skipped: dict[str, str] = {}
    for job in candidates:
        job_id = str(job["id"])
        if _duration(job) is None:
            skipped[job_id] = _DURATION_REASON
    # Reserve the longest compatible videos for monetized channels first.
    # This is intentionally independent from the order in which the operator
    # selected rows, so a long video cannot be consumed by a fresh channel
    # merely because it was listed first in the queue.
    ranked_profiles = sorted(enumerate(normalized), key=lambda item: (not item[1].monetized, item[0]))
    for _position, profile in ranked_profiles:
        target = recommend_quota(profile)
        ranked_candidates = sorted(
            candidates,
            key=lambda job: _duration(job) or 0,
            reverse=profile.monetized,
        )
        for job in ranked_candidates:
            job_id = str(job["id"])
            if len(assignments[profile.channel_id]) >= target or job_id in consumed or job_id in skipped:
                continue
            if duration_matches(job, profile):
                assignments[profile.channel_id].append(job_id)
                consumed.add(job_id)
    for job in candidates:
        job_id = str(job["id"])
        if job_id not in consumed and job_id not in skipped and not any(duration_matches(job, profile) for profile in normalized):
            skipped[job_id] = _RANGE_REASON
    # The choice is priority-based, while the displayed assignment keeps the
    # queue's original order. This makes the recommendation easier to review
    # and preserves stable UI/test output for an unchanged queue.
    queue_order = {str(job.get("id", "")): index for index, job in enumerate(candidates)}
    for job_ids in assignments.values():
        job_ids.sort(key=lambda job_id: queue_order.get(job_id, len(queue_order)))
    return {
        "assignments": assignments,
        "skipped": skipped,
        "summary": build_allocation_summary(profiles, jobs),
    }
