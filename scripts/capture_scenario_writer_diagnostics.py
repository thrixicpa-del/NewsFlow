"""Capture a fixed, disposable Writer D1–D4 diagnostic matrix.

The harness deliberately reuses the production Writer prompt builder and
OpenAI client.  It never mutates a NewsFlow session: the only durable output is
safe evidence beneath an explicitly supplied disposable root.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Direct execution starts Python with ``scripts/`` rather than the repository
# root on sys.path.  Add the known repository parent before importing runtime
# modules; module execution already has it and remains unchanged.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:  # ``python -m`` and direct ``python scripts/...`` are both supported.
    from scripts.capture_scenario_acceptance import (
        _complete_budget_reservation,
        _production_hashes,
        _redact,
        _reserve_budget,
        _safe_export_scan,
        _sha,
        _write_json,
        _write_text,
    )
except ModuleNotFoundError:  # pragma: no cover - exercised by the script subprocess test.
    from capture_scenario_acceptance import (
        _complete_budget_reservation,
        _production_hashes,
        _redact,
        _reserve_budget,
        _safe_export_scan,
        _sha,
        _write_json,
        _write_text,
    )
from scriptor.core import ScenarioRequest
from scriptor.story_planner import (
    StoryPlan,
    split_story_writer_request,
    story_plan_from_dict,
)

DEFAULT_FULL_TEMPLATE = (
    Path("docs/verification/evidence/scenario-live-293-final-stage-20260930")
    / "scenario-live-293-a3-20260930-140000"
    / "01-user-template.txt"
)
DEFAULT_EVIDENCE_PARENT = Path(r"D:\NewsFlow-RC\test-profiles")
_MAX_OUTPUT_TOKENS = 5120


@dataclass(frozen=True)
class DiagnosticCase:
    """One frozen Writer condition; it is not a Scenario acceptance result."""

    id: str
    part_id: str
    template_kind: str
    request: ScenarioRequest
    plan: StoryPlan
    accepted_parts: tuple[dict[str, object], ...]
    instructions: str
    input: str
    payload: dict[str, object]


def _git(command: str) -> str:
    return subprocess.check_output(command, shell=True, text=True).strip()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_control_fixture(path: Path) -> dict[str, Any]:
    """Load only a complete, pre-authored control fixture."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("plan"), dict):
        raise TypeError("writer diagnostic control fixture must contain a plan object")
    if not isinstance(value.get("title"), str) or not value["title"].strip():
        raise ValueError("writer diagnostic control fixture must contain a title")
    if not isinstance(value.get("fixed_prefix_for_final"), list):
        raise TypeError("writer diagnostic control fixture must contain the fixed final prefix")
    return value


def _fixture_plan(fixture: dict[str, Any]) -> StoryPlan:
    plan = story_plan_from_dict(copy.deepcopy(fixture["plan"]))
    if [part.id for part in plan.parts] != ["P1", "P2", "P3"]:
        raise ValueError("writer diagnostic fixture must provide P1/P2/P3")
    if [part.role for part in plan.parts] != ["OPENING", "MIDDLE", "FINAL"]:
        raise ValueError("writer diagnostic fixture must preserve OPENING/MIDDLE/FINAL")
    return plan


def _fixed_final_prefix(fixture: dict[str, Any], plan: StoryPlan) -> tuple[dict[str, object], ...]:
    by_id = {part.id: part for part in plan.parts}
    rows: list[dict[str, object]] = []
    for raw in fixture["fixed_prefix_for_final"]:
        if not isinstance(raw, dict):
            raise TypeError("writer diagnostic final prefix row must be an object")
        part_id = str(raw.get("part_id", ""))
        part = by_id.get(part_id)
        if part is None or part_id == "P3":
            raise ValueError("writer diagnostic final prefix must contain only planned prior parts")
        text = str(raw.get("text", "")).strip()
        if not text:
            raise ValueError("writer diagnostic final prefix text is missing")
        content_ids = tuple(str(item) for item in raw.get("content_ids", ()))
        if content_ids != part.content_ids:
            raise ValueError("writer diagnostic final prefix ownership differs from fixture plan")
        if int(raw.get("target_chars", 0) or 0) != part.target_chars:
            raise ValueError("writer diagnostic final prefix target differs from fixture plan")
        rows.append({
            "part_id": part.id,
            "content_ids": list(part.content_ids),
            "target_chars": part.target_chars,
            "text": text,
        })
    if [row["part_id"] for row in rows] != ["P1", "P2"]:
        raise ValueError("writer diagnostic final prefix must be P1 then P2")
    return tuple(rows)


