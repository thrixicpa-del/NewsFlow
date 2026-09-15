from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import tempfile
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


API_BASE = "https://secret-voicer.ru/api/v1"
PUBLIC_VOICES = "https://secretvoicer.com/api/public/showcase-voices-filtered/"
VOICE_BROWSER_URL = "https://secretvoicer.com/app/"
_BROWSER_QUEUE = threading.Lock()
# A Chrome profile can be controlled by only one persistent Playwright context.
# Keeping it alive also keeps a separate, inspectable tab for every scenario.
_BROWSER_RUNTIMES: dict[str, tuple[object, object]] = {}


class VoicerError(RuntimeError):
    pass


@dataclass
class VoiceProfile:
    name: str = "Новости"
    voice_id: str = ""
    stability: float = 0.30
    style: float = 0.50
    voice_name: str = ""
    provider: str = "chrome"
    model_id: str = ""
    template_id: str = ""
    template_signature: str = ""
    settings_preset: str = "standard"
    chunk_size: int = 1200
    delay_between_chunks: float = 0.5
    task_threads: int = 5
    secret_mode: str = "emotional"
    # W-Voice (WProject) exposes these controls directly in its documented
    # TTS request.  They live on the profile and therefore get frozen into a
    # NewsFlow job snapshot before an external task starts.
    wproject_split: str = "single"
    wproject_join: bool = True
    wproject_join_pause: float = 0.3
    wproject_autotag: str = "off"
    wproject_prosody_speed: float = 1.0
    wproject_prosody_volume: float = 0.0
    wproject_latency: str = "normal"
    wproject_normalize: bool = True
    wproject_normalize_loudness: bool = True
    wproject_tag_compat: bool = True


def split_text(text: str, maximum: int = 4000) -> list[str]:
    rest = " ".join((text or "").split()).strip()
    result: list[str] = []
    while len(rest) > maximum:
        window = rest[:maximum + 1]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "), window.rfind(" "))
        cut = cut + 1 if cut > maximum * 0.55 else maximum
        result.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        result.append(rest)
    return result


def safe_audio_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "_", value).strip(" ._")
    return (name or "Озвучка")[:120] + ".mp3"


