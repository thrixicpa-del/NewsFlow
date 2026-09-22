"""Thin, testable YouTube API adapter used after explicit OAuth consent."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


YOUTUBE_TAG_CHARACTER_LIMIT = 500
YOUTUBE_DESCRIPTION_BYTE_LIMIT = 5000


def youtube_tag_character_length(tags: Iterable[object]) -> int:
    """Return YouTube's effective tag-list length, including commas and quoted spaces."""

    normalized = [" ".join(str(value or "").split()) for value in tags]
    normalized = [value for value in normalized if value]
    if not normalized:
        return 0
    return (
        sum(len(value) + (2 if " " in value else 0) for value in normalized)
        + max(0, len(normalized) - 1)
    )


def validate_youtube_description(value: object, *, limit: int = YOUTUBE_DESCRIPTION_BYTE_LIMIT) -> str:
    """Return a YouTube-safe description or raise before an upload can fail."""

    description = str(value or "")
    if "<" in description or ">" in description:
        raise ValueError("Описание YouTube не может содержать символы < или >")
    if len(description.encode("utf-8")) > int(limit):
        raise ValueError(f"Описание YouTube превышает лимит {int(limit)} байт UTF-8")
    return description


def parse_google_account_email(payload: dict[str, Any]) -> str:
    """Return the verified Google identity reported for the OAuth grant."""

    email = str(payload.get("email", "")).strip()
    if "@" not in email:
        raise ValueError("Google не вернул адрес авторизованного аккаунта")
    return email


def fetch_google_account_email(credentials_payload: dict[str, Any]) -> str:
    """Identify the Google account behind an explicitly authorised token."""

    try:
        from google.auth.transport.requests import AuthorizedSession, Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google OAuth.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    response = AuthorizedSession(credentials).get("https://openidconnect.googleapis.com/v1/userinfo", timeout=15)
    if not response.ok:
        raise RuntimeError("Не удалось определить авторизованный Google-аккаунт")
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError("Google вернул некорректный профиль аккаунта") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Google вернул некорректный профиль аккаунта")
    return parse_google_account_email(payload)


def parse_analytics_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Map a YouTube Analytics response using its returned column headers.

    Google explicitly permits report column ordering to follow the query, so
    callers must not assume that a metric occupies a fixed array position.
    """

    headers = payload.get("columnHeaders", []) if isinstance(payload, dict) else []
    names = [str(item.get("name", "")).strip() for item in headers if isinstance(item, dict)]
    if not names or len(names) != len(headers):
        return []
    result: list[dict[str, Any]] = []
    for row in payload.get("rows", []) if isinstance(payload, dict) else []:
        if not isinstance(row, list) or len(row) != len(names):
            continue
        result.append(dict(zip(names, row, strict=True)))
    return result


def fetch_youtube_analytics(
    credentials_payload: dict[str, Any],
    *,
    include_monetary: bool,
    days: int = 30,
) -> dict[str, Any]:
    """Return channel/day and top-video metrics available to this OAuth grant.

    The Reporting API is intentionally not required here: Analytics queries
    are interactive and enough for the dashboard. A failed optional report is
    represented as an explanatory error while successful public metrics keep
    rendering.
    """

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google YouTube API.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    analytics = build("youtubeAnalytics", "v2", credentials=credentials, cache_discovery=False)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=max(1, min(int(days), 365)) - 1)
    base = {"ids": "channel==MINE", "startDate": start.isoformat(), "endDate": end.isoformat()}
    errors: list[str] = []

    def request_report(*, dimensions: str, metrics: str, **extra: Any) -> list[dict[str, Any]]:
        try:
            response = analytics.reports().query(
                **base, dimensions=dimensions, metrics=metrics, **extra,
            ).execute()
            return parse_analytics_rows(response)
        except Exception as exc:  # the API reports metric/scope availability at runtime
            errors.append(str(exc)[:220])
            return []

    daily = request_report(
        dimensions="day",
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained,subscribersLost",
    )
    videos = request_report(
        dimensions="video",
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares",
        sort="-views",
        maxResults=100,
    )
    # Impressions are requested separately because channels can have a metric
    # availability restriction that should not hide their basic video rows.
    impressions = request_report(
        dimensions="video",
        metrics="impressions,impressionsClickThroughRate",
        sort="-impressions",
        maxResults=100,
    )
    by_video = {str(item.get("video", "")): dict(item) for item in videos if str(item.get("video", ""))}
    for item in impressions:
        video_id = str(item.get("video", ""))
        if video_id:
            by_video.setdefault(video_id, {"video": video_id}).update(item)
    revenue: list[dict[str, Any]] = []
    financial_available = False
    if include_monetary:
        revenue = request_report(dimensions="day", metrics="estimatedRevenue")
        financial_available = bool(revenue) and not any("estimatedRevenue" in error for error in errors)
    return {
        "daily": daily,
        "videos": list(by_video.values()),
        "revenue": revenue,
        "financialAvailable": financial_available,
        "errors": errors,
        "credentials": json.loads(credentials.to_json()),
    }


def normalize_youtube_tags(tags: Iterable[object], *, limit: int = YOUTUBE_TAG_CHARACTER_LIMIT) -> list[str]:
    """Keep ordered whole tags that fit YouTube's combined 500-character limit.

    The sequence submitted through the API is the same sequence shown later in
    Creator Studio.  Removing excess locally avoids a rejected upload and
    never cuts a tag in the middle.
    """

    if limit < 1:
        raise ValueError("Лимит символов тегов должен быть положительным")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = " ".join(str(raw or "").split())
        identity = tag.casefold()
        if not tag or identity in seen:
            continue
        candidate_length = youtube_tag_character_length([*normalized, tag])
        if candidate_length > limit:
            break
        normalized.append(tag)
        seen.add(identity)
    return normalized


def parse_current_channel(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the one authenticated channel from a channels.list response."""

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError(
            "У выбранного Google-аккаунта нет доступного YouTube-канала: "
            "при нескольких бренд-каналах сделайте нужный канал каналом по умолчанию "
            "в настройках YouTube и подключите его повторно"
        )
    item = items[0]
    snippet = item.get("snippet", {}) if isinstance(item.get("snippet"), dict) else {}
    statistics = item.get("statistics", {}) if isinstance(item.get("statistics"), dict) else {}
    thumbnails = snippet.get("thumbnails", {}) if isinstance(snippet.get("thumbnails"), dict) else {}
    thumbnail_url = ""
    for size in ("high", "medium", "default"):
        candidate = thumbnails.get(size, {})
        if isinstance(candidate, dict) and str(candidate.get("url", "")).strip():
            thumbnail_url = str(candidate["url"])
            break
    channel_id = str(item.get("id", "")).strip()
    if not channel_id:
        raise ValueError("YouTube не вернул ID подключённого канала")
    try:
        subscribers = int(statistics.get("subscriberCount", 0))
    except (TypeError, ValueError):
        subscribers = 0
    try:
        views_total = int(statistics.get("viewCount", 0))
    except (TypeError, ValueError):
        views_total = 0
    return {
        "channelId": channel_id,
        "name": str(snippet.get("title", "")).strip() or channel_id,
        "thumbnailUrl": thumbnail_url,
        "subscribers": subscribers,
        "viewsTotal": views_total,
    }