def _case(
    *, case_id: str, plan: StoryPlan, fixture: dict[str, Any], template: str,
    template_kind: str, part_index: int, model: str,
) -> DiagnosticCase:
    contract = fixture["scenario_contract"]
    request = ScenarioRequest(
        index=0,
        title=str(fixture["title"]),
        prompt=template,
        production_item_id="manual-diagnostic-control-water-restoration",
        target_chars=int(contract["target_chars"]),
        allowed_min=int(contract["allowed_min"]),
        allowed_max=int(contract["allowed_max"]),
        factual_context_available=False,
        dramatized_allowed=True,
    )
    accepted_parts = _fixed_final_prefix(fixture, plan) if part_index == 2 else ()
    instructions, user_input = split_story_writer_request(
        request,
        plan,
        list(accepted_parts),
        part_index,
        current_target_chars=plan.parts[part_index].target_chars,
    )
    payload: dict[str, object] = {
        "model": model,
        "input": user_input,
        "instructions": instructions,
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
    }
    return DiagnosticCase(
        id=case_id,
        part_id=plan.parts[part_index].id,
        template_kind=template_kind,
        request=request,
        plan=plan,
        accepted_parts=accepted_parts,
        instructions=instructions,
        input=user_input,
        payload=payload,
    )


def build_diagnostic_cases(
    fixture: dict[str, Any], full_template: str, short_template: str,
    *, model: str = "gpt-5.4-mini",
) -> tuple[DiagnosticCase, ...]:
    """Create the four frozen matrix cells before any provider request."""
    if not full_template.strip() or not short_template.strip():
        raise ValueError("both diagnostic templates must be non-empty")
    plan = _fixture_plan(fixture)
    return (
        _case(case_id="D1", plan=plan, fixture=fixture, template=full_template,
              template_kind="FULL", part_index=0, model=model),
        _case(case_id="D2", plan=plan, fixture=fixture, template=short_template,
              template_kind="SHORT", part_index=0, model=model),
        _case(case_id="D3", plan=plan, fixture=fixture, template=full_template,
              template_kind="FULL", part_index=2, model=model),
        _case(case_id="D4", plan=plan, fixture=fixture, template=short_template,
              template_kind="SHORT", part_index=2, model=model),
    )


def _normalised_pair_input(case: DiagnosticCase, template: str) -> str:
    if case.input.count(template) != 1:
        raise ValueError(f"{case.id} did not preserve the manual template exactly once")
    return case.input.replace(template, "<MANUAL_TEMPLATE>")


def _validate_pair_isolation(
    left: DiagnosticCase, right: DiagnosticCase, left_template: str, right_template: str,
) -> None:
    if left.instructions != right.instructions:
        raise ValueError(f"{left.id}/{right.id} changed trusted Writer instructions")
    if _normalised_pair_input(left, left_template) != _normalised_pair_input(right, right_template):
        raise ValueError(f"{left.id}/{right.id} changed input outside the manual template")
    for case in (left, right):
        if case.payload.get("text") is not None or case.payload.get("tools") is not None:
            raise ValueError(f"{case.id} unexpectedly enables tools or Structured Outputs")
        if "previous_response_id" in case.payload:
            raise ValueError(f"{case.id} unexpectedly carries prior conversation state")


