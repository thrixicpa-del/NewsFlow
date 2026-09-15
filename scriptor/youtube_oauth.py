"""Google OAuth helpers for NewsFlow's local YouTube publisher.

Network-dependent imports stay inside the actual flow so that the local queue,
tests and offline desktop screens remain usable before the user supplies a
Google Desktop Client JSON file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_READ_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
YOUTUBE_MONETARY_SCOPE = "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
GOOGLE_OPENID_SCOPE = "openid"
GOOGLE_EMAIL_SCOPE = "email"


@dataclass(frozen=True)
class CloudflareOAuthSession:
    """Private, short-lived capability used only by the desktop core process."""

    session_id: str
    poll_capability: str
    authorization_url: str
    expires_at: datetime


def _oauth_service_url(service_url: str) -> str:
    parsed = urllib.parse.urlsplit(str(service_url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Адрес сервиса входа должен быть HTTPS-адресом без параметров")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _handoff_json_request(url: str, *, method: str, payload: dict | None = None, capability: str = "") -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        # Cloudflare rejects urllib's generic Python user agent before it can
        # create an OAuth session. Identify the desktop client explicitly.
        "User-Agent": "NewsFlow Studio OAuth/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    if capability:
        headers["Authorization"] = f"Bearer {capability}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("Не удалось получить ответ от сервиса входа") from exc
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Сервис входа вернул некорректный ответ") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Сервис входа вернул некорректный ответ")
    return value


def start_cloudflare_channel_authorization(
    service_url: str,
    profile_id: str,
    *,
    include_monetary: bool,
) -> CloudflareOAuthSession:
    """Create a remote handoff without sending local tokens or browser data."""

    base_url = _oauth_service_url(service_url)
    response = _handoff_json_request(
        f"{base_url}/oauth/youtube/sessions",
        method="POST",
        payload={"channelProfileId": str(profile_id), "includeMonetary": bool(include_monetary)},
    )
    session_id = str(response.get("sessionId", ""))
    poll_capability = str(response.get("pollCapability", ""))
    authorization_url = str(response.get("authorizationUrl", ""))
    expires_at_text = str(response.get("expiresAt", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session_id) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", poll_capability):
        raise RuntimeError("Сервис входа вернул некорректную сессию")
    parsed_authorization = urllib.parse.urlsplit(authorization_url)
    if parsed_authorization.scheme != "https" or parsed_authorization.netloc != "accounts.google.com":
        raise RuntimeError("Сервис входа вернул небезопасную ссылку Google")
    try:
        expires_at = datetime.fromisoformat(expires_at_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("Сервис входа вернул некорректный срок сессии") from exc
    return CloudflareOAuthSession(session_id, poll_capability, authorization_url, expires_at)


def open_channel_authorization(chrome_executable: str, profile_dir: Path, authorization_url: str) -> None:
    """Open Google in one dedicated NewsFlow Chrome profile."""

    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 3  # SW_SHOWMAXIMIZED
    subprocess.Popen([
        chrome_executable,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "--start-maximized",
        authorization_url,
    ], startupinfo=startupinfo)


def wait_for_cloudflare_credentials(
    service_url: str,
    session: CloudflareOAuthSession,
    *,
    timeout_seconds: float = 600.0,
    poll_seconds: float = 1.5,
) -> dict[str, Any]:
    """Consume credentials once; every terminal remote state has a safe local message."""

    base_url = _oauth_service_url(service_url)
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    messages = {
        "denied": "Доступ Google не предоставлен",
        "expired": "Вход не завершён за 10 минут",
        "cancelled": "Вход в Google отменён",
        "consumed": "Сессия входа уже использована. Начните заново.",
    }
    while time.monotonic() <= deadline:
        response = _handoff_json_request(
            f"{base_url}/oauth/youtube/sessions/{session.session_id}/consume",
            method="POST",
            capability=session.poll_capability,
        )
        status = str(response.get("status", ""))
        if status == "ready":
            credentials = response.get("credentials")
            if isinstance(credentials, dict) and isinstance(credentials.get("refresh_token"), str) and credentials["refresh_token"]:
                return credentials
            raise RuntimeError("Сервис входа не вернул постоянный доступ к каналу")
        if status in messages:
            raise RuntimeError(messages[status])
        if status != "pending":
            raise RuntimeError("Сервис входа вернул некорректный статус")
        time.sleep(max(0.1, poll_seconds))
    raise RuntimeError("Вход не завершён за 10 минут")


def cancel_cloudflare_authorization(service_url: str, session: CloudflareOAuthSession) -> None:
    base_url = _oauth_service_url(service_url)
    _handoff_json_request(
        f"{base_url}/oauth/youtube/sessions/{session.session_id}/cancel",
        method="POST",
        capability=session.poll_capability,
    )


def youtube_oauth_scopes(*, include_monetary: bool) -> list[str]:
    """Return the smallest OAuth scope set required by the chosen features."""

    scopes = [GOOGLE_OPENID_SCOPE, GOOGLE_EMAIL_SCOPE, YOUTUBE_UPLOAD_SCOPE, YOUTUBE_READ_SCOPE, YOUTUBE_ANALYTICS_SCOPE]
    if include_monetary:
        scopes.append(YOUTUBE_MONETARY_SCOPE)
    return scopes


def validate_desktop_client_file(path: str | Path) -> dict[str, Any]:
    """Validate a Google OAuth JSON without touching the network."""

    client_path = Path(path)
    if not client_path.is_file() or client_path.suffix.casefold() != ".json":
        raise ValueError("Выберите существующий Google OAuth Desktop Client JSON")
    try:
        payload = json.loads(client_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("OAuth-файл Google не удалось прочитать") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("installed"), dict):
        raise ValueError("Нужен OAuth-клиент типа Desktop app (раздел installed)")
    return payload


def authorize_desktop_channel(
    path: str | Path,
    *,
    include_monetary: bool,
    browser_command: str | None = None,
) -> dict[str, Any]:
    """Open Google's consent page and return a serializable token payload.

    This function is called only from the explicit UI action. The caller can
    provide a Chrome command with a NewsFlow-owned ``--user-data-dir`` so an
    OAuth login cannot accidentally reuse the operator's everyday browser.
    It never accepts a Google password or Chrome cookie from the interface.
    """

    validate_desktop_client_file(path)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Для подключения YouTube установите google-auth-oauthlib и google-api-python-client в runtime NewsFlow."
        ) from exc
    flow = InstalledAppFlow.from_client_secrets_file(str(path), scopes=youtube_oauth_scopes(include_monetary=include_monetary))
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=True,
        authorization_prompt_message="",
        browser=browser_command,
    )
    return json.loads(credentials.to_json())