def build_private_video_insert_body(
    *,
    title: str,
    description: str,
    tags: list[str],
    publish_at: str = "",
    privacy: str = "private",
) -> dict[str, Any]:
    """Construct only safe YouTube metadata for a NewsFlow package upload."""

    clean_title = " ".join(str(title).split())
    if not 0 < len(clean_title) <= 100:
        raise ValueError("Заголовок YouTube должен содержать от 1 до 100 символов")
    resolved_privacy = str(privacy).strip().lower() or "private"
    if resolved_privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Некорректный privacy режим YouTube")
    if publish_at and resolved_privacy != "private":
        raise ValueError("Запланированная публикация YouTube должна начинаться в режиме private")
    status: dict[str, Any] = {"privacyStatus": resolved_privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        scheduled = datetime.fromisoformat(publish_at)
        if scheduled.tzinfo is None:
            raise ValueError("Время публикации должно содержать часовой пояс")
        status["publishAt"] = scheduled.isoformat()
    if "<" in clean_title or ">" in clean_title:
        raise ValueError("Заголовок YouTube не может содержать символы < или >")
    clean_description = validate_youtube_description(description)
    return {
        "snippet": {
            "title": clean_title,
            "description": clean_description,
            "tags": normalize_youtube_tags(tags),
        },
        "status": status,
    }


def fetch_current_channel(credentials_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch profile data and return any refreshed credential serialization.

    Imports are delayed so missing optional Google packages do not prevent
    NewsFlow from starting before a user configures YouTube publishing.
    """

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google YouTube API.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
    return parse_current_channel(response), json.loads(credentials.to_json())


def upload_private_video(
    credentials_payload: dict[str, Any],
    *,
    video_path: str,
    body: dict[str, Any],
    thumbnail_path: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Upload one NewsFlow package using an explicitly authorised channel.

    The request is always created from ``build_private_video_insert_body``:
    it is private until YouTube reaches the selected ``publishAt``.  A
    returned ID is the only proof used by the queue to mark a job uploaded.
    """

    source = Path(video_path)
    if not source.is_file():
        raise ValueError("MP4 для публикации не найден")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google YouTube API.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(source), mimetype="video/mp4", resumable=True),
    ).execute()
    video_id = str(response.get("id", "")).strip() if isinstance(response, dict) else ""
    if not video_id:
        raise RuntimeError("YouTube не вернул ID после загрузки ролика")
    cover = Path(thumbnail_path)
    if cover.is_file():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(cover), resumable=True),
        ).execute()
    return {
        "videoId": video_id,
        "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
        "privacyStatus": str((response.get("status") or {}).get("privacyStatus", "private")) if isinstance(response, dict) else "private",
    }, json.loads(credentials.to_json())


def fetch_youtube_video_state(credentials_payload: dict[str, Any], video_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read back an owned YouTube video for truthful V2 stage confirmation."""
    clean_id = str(video_id or "").strip()
    if not clean_id:
        raise ValueError("Для проверки требуется YouTube video ID")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google YouTube API.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.videos().list(part="snippet,status,processingDetails", id=clean_id).execute()
    items = response.get("items", []) if isinstance(response, dict) else []
    if not items or not isinstance(items[0], dict):
        raise RuntimeError("YouTube не подтвердил существование ролика по сохранённому ID")
    return dict(items[0]), json.loads(credentials.to_json())


def set_youtube_thumbnail(credentials_payload: dict[str, Any], video_id: str, thumbnail_path: str) -> dict[str, Any]:
    """Set one thumbnail as an independent post-upload operation."""
    source = Path(thumbnail_path)
    clean_id = str(video_id or "").strip()
    if not clean_id:
        raise ValueError("Для обложки требуется YouTube video ID")
    if not source.is_file():
        raise ValueError("Файл обложки не найден")
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError("В runtime NewsFlow не установлены библиотеки Google YouTube API.") from exc
    credentials = Credentials.from_authorized_user_info(credentials_payload)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.thumbnails().set(videoId=clean_id, media_body=MediaFileUpload(str(source), resumable=True)).execute()
    return {"response": response if isinstance(response, dict) else {}, "credentials": json.loads(credentials.to_json())}
