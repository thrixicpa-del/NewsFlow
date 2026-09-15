"""Static, non-flaky performance policy shared by isolated NewsFlow tests."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PerformanceBaseline:
    known_good_seconds: float
    warning_seconds: float
    hard_seconds: float


def load_performance_baselines() -> dict[str, PerformanceBaseline]:
    source = Path(__file__).with_name("performance-baselines.json")
    raw = json.loads(source.read_text(encoding="utf-8"))
    if raw.get("format") != 1:
        raise ValueError("unsupported NewsFlow performance baseline format")
    return {
        name: PerformanceBaseline(
            known_good_seconds=float(value["knownGoodSeconds"]),
            warning_seconds=float(value["warningSeconds"]),
            hard_seconds=float(value["hardSeconds"]),
        )
        for name, value in raw["metrics"].items()
    }


def classify_duration(baseline: PerformanceBaseline, elapsed_seconds: float) -> str:
    if elapsed_seconds > baseline.hard_seconds:
        return "HARD_REGRESSION"
    if elapsed_seconds > baseline.warning_seconds:
        return "WARNING"
    return "PASS"