def _write_pair_diff(evidence: Path, left: DiagnosticCase, right: DiagnosticCase) -> None:
    left_lines = json.dumps(left.payload, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    right_lines = json.dumps(right.payload, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    diff = "\n".join(difflib.unified_diff(
        left_lines, right_lines, fromfile=f"{left.id}.json", tofile=f"{right.id}.json", lineterm="",
    )) + "\n"
    _write_text(evidence / f"{left.id}-{right.id}-payload.diff", diff)


def _preflight(cases: tuple[DiagnosticCase, ...]) -> list[dict[str, object]]:
    """Exercise the regular client shape with a stub transport and no network."""
    from scriptor.openai_client import OpenAITextClient

    records: list[dict[str, object]] = []
    for case in cases:
        client = OpenAITextClient("diagnostic-preflight-key", str(case.payload["model"]))
        response = {
            "id": f"preflight-{case.id}", "model": case.payload["model"],
            "status": "completed", "output_text": "PREFLIGHT_ONLY",
        }
        with patch.object(client, "_request", return_value=response) as mocked:
            output = asyncio.run(client.generate(
                case.input,
                max_output_tokens=_MAX_OUTPUT_TOKENS,
                instructions=case.instructions,
            ))
        payload = mocked.call_args.args[2]
        if payload != case.payload or output != "PREFLIGHT_ONLY":
            raise AssertionError(f"preflight payload drift for {case.id}")
        records.append({
            "id": case.id,
            "result": "PASS",
            "provider_calls": 0,
            "payload_sha256": _sha(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        })
    return records


def _write_common_evidence(
    evidence: Path, fixture_path: Path, full_template_path: Path,
    short_template_path: Path, fixture: dict[str, Any], cases: tuple[DiagnosticCase, ...],
    source_head: str, model: str,
) -> None:
    _write_json(evidence / "00-diagnostic-manifest-safe.json", {
        "source_head": source_head,
        "fixture_origin": fixture.get("fixture_origin", "UNKNOWN"),
        "fixture_sha256": _sha_file(fixture_path),
        "full_template_sha256": _sha_file(full_template_path),
        "short_template_sha256": _sha_file(short_template_path),
        "configured_model": model,
        "matrix": [
            {"id": case.id, "part": case.part_id, "template_kind": case.template_kind,
             "target_chars": case.plan.parts[int(case.part_id[1:]) - 1].target_chars}
            for case in cases
        ],
        "max_output_tokens": _MAX_OUTPUT_TOKENS,
        "provider_calls_before_matrix": 0,
        "production_context": "NONE: fixture is explicitly fictional",
    })
    shutil.copyfile(fixture_path, evidence / "CONTROL_FIXTURE.json")
    shutil.copyfile(full_template_path, evidence / "01-full-user-template.txt")
    shutil.copyfile(short_template_path, evidence / "02-diagnostic-short-template.txt")
    for case in cases:
        _write_text(evidence / f"{case.id}-instructions.txt", case.instructions)
        _write_text(evidence / f"{case.id}-input.txt", case.input)
        _write_json(evidence / f"{case.id}-post-adapter-safe.json", case.payload)
    _write_pair_diff(evidence, cases[0], cases[1])
    _write_pair_diff(evidence, cases[2], cases[3])


def _archive_evidence(evidence: Path) -> Path:
    archive = evidence.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in evidence.rglob("*"):
            if path.is_file() and "runtime-root" not in path.parts:
                bundle.write(path, path.relative_to(evidence))
    return archive


def _finish(evidence: Path, before: dict[str, str | None], local_appdata: Path) -> int:
    guard = {"before": before, "after": _production_hashes(local_appdata)}
    guard["result"] = "PASS" if guard["before"] == guard["after"] else "FAIL"
    _write_json(evidence / "31-production-write-guard.json", guard)
    findings = _safe_export_scan(evidence)
    _write_json(evidence / "32-secret-export-scan.json", {
        "result": "PASS" if not findings else "FAIL", "matched_files": findings,
    })
    if guard["result"] != "PASS" or findings:
        return 91
    _archive_evidence(evidence)
    return 0


def _run_live_matrix(
    evidence: Path, cases: tuple[DiagnosticCase, ...], active_keys: list[Any],
    model: str, ledger_path: Path, source_head: str,
) -> list[dict[str, object]]:
    from scriptor.openai_client import (
        HybridTextPool,
        OpenAITextClient,
        extract_visible_response_text,
    )

    attempts: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    original_request = OpenAITextClient._request

    def capture_request(client: OpenAITextClient, method: str, path: str, payload: object = None):
        attempt = len(attempts) + 1
        safe_payload = _redact(payload)
        _write_json(evidence / f"transport-{attempt:02d}-post-adapter-safe.json", safe_payload)
        entry: dict[str, object] = {
            "transport_attempt": attempt, "method": method, "path": path,
            "payload_sha256": _sha(json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)),
            "headers": "NOT_CAPTURED",
        }
        attempts.append(entry)
        response = original_request(client, method, path, payload)
        visible = extract_visible_response_text(response)
        meta = {
            **entry,
            "id": response.get("id", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "model": response.get("model", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "status": response.get("status", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "usage": response.get("usage", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "incomplete_details": response.get("incomplete_details", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "visible_response_chars": len(visible),
            "visible_response_sha256": _sha(visible),
        }
        _write_json(evidence / f"transport-{attempt:02d}-response-meta.json", meta)
        _write_text(evidence / f"transport-{attempt:02d}-visible.txt", visible)
        return response

    pool = HybridTextPool([], active_keys, "", model)
    with patch.object(OpenAITextClient, "_request", new=capture_request):
        for case in cases:
            reservation = _reserve_budget(
                ledger_path,
                run_id=case.id,
                run_kind="D",
                target=case.request.target_chars,
                source_head=source_head,
                reserved_logical_calls=1,
                reserved_http_attempts=1,
                max_full_runs=2,
                max_logical_calls=18,
                max_http_attempts=24,
            )
            _write_json(evidence / f"{case.id}-budget-reservation-safe.json", reservation)
            start_attempt = len(attempts)
            record: dict[str, object] = {
                "id": case.id, "logical_call": 1, "part_id": case.part_id,
                "template_kind": case.template_kind, "result": "UNKNOWN",
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
            }
            try:
                text = asyncio.run(pool.generate(
                    case.input,
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    instructions=case.instructions,
                ))
                _write_text(evidence / f"{case.id}-visible-response.txt", text)
                record.update({
                    "result": "OK", "visible_response_chars": len(text),
                    "visible_response_sha256": _sha(text),
                })
            except Exception as error:  # noqa: BLE001 - preserve any provider/runtime class without retrying the cell
                record.update({"result": "ERROR", "error_type": type(error).__name__})
                for key in ("status", "response_id", "incomplete_reason", "refusal", "visible_text"):
                    if hasattr(error, key):
                        value = str(getattr(error, key) or "")
                        record[key] = "[NOT_EXPORTED]" if key == "visible_text" else value
            finally:
                record["transport_attempts"] = len(attempts) - start_attempt
                _complete_budget_reservation(
                    ledger_path, case.id,
                    logical_calls=1,
                    http_attempts=int(record["transport_attempts"]),
                    result="COMPLETED" if record["result"] == "OK" else "FAILED",
                )
            results.append(record)
    _write_json(evidence / "10-logical-calls.json", results)
    _write_json(evidence / "11-transport-attempts.json", {
        "attempts": attempts, "sdk_retries": "UNKNOWN",
    })
    _write_json(evidence / "13-stage-budget-ledger-safe.json", json.loads(ledger_path.read_text(encoding="utf-8")))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--short-template", type=Path, required=True)
    parser.add_argument("--full-template", type=Path, default=DEFAULT_FULL_TEMPLATE)
    parser.add_argument("--evidence-parent", type=Path, default=DEFAULT_EVIDENCE_PARENT)
    parser.add_argument("--suite-ledger", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    repo = Path.cwd().resolve()
    sys.path.insert(0, str(repo))
    fixture_path = args.fixture.resolve()
    full_template_path = args.full_template.resolve()
    short_template_path = args.short_template.resolve()
    fixture = load_control_fixture(fixture_path)
    full_template = full_template_path.read_text(encoding="utf-8")
    short_template = short_template_path.read_text(encoding="utf-8")
    from scriptor.config import load_settings

    source_settings = load_settings()
    model = source_settings.openai_model.strip() or "gpt-5.4-mini"
    cases = build_diagnostic_cases(fixture, full_template, short_template, model=model)
    _validate_pair_isolation(cases[0], cases[1], full_template, short_template)
    _validate_pair_isolation(cases[2], cases[3], full_template, short_template)
    evidence = args.evidence_parent.resolve() / args.run_id
    if evidence.exists():
        raise SystemExit(f"evidence path already exists: {evidence}")
    production_localappdata = Path(os.environ["LOCALAPPDATA"]).resolve()
    before = _production_hashes(production_localappdata)
    evidence.mkdir(parents=True)
    runtime_root = evidence / "runtime-root"
    runtime_root.mkdir()
    os.environ.update({
        "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": str(runtime_root),
        "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(production_localappdata),
        "LOCALAPPDATA": str(runtime_root), "TEMP": str(runtime_root), "TMP": str(runtime_root),
    })
    _write_common_evidence(
        evidence, fixture_path, full_template_path, short_template_path, fixture, cases,
        _git("git rev-parse HEAD"), model,
    )
    preflight = _preflight(cases)
    _write_json(evidence / "09-preflight.json", {"result": "PASS", "cells": preflight})
    if args.preflight_only:
        return _finish(evidence, before, production_localappdata)

    active_keys = [key for key in source_settings.openai_api_keys if key.active and key.secret.strip()]
    if source_settings.scenario_provider != "openai" or not active_keys:
        raise SystemExit("configured OpenAI Scenario route with an active key is required")
    ledger_path = args.suite_ledger or args.evidence_parent.resolve() / "scenario-live-293-writer-diagnostic-budget.json"
    _run_live_matrix(evidence, cases, active_keys, model, ledger_path, _git("git rev-parse HEAD"))
    return _finish(evidence, before, production_localappdata)


if __name__ == "__main__":
    raise SystemExit(main())
