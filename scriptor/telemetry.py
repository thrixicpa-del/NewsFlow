"""Local-first telemetry contracts for future Sentry/OpenTelemetry adapters.

This module has no network client and no provider dependency.  It makes the
future boundary explicit while keeping the present runtime private by default.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .config import app_data_root

_WRITE_LOCK = threading.Lock()
_SENSITIVE_KEY = re.compile(
    r"(?:api.?key|secret|token|password|authorization|cookie|credential)", re.IGNORECASE,
)
_SENSITIVE_VALUE = re.compile(
    r"(?i)(?:bearer\s+|sk-[\w-]+|AIza[\w-]+|(?:oauth(?:\s+token)?|api.?key|secret|token|password|authorization)\s*(?:[=:]|\s)\s*)[^\s,;]+"
)


def redact_attributes(value: Any) -> Any:
    """Return structured telemetry data without credential-bearing values."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact_attributes(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_attributes(item) for item in value]
    if isinstance(value, tuple):
        return [redact_attributes(item) for item in value]
    if isinstance(value, str):
        return _SENSITIVE_VALUE.sub("[REDACTED]", value)
    return value


@dataclass(frozen=True)
class OptionalAdapter:
    """A documented, opt-in adapter integration; never a network client itself."""

    name: str
    environment_flag: str
    purpose: str


@dataclass(frozen=True)
class TelemetryPlan:
    default_exporter: str
    external_export_enabled: bool
    optional_adapters: tuple[OptionalAdapter, ...]


def telemetry_plan(environment: Mapping[str, str] | None = None) -> TelemetryPlan:
    """Describe the current offline-safe telemetry routing policy.

    Setting an environment flag alone never creates an exporter or a network
    connection.  An adapter must be explicitly installed and injected later.
    """
    del environment
    return TelemetryPlan(
        default_exporter="local",
        external_export_enabled=False,
        optional_adapters=(
            OptionalAdapter("opentelemetry", "NEWSFLOW_ENABLE_OPENTELEMETRY", "traces, metrics and timings"),
            OptionalAdapter("sentry", "NEWSFLOW_ENABLE_SENTRY", "crash and error reporting"),
        ),
    )


@dataclass(frozen=True)
class TelemetryEvent:
    """Provider-neutral structured event accepted by any future exporter."""

    name: str
    action_id: str
    duration_ms: float | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


class TelemetryExporter(Protocol):
    def emit(self, event: TelemetryEvent) -> None:
        """Export one redacted, provider-neutral telemetry event."""


class LocalTelemetryExporter:
    """JSONL diagnostic exporter that never performs network I/O."""

    def path(self) -> Path:
        return app_data_root() / "diagnostics" / "telemetry.jsonl"

    def emit(self, event: TelemetryEvent) -> None:
        record = {
            "format": 1,
            "timestamp": datetime.now(UTC).isoformat(),
            "name": event.name,
            "actionId": event.action_id,
            "durationMs": event.duration_ms,
            "attributes": redact_attributes(dict(event.attributes)),
        }
        path = self.path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _WRITE_LOCK, path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
