"""Produce standard Allure result files from NewsFlow's existing test commands.

The adapter deliberately keeps the existing unittest/Vitest/Electron tooling
unchanged.  Each executed suite becomes one explicit Allure result with its
stdout/stderr and any test-owned screenshots attached.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "studio-ui-remotion-verify"


@dataclass(frozen=True)
class Suite:
    key: str
    suite: str
    command: tuple[str, ...]
    enabled: bool
    skipped_reason: str = ""


def suite_plan(include_source_e2e: bool, packaged_exe: str) -> list[Suite]:
    python = sys.executable
    pnpm = "pnpm.cmd" if os.name == "nt" else "pnpm"
    source_e2e_enabled = include_source_e2e
    packaged_enabled = bool(packaged_exe)
    return [
        Suite("python", "Python", (python, "tests/run_isolated.py", "discover", "-s", "tests", "-q"), True),
        Suite("frontend", "Frontend", (pnpm, "--dir", str(APP_ROOT), "test:ui"), True),
        Suite(
            "integration",
            "Integration",
            (python, "tests/run_isolated.py", "tests.test_runtime_action_map", "tests.test_electron_security", "-v"),
            True,
        ),
        Suite(
            "source-e2e",
            "E2E",
            (python, "tests/run_isolated.py", "tests.test_electron_e2e", "-v"),
            source_e2e_enabled,
            "source Electron smoke was not requested",
        ),
        Suite(
            "packaged-smoke",
            "Packaged smoke",
            (python, "tests/run_isolated.py", "tests.test_electron_e2e", "-v"),
            packaged_enabled,
            "a packaged EXE was not supplied",
        ),
    ]


def _copy_attachment(results_root: Path, source: Path, name: str, media_type: str) -> dict[str, str]:
    target_name = f"{uuid.uuid4()}-attachment-{source.name if source.suffix else name}.txt"
    if source.suffix.lower() == ".png":
        target_name = f"{uuid.uuid4()}-attachment-{source.name}"
    target = results_root / target_name
    shutil.copyfile(source, target)
    return {"name": name, "source": target.name, "type": media_type}


def _write_text_attachment(results_root: Path, name: str, value: str) -> dict[str, str]:
    target = results_root / f"{uuid.uuid4()}-attachment-{name}.txt"
    target.write_text(value, encoding="utf-8")
    return {"name": name, "source": target.name, "type": "text/plain"}


def write_suite_result(
    *,
    results_root: Path,
    suite: str,
    name: str,
    status: str,
    started_at: int,
    stopped_at: int,
    stdout: str,
    stderr: str,
    screenshots: Iterable[Path] = (),
) -> Path:
    """Write one self-contained Allure result plus logs and optional images."""
    results_root.mkdir(parents=True, exist_ok=True)
    attachments = [
        _write_text_attachment(results_root, "stdout", stdout),
        _write_text_attachment(results_root, "stderr", stderr),
    ]
    for screenshot in screenshots:
        if screenshot.is_file():
            attachments.append(_copy_attachment(results_root, screenshot, screenshot.name, "image/png"))
    status_details = {"message": stderr or stdout} if status == "failed" else {}
    result = {
        "uuid": str(uuid.uuid4()),
        "historyId": hashlib.sha256(f"NewsFlow:{suite}:{name}".encode()).hexdigest(),
        "name": name,
        "fullName": f"NewsFlow.{suite}.{name}",
        "status": status,
        "statusDetails": status_details,
        "stage": "finished",
        "start": started_at,
        "stop": stopped_at,
        "labels": [
            {"name": "suite", "value": suite},
            {"name": "framework", "value": "NewsFlow reporting adapter"},
        ],
        "links": [],
        "attachments": attachments,
        "parameters": [],
    }
    target = results_root / f"{result['uuid']}-result.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _screenshots(artifact_root: Path) -> list[Path]:
    if not artifact_root.is_dir():
        return []
    return sorted(path for path in artifact_root.rglob("*.png") if path.is_file())


def run_suite(suite: Suite, results_root: Path, packaged_exe: str) -> tuple[str, Path]:
    started_at = int(time.time() * 1000)
    if not suite.enabled:
        result = write_suite_result(
            results_root=results_root,
            suite=suite.suite,
            name=suite.key,
            status="skipped",
            started_at=started_at,
            stopped_at=started_at,
            stdout=suite.skipped_reason,
            stderr="",
        )
        return "skipped", result

    artifact_root = results_root / "raw-artifacts" / suite.key
    environment = os.environ.copy()
    environment.update({
        "NEWSFLOW_TEST_MODE": "1",
        "NEWSFLOW_TEST_ARTIFACTS_DIR": str(artifact_root),
    })
    if suite.key == "source-e2e":
        environment.update({"NEWSFLOW_RUN_ELECTRON_E2E": "1", "NEWSFLOW_E2E_TARGET": "source"})
    if suite.key == "packaged-smoke":
        environment.update({
            "NEWSFLOW_RUN_ELECTRON_E2E": "1",
            "NEWSFLOW_E2E_TARGET": "packaged",
            "NEWSFLOW_PACKAGED_EXE": packaged_exe,
        })
    completed = subprocess.run(suite.command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, check=False)
    stopped_at = int(time.time() * 1000)
    status = "passed" if completed.returncode == 0 else "failed"
    result = write_suite_result(
        results_root=results_root,
        suite=suite.suite,
        name=suite.key,
        status=status,
        started_at=started_at,
        stopped_at=stopped_at,
        stdout=completed.stdout,
        stderr=completed.stderr,
        screenshots=_screenshots(artifact_root),
    )
    return status, result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--include-source-e2e", action="store_true")
    parser.add_argument("--packaged-exe", default="")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    suites = suite_plan(arguments.include_source_e2e, arguments.packaged_exe)
    if arguments.dry_run:
        print(json.dumps({"format": 1, "testOnly": True, "suites": [suite.key for suite in suites]}))
        return 0
    if arguments.packaged_exe and not Path(arguments.packaged_exe).is_file():
        raise SystemExit("--packaged-exe must point to an existing EXE")

    outcomes = []
    for suite in suites:
        status, result = run_suite(suite, arguments.results_root, arguments.packaged_exe)
        outcomes.append({"suite": suite.key, "status": status, "result": str(result)})
    print(json.dumps({"format": 1, "resultsRoot": str(arguments.results_root), "outcomes": outcomes}))
    return 0 if all(outcome["status"] != "failed" for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
