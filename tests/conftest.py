"""Pytest categorisation and hard test-root enforcement for NewsFlow."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

_CONTRACT = {
    "tests/test_runtime_action_map.py",
    "scriptor/test_command_contract.py",
}
_INTEGRATION_PREFIXES = (
    "tests/test_ideas.py",
    "tests/test_scenarios.py",
    "tests/test_session.py",
    "tests/test_covers.py",
    "tests/test_cover_queue_tombstones.py",
    "tests/test_voicer.py",
    "tests/test_montage_queue.py",
    "tests/test_publication_v2.py",
    "tests/test_electron_e2e.py",
)
_PACKAGED = {
    "tests/test_core_runtime_guard.py",
    "tests/test_build_montage_runtime_guard.py",
    "tests/test_frozen_core_command_contract.py",
}
_SLOW = {
    "tests/test_montage_benchmark.py",
    "tests/test_resource_soak.py",
    "scriptor/test_montage_render.py",
}


def pytest_sessionstart(session: pytest.Session) -> None:
    if os.environ.get("NEWSFLOW_TEST_MODE") != "1" or not os.environ.get("NEWSFLOW_TEST_ROOT", "").strip():
        raise pytest.UsageError(
            "NewsFlow pytest must run through tests/run_isolated.py --pytest; "
            "NEWSFLOW_TEST_MODE=1 and NEWSFLOW_TEST_ROOT are required."
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    root = Path(str(config.rootpath)).resolve()
    for item in items:
        relative = Path(str(item.path)).resolve().relative_to(root).as_posix()
        if relative in _CONTRACT:
            item.add_marker(pytest.mark.contract)
        if relative in _INTEGRATION_PREFIXES:
            item.add_marker(pytest.mark.integration)
        if relative in _PACKAGED:
            item.add_marker(pytest.mark.packaged)
        if relative in _SLOW:
            item.add_marker(pytest.mark.slow)
        if not any(item.get_closest_marker(category) for category in (
            "contract", "integration", "packaged", "slow", "provider_real",
        )):
            item.add_marker(pytest.mark.unit)
        if item.get_closest_marker("provider_real") and os.environ.get("NEWSFLOW_ENABLE_REAL_PROVIDERS") != "1":
            item.add_marker(pytest.mark.skip(reason="real provider tests require NEWSFLOW_ENABLE_REAL_PROVIDERS=1"))
