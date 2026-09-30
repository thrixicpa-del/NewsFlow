"""Run one opt-in, disposable Scenario acceptance capture.

This is deliberately a test-only harness.  It uses the ordinary bridge and
configured Scenario provider, but redirects all state to ``NEWSFLOW_TEST_ROOT``
and exports neither credentials nor transport headers.  It is not part of the
runtime and must be invoked explicitly by a reviewer who has already approved
the paid-call budget.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

TITLE_A = (
    "МИР ОПЯТЬ ОТКЛАДЫВАЕТСЯ? — РОССИЯ УСИЛИЛА УДАРЫ ПО УКРАИНЕ — "
    "КИЕВ СНОВА ОКАЗАЛСЯ ПОД МАССИРОВАННОЙ АТАКОЙ"
)
TITLE_B = (
    "ГОРОД ОСТАЛСЯ БЕЗ ВОДЫ — АВАРИЯ ОСТАНОВИЛА ВОДОСНАБЖЕНИЕ — "
    "КАК СЛУЖБЫ ВОССТАНОВИЛИ ПОДАЧУ"
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_MAX_FULL_RUNS = 4
_MAX_LOGICAL_CALLS = 32
_MAX_HTTP_ATTEMPTS = 40
_MODEL_USD_PER_MILLION_TOKENS = {
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
}


def _sha(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _estimate_max_call_usd(model: str, *, input_chars: int, max_output_tokens: int) -> dict[str, object]:
    """Conservatively reserve an upper bound before an opt-in live request.

    One input character per token deliberately over-reserves Russian text.
    Reasoning is part of output tokens in Responses usage, so it is never
    charged a second time in this estimate.
    """
    normalized = str(model or "").strip()
    tariff_key = next((key for key in _MODEL_USD_PER_MILLION_TOKENS if normalized.startswith(key)), "")
    if not tariff_key:
        raise ValueError(f"no approved cost tariff for model {normalized!r}")
    tariff = _MODEL_USD_PER_MILLION_TOKENS[tariff_key]
    input_upper = max(0, int(input_chars))
    output_upper = max(0, int(max_output_tokens))
    estimate = (input_upper * tariff["input"] + output_upper * tariff["output"]) / 1_000_000
    return {
        "model": normalized,
        "pricing_basis": "official USD per 1M input/output tokens; one input character per token upper bound",
        "input_token_upper_bound": input_upper,
        "output_token_upper_bound": output_upper,
        "reasoning_tokens_charged_separately": False,
        "estimated_max_usd": round(estimate, 6),
    }


def _write_text(path: Path, value: str) -> None:
    """Write evidence bytes verbatim across Windows and POSIX hosts."""
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(value)


def _write_json(path: Path, value: object) -> None:
    _write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _git(command: str) -> str:
    return subprocess.check_output(command, shell=True, text=True).strip()


def _production_hashes(local_appdata: Path) -> dict[str, str | None]:
    root = local_appdata / "NewsFlow"
    return {
        name: _sha((root / name).read_bytes()) if (root / name).is_file() else None
        for name in ("settings.json", "session.json", "covers-library.json")
    }


def _redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).casefold() in {
                "authorization", "api_key", "apikey", "secret", "password", "cookie",
            } else _redact(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact(child) for child in value]
    return value


def _phase(prompt: str, instructions: object, method: str) -> str:
    combined = f"{instructions or ''}\n{prompt}"
    if "structural repairer" in combined:
        return "STRUCTURAL_REPAIR"
    if "FRESH STORY PLANNER RETRY" in combined:
        return "FRESH_PLANNER"
    if "NewsFlow Story Planner" in combined:
        return "PLANNER"
    match = re.search(r"CURRENT PART: (P\d+)", combined)
    return f"WRITER_{match.group(1)}" if match else f"UNKNOWN:{method}"


def _planner_test_route_kwargs(
    kwargs: dict[str, object], *, model: str | None, reasoning_effort: str | None,
) -> dict[str, object]:
    """Route only Structured-Output Planner calls in an opt-in test harness.

    The normal runtime has no route override.  In this harness a non-empty
    ``text_format`` is the adapter's trusted technical indication of a Planner
    or structural-repair request; Writer calls do not carry a schema and keep
    their configured model and parameters exactly as-is.
    """
    routed = dict(kwargs)
    if routed.get("text_format") is not None:
        if model:
            routed["model"] = model
        if reasoning_effort is not None:
            routed["reasoning_effort"] = reasoning_effort
    return routed


def _post_adapter_payload_comparison(payload: object) -> object:
    """Return a comparison projection that excludes only matrix variables."""
    if not isinstance(payload, dict):
        raise TypeError("post-adapter payload must be an object")
    return {
        key: value for key, value in payload.items()
        if key not in {"model", "reasoning"}
    }


def _test_scenario_request(settings, title: str, item: dict, bridge):
    """Use the same request constructors and trusted item contract as bridge."""
    from scriptor.core import PromptRange, ScenarioRequest, build_requests

    ranges = [PromptRange(
        int(value.get("start", 1)), int(value.get("end", 1)), str(value.get("prompt", "")),
        max(0, int(value.get("target_chars", 0) or 0)),
        max(0, int(value.get("allowed_min", 0) or 0)),
        max(0, int(value.get("allowed_max", 0) or 0)),
    ) for value in settings.prompt_ranges]
    base = build_requests(
        [title], settings.template, ranges,
        settings.scenario_target_chars,
        settings.scenario_allowed_min,
        settings.scenario_allowed_max,
    )[0]
    narration_only = (
        "\n\nФОРМАТ ОТВЕТА ОБЯЗАТЕЛЕН: верни только готовый цельный текст для озвучки. "
        "Не добавляй рабочую концепцию, ядро новости, лейтмотив, план, структуру, подзаголовки, "
        "Markdown, списки, технические комментарии или фразы вроде «если план согласован». "
        "Допускаются только обычные связные абзацы самого сценария."
    )
    factual_context_available, dramatized_allowed = bridge._production_item_material_contract(item)
    return ScenarioRequest(
        base.index, base.title, base.prompt + bridge.production_item_prompt(item) + narration_only,
        str(item.get("id", "")), base.target_chars, base.allowed_min, base.allowed_max,
        factual_context_available, dramatized_allowed,
    )


def _read_budget_ledger(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"version": 1, "runs": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("runs"), list):
        raise TypeError("scenario acceptance budget ledger is invalid")
    return value


def _budget_totals(ledger: dict[str, object]) -> tuple[int, int, int]:
    runs = ledger.get("runs", [])
    if not isinstance(runs, list):
        return 0, 0, 0
    # A fixed one-call diagnostic cell consumes model/API budget but is not a
    # full Scenario acceptance run.  Keeping that distinction in the shared
    # ledger lets a bounded diagnostic precede at most the approved number of
    # ordinary pipeline runs without silently resetting either allowance.
    full_runs = sum(
        1 for item in runs
        if isinstance(item, dict) and str(item.get("kind", "")).upper() not in {"D", "M"}
    )
    logical = sum(max(0, int(item.get("reserved_logical_calls", 0) or 0))
                  for item in runs if isinstance(item, dict))
    http = sum(max(0, int(item.get("reserved_http_attempts", 0) or 0))
               for item in runs if isinstance(item, dict))
    return full_runs, logical, http


def _reserve_budget(
    path: Path, *, run_id: str, run_kind: str, target: int, source_head: str,
    reserved_logical_calls: int | None = None,
    reserved_http_attempts: int | None = None,
    max_full_runs: int = _MAX_FULL_RUNS,
    max_logical_calls: int = _MAX_LOGICAL_CALLS,
    max_http_attempts: int = _MAX_HTTP_ATTEMPTS,
) -> dict[str, object]:
    """Persist a conservative reservation before the first external request."""
    ledger = _read_budget_ledger(path)
    full_runs, logical, http = _budget_totals(ledger)
    # The normal route is Planner + one Writer per part.  Reserve its bounded
    # planner recovery room too, so an interrupted capture cannot silently
    # consume a new allowance from another disposable profile.
    part_count = max(1, (target + 4999) // 5000)
    reserve_logical = (
        max(0, int(reserved_logical_calls))
        if reserved_logical_calls is not None
        else 3 + part_count  # initial + repair + fresh + Writers
    )
    reserve_http = (
        max(0, int(reserved_http_attempts))
        if reserved_http_attempts is not None
        else reserve_logical + 2  # bounded key/transport contingency
    )
    is_full_run = str(run_kind).upper() not in {"D", "M"}
    if (
        (is_full_run and full_runs >= max_full_runs)
        or logical + reserve_logical > max_logical_calls
        or http + reserve_http > max_http_attempts
    ):
        raise RuntimeError("Scenario acceptance paid-call budget is exhausted")
    entry = {
        "run_id": run_id,
        "kind": run_kind,
        "target_chars": target,
        "source_head": source_head,
        "reserved_at_utc": datetime.now(timezone.utc).isoformat(),
        "reserved_logical_calls": reserve_logical,
        "reserved_http_attempts": reserve_http,
        "status": "RESERVED",
    }
    ledger["runs"].append(entry)
    _write_json(path, ledger)
    return entry


def _complete_budget_reservation(
    path: Path, run_id: str, *, logical_calls: int, http_attempts: int,
    result: str,
) -> dict[str, object]:
    ledger = _read_budget_ledger(path)
    for entry in reversed(ledger["runs"]):
        if isinstance(entry, dict) and entry.get("run_id") == run_id:
            entry.update({
                "status": result,
                "actual_logical_calls": logical_calls,
                "actual_http_attempts": http_attempts,
                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            break
    _write_json(path, ledger)
    return ledger


class RecordingPool:
    """Transparent logical-call ledger; it does not change provider retries."""

    def __init__(self, sessions, openai_keys, chat_url, model, *, planner_model=None,
                 planner_reasoning_effort=None):
        from scriptor.openai_client import HybridTextPool

        self.inner = HybridTextPool(sessions, openai_keys, chat_url, model)
        self.concurrency = self.inner.concurrency
        self.calls: list[dict[str, object]] = []
        self.max_logical_calls: int | None = None
        self.planner_model = planner_model
        self.planner_reasoning_effort = planner_reasoning_effort

    async def _call(self, method: str, prompt: str, *args, **kwargs):
        if self.max_logical_calls is not None and len(self.calls) >= self.max_logical_calls:
            raise RuntimeError("Scenario acceptance logical-call reservation exhausted")
        routed_kwargs = _planner_test_route_kwargs(
            kwargs,
            model=self.planner_model,
            reasoning_effort=self.planner_reasoning_effort,
        )
        instructions = routed_kwargs.get("instructions")
        entry = {
            "logical_call": len(self.calls) + 1,
            "method": method,
            "phase": _phase(prompt, instructions, method),
            "input_chars": len(prompt),
            "input_sha256": _sha(prompt),
            "instructions_chars": len(str(instructions or "")),
            "instructions_sha256": _sha(str(instructions or "")),
            "max_output_tokens": routed_kwargs.get("max_output_tokens", "UNKNOWN"),
            "text_format": _redact(routed_kwargs.get("text_format", "NONE")),
            "model_override": routed_kwargs.get("model", "NONE"),
            "reasoning_effort": routed_kwargs.get("reasoning_effort", "NONE"),
        }
        self.calls.append(entry)
        try:
            result = await getattr(self.inner, method)(prompt, *args, **routed_kwargs)
        except Exception as error:
            entry.update({"result": "ERROR", "error_type": type(error).__name__})
            for key in ("status", "response_id", "incomplete_reason"):
                if hasattr(error, key):
                    entry[key] = str(getattr(error, key) or "")
            raise
        entry.update({
            "result": "OK",
            "visible_response_chars": len(result),
            "visible_response_sha256": _sha(result),
        })
        return result

    async def generate(self, prompt: str, *args, **kwargs):
        return await self._call("generate", prompt, *args, **kwargs)

    async def generate_fresh(self, prompt: str, *args, **kwargs):
        return await self._call("generate_fresh", prompt, *args, **kwargs)

    async def generate_openai(self, prompt: str, *args, **kwargs):
        return await self._call("generate_openai", prompt, *args, **kwargs)


def _write_readme(evidence: Path, run_id: str) -> None:
    _write_text(
        evidence / "README.md",
        "# Disposable Scenario acceptance evidence\n\n"
        f"Run: `{run_id}`. This directory contains safe post-adapter payloads, "
        "visible model text, persisted Story Map/session projection, accepted "
        "parts, assembly facts and call ledgers. Credentials, headers, cookies, "
        "runtime-root and account settings are intentionally excluded.\n",
    )


def _safe_export_scan(evidence: Path) -> list[str]:
    findings: list[str] = []
    for path in evidence.rglob("*"):
        if not path.is_file() or "runtime-root" in path.parts:
            continue
        if path.suffix.lower() not in {".json", ".txt", ".md", ".py"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            findings.append(str(path.relative_to(evidence)))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--title", default=TITLE_A)
    parser.add_argument("--target", type=int, default=12000)
    parser.add_argument("--minimum", type=int, default=11500)
    parser.add_argument("--maximum", type=int, default=12500)
    parser.add_argument("--run-kind", choices=("A", "B", "M", "R"), default="A")
    parser.add_argument("--planner-only", action="store_true")
    parser.add_argument("--planner-model")
    parser.add_argument("--planner-reasoning-effort", choices=("none", "low", "medium", "high", "xhigh"))
    parser.add_argument("--planner-output-tokens", type=int)
    parser.add_argument("--suite-ledger", type=Path)
    parser.add_argument("--a-editorial-passed", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--full-run-limit", type=int, default=_MAX_FULL_RUNS)
    parser.add_argument("--logical-limit", type=int, default=_MAX_LOGICAL_CALLS)
    parser.add_argument("--http-limit", type=int, default=_MAX_HTTP_ATTEMPTS)
    args = parser.parse_args()
    if args.minimum > args.maximum:
        raise SystemExit("minimum must not exceed maximum")
    if args.planner_only != (args.run_kind == "M"):
        raise SystemExit("planner-only is required exactly for an M matrix cell")
    if args.planner_only and (
        not str(args.planner_model or "").strip()
        or args.planner_reasoning_effort is None
        or args.planner_output_tokens != 32768
    ):
        raise SystemExit("M cells require model, reasoning effort, and planner-output-tokens=32768")

    repo = Path.cwd().resolve()
    sys.path.insert(0, str(repo))
    from scriptor.config import load_settings

    production_localappdata = Path(os.environ["LOCALAPPDATA"]).resolve()
    before = _production_hashes(production_localappdata)
    source_settings = load_settings()
    active_keys = [key for key in source_settings.openai_api_keys if key.active and key.secret.strip()]
    if source_settings.scenario_provider != "openai" or not active_keys:
        raise SystemExit("configured OpenAI Scenario route with an active key is required")

    evidence_parent = Path(r"D:\NewsFlow-RC\test-profiles")
    evidence = evidence_parent / args.run_id
    if evidence.exists():
        raise SystemExit(f"evidence path already exists: {evidence}")
    evidence.mkdir(parents=True)
    test_root = evidence / "runtime-root"
    test_root.mkdir()
    os.environ.update({
        "NEWSFLOW_TEST_MODE": "1",
        "NEWSFLOW_TEST_ROOT": str(test_root),
        "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(production_localappdata),
        "LOCALAPPDATA": str(test_root),
        "TEMP": str(test_root),
        "TMP": str(test_root),
    })

    from scriptor import bridge
    from scriptor.openai_client import OpenAITextClient, extract_visible_response_text
    from scriptor.session import load_session

    settings = copy.deepcopy(source_settings)
    settings.prompt_ranges = [*settings.prompt_ranges, {
        "start": 1, "end": 1, "prompt": "", "target_chars": args.target,
        "allowed_min": args.minimum, "allowed_max": args.maximum,
    }]
    item_id = "test-scenario-" + _sha(args.title)[:12]
    item = {
        "id": item_id, "title": args.title, "topic": args.title, "manual": True,
        "framing_type": "EDITORIAL", "core_event": "", "supporting_context": [],
        "script_requirements": [], "test_context_origin": "HEADLINE_ONLY_DRAMATIZED_TEST",
    }
    settings.idea_production_items = [item]
    settings.idea_scenario_context = {args.title: dict(item)}
    settings.idea_results = []
    settings.cover_queue = []

    _write_json(evidence / "00-run-manifest-safe.json", {
        "run_id": args.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_head": _git("git rev-parse HEAD"),
        "git_status_short": _git("git status --short"),
        "provider": settings.scenario_provider,
        "configured_model": settings.openai_model,
        "test_planner_route": {
            "enabled": bool(args.planner_model),
            "model": args.planner_model or "NONE",
            "reasoning_effort": args.planner_reasoning_effort or "NONE",
            "max_output_tokens": args.planner_output_tokens or "RUNTIME_DEFAULT",
        },
        "active_key_count": len(active_keys),
        "key_material": "NOT_CAPTURED_MEMORY_ONLY",
        "contract": {"target_chars": args.target, "allowed_min": args.minimum, "allowed_max": args.maximum},
        "test_context_origin": item["test_context_origin"],
        "production_context": "NONE: headline is not factual evidence",
    })
    _write_text(evidence / "01-user-template.txt", settings.template)
    _write_json(evidence / "02-production-item-test-context.json", item)
    _write_readme(evidence, args.run_id)

    if args.preflight_only:
        _write_json(evidence / "99-preflight.json", {"result": "PASS", "provider_calls": 0})
        return _finish(evidence, before, production_localappdata, [], [], None)

    if args.run_kind == "B" and not args.a_editorial_passed:
        raise SystemExit("B requires a completed editorially accepted A run")
    ledger_path = args.suite_ledger or evidence_parent / "scenario-live-293-stage-budget-ledger.json"
    reservation = _reserve_budget(
        ledger_path,
        run_id=args.run_id,
        run_kind=args.run_kind,
        target=args.target,
        source_head=_git("git rev-parse HEAD"),
        reserved_logical_calls=1 if args.planner_only else None,
        reserved_http_attempts=1 if args.planner_only else None,
        max_full_runs=args.full_run_limit,
        max_logical_calls=args.logical_limit,
        max_http_attempts=args.http_limit,
    )
    _write_json(evidence / "12-budget-reservation-safe.json", {
        "ledger_name": ledger_path.name,
        "reservation": reservation,
        "limits": {
            "full_runs": args.full_run_limit,
            "logical_calls": args.logical_limit,
            "http_attempts": args.http_limit,
        },
    })

    captured_requests: list[dict[str, object]] = []
    captured_responses: list[dict[str, object]] = []
    original_request = OpenAITextClient._request

    def capture_request(client, method, path, payload=None):
        number = len(captured_requests) + 1
        if number > int(reservation["reserved_http_attempts"]):
            raise RuntimeError("Scenario acceptance HTTP-attempt reservation exhausted")
        safe_payload = _redact(payload)
        _write_json(evidence / f"request-{number:02d}-post-adapter-safe.json", safe_payload)
        captured_requests.append({
            "transport_attempt": number, "method": method, "path": path,
            "payload_chars": len(json.dumps(safe_payload, ensure_ascii=False)),
            "payload_sha256": _sha(json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)),
            "headers": "NOT_CAPTURED",
        })
        response = original_request(client, method, path, payload)
        visible = extract_visible_response_text(response)
        meta = {
            "transport_attempt": number,
            "id": response.get("id", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "model": response.get("model", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "status": response.get("status", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "usage": response.get("usage", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "incomplete_details": response.get("incomplete_details", "UNKNOWN") if isinstance(response, dict) else "UNKNOWN",
            "visible_output_chars": len(visible),
            "visible_output_sha256": _sha(visible),
        }
        captured_responses.append(meta)
        _write_json(evidence / f"response-{number:02d}-transport-meta.json", meta)
        _write_text(evidence / f"response-{number:02d}-visible.txt", visible)
        return response

    pool_box: dict[str, RecordingPool] = {}

    def pool_factory(*pool_args, **pool_kwargs):
        pool = RecordingPool(
            *pool_args,
            **pool_kwargs,
            planner_model=args.planner_model,
            planner_reasoning_effort=args.planner_reasoning_effort,
        )
        pool.max_logical_calls = int(reservation["reserved_logical_calls"])
        pool_box["pool"] = pool
        return pool

    planner_only_calls: list[dict[str, object]] = []
    try:
        with patch.object(OpenAITextClient, "_request", new=capture_request):
            if args.planner_only:
                from scriptor.story_planner import (
                    calculate_story_part_targets,
                    parse_story_plan_response,
                    split_story_planner_request,
                    story_planner_response_format,
                )

                request = _test_scenario_request(settings, args.title, item, bridge)
                part_targets = calculate_story_part_targets(max(request.target_chars, request.allowed_min))
                instructions, planner_input = split_story_planner_request(request, part_targets)
                response_format = story_planner_response_format()
                _write_text(evidence / "03-planner-instructions.txt", instructions)
                _write_text(evidence / "04-planner-input.txt", planner_input)
                _write_json(evidence / "05-planner-response-format.json", response_format)
                client = OpenAITextClient(active_keys[0].secret, settings.openai_model, active_keys[0].label)
                planner_response = asyncio.run(client.generate(
                    planner_input,
                    instructions=instructions,
                    text_format=response_format,
                    max_output_tokens=args.planner_output_tokens,
                    model=args.planner_model,
                    reasoning_effort=args.planner_reasoning_effort,
                ))
                planner_only_calls.append({
                    "logical_call": 1,
                    "phase": "PLANNER",
                    "method": "generate",
                    "model_override": args.planner_model,
                    "reasoning_effort": args.planner_reasoning_effort,
                    "max_output_tokens": args.planner_output_tokens,
                    "input_chars": len(planner_input),
                    "input_sha256": _sha(planner_input),
                    "instructions_chars": len(instructions),
                    "instructions_sha256": _sha(instructions),
                    "text_format": response_format,
                    "result": "OK",
                    "visible_response_chars": len(planner_response),
                    "visible_response_sha256": _sha(planner_response),
                })
                try:
                    parsed = parse_story_plan_response(
                        planner_response, part_targets, require_state_transitions=True,
                    )
                    _write_json(evidence / "20-story-map-parsed.json", parsed.to_dict())
                    _write_json(evidence / "21-planner-parse.json", {"result": "PASS"})
                except (TypeError, ValueError) as error:
                    _write_json(evidence / "21-planner-parse.json", {
                        "result": "FAIL", "error_type": type(error).__name__,
                        "message_chars": len(str(error)),
                    })
            else:
                with patch.object(bridge, "load_settings", return_value=settings), \
                     patch.object(bridge, "save_settings", return_value=None), \
                     patch.object(bridge, "HybridTextPool", side_effect=pool_factory):
                    bridge.add_scenarios({"titles": args.title})
                    bridge.generate_scenarios({"provider": "openai", "indices": [0]})
    except Exception as error:  # noqa: BLE001 - preserve safe evidence on a provider/runtime failure
        _write_json(evidence / "98-harness-exception.json", {
            "type": type(error).__name__, "message_chars": len(str(error)),
        })

    _titles, jobs = load_session()
    job = jobs[0] if jobs else None
    calls = planner_only_calls or (pool_box.get("pool").calls if pool_box.get("pool") else [])
    _write_json(evidence / "10-logical-calls.json", calls)
    _write_json(evidence / "11-transport-attempts.json", {
        "attempts": captured_requests, "responses": captured_responses, "sdk_retries": "UNKNOWN",
    })
    if job is not None:
        _write_json(evidence / "20-story-map-persisted.json", job.story_plan or {})
        _write_json(evidence / "21-job-safe.json", {
            "state": job.state.value, "error": job.error, "actual_chars": job.actual_chars,
            "length_status": job.length_status, "story_planner_status": job.story_planner_status,
            "story_planner_failure": job.story_planner_failure,
            "accepted_story_parts": [
                {key: row.get(key) for key in ("part_id", "content_ids", "target_chars", "text")}
                for row in job.accepted_story_parts
            ],
        })
        for row in job.accepted_story_parts:
            _write_text(evidence / f"part-{row['part_id']}.txt", str(row.get("text", "")))
        _write_text(evidence / "scenario.txt", job.result)
        _write_json(evidence / "30-assembly.json", {
            "separator": "\\n\\n", "python_len_stripped": len(job.result.strip()),
            "scenario_sha256": _sha(job.result),
            "parts": [
                {"part_id": row.get("part_id"), "target_chars": row.get("target_chars"),
                 "chars": len(str(row.get("text", "")).strip()), "sha256": _sha(str(row.get("text", "")))}
                for row in job.accepted_story_parts
            ],
        })
    result = _finish(evidence, before, production_localappdata, captured_requests, captured_responses, job)
    ledger = _complete_budget_reservation(
        ledger_path, args.run_id,
        logical_calls=len(calls), http_attempts=len(captured_requests),
        result="COMPLETED" if result == 0 else "FAILED",
    )
    ledger_export = evidence / "13-budget-ledger-safe.json"
    _write_json(ledger_export, ledger)
    if result == 0:
        # _finish has already created the immutable archive.  Append the
        # completion record so the published ZIP contains both reservation and
        # actual usage without rewriting any captured request/response file.
        with zipfile.ZipFile(evidence.with_suffix(".zip"), "a", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(ledger_export, ledger_export.relative_to(evidence))
    return result


def _finish(evidence: Path, before: dict[str, str | None], local_appdata: Path, requests: list, responses: list, job: object) -> int:
    guard = {"before": before, "after": _production_hashes(local_appdata)}
    guard["result"] = "PASS" if guard["before"] == guard["after"] else "FAIL"
    _write_json(evidence / "31-production-write-guard.json", guard)
    findings = _safe_export_scan(evidence)
    _write_json(evidence / "32-secret-export-scan.json", {"result": "PASS" if not findings else "FAIL", "matched_files": findings})
    summary = {
        "evidence_dir": str(evidence), "logical_calls": len(_load_calls(evidence)),
        "transport_attempts": len(requests), "captured_responses": len(responses),
        "job_state": getattr(getattr(job, "state", None), "value", "MISSING"),
        "production_write_guard": guard["result"], "secret_export_scan": "PASS" if not findings else "FAIL",
    }
    _write_json(evidence / "99-summary.json", summary)
    if findings or guard["result"] != "PASS":
        print(json.dumps(summary, ensure_ascii=False))
        return 91
    archive = evidence.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in evidence.rglob("*"):
            if path.is_file() and "runtime-root" not in path.parts:
                bundle.write(path, path.relative_to(evidence))
    summary["zip"] = str(archive)
    _write_json(evidence / "99-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def _load_calls(evidence: Path) -> list[object]:
    path = evidence / "10-logical-calls.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


if __name__ == "__main__":
    raise SystemExit(main())
