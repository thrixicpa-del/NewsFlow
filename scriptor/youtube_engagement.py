"""Deterministic plans and state for YouTube post/card/end-screen work.

The module never opens a browser or touches OAuth data.  It only selects safe
same-channel targets and records resumable state for the Studio adapter.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Mapping, Sequence


_TERMINAL_STATUSES = {"scheduled", "done", "failed", "skipped"}
_VALID_STEPS = {"post", "cards", "endScreen", "ads"}
_VALID_STATUSES = {"pending", "running", "scheduled", "done", "failed", "skipped"}


def _duration(value: Mapping[str, object]) -> float:
    try:
        return max(0.0, float(value.get("durationSeconds") or 0))
    except (TypeError, ValueError):
        return 0.0


def _eligible_catalog(job: Mapping[str, object], catalog: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    channel_id = str(job.get("channelId", "")).strip()
    current_video_id = str(job.get("videoId", "")).strip()
    eligible = [
        item for item in catalog
        if str(item.get("channelId", "")).strip() == channel_id
        and str(item.get("privacyStatus", "")).strip() == "public"
        and str(item.get("videoId", "")).strip()
        and str(item.get("title", "")).strip()
        and str(item.get("videoId", "")).strip() != current_video_id
    ]
    return sorted(
        eligible,
        key=lambda item: (-float(item.get("score", 0) or 0), str(item.get("publishedAt", ""))),
    )


def build_ad_plan(
    duration_seconds: float,
    *,
    monetized: bool,
    interval_seconds: int = 39,
) -> dict:
    """Build the canonical Studio monetization plan without touching YouTube."""
    try:
        duration = max(0, int(float(duration_seconds or 0)))
        interval = int(interval_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("Длительность и интервал рекламы должны быть числами") from error
    if interval < 1:
        raise ValueError("Интервал рекламных слотов должен быть положительным")
    if not monetized:
        return {
            "enabled": False,
            "mode": "NONE",
            "monetizationEnabled": False,
            "automatic": False,
            "automaticSlotsEnabled": False,
            "manual": False,
            "manualMidrollApplicable": False,
            "midRollEligible": False,
            "manualSlots": [],
            "manualSlotsSeconds": [],
            "intervalSeconds": interval,
        }

    applicable = duration >= 8 * 60
    slots = [
        second for second in range(interval, duration, interval)
        if applicable and second + 15 <= duration
    ]
    mode = "AUTO+MANUAL" if applicable else "AUTO_ONLY"
    return {
        "enabled": True,
        "mode": mode,
        "monetizationEnabled": True,
        "automatic": True,
        "automaticSlotsEnabled": True,
        "manual": applicable,
        "manualMidrollApplicable": applicable,
        "midRollEligible": applicable,
        "manualSlots": slots,
        "manualSlotsSeconds": slots,
        "intervalSeconds": interval,
    }


def build_engagement_plan(
    job: Mapping[str, object],
    catalog: Sequence[Mapping[str, object]],
    playlists: Sequence[Mapping[str, object]],
) -> dict:
    """Choose same-channel public targets and deterministic placement times."""

    duration = _duration(job)
    targets = _eligible_catalog(job, catalog)
    # YouTube Studio allows up to five cards.  Plan only same-channel
    # public videos that have a visible title, because Studio's own-video
    # picker is reliable by title rather than by opaque video ID.
    card_ratios = (0.17, 0.33, 0.50, 0.67, 0.83)
    cards = [
        {
            "videoId": str(item["videoId"]),
            "videoTitle": str(item["title"]).strip(),
            "atSeconds": round(duration * ratio),
        }
        for ratio, item in zip(card_ratios, targets[:5])
        if round(duration * ratio) < duration - 20
    ]
    if duration < 25:
        end_screen = {"status": "skipped", "reason": "Видео короче 25 секунд", "items": []}
    else:
        playlist = next(
            (
                str(item.get("playlistId", "")).strip()
                for item in playlists
                if str(item.get("channelId", "")).strip() == str(job.get("channelId", "")).strip()
                and bool(item.get("public", True))
                and str(item.get("playlistId", "")).strip()
            ),
            "",
        )
        end_screen_items = [
            *([
                {
                    "kind": "video",
                    "videoId": str(targets[0]["videoId"]),
                    "videoTitle": str(targets[0]["title"]).strip(),
                },
            ] if targets else []),
            {"kind": "best-for-viewer"},
            *([{"kind": "playlist", "playlistId": playlist}] if playlist else []),
            {"kind": "subscribe"},
        ][:4]
        end_screen = {
            "startSeconds": round(duration - 20),
            "items": end_screen_items,
        }
    return {"cards": cards, "endScreen": end_screen}


def new_engagement_state(job_id: str, channel_id: str) -> dict:
    """Create a serializable, retryable state record for one publication job."""

    return {
        "jobId": str(job_id).strip(),
        "channelId": str(channel_id).strip(),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "post": {"status": "pending"},
        "cards": {"status": "pending"},
        "endScreen": {"status": "pending"},
        "ads": {"status": "pending", "mode": "PENDING", "automatic": False, "manual": False,
                "manualSlots": [], "manualMidrollApplicable": None},
        "attempts": [],
    }


def transition_engagement_step(state: Mapping[str, object], step: str, status: str, **fields: object) -> dict:
    """Return an updated state without allowing a terminal step to regress."""

    if step not in _VALID_STEPS:
        raise ValueError("Неизвестный шаг автоматизации")
    if status not in _VALID_STATUSES:
        raise ValueError("Неизвестный статус автоматизации")
    result = deepcopy(dict(state))
    current = dict(result.get(step, {}))
    if str(current.get("status", "pending")) in _TERMINAL_STATUSES and status not in _TERMINAL_STATUSES:
        raise ValueError("Завершённый шаг нельзя вернуть в работу")
    current.update(fields)
    current["status"] = status
    current["updatedAt"] = datetime.now(timezone.utc).isoformat()
    result[step] = current
    return result


def is_terminal(state: Mapping[str, object]) -> bool:
    """Whether every Studio step has reached a non-retry state."""

    return all(str(dict(state.get(step, {})).get("status", "pending")) in _TERMINAL_STATUSES for step in _VALID_STEPS)
