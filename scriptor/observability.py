"""Provider-neutral, local-only action tracing for NewsFlow.

The trace is deliberately compact: it records the immutable identifiers needed
to follow one command through the current runtime without retaining prompts,
credentials, OAuth data, or provider responses.  Trace write failures are
never allowed to change a user action's outcome.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import app_data_root

_TRACE_LOCK = threading.Lock()
_SECRET_FIELD = re.compile(
    r"(?:api.?key|secret|token|password|authorization|cookie|credential)", re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s+|sk-[\w-]+|AIza[\w-]+|(?:oauth(?:\s+token)?|api.?key|secret|token|password|authorization)\s*(?:[=:]|\s)\s*)[^\s,;]+"
)
_ACTION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}")
_IDENTITY_KEYS = {
    "jobId": "jobIds",
    "jobIds": "jobIds",
    "productionItemId": "productionItemIds",
    "productionItemIds": "productionItemIds",
    "snapshotId": "snapshotIds",
    "snapshotIds": "snapshotIds",
    "executionId": "executionIds",
    "executionIds": "executionIds",
}
_PROVIDERS = {
    "generate-ideas": "openai",
    "generate-scenarios": "openai",
    "generate-covers": "fastgen",
    "regenerate-covers": "fastgen",
    "regenerate-cover-with-face": "fastgen",
    "generate-voice": "voice",
    "generate-voice-queue": "voice",
    "generate-voice-range": "voice",
    "run-montage-queue": "ffmpeg",
    "render-montage": "ffmpeg",
    "upload-publication-jobs": "youtube",
    "upload-publication-v2-snapshots": "youtube",
}


def action_trace_path() -> Path:
    """Return the local, non-secret JSONL trace path for the active runtime."""
    return app_data_root() / "diagnostics" / "action-trace.jsonl"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_FIELD.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub("[REDACTED]", value)
    return value


def _identities(value: Any) -> dict[str, list[str]]:
    found = {name: [] for name in set(_IDENTITY_KEYS.values())}

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                target = _IDENTITY_KEYS.get(str(key))
                if target:
                    values = child if isinstance(child, list) else [child]
                    found[target].extend(str(value).strip() for value in values if str(value).strip())
                walk(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                walk(child)

    walk(value)
    return {name: list(dict.fromkeys(values)) for name, values in found.items() if values}


def _record(record: dict[str, Any]) -> None:
    """Best-effort append; observability may never fail a production command."""
    try:
        path = action_trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(_redact(record), ensure_ascii=False, sort_keys=True) + "\n"
        with _TRACE_LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except Exception:  # noqa: BLE001 - a diagnostic failure must not change a command result.
        return


@dataclass
class ActionTrace:
    """Lifecycle recorder for one bridge command and its durable job IDs."""

    command: str
    action_id: str
    provider: str | None
    identities: dict[str, list[str]]
    started_at: float = field(default_factory=time.perf_counter)

    def _emit(self, event: str, **fields: Any) -> None:
        record: dict[str, Any] = {
            "format": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "actionId": self.action_id,
            "correlationId": self.action_id,
            "command": self.command,
            "boundary": "bridge",
            "provider": self.provider,
            "durationMs": round((time.perf_counter() - self.started_at) * 1000, 3),
            **self.identities,
            **fields,
        }
        _record(record)

    def succeeded(self, result: Any) -> None:
        for name, values in _identities(result).items():
            self.identities[name] = list(dict.fromkeys([*self.identities.get(name, []), *values]))
        self._emit("succeeded")

    def failed(self, error: BaseException) -> None:
        self._emit("failed", error=_redact(str(error))[:500])

    def result_context(self) -> dict[str, str]:
        """Small additive response context; the renderer need not render it."""
        return {"id": self.action_id}


def start_action_trace(command: str, payload: Any) -> ActionTrace:
    """Start a local action trace without retaining an arbitrary user payload."""
    supplied_id = ""
    if isinstance(payload, dict):
        context = payload.get("_actionTrace")
        if isinstance(context, dict):
            supplied_id = str(context.get("id", "")).strip()
    trace = ActionTrace(
        command=str(command),
        action_id=supplied_id if _ACTION_ID.fullmatch(supplied_id) else uuid.uuid4().hex,
        provider=_PROVIDERS.get(str(command)),
        identities=_identities(payload),
    )
    trace._emit("started")
    return trace
