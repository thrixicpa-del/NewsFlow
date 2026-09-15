"""Durable, cross-version state for the thumbnail queue.

The media files remain in the user-selected cover folder.  This sidecar holds
the non-secret state that must survive a release update or an unrelated worker
writing an older settings snapshot.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_VERSION = 1
_WRITE_LOCK = threading.RLock()
_LOCK_WAIT_SECONDS = 30.0
_LOCK_STALE_SECONDS = 600.0
_REPLACE_ATTEMPTS = 8


def _identity(item: dict[str, Any]) -> str:
    production_item_id = str(item.get("production_item_id") or item.get("productionItemId") or "").strip()
    if production_item_id:
        return production_item_id
    title = " ".join(str(item.get("title") or "").split()).casefold()
    scenario = str(item.get("scenario_index") or "")
    digest = hashlib.sha256(f"{scenario}|{title}".encode("utf-8")).hexdigest()[:20]
    return f"legacy-cover:{digest}"


def _updated_at(item: dict[str, Any]) -> str:
    return str(item.get("updatedAt") or item.get("updated_at") or "")


def _retryable_replace_error(error: OSError) -> bool:
    """Windows reports a briefly locked JSON file as either errno or winerror."""
    return error.errno in {5, 13, 32, 33} or getattr(error, "winerror", None) in {5, 32, 33}


@contextmanager
def _interprocess_write_lock(path: Path):
    """Serialize read-merge-replace across separate NewsFlowCore processes.

    A normal threading lock only protects FastGen workers running in one
    process. Electron starts each bridge command as a new executable, so the
    durable registry needs a small lock file shared by all those processes.
    """
    lock_path = path.with_suffix(path.suffix + ".write.lock")
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"{os.getpid()} {time.time():.6f}".encode("ascii"))
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > _LOCK_STALE_SECONDS
            except OSError:
                continue
            if stale:
                try:
                    lock_path.unlink()
                    continue
                except OSError:
                    pass
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Не удалось дождаться сохранения библиотеки обложек: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(descriptor)
        finally:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass


class CoverLibrary:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {"version": _VERSION, "items": {}, "tombstones": [], "fastgenCapabilities": {"image": [], "video": []}, "fastgenUsage": {}, "faceConfig": {}}
        if not isinstance(payload, dict):
            return {"version": _VERSION, "items": {}, "tombstones": [], "fastgenCapabilities": {"image": [], "video": []}, "fastgenUsage": {}, "faceConfig": {}}
        payload.setdefault("version", _VERSION)
        payload.setdefault("items", {})
        payload.setdefault("tombstones", [])
        payload.setdefault("fastgenCapabilities", {"image": [], "video": []})
        payload.setdefault("fastgenUsage", {})
        payload.setdefault("faceConfig", {})
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            previous = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        except OSError:
            previous = ""
        if previous:
            archive_dir = self.path.parent / "state-backups"
            archive_dir.mkdir(parents=True, exist_ok=True)
            archive = archive_dir / "covers-library-last-known-good.json"
            archive_temp = archive.with_name(f".{archive.name}.{uuid.uuid4().hex}.tmp")
            try:
                archive_temp.write_text(previous, encoding="utf-8")
                os.replace(archive_temp, archive)
            finally:
                try:
                    if archive_temp.exists():
                        archive_temp.unlink()
                except OSError:
                    pass
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        last_error: OSError | None = None
        for attempt in range(_REPLACE_ATTEMPTS):
            temporary = self.path.with_suffix(self.path.suffix + f".{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(serialized, encoding="utf-8")
                temporary.replace(self.path)
                return
            except OSError as error:
                if not _retryable_replace_error(error):
                    raise
                last_error = error
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                if attempt + 1 < _REPLACE_ATTEMPTS:
                    time.sleep(0.05 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def persist(
        self,
        queue: list[dict[str, Any]],
        capabilities: dict[str, list[dict]],
        usage: dict[str, Any],
        *,
        face_config: dict[str, Any] | None = None,
    ) -> None:
        # Ten FastGen workers update status independently.  Keep the complete
        # read-merge-replace sequence serial so one worker cannot erase another
        # record or race the temporary file on Windows.
        with _WRITE_LOCK, _interprocess_write_lock(self.path):
            payload = self._read()
            items = payload["items"] if isinstance(payload.get("items"), dict) else {}
            tombstones = {str(value).strip() for value in payload.get("tombstones", []) if str(value).strip()}
            for source in queue:
                if not isinstance(source, dict):
                    continue
                item = dict(source)
                item["production_item_id"] = _identity(item)
                key = item["production_item_id"]
                if key in tombstones:
                    continue
                previous = items.get(key)
                if not isinstance(previous, dict) or _updated_at(item) >= _updated_at(previous):
                    items[key] = item
            payload["items"] = items
            payload["tombstones"] = sorted(tombstones)[-10000:]
            if capabilities.get("image") or capabilities.get("video"):
                payload["fastgenCapabilities"] = capabilities
            if usage:
                payload["fastgenUsage"] = usage
            if face_config is not None:
                payload["faceConfig"] = dict(face_config)
            self._write(payload)

    def face_config(self) -> dict[str, Any]:
        """Return the release-independent portrait-library configuration."""
        value = self._read().get("faceConfig")
        return dict(value) if isinstance(value, dict) else {}

    def remove(self, production_item_ids: list[str]) -> None:
        """Forget only explicitly removed queue rows; media deletion is separate."""
        keys = {str(value).strip() for value in production_item_ids if str(value).strip()}
        if not keys:
            return
        with _WRITE_LOCK, _interprocess_write_lock(self.path):
            payload = self._read()
            items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
            tombstones = {str(value).strip() for value in payload.get("tombstones", []) if str(value).strip()}
            for key in keys:
                items.pop(key, None)
                tombstones.add(key)
            payload["items"] = items
            payload["tombstones"] = sorted(tombstones)[-10000:]
            self._write(payload)

    def hydrate(
        self,
        queue: list[dict[str, Any]],
        capabilities: dict[str, list[dict]],
        usage: dict[str, Any],
        *,
        active_production_ids: set[str] | None = None,
    ) -> tuple[list[dict], dict, dict]:
        payload = self._read()
        stored = payload.get("items") if isinstance(payload.get("items"), dict) else {}
        tombstones = {str(value).strip() for value in payload.get("tombstones", []) if str(value).strip()}
        result: list[dict] = []
        seen: set[str] = set()
        position_by_key: dict[str, int] = {}
        for source in queue:
            item = dict(source) if isinstance(source, dict) else {}
            key = _identity(item)
            if active_production_ids is not None and key not in active_production_ids:
                continue
            if key in tombstones:
                continue
            item["production_item_id"] = key
            # Interrupted older workers can leave the same legacy row twice in
            # settings.  It is one ProductionItem, not two gallery topics.
            # Keep the newer source deterministically instead of multiplying
            # counters or generating a second cover for it.
            if key in position_by_key:
                position = position_by_key[key]
                if _updated_at(item) >= _updated_at(result[position]):
                    result[position] = item
                continue
            saved = stored.get(key)
            if isinstance(saved, dict) and _updated_at(saved) > _updated_at(item):
                item = dict(saved)
            position_by_key[key] = len(result)
            result.append(item)
            seen.add(key)
        # A release can start with a new empty settings file.  Preserve legacy
        # rows rather than silently creating an empty thumbnail library.
        for key, item in stored.items():
            if active_production_ids is not None and key not in active_production_ids:
                continue
            if key not in seen and key not in tombstones and isinstance(item, dict):
                result.append(dict(item))
        stored_capabilities = payload.get("fastgenCapabilities")
        if (not capabilities.get("image") and not capabilities.get("video")) and isinstance(stored_capabilities, dict):
            capabilities = stored_capabilities
        stored_usage = payload.get("fastgenUsage")
        if not usage and isinstance(stored_usage, dict):
            usage = stored_usage
        return result, capabilities, usage
