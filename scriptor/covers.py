from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .config import app_data_root
from .core import safe_filename

API_ROOT = "https://api.fast-gen.ai"


_REFERENCE_MIME_FALLBACKS = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jfif": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_FASTGEN_REFERENCE_MAX_BYTES = 5 * 1024 * 1024
_FASTGEN_REFERENCE_SAFE_BYTES = int(4.7 * 1024 * 1024)


def _prepare_reference_for_upload(path: Path) -> Path:
    """Return an upload-safe image without ever modifying the user's source.

    FastGen rejects references larger than 5 MiB. Portrait cut-outs are often
    lossless PNG files well over that threshold, so convert only an ephemeral
    cached copy to WebP and keep the original file/path unchanged.
    """
    path = Path(path)
    if not path.is_file() or path.stat().st_size <= _FASTGEN_REFERENCE_MAX_BYTES:
        return path
    try:
        from PIL import Image
    except ImportError as exc:
        raise FastGenError("Нужна Pillow, чтобы подготовить большой референс для FastGen") from exc

    stamp = f"{path.resolve()}:{path.stat().st_size}:{path.stat().st_mtime_ns}".encode("utf-8", errors="replace")
    cache = app_data_root() / "FastGenReferenceCache"
    cache.mkdir(parents=True, exist_ok=True)
    prepared = cache / f"{hashlib.sha256(stamp).hexdigest()}.webp"
    if prepared.is_file() and 0 < prepared.stat().st_size <= _FASTGEN_REFERENCE_MAX_BYTES:
        return prepared
    try:
        with Image.open(path) as source:
            source.load()
            image = source.copy()
    except Exception as exc:
        raise FastGenError(f"Не удалось подготовить референс {path.name} для FastGen") from exc

    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    for edge in (3840, 3072, 2560, 2048, 1600, 1280):
        candidate = image.copy()
        candidate.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        for quality in (90, 82, 74, 66):
            candidate.save(prepared, format="WEBP", quality=quality, method=6)
            if prepared.stat().st_size <= _FASTGEN_REFERENCE_SAFE_BYTES:
                return prepared
    try:
        prepared.unlink(missing_ok=True)
    except OSError:
        pass
    raise FastGenError(f"Референс {path.name} не удалось сжать до лимита FastGen 5 МБ")


def reference_mime_type(path: Path) -> str:
    """Return the real MIME type required by FastGen object storage.

    The storage endpoint rejects ``application/octet-stream`` even when the
    bytes are a perfectly valid PNG/JPEG.  Windows often has incomplete MIME
    registrations, so keep image fallbacks in the application as well.
    """
    suffix = Path(path).suffix.casefold()
    mime = mimetypes.guess_type(str(path))[0] or _REFERENCE_MIME_FALLBACKS.get(suffix)
    if mime in set(_REFERENCE_MIME_FALLBACKS.values()):
        return mime
    supported = ", ".join(sorted(_REFERENCE_MIME_FALLBACKS))
    raise FastGenError(
        f"Референс {Path(path).name} имеет неподдерживаемый формат {suffix or 'без расширения'}. "
        f"Используйте PNG, JPG, WEBP, BMP или GIF ({supported})."
    )


class FastGenError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, generation_id: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.generation_id = str(generation_id or "")

    @property
    def generation_accepted(self) -> bool:
        return bool(self.generation_id)

    @property
    def quota_exhausted(self):
        text = str(self).lower()
        return self.status_code == 402 or any(word in text for word in (
            "insufficient credit", "insufficient balance", "out of credits", "quota exhausted",
            "not enough credits", "недостаточно кредит",
        ))

    @property
    def credential_rejected(self):
        """Whether retrying this request with another configured key is safe."""
        text = str(self).casefold()
        return self.status_code in {401, 403} and any(marker in text for marker in (
            "license expired", "invalid api key", "invalid key", "unauthorized", "authentication",
            "срок действия лицензии истек", "недействительный ключ", "авторизац",
        ))


def _count_option_rejected(error: FastGenError) -> bool:
    """Identify stale/unknown provider schemas that reject a count option."""
    message = str(error).casefold()
    return (error.status_code == 400 and "count" in message and
            any(marker in message for marker in ("does not support", "unsupported", "invalid", "not allowed")))


