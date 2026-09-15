# Script Engine

## Active Light path

`Scenarios → generate-scenarios → bridge.generate_scenarios → core.build_requests → ParallelRunner → canonical selected text provider → session.json → snapshot → Scenarios UI`.

`PromptRange` is the Python-owned range contract. A range can carry `target_chars`, `allowed_min` and `allowed_max`; one scenario is overridden by using the same `start` and `end`. `build_requests()` includes the resolved range in the provider assignment, and `generate_scenarios()` keeps it when it binds the stable ProductionItem ID and the final narration/editor prompt.

## Length/status rule

After every provider response `ParallelRunner.scenario_length_status()` counts trimmed characters. An unbounded legacy range has no length status and incurs no extra provider call. For an opted-in contract, a result is `READY`, `SHORT` or `LONG`. `SHORT`/`LONG` causes at most two fresh correction requests. An unresolved result becomes `RunState.ERROR` with `length_status=FAILED`; it is never marked ready.

The durable session row stores target/min/max, actual character count, length status and repair attempt count. `snapshot()` projects those backend values as `targetChars`, `allowedMin`, `allowedMax`, `actualChars`, `lengthStatus` and `lengthRepairAttempts`. The existing Templates editor exposes compact target/min/max inputs; the Scenarios row displays backend status and correction count.

## Regression evidence — 2026-09-11

- `test_range_target_is_included_in_the_python_owned_scenario_contract`
- `test_generated_script_persists_its_production_item_id`
- `test_scenario_length_contract_survives_session_roundtrip`
- `test_short_script_is_repaired_within_the_configured_bounds`
- `test_unresolved_length_is_not_marked_ready_after_two_repairs`

Focused provider tests use local fakes. No provider call, production queue write, or user-data reset was performed.