class SecretVoicerClient:
    """Small, dependency-free implementation of the stable Secret Voicer API contract."""

    def __init__(self, api_key: str, poll_seconds: float = 3.0):
        if not api_key.strip():
            raise VoicerError("Добавьте активный API-ключ Secret Voicer")
        self.api_key = api_key.strip()
        self.poll_seconds = poll_seconds

    def _request(self, method: str, url: str, body: dict | None = None, *, key: bool = True):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"User-Agent": "NewsFlow/0.3"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if key:
            headers["X-API-Key"] = self.api_key
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return raw, response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(text)
                message = detail.get("error") or detail.get("detail") or text
            except Exception:
                message = text
            raise VoicerError(f"Secret Voicer: {message or exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VoicerError(f"Нет соединения с Secret Voicer: {exc.reason}") from exc

    def _json(self, method: str, path: str, body: dict | None = None, *, key: bool = True) -> dict:
        raw, _ = self._request(method, f"{API_BASE}{path}" if path.startswith("/") else path, body, key=key)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise VoicerError("Secret Voicer вернул непонятный ответ") from exc

    def voices(self) -> list[dict]:
        catalog = self._json("GET", "/voices").get("voices", [])
        try:
            raw, _ = self._request("GET", PUBLIC_VOICES, key=False)
            showcase = json.loads(raw.decode("utf-8")).get("voices", [])
        except Exception:
            showcase = []
        preview_by_id = {str(item.get("voice_id", "")): item for item in showcase}
        return [{**preview_by_id.get(str(item.get("voice_id", "")), {}), **item} for item in catalog]

    def account_info(self) -> dict:
        """Return account/quota data when the installed API exposes it.

        Secret Voicer installations have used more than one account endpoint.
        We try only read-only endpoints and deliberately do not guess a balance:
        if the server does not expose one, the caller receives a clear status.
        """
        failures: list[str] = []
        for path in ("/account", "/balance", "/me"):
            try:
                result = self._json("GET", path)
                if isinstance(result, dict):
                    return result
            except VoicerError as exc:
                failures.append(str(exc))
        raise VoicerError("Secret Voicer API не вернул баланс по доступным read-only endpoint'ам")

    def balance_label(self) -> str:
        """Convert common quota fields to a compact display label without loss."""
        payload = self.account_info()
        sources = [payload]
        for key in ("data", "account", "balance", "quota", "limits"):
            value = payload.get(key)
            if isinstance(value, dict):
                sources.append(value)
        fields = (
            ("balance", "Баланс"), ("credits", "Кредиты"),
            ("remaining", "Остаток"), ("characters_remaining", "Символов"),
            ("characters", "Символов"), ("tokens", "Токенов"),
            ("subscription", "Подписка"), ("plan", "Тариф"),
        )
        parts = []
        for source in sources:
            for key, title in fields:
                value = source.get(key)
                if value not in (None, "", [], {}):
                    part = f"{title}: {value}"
                    if part not in parts:
                        parts.append(part)
        if not parts:
            raise VoicerError("Secret Voicer API ответил, но не передал поля баланса или лимита")
        return " · ".join(parts[:3])

    def synthesize(self, text: str, profile: VoiceProfile,
                   progress: Callable[[str, int], None] | None = None) -> bytes:
        if not profile.voice_id.strip():
            raise VoicerError("Выберите Voice ID в профиле")
        chunks = split_text(text)
        if not chunks:
            raise VoicerError("Добавьте текст для озвучки")
        audio: list[bytes] = []
        for position, chunk in enumerate(chunks, 1):
            if progress:
                progress(f"Отправляем часть {position}/{len(chunks)}", round((position - 1) * 100 / len(chunks)))
            created = self._json("POST", "/synthesize", {
                "text": chunk, "voice_id": profile.voice_id,
                # This is the full current public Secret Voicer API choice:
                # standard or emotional. model_id is documented as legacy.
                "mode": profile.secret_mode if profile.secret_mode in {"standard", "emotional"} else "emotional",
                "stability": float(profile.stability), "style": float(profile.style),
            })
            task_id = created.get("task_id")
            if not task_id:
                raise VoicerError("Secret Voicer не вернул номер задачи")
            result = None
            for attempt in range(60):
                result = self._json("GET", f"/task/{task_id}")
                status = str(result.get("status", "")).upper()
                task_progress = result.get("progress")
                percent = int(float(task_progress) * 100) if isinstance(task_progress, (float, int)) and task_progress <= 1 else int(task_progress or min(95, attempt * 3))
                if progress:
                    total = int(((position - 1) + max(0, min(100, percent)) / 100) * 100 / len(chunks))
                    progress("Secret Voicer обрабатывает текст" if status != "PENDING" else "Ожидание в очереди", total)
                if status == "COMPLETED":
                    break
                if status == "FAILED":
                    raise VoicerError(str(result.get("error_message") or "Secret Voicer вернул ошибку"))
                time.sleep(self.poll_seconds)
            if not result or str(result.get("status", "")).upper() != "COMPLETED" or not result.get("audio_url"):
                raise VoicerError("Таймаут ожидания озвучки (3 минуты)")
            raw, _ = self._request("GET", str(result["audio_url"]), key=False)
            audio.append(raw)
        if progress:
            progress("Озвучка готова", 100)
        return b"".join(audio)

    def save_audio(self, folder: Path, name: str, content: bytes) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_audio_name(name)
        # A full MP3 must be on disk before the next browser tab starts.  A
        # temporary file prevents the montage from seeing a half-written file.
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_bytes(content)
        temporary.replace(path)
        return path


LUMEAN_API_BASE = "https://api.lumean.app/api/public"


class LumeanClient:
    """Template-first Lumean TTS client.

    Lumean intentionally does not accept a raw voice ID in an order.  A
    template captures the voice and model first; an order then contains only
    the text.  Keeping that distinction here prevents accidentally using a
    stale voice when profiles are switched by scenario range.
    """

    def __init__(self, api_key: str, poll_seconds: float = 2.5):
        if not api_key.strip():
            raise VoicerError("Добавьте активный API-ключ Lumean")
        self.api_key = api_key.strip()
        self.poll_seconds = poll_seconds

    def _request(self, method: str, path: str, body: dict | None = None, *, timeout: int = 90,
                 headers: dict[str, str] | None = None):
        url = path if path.startswith("http") else f"{LUMEAN_API_BASE}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "User-Agent": "NewsFlow/2",
            "X-API-KEY": self.api_key,
            "X-Timezone": "Europe/Moscow",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
                detail = payload.get("message") or payload.get("detail") or payload.get("error") or raw
                if isinstance(detail, dict):
                    detail = detail.get("message") or json.dumps(detail, ensure_ascii=False)
            except Exception:
                detail = raw
            if exc.code == 402:
                detail = f"Лимит или баланс Lumean: {detail}"
            elif exc.code == 429:
                detail = f"Lumean временно ограничил запросы: {detail}"
            raise VoicerError(f"Lumean: {detail or exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VoicerError(f"Нет соединения с Lumean: {exc.reason}") from exc

    def _json(self, method: str, path: str, body: dict | None = None) -> dict:
        raw, _ = self._request(method, path, body)
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise VoicerError("Lumean вернул непонятный ответ API") from exc
        if not isinstance(value, dict):
            raise VoicerError("Lumean вернул ответ неверного формата")
        if value.get("success") is False:
            raise VoicerError(f"Lumean: {value.get('message') or value.get('error') or 'операция не выполнена'}")
        return value

    @staticmethod
    def _data(payload: dict):
        return payload.get("data", payload)

    @staticmethod
    def _items(value) -> list[dict]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            for key in ("items", "voices", "results", "data"):
                if isinstance(value.get(key), list):
                    return [item for item in value[key] if isinstance(item, dict)]
        return []

    def voices(self) -> list[dict]:
        """Return the unified voice catalogue, with the public library fallback."""
        result: list[dict] = []
        failures: list[Exception] = []
        for path in ("/voices", "/voices/elevenlabs/library?page=0&page_size=100"):
            try:
                result.extend(self._items(self._data(self._json("GET", path))))
            except VoicerError as exc:
                failures.append(exc)
        unique: dict[str, dict] = {}
        for item in result:
            voice_id = str(item.get("voice_id") or item.get("id") or item.get("voiceId") or "").strip()
            if voice_id:
                unique[voice_id] = {**item, "voice_id": voice_id,
                                    "name": str(item.get("name") or item.get("voice_name") or voice_id)}
        if not unique and failures:
            raise failures[-1]
        return list(unique.values())

    def models(self) -> list[str]:
        """Read provider options without hard-coding a model such as a future V3."""
        try:
            data = self._data(self._json("GET", "/templates/config-options?service=elevenlabs"))
        except VoicerError:
            return []
        values: list[str] = []
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"model_id", "models", "model"}:
                        collect(item)
                    elif isinstance(item, (dict, list)):
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, str) and value.strip():
                values.append(value.strip())
        collect(data)
        return list(dict.fromkeys(values))

    def usage(self) -> list[dict]:
        data = self._data(self._json("GET", "/usage"))
        return self._items(data)

    def balance_label(self) -> str:
        records = self.usage()
        matches = [item for item in records if "eleven" in str(item.get("service_code") or item.get("service_name") or "").casefold()]
        records = matches or records
        parts: list[str] = []
        for item in records[:4]:
            limit_type = str(item.get("limit_type") or item.get("type") or "лимит")
            remaining = item.get("remaining")
            limit = item.get("limit_value", item.get("limit"))
            if remaining is not None or limit is not None:
                parts.append(f"{limit_type}: {remaining if remaining is not None else '—'} / {limit if limit is not None else '—'}")
        return " · ".join(parts) if parts else "Lumean ответил, но не передал лимит"

    @staticmethod
    def template_signature(profile: VoiceProfile) -> str:
        source = "|".join((profile.voice_id, profile.model_id, f"{profile.stability:.3f}", f"{profile.style:.3f}"))
        import hashlib
        return hashlib.sha256(source.encode("utf-8")).hexdigest()[:20]

    def create_template(self, profile: VoiceProfile) -> str:
        if not profile.voice_id.strip():
            raise VoicerError("Для профиля Lumean выберите Voice ID")
        if not profile.model_id.strip():
            raise VoicerError("Для профиля Lumean укажите model_id из каталога сервиса")
        config = {
            "tts_settings": {
                "mode": "mode_v1",
                "model_id": profile.model_id,
                "voice_id": profile.voice_id,
                "advanced_voice_settings": True,
                "voice_settings": {
                    "stability": float(profile.stability),
                    "similarity_boost": float(profile.style),
                    "use_speaker_boost": True,
                    "speed": 1.0,
                },
            }
        }
        response = self._data(self._json("POST", "/templates", {
            "service_key": "elevenlabs", "name": f"NewsFlow — {profile.name}", "config": config,
        }))
        if isinstance(response, dict):
            template_id = response.get("id") or response.get("template_id") or response.get("uuid")
        else:
            template_id = None
        if not template_id:
            raise VoicerError("Lumean не вернул ID шаблона для озвучки")
        return str(template_id)

    def create_order(self, template_id: str, text: str) -> str:
        response = self._data(self._json("POST", "/orders", {"template_id": template_id, "input_text": text}))
        if isinstance(response, dict):
            order_id = response.get("id") or response.get("order_id") or response.get("uuid")
        else:
            order_id = None
        if not order_id:
            raise VoicerError("Lumean не вернул номер заказа")
        return str(order_id)

    def _wait_order(self, order_id: str, progress: Callable[[str, int], None] | None = None) -> list[str]:
        for attempt in range(360):
            response = self._data(self._json("GET", f"/orders/{urllib.parse.quote(order_id)}"))
            if not isinstance(response, dict):
                raise VoicerError("Lumean вернул неверный статус заказа")
            status = str(response.get("status") or "").casefold()
            result = response.get("result") if isinstance(response.get("result"), dict) else response
            files = result.get("files") if isinstance(result, dict) else None
            if status in {"completed", "partially_completed", "complete", "done"} and isinstance(files, list) and files:
                return [str(item) for item in files if str(item).strip()]
            if status in {"failed", "error", "cancelled", "canceled"}:
                raise VoicerError(str(response.get("message") or response.get("error") or "Lumean не выполнил заказ"))
            if progress:
                progress("Lumean создаёт озвучку", min(92, 25 + attempt // 4))
            time.sleep(self.poll_seconds)
        raise VoicerError("Таймаут ожидания Lumean (15 минут)")

    def _download_storage(self, storage_path: str) -> bytes:
        data = self._data(self._json("POST", "/storage/url", {"path": storage_path}))
        url = data.get("url") if isinstance(data, dict) else None
        if not url:
            raise VoicerError("Lumean не вернул ссылку на готовый MP3")
        request = urllib.request.Request(str(url), headers={"User-Agent": "NewsFlow/2"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except Exception as exc:
            raise VoicerError(f"Не удалось скачать MP3 из Lumean: {exc}") from exc

    def synthesize(self, text: str, profile: VoiceProfile,
                   progress: Callable[[str, int], None] | None = None) -> tuple[bytes, str, str]:
        if not (text or "").strip():
            raise VoicerError("Добавьте текст для озвучки")
        signature = self.template_signature(profile)
        template_id = profile.template_id if profile.template_signature == signature else ""
        if not template_id:
            if progress:
                progress("Lumean: создаём шаблон голоса", 8)
            template_id = self.create_template(profile)
        if progress:
            progress("Lumean: отправляем заказ", 20)
        files = self._wait_order(self.create_order(template_id, text), progress)
        if progress:
            progress("Lumean: скачиваем MP3", 95)
        audio = b"".join(self._download_storage(path) for path in files)
        if not audio:
            raise VoicerError("Lumean вернул пустой аудиофайл")
        if progress:
            progress("Готово", 100)
        return audio, template_id, signature


VOICEGEN_API_BASE = "https://qw1voicegencore.pro/api/v1/client"

WPROJECT_API_BASE = "https://api.wproject.space"


class WProjectClient:
    """Official W-Voice asynchronous REST client.

    API contract: https://docs.wproject.space/ (OpenAPI v1).  The client
    deliberately works only with persisted task ids, so an interrupted local
    NewsFlow process can resume polling without creating a duplicate request.
    """

    def __init__(self, api_key: str, poll_seconds: float = 2.0):
        if not api_key.strip():
            raise VoicerError("Добавьте активный API-ключ WProject")
        self.api_key = api_key.strip()
        self.poll_seconds = poll_seconds

    def _request(self, method: str, path: str, body: dict | None = None, *, timeout: int = 90,
                 headers: dict[str, str] | None = None):
        url = path if path.startswith("http") else f"{WPROJECT_API_BASE}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request_headers = {"User-Agent": "NewsFlow/2", "Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=request_headers, method=method), timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
                message = payload.get("detail") or payload.get("message") or payload.get("error") or raw
            except Exception:
                message = raw
            if exc.code == 401:
                message = "ключ WProject не принят"
            elif exc.code == 403:
                message = "ключ WProject отозван, истёк или действие недоступно"
            elif exc.code == 429:
                message = f"429 лимит WProject: {message or 'попробуйте позже'}"
            elif exc.code == 503:
                message = f"503 WProject временно недоступен: {message or 'попробуйте позже'}"
            raise VoicerError(f"WProject: {message or exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VoicerError(f"Нет соединения с WProject: {exc.reason}") from exc

    def _json(self, method: str, path: str, body: dict | None = None, *, headers: dict[str, str] | None = None):
        raw, _ = self._request(method, path, body, headers=headers)
        try:
            result = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise VoicerError("WProject вернул непонятный ответ API") from exc
        if not isinstance(result, dict):
            raise VoicerError("WProject вернул ответ неверного формата")
        return result

    def profile(self) -> dict:
        return self._json("GET", "/v1/me")

    def usage(self) -> dict:
        return self._json("GET", "/v1/usage")

    def voices(self) -> list[dict]:
        result = self._json("GET", "/v1/voices")
        values = result.get("voices", [])
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []

    def create_task(self, text: str, filename: str, profile: VoiceProfile, *, threads: int,
                    idempotency_key: str | None = None) -> str:
        if not text.strip():
            raise VoicerError("Добавьте текст для озвучки")
        if not profile.voice_id.strip():
            raise VoicerError("Для WProject выберите Voice ID")
        params = {
            "split": profile.wproject_split if profile.wproject_split in {"paragraphs", "lines", "sentences", "single"} else "single",
            "join": bool(profile.wproject_join),
            "join_pause": max(0.0, min(5.0, float(profile.wproject_join_pause))),
            "autotag": profile.wproject_autotag if profile.wproject_autotag in {"off", "light", "medium", "heavy"} else "off",
            "prosody_speed": max(.5, min(2.0, float(profile.wproject_prosody_speed))),
            "prosody_volume": max(-20.0, min(20.0, float(profile.wproject_prosody_volume))),
            "latency": profile.wproject_latency if profile.wproject_latency in {"normal", "balanced"} else "normal",
            "normalize": bool(profile.wproject_normalize),
            "normalize_loudness": bool(profile.wproject_normalize_loudness),
            "tag_compat": bool(profile.wproject_tag_compat),
        }
        key = str(idempotency_key or uuid.uuid4().hex).strip()[:128]
        if not key:
            raise VoicerError("Не удалось создать Idempotency-Key для WProject")
        result = self._json("POST", "/v1/tts", {
            "text": text, "voice_id": profile.voice_id,
            "threads": max(1, int(threads)), "params": params,
        }, headers={"Idempotency-Key": key})
        task_id = result.get("task_id")
        if not task_id:
            raise VoicerError("WProject не вернул ID задачи")
        return str(task_id)

    def wait_download(self, task_id: str, progress: Callable[[str, int], None] | None = None) -> bytes:
        for attempt in range(600):
            task = self._json("GET", f"/v1/tts/{urllib.parse.quote(task_id)}")
            state = str(task.get("state", "")).casefold()
            done, total = task.get("done", 0), task.get("total", 0)
            try:
                percentage = int(90 * float(done) / max(1, float(total)))
            except (TypeError, ValueError):
                percentage = min(90, 10 + attempt // 5)
            if state == "done":
                files = task.get("files", [])
                if not isinstance(files, list) or not files:
                    raise VoicerError("WProject завершил задачу без MP3")
                if progress:
                    progress("WProject: скачиваем MP3", 96)
                raw, _ = self._request("GET", f"/v1/tts/{urllib.parse.quote(task_id)}/file/0", timeout=120)
                if not raw:
                    raise VoicerError("WProject вернул пустой MP3")
                return raw
            if state in {"error", "cancelled"}:
                errors = task.get("errors", [])
                detail = "; ".join(str(item) for item in errors) if isinstance(errors, list) else ""
                raise VoicerError(detail or f"WProject завершил задачу: {state}")
            if progress:
                stage = str(task.get("stage") or "создаёт озвучку")
                progress(f"WProject: {stage}", max(8, min(92, percentage)))
            time.sleep(self.poll_seconds)
        raise VoicerError("Таймаут ожидания WProject (20 минут)")

    def synthesize(self, text: str, filename: str, profile: VoiceProfile, *, threads: int,
                   progress: Callable[[str, int], None] | None = None,
                   idempotency_key: str | None = None) -> bytes:
        if progress:
            progress("WProject: отправляем задачу", 8)
        return self.wait_download(
            self.create_task(text, filename, profile, threads=threads, idempotency_key=idempotency_key),
            progress,
        )


class VoiceGenClient:
    """REST client for VoiceGen's task queue, with no browser dependency."""

    def __init__(self, api_key: str, poll_seconds: float = 2.0):
        if not api_key.strip():
            raise VoicerError("Добавьте активный API-ключ VoiceGen")
        self.api_key = api_key.strip()
        self.poll_seconds = poll_seconds

    def _request(self, method: str, path: str, body: dict | None = None, *, timeout: int = 90):
        url = path if path.startswith("http") else f"{VOICEGEN_API_BASE}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {"User-Agent": "NewsFlow/2", "Authorization": f"Bearer {self.api_key}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
                return response.read(), response.headers.get_content_type()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(raw)
                message = payload.get("detail") or payload.get("message") or payload.get("error") or raw
            except Exception:
                message = raw
            if exc.code == 401:
                message = "ключ VoiceGen не принят"
            elif exc.code == 403:
                message = "ключ принят, но активная подписка VoiceGen не найдена"
            raise VoicerError(f"VoiceGen: {message or exc.code}") from exc
        except urllib.error.URLError as exc:
            raise VoicerError(f"Нет соединения с VoiceGen: {exc.reason}") from exc

    def _json(self, method: str, path: str, body: dict | None = None):
        raw, _ = self._request(method, path, body)
        try:
            value = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise VoicerError("VoiceGen вернул непонятный ответ API") from exc
        return value

    def profile(self) -> dict:
        payload = self._json("GET", "/me")
        if not isinstance(payload, dict):
            raise VoicerError("VoiceGen вернул профиль неверного формата")
        return payload

    def bootstrap(self) -> dict:
        payload = self._json("GET", "/bootstrap")
        if not isinstance(payload, dict):
            raise VoicerError("VoiceGen вернул bootstrap неверного формата")
        return payload

    def engines(self) -> list[str]:
        """Discover engines from the account's real catalogue, not a static list."""
        engines: set[str] = set()
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"voice_engines", "voice_engine", "default_voice_engine", "engine"}:
                        if isinstance(item, list):
                            engines.update(str(part).strip() for part in item if str(part).strip())
                        elif str(item).strip():
                            engines.add(str(item).strip())
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
        collect(self.bootstrap())
        return sorted(engines, key=str.casefold)

    def voices(self) -> tuple[list[dict], dict]:
        payload = self._json("GET", "/voice-catalog")
        if not isinstance(payload, dict):
            raise VoicerError("VoiceGen вернул каталог голосов неверного формата")
        voices = payload.get("voices", payload.get("items", payload.get("data", [])))
        if isinstance(voices, dict):
            voices = voices.get("voices", [])
        result = [item for item in voices if isinstance(item, dict)] if isinstance(voices, list) else []
        return result, payload.get("voice_capacity", {}) if isinstance(payload.get("voice_capacity", {}), dict) else {}

    def presets(self, engine: str = "elevenLabsV3") -> list[dict]:
        payload = self._json("GET", f"/generation-presets?voice_engine={urllib.parse.quote(engine)}")
        values = payload if isinstance(payload, list) else payload.get("presets", payload.get("data", []))
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []

    def balance_label(self) -> str:
        payload = self.profile()
        active = payload.get("has_active_subscription")
        plan = payload.get("current_plan") or "—"
        expires = payload.get("subscription_expires_at") or "—"
        worker = payload.get("api_worker_index")
        return f"{plan} · {'активна' if active else 'не активна'} · до {expires}" + (f" · worker {worker}" if worker is not None else "")

    def create_task(self, text: str, filename: str, profile: VoiceProfile, *, threads: int) -> str:
        if not text.strip():
            raise VoicerError("Добавьте текст для озвучки")
        payload: dict = {
            "text": text,
            "filename": filename,
            "thread_count": max(1, int(threads)),
            "client_task_id": f"newsflow-{int(time.time() * 1000)}",
            "auto_start": True,
        }
        template_id = getattr(profile, "template_id", "")
        if template_id:
            payload["template_id"] = template_id
        else:
            if not profile.voice_id.strip():
                raise VoicerError("Для VoiceGen выберите Voice ID")
            payload.update({
                "voice_id": profile.voice_id,
                "voice_engine": profile.model_id or "elevenLabsV3",
                "settings_preset": getattr(profile, "settings_preset", "") or "standard",
                "chunk_size": max(200, int(getattr(profile, "chunk_size", 1200) or 1200)),
                "delay_between_chunks": max(0.0, float(getattr(profile, "delay_between_chunks", .5) or 0)),
            })
        response = self._json("POST", "/tasks", payload)
        if not isinstance(response, dict):
            raise VoicerError("VoiceGen вернул создание задачи неверного формата")
        task = response.get("task", response)
        task_id = task.get("task_id") or task.get("id") if isinstance(task, dict) else None
        if not task_id:
            raise VoicerError("VoiceGen не вернул ID задачи")
        return str(task_id)

    def wait_download(self, task_id: str, progress: Callable[[str, int], None] | None = None) -> bytes:
        for attempt in range(600):
            payload = self._json("GET", f"/tasks/{urllib.parse.quote(task_id)}")
            if not isinstance(payload, dict):
                raise VoicerError("VoiceGen вернул статус задачи неверного формата")
            task = payload.get("task", payload)
            status = str(task.get("status", "")).casefold() if isinstance(task, dict) else ""
            raw_progress = task.get("progress", 0) if isinstance(task, dict) else 0
            try:
                percentage = int(float(raw_progress) * 100) if float(raw_progress) <= 1 else int(float(raw_progress))
            except (TypeError, ValueError):
                percentage = min(92, 20 + attempt // 5)
            if status == "done":
                if progress:
                    progress("VoiceGen: скачиваем MP3", 96)
                raw, _ = self._request("GET", f"/tasks/{urllib.parse.quote(task_id)}/download", timeout=120)
                if not raw:
                    raise VoicerError("VoiceGen вернул пустой MP3")
                return raw
            if status in {"error", "cancelled"}:
                detail = task.get("error") or task.get("message") or "VoiceGen завершил задачу с ошибкой"
                raise VoicerError(str(detail))
            if progress:
                progress("VoiceGen: в очереди" if status == "queued" else "VoiceGen: создаёт озвучку", max(10, min(92, percentage)))
            time.sleep(self.poll_seconds)
        raise VoicerError("Таймаут ожидания VoiceGen (20 минут)")

    def synthesize(self, text: str, filename: str, profile: VoiceProfile, *, threads: int,
                   progress: Callable[[str, int], None] | None = None) -> bytes:
        if progress:
            progress("VoiceGen: отправляем задачу", 8)
        return self.wait_download(self.create_task(text, filename, profile, threads=threads), progress)


def chrome_path() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise VoicerError("Google Chrome не найден. Установите Chrome и повторите попытку.")


def open_voice_login(profile_dir: Path) -> subprocess.Popen:
    """Open the dedicated profile for a user-controlled Telegram sign-in."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([
        str(chrome_path()), f"--user-data-dir={profile_dir}",
        "--no-first-run", "--no-default-browser-check", VOICE_BROWSER_URL,
    ])


class ChromeSecretVoicer:
    """Secret Voicer browser provider ported from Voicer's background queue.

    It controls only a dedicated local Chrome profile after the user signs in.
    Cookies and Telegram credentials are neither copied nor read from regular Chrome.
    """

    def __init__(self, profile_dir: Path, poll_seconds: float = 2.0):
        self.profile_dir = Path(profile_dir)
        self.poll_seconds = poll_seconds

    @staticmethod
    def _authorized_url(url: str) -> bool:
        value = (url or "").lower()
        return "secretvoicer.com/app" in value and "/login" not in value and "/auth" not in value

    @staticmethod
    def _click_text(page, expression: str) -> bool:
        return bool(page.evaluate("""(pattern) => {
            const re = new RegExp(pattern, 'i');
            const items = [...document.querySelectorAll('button,[role="button"],label')];
            const item = items.find((node) => re.test(node.innerText || ''));
            if (!item) return false; item.click(); return true;
        }""", expression))

    @staticmethod
    def _minimize(page) -> None:
        try:
            session = page.context.new_cdp_session(page)
            window = session.send("Browser.getWindowForTarget")
            session.send("Browser.setWindowBounds", {
                "windowId": window["windowId"], "bounds": {"windowState": "minimized"},
            })
            session.detach()
        except Exception:
            # Synthesis remains functional if a Chrome build does not expose window bounds.
            pass

    def _configure(self, page, text: str, profile: VoiceProfile) -> None:
        # Always choose the emotional renderer for every new task, rather
        # than relying on a leftover state in an earlier browser tab.
        emotional_enabled = page.evaluate("""() => {
            const options = [...document.querySelectorAll('button, [role="button"], label')]
              .filter((item) => /эмоциональн|emotional/i.test(item.innerText || item.textContent || ''));
            const target = options[0];
            if (!target) return false;
            const active = target.getAttribute('aria-selected') === 'true'
              || target.getAttribute('aria-pressed') === 'true'
              || target.classList.contains('active') || target.classList.contains('selected')
              || target.classList.contains('is-active');
            if (!active) target.click();
            return true;
        }""")
        if not emotional_enabled:
            raise VoicerError("Не найдена настройка «Эмоциональная озвучка» в Secret Voicer.")
        page.wait_for_timeout(350)
        # An empty profile deliberately preserves the currently chosen voice
        # in the authenticated Chrome session.
        if profile.voice_id.strip() or profile.voice_name.strip():
            if not page.evaluate("""() => {
                const button = document.querySelector('#openVoiceSelectorBtn');
                if (!button) return false; button.click(); return true;
            }"""):
                raise VoicerError("Не найден выбор голоса в Secret Voicer.")
            page.wait_for_selector(".tw-voice-card[data-voice-id]", state="visible", timeout=10_000)
            applied = page.evaluate("""({voiceId, voiceName}) => {
                const cards = [...document.querySelectorAll('.tw-voice-card[data-voice-id]')];
                const name = (voiceName || '').toLocaleLowerCase();
                const card = cards.find((item) => item.dataset.voiceId === voiceId)
                    || cards.find((item) => name && (item.innerText || '').toLocaleLowerCase().includes(name));
                if (!card) return false; card.click(); return true;
            }""", {"voiceId": profile.voice_id, "voiceName": profile.voice_name})
            if not applied:
                raise VoicerError("Выбранный голос не найден в Secret Voicer. Проверьте Voice ID.")
            page.wait_for_timeout(250)
        configured = page.evaluate("""({stability, style, text}) => {
            const set = (selector, value) => {
              const input = document.querySelector(selector); if (!input) return;
              const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
              setter?.call(input, String(value));
              input.dispatchEvent(new Event('input', {bubbles: true}));
              input.dispatchEvent(new Event('change', {bubbles: true}));
            };
            set('#default-stability', stability); set('#default-style', style);
            const areas = [...document.querySelectorAll('textarea')]
              .filter((item) => !item.disabled && item.offsetParent !== null);
            const area = document.querySelector('textarea.form-control')
              || areas.find((item) => /введи текст|текст для озвучки|text/i.test(item.placeholder || ''))
              || areas.sort((left, right) => (right.clientHeight * right.clientWidth) - (left.clientHeight * left.clientWidth))[0];
            if (!area) return {found: false, value: ''};
            const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
            setter?.call(area, text);
            area.dispatchEvent(new Event('input', {bubbles: true}));
            area.dispatchEvent(new Event('change', {bubbles: true}));
            area.dispatchEvent(new Event('blur', {bubbles: true}));
            area.setAttribute('data-newsflow-voice-text', 'true');
            return {found: true, value: area.value || ''};
        }""", {"stability": profile.stability, "style": profile.style, "text": text})
        if not isinstance(configured, dict) or not configured.get("found"):
            raise VoicerError("Не найдено поле «Текст для озвучки» в Secret Voicer.")
        # React/Vue forms can discard synthetic changes a moment later.  Do
        # not press the generation button until the exact current scenario is
        # read back from the page.  This is what prevents an old tab's text
        # from being voiced and downloaded under a new scenario name.
        page.wait_for_timeout(250)
        inserted = page.evaluate("""() => {
            const area = document.querySelector('textarea[data-newsflow-voice-text="true"]');
            return area ? area.value || '' : '';
        }""")
        expected = " ".join(text.split())
        actual = " ".join(str(inserted or "").split())
        if expected != actual:
            raise VoicerError("Secret Voicer не принял текст текущего сценария. Озвучка не запущена, чтобы не скачать чужой MP3.")

    @staticmethod
    def _start_generation(page, text: str) -> bool:
        """Start only after the marked field still contains this scenario."""
        return bool(page.evaluate("""(expected) => {
            const area = document.querySelector('textarea[data-newsflow-voice-text="true"]');
            const normal = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            if (!area || normal(area.value) !== normal(expected)) return false;
            const buttons = [...document.querySelectorAll('button')]
              .filter((item) => !item.disabled);
            const button = buttons.find((item) => /^озвучить$/i.test((item.innerText || '').trim()))
              || buttons.find((item) => /озвуч|сгенер|создать/i.test(item.innerText || ''));
            if (!button) return false;
            button.click();
            return true;
        }""", text))

    @staticmethod
    def _audio_candidates(page) -> list[dict[str, str]]:
        """Read result links together with the history-card text around them.

        A bare first MP3 link is not trustworthy: Secret Voicer's history can
        initially render an older job before the current one.  The surrounding
        text is the stable association with a scenario.
        """
        return page.eval_on_selector_all(
            "a[href*='.mp3'],audio[src*='.mp3']",
            """items => items.map(item => ({
                href: item.href || item.src || '',
                text: (item.closest('.history-item, [data-history-item], .history-card, .generation-item')
                  || item.parentElement || item).innerText || ''
            })).filter(item => item.href)""",
        )

    @staticmethod
    def _matching_history_candidate(text: str, candidates: list[dict[str, str]]) -> dict[str, str] | None:
        """Find the one history row whose preview starts with this scenario."""
        target = " ".join((text or "").casefold().split())[:60]
        if not target:
            return None
        for candidate in candidates:
            candidate_text = " ".join(str(candidate.get("text", "")).casefold().split())
            if target in candidate_text:
                return candidate
        return None

    @staticmethod
    def _matching_audio_href(text: str, candidates: list[dict[str, str]]) -> str:
        """Return only an MP3 whose own history row belongs to ``text``."""
        candidate = ChromeSecretVoicer._matching_history_candidate(text, candidates)
        return str(candidate.get("href", "")) if candidate else ""

    @staticmethod
    def _history_candidates(page) -> list[dict[str, str]]:
        """Read history rows even when Secret Voicer exposes an icon button only."""
        return page.evaluate("""() => {
            const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
            const rows = [];
            const seen = new Set();
            for (const node of document.querySelectorAll('div, article, li, section')) {
              const text = normalize(node.innerText || '');
              if (text.length < 24) continue;
              const items = [...node.querySelectorAll('button, a')];
              const direct = node.querySelector("a[href*='.mp3'],audio[src*='.mp3']");
              const download = items.find((item) => /скач|download/i.test(
                `${item.innerText || ''} ${item.getAttribute('aria-label') || ''} ${item.getAttribute('title') || ''}`
              ));
              const control = download || (items.length >= 2 ? items[items.length - 1] : null);
              if (!direct && !control) continue;
              // Parent panels contain several cards; retain the smallest row.
              if ([...node.children].some((child) => normalize(child.innerText || '') === text)) continue;
              if (seen.has(node)) continue;
              seen.add(node);
              const id = `newsflow-history-${rows.length}`;
              node.setAttribute('data-newsflow-history-id', id);
              rows.push({id, text, href: direct?.href || direct?.src || '', hasDownload: Boolean(control)});
            }
            return rows;
        }""") or []

    @staticmethod
    def _download_history_row(page, candidate: dict[str, str]) -> bytes:
        """Download only from the already matched scenario-history row."""
        row_id = str(candidate.get("id", ""))
        if not row_id or not candidate.get("hasDownload"):
            return b""
        available = page.evaluate("""(id) => {
            const row = document.querySelector(`[data-newsflow-history-id="${id}"]`);
            return Boolean(row && row.querySelector('button, a'));
        }""", row_id)
        if not available:
            return b""
        try:
            with page.expect_download(timeout=30_000) as download_info:
                clicked = page.evaluate("""(id) => {
                    const row = document.querySelector(`[data-newsflow-history-id="${id}"]`);
                    if (!row) return false;
                    const items = [...row.querySelectorAll('button, a')];
                    const control = items.find((item) => /скач|download/i.test(
                      `${item.innerText || ''} ${item.getAttribute('aria-label') || ''} ${item.getAttribute('title') || ''}`
                    )) || (items.length >= 2 ? items[items.length - 1] : null);
                    if (!control) return false;
                    control.click();
                    return true;
                }""", row_id)
            if not clicked:
                return b""
            download = download_info.value
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as stream:
                temporary = Path(stream.name)
            try:
                download.save_as(str(temporary))
                return temporary.read_bytes()
            finally:
                temporary.unlink(missing_ok=True)
        except Exception:
            return b""

    def _persistent_context(self):
        """Reuse the dedicated Chrome session so generated tabs stay open."""
        key = str(self.profile_dir.resolve())
        cached = _BROWSER_RUNTIMES.get(key)
        if cached:
            _playwright, context = cached
            try:
                # Accessing pages fails after the user closes Chrome.  In that
                # case a clean runtime is created below.
                _ = context.pages
                return context
            except Exception:
                try:
                    _playwright.stop()
                except Exception:
                    pass
                _BROWSER_RUNTIMES.pop(key, None)

        from playwright.sync_api import sync_playwright
        playwright = sync_playwright().start()
        try:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_dir), executable_path=str(chrome_path()), headless=False,
                args=["--no-first-run", "--no-default-browser-check",
                      "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
                      "--disable-renderer-backgrounding"],
                viewport={"width": 1280, "height": 900}, accept_downloads=True,
            )
        except Exception:
            playwright.stop()
            raise
        _BROWSER_RUNTIMES[key] = (playwright, context)
        return context

    def synthesize(self, text: str, profile: VoiceProfile,
                   progress: Callable[[str, int], None] | None = None) -> bytes:
        if not (text or "").strip():
            raise VoicerError("Добавьте текст для озвучки.")
        try:
            import playwright.sync_api  # noqa: F401 - validates bundled support
        except ImportError as exc:
            raise VoicerError("Компонент Chrome-озвучки не установлен. Переустановите NewsFlow.") from exc

        # One background Chrome profile can reliably process one task at a time.
        with _BROWSER_QUEUE:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                context = self._persistent_context()
                # Each scenario gets its own tab and tabs are intentionally
                # retained after download. This lets the editor verify the
                # generated result and prevents the next text from replacing
                # an earlier task in the Secret Voicer UI.
                page = context.new_page()
                try:
                    if progress: progress("Открываем Secret Voicer в Chrome", 5)
                    page.goto(VOICE_BROWSER_URL, wait_until="domcontentloaded", timeout=120_000)
                    # Playwright exposes the current URL as a string property.
                    if not self._authorized_url(page.url):
                        raise VoicerError("Chrome не авторизован в Secret Voicer. Нажмите «Открыть Chrome / войти через Telegram», войдите и закройте это окно Chrome.")
                    if progress: progress("Настраиваем голос", 15)
                    self._configure(page, text, profile)
                    if progress: progress("Отправляем текст на озвучку", 25)
                    started = self._start_generation(page, text)
                    if not started:
                        raise VoicerError("Secret Voicer не разрешил запуск или текст в поле изменился. Проверьте голос и текущую вкладку.")
                    self._minimize(page)
                    if progress: progress("Secret Voicer создаёт MP3 в фоновом Chrome", 30)
                    # Wait up to 20 minutes. Some long news scripts stay in
                    # the service queue noticeably longer than six minutes.
                    for attempt in range(600):
                        page.wait_for_timeout(int(self.poll_seconds * 1000))
                        # Reload approximately every 30 seconds. The server
                        # task remains active; the tab merely gets fresh state.
                        if attempt and attempt % 15 == 0:
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=120_000)
                            except Exception:
                                pass
                        result = page.evaluate("""() => {
                            const text = document.body.innerText || '';
                            return {failed: /ошибка|failed|не удалось/i.test(text),
                              processing: /обработ|очеред|генерац/i.test(text)};
                        }""")
                        if result["failed"]:
                            raise VoicerError("Secret Voicer сообщил об ошибке генерации.")
                        # The history preview is the source of truth.  Never
                        # take the first player/link on the page: it may be a
                        # completed result of an older scenario.
                        candidate = self._matching_history_candidate(text, self._history_candidates(page))
                        if candidate is None:
                            candidate = self._matching_history_candidate(text, self._audio_candidates(page))
                        if candidate:
                            if progress: progress("Скачиваем готовый MP3", 95)
                            raw = b""
                            href = str(candidate.get("href", ""))
                            if href:
                                try:
                                    response = page.context.request.get(href, timeout=120_000)
                                    if response.ok:
                                        raw = response.body()
                                except Exception:
                                    pass
                                if not raw:
                                    raw, _ = SecretVoicerClient("browser-session")._request("GET", href, key=False)
                            if not raw:
                                raw = self._download_history_row(page, candidate)
                            if not raw:
                                # The matching row can render the preview
                                # before its download control becomes active.
                                # Keep polling instead of accepting another
                                # row or attaching a stale file.
                                if progress: progress("Ожидаем кнопку скачивания в истории", 95)
                                continue
                            if progress: progress("Готово", 100)
                            return raw
                        if progress:
                            progress("Secret Voicer обрабатывает текст" if result["processing"] else "Ожидаем готовый MP3",
                                     min(90, 30 + attempt // 3))
                    raise VoicerError("Таймаут ожидания MP3 в Secret Voicer.")
                finally:
                    # Do not close this tab or its persistent context. The
                    # page is the visual audit trail for this scenario.
                    pass
            except VoicerError:
                raise
            except Exception as exc:
                message = str(exc)
                if "ProcessSingleton" in message or "profile" in message.lower() and "lock" in message.lower():
                    raise VoicerError("Закройте окно Chrome, открытое для входа в Secret Voicer, затем повторите озвучку.") from exc
                raise VoicerError(f"Chrome-озвучка: {message}") from exc
