# Observability

## Current local trace

The active bridge writes a compact local JSONL action lifecycle to
`NewsFlow/diagnostics/action-trace.jsonl`.  Electron creates one opaque ID per
IPC command, passes it in the existing generic payload, and the bridge returns
it as `actionTrace.id`.  Each lifecycle has `started` plus `succeeded` or
`failed`, a command, elapsed time, an inferred provider where relevant, and
only durable job/ProductionItem/snapshot/execution identifiers.

No arbitrary request payload or provider response is recorded.  Credential-
like fields and values are redacted before a write.  Trace failure is
best-effort and cannot change a user command result.  Under the isolated test
runner every diagnostic path resolves below `NEWSFLOW_TEST_ROOT`.

## Adapter boundary

`scriptor.telemetry` defines the provider-neutral event envelope and exporter
protocol for metrics, timings, structured events and future trace adapters.
The present `LocalTelemetryExporter` writes only `telemetry.jsonl` beside the
action trace.  It imports no network SDK and performs no outbound request.

Sentry and OpenTelemetry are declared as optional adapter plans only:

| Adapter | Intended use | Explicit future switch |
| --- | --- | --- |
| OpenTelemetry | traces, timings and metrics | `NEWSFLOW_ENABLE_OPENTELEMETRY` |
| Sentry | crash and error reporting | `NEWSFLOW_ENABLE_SENTRY` |

An environment flag alone never creates an exporter, imports an SDK, sends
data, or reads a DSN.  A future hosted integration requires a separately
reviewed adapter, explicit dependency, an injected destination and a user
decision about account/retention policy.  Until then all telemetry remains
local and redacted by default.

## Verification

```powershell
python tests/run_isolated.py tests.test_observability tests.test_telemetry_architecture
```

The frozen-core trace contract is separately verified by
`tests.test_frozen_core_command_contract`; `verify:core-runtime` rejects a
core older than the imported `observability.py` runtime.