class FastGenClient:
    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("Введите API-ключ FastGen")
        self.api_key = api_key.strip()
        self._reference_uploads: dict[str, str] = {}
        self._reference_upload_lock = threading.Lock()

    def _json(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            API_ROOT + path, data=data, method=method,
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FastGenError(f"FastGen API ({exc.code}): {detail}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise FastGenError(f"Ошибка сети FastGen: {exc.reason}") from exc

    def validate(self, media_type: str = "image"):
        if media_type not in ("image", "video"):
            raise ValueError("Некорректный тип моделей FastGen")
        return self._json("GET", f"/api/v6/models?media_type={media_type}")

    def capabilities(self, media_type: str):
        if media_type not in ("image", "video"):
            raise ValueError("Некорректный тип моделей FastGen")
        return self._json("GET", f"/api/v6/capabilities?media_type={media_type}")

    def usage(self):
        data = self._json("GET", "/api/v6/usage")
        data.pop("api_key", None)
        return data

    def recover_generation(self, generation_id: str, output_folder: Path, title: str) -> dict:
        """Inspect an accepted generation without issuing another billable create."""
        generation_id = str(generation_id or "").strip()
        if not generation_id:
            raise ValueError("Не указан FastGen generation ID")
        status = self._json("GET", f"/api/v6/generations/{generation_id}")
        state = str(status.get("status", "")).casefold()
        if state == "succeeded":
            results = status.get("results") or []
            if not results:
                return {"status": "failed", "error": "FastGen завершил задачу без изображения", "generation_id": generation_id}
            return {"status": "succeeded", "generation_id": generation_id,
                    "paths": [self._save_result(result, output_folder, title, index + 1)
                              for index, result in enumerate(results)]}
        if state == "failed":
            return {"status": "failed", "generation_id": generation_id,
                    "error": str(status.get("error") or "Генерация FastGen завершилась ошибкой")}
        return {"status": "processing", "generation_id": generation_id,
                "error": str(status.get("error") or "")}

    def upload_reference(self, path: Path) -> str:
        path = Path(path)
        if not path.is_file():
            raise FastGenError(f"Референс не найден: {path}")
        path = _prepare_reference_for_upload(path)
        if path.stat().st_size > _FASTGEN_REFERENCE_MAX_BYTES:
            raise FastGenError(f"Референс {path.name} больше 5 МБ")
        mime_type = reference_mime_type(path)
        stat = path.stat()
        cache_key = f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}"
        with self._reference_upload_lock:
            cached = self._reference_uploads.get(cache_key)
            if cached:
                return cached
            storage_id = self._upload_reference(path, mime_type)
            self._reference_uploads[cache_key] = storage_id
            return storage_id

    def _upload_reference(self, path: Path, mime_type: str) -> str:
        boundary = "----Scriptor" + uuid.uuid4().hex
        # The FastGen storage parser does not reliably decode non-ASCII names
        # in a multipart ``filename`` parameter. A valid ``путин3.png`` can
        # otherwise reach it with an unknown MIME type. The API does not use
        # the original filename, but it does validate the extension.
        transport_name = f"reference-{uuid.uuid4().hex}{path.suffix.casefold()}"
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{transport_name}\"\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        request = urllib.request.Request(
            "https://storage.fast-gen.ai/v2/upload", data=body, method="POST",
            headers={"X-API-Key": self.api_key, "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FastGenError(f"Загрузка референса ({exc.code}): {detail}", exc.code) from exc
        storage_id = result.get("id") or result.get("file_hash")
        if not storage_id:
            raise FastGenError("Сервер хранения не вернул ID референса")
        return storage_id

    def generate_cover(self, prompt: str, output_folder: Path, title: str,
                       operation: str = "flower_image_generate", aspect_ratio: str = "16:9",
                       references=None, seed=None, upscale=False) -> Path:
        return self.generate_media(prompt, output_folder, title, operation, aspect_ratio,
                                   references, 1, seed, upscale=upscale)[0]

    def generate_media(self, prompt: str, output_folder: Path, title: str, operation: str,
                       aspect_ratio: str = "16:9", references=None, count: int = 1, seed=None,
                       quality=None, resolution=None, upscale=False, progress_callback=None) -> list[Path]:
        requested_count = max(1, min(10, int(count or 1)))
        capability = self._operation_capability(operation)
        inputs = [self.upload_reference(Path(path)) for path in (references or [])]
        payload, supports_count, max_items = self._generation_payload(
            operation, prompt, aspect_ratio, inputs, seed, quality, resolution, upscale, capability,
        )
        # Nano Banana 2, Nano Banana Pro and several other FastGen models return
        # one image per request.  Sending count=2+ to them causes a 400 response.
        # Split a user-selected amount into safe requests and keep all variants.
        batch_size = max_items if supports_count else 1
        batch_size = max(1, min(batch_size, requested_count))
        total_batches = (requested_count + batch_size - 1) // batch_size
        results: list[Path] = []
        remaining = requested_count
        batch_number = 0
        # Some FastGen adapters accept `count`, but currently return only one
        # result.  Never silently call that a successful two-variant render:
        # ask again only for the remainder until the user-selected amount is
        # actually present on disk.
        while remaining:
            batch_number += 1
            current_count = min(batch_size, remaining)
            request_payload = dict(payload)
            if supports_count:
                request_payload["count"] = current_count
            if progress_callback:
                planned = max(total_batches, batch_number)
                progress_callback(f"FastGen: запрос {batch_number}/{planned}",
                                  max(12, min(78, int((len(results)) / requested_count * 75) + 12)), "")
            try:
                received = self._wait_for_generation(
                    request_payload, output_folder, title, len(results) + 1,
                    progress_callback, batch_number, total_batches,
                )
            except FastGenError as error:
                # If the live capability endpoint was unavailable, the
                # generation endpoint is the authoritative schema. Retry this
                # item one-at-a-time instead of leaving the topic failed.
                if supports_count and _count_option_rejected(error):
                    supports_count = False
                    batch_size = 1
                    total_batches = requested_count - len(results)
                    if progress_callback:
                        progress_callback("FastGen не принимает count — варианты будут запрошены по одному", 12, "")
                    continue
                raise
            if not received:
                raise FastGenError("FastGen вернул пустой набор вариантов")
            results.extend(received[:remaining])
            remaining = requested_count - len(results)
            if remaining and progress_callback:
                progress_callback("FastGen вернул не все варианты — запрашивается остаток",
                                  max(12, min(78, int(len(results) / requested_count * 75) + 12)), "")
        return results[:requested_count]

    def _operation_capability(self, operation: str) -> dict:
        """Use FastGen's live schema, but do not block rendering if it is temporarily unavailable."""
        try:
            for item in self.capabilities("image"):
                if isinstance(item, dict) and str(item.get("id") or item.get("operation") or "") == operation:
                    return item
        except FastGenError:
            pass
        return {}

    def _generation_payload(self, operation: str, prompt: str, aspect_ratio: str, inputs: list[str],
                            seed, quality, resolution, upscale: bool, capability: dict) -> tuple[dict, bool, int]:
        options = capability.get("options") if isinstance(capability.get("options"), dict) else {}
        input_rules = capability.get("inputs") if isinstance(capability.get("inputs"), dict) else {}
        output_rules = capability.get("outputs") if isinstance(capability.get("outputs"), dict) else {}
        minimum_inputs = int(input_rules.get("min") or 0)
        maximum_inputs = int(input_rules.get("max") or 10)
        if len(inputs) < minimum_inputs:
            raise FastGenError(f"Модель FastGen требует минимум {minimum_inputs} референс(а/ов)")
        if len(inputs) > maximum_inputs:
            raise FastGenError(f"Модель FastGen принимает не больше {maximum_inputs} референс(а/ов)")
        payload = {"operation": operation, "prompt": prompt}
        # inputs are optional in the FastGen schema.  Do not send inputs: [] to
        # strict provider adapters such as Nano Banana 2.
        if inputs:
            payload["inputs"] = inputs
        ratio_option = options.get("aspect_ratio") if isinstance(options.get("aspect_ratio"), dict) else None
        if ratio_option is not None or not capability:
            allowed_ratios = ratio_option.get("enum") if isinstance(ratio_option, dict) else None
            if isinstance(allowed_ratios, list) and allowed_ratios and aspect_ratio not in allowed_ratios:
                aspect_ratio = str(ratio_option.get("default") or allowed_ratios[0])
            payload["aspect_ratio"] = aspect_ratio
        if seed is not None and ("seed" in options or not capability):
            payload["seed"] = seed
        if quality and ("quality" in options or not capability):
            payload["quality"] = quality
        if resolution and ("resolution" in options or not capability):
            payload["resolution"] = resolution
        if upscale and ("generation_config" in options or not capability):
            payload["generation_config"] = {"upscale": {"type": "2x"}}
        max_items = max(1, int(output_rules.get("max_items") or 1))
        # A capabilities timeout gives us no permission to invent provider
        # options.  Every current FastGen image operation accepts one request
        # per image, whereas several reject even ``count: 1``.  Stay with the
        # universally accepted one-image shape until the live schema confirms
        # multi-item support.
        return payload, "count" in options, max_items

    def _wait_for_generation(self, payload: dict, output_folder: Path, title: str, start_index: int,
                             progress_callback=None, batch_number: int = 1, total_batches: int = 1) -> list[Path]:
        accepted = self._json("POST", "/api/v6/generations", payload)
        generation_id = accepted.get("id")
        if not generation_id:
            raise FastGenError("FastGen не вернул идентификатор генерации")
        if progress_callback:
            progress_callback(f"FastGen принял запрос {batch_number}/{total_batches}", 25, generation_id)
        try:
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                status = self._json("GET", f"/api/v6/generations/{generation_id}")
                if status.get("status") == "failed":
                    raise FastGenError(status.get("error") or "Генерация обложки завершилась ошибкой")
                if status.get("status") == "succeeded":
                    results = status.get("results") or []
                    if not results:
                        raise FastGenError("FastGen завершил задачу без изображения")
                    if progress_callback:
                        progress_callback("FastGen готовит файлы", 85, generation_id)
                    return [self._save_result(result, output_folder, title, start_index + index)
                            for index, result in enumerate(results)]
                if progress_callback:
                    api_progress = status.get("progress")
                    try:
                        percent = max(30, min(80, int(float(api_progress))))
                    except (TypeError, ValueError):
                        percent = 45
                    progress_callback("FastGen генерирует", percent, generation_id)
                time.sleep(3)
            raise FastGenError("FastGen не завершил обложку за 15 минут")
        except FastGenError as exc:
            if exc.generation_accepted:
                raise
            raise FastGenError(str(exc), exc.status_code, generation_id) from exc
        except Exception as exc:
            raise FastGenError(str(exc), generation_id=generation_id) from exc

    def _save_result(self, result: dict, folder: Path, title: str, index: int = 1) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        mime = result.get("mime_type") or "image/png"
        if "mp4" in mime or result.get("type") == "video":
            suffix = ".mp4"
        elif "webm" in mime:
            suffix = ".webm"
        else:
            suffix = ".jpg" if "jpeg" in mime or "jpg" in mime else ".webp" if "webp" in mime else ".png"
        extra = f" ({index})" if index > 1 else ""
        path = folder / f"{safe_filename(title)}{extra}{suffix}"
        if result.get("download_url"):
            with urllib.request.urlopen(result["download_url"], timeout=180) as response:
                path.write_bytes(response.read())
            return path
        data = result.get("data") or ""
        if data.startswith("data:") and "," in data:
            path.write_bytes(base64.b64decode(data.split(",", 1)[1]))
            return path
        raise FastGenError("В результате FastGen нет ссылки или данных изображения")


class FastGenPool:
    def __init__(self, keys):
        self.entries = [item for item in keys if item.active and item.secret.strip()]
        if not self.entries:
            raise ValueError("Добавьте и включите хотя бы один ключ FastGen")
        self.exhausted: set[int] = set()
        self.clients = [FastGenClient(item.secret) for item in self.entries]

    def validate(self, media_type: str = "image"):
        return FastGenClient(self.entries[0].secret).validate(media_type)

    def validate_all(self):
        client = FastGenClient(self.entries[0].secret)
        return {"image": client.validate("image"), "video": client.validate("video")}

    def capabilities_all(self):
        client = FastGenClient(self.entries[0].secret)
        return {"image": client.capabilities("image"), "video": client.capabilities("video")}

    def usage_all(self):
        results = []
        for entry in self.entries:
            try:
                results.append({"label": entry.label, "usage": FastGenClient(entry.secret).usage(), "error": ""})
            except Exception as exc:  # noqa: BLE001 - isolate one key's provider health failure
                results.append({"label": entry.label, "usage": {}, "error": str(exc)})
        return results

    def generate_cover(self, *args, **kwargs):
        errors = []
        for index, entry in enumerate(self.entries):
            if index in self.exhausted:
                continue
            try:
                return self.clients[index].generate_cover(*args, **kwargs)
            except FastGenError as exc:
                if exc.quota_exhausted or exc.credential_rejected:
                    self.exhausted.add(index)
                    errors.append(f"{entry.label}: ключ недоступен ({exc})")
                    continue
                raise
        raise FastGenError("Нет ключей FastGen с доступными кредитами. " + "; ".join(errors))

    def generate_media(self, *args, **kwargs):
        errors = []
        for index, entry in enumerate(self.entries):
            if index in self.exhausted:
                continue
            try:
                return self.clients[index].generate_media(*args, **kwargs)
            except FastGenError as exc:
                if exc.quota_exhausted or exc.credential_rejected:
                    self.exhausted.add(index)
                    errors.append(f"{entry.label}: ключ недоступен ({exc})")
                    continue
                raise
        raise FastGenError("Нет ключей FastGen с доступными кредитами. " + "; ".join(errors))

    def recover_generation(self, generation_id: str, output_folder: Path, title: str) -> dict:
        errors = []
        for index, entry in enumerate(self.entries):
            if index in self.exhausted:
                continue
            try:
                return self.clients[index].recover_generation(generation_id, output_folder, title)
            except FastGenError as exc:
                if exc.quota_exhausted or exc.credential_rejected:
                    self.exhausted.add(index)
                    errors.append(f"{entry.label}: ключ недоступен ({exc})")
                    continue
                raise
        raise FastGenError("Не удалось проверить принятую генерацию FastGen. " + "; ".join(errors))
