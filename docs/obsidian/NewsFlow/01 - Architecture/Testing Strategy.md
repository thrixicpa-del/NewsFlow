# Testing Strategy

## Safety first

Every Python test command goes through `tests/run_isolated.py`. It creates a disposable root, requires `NEWSFLOW_TEST_MODE=1`, preserves a separate `NEWSFLOW_PRODUCTION_LOCALAPPDATA` boundary, and finishes with the production write guard.

```powershell
python tests/run_isolated.py discover -s tests -q
python tests/run_isolated.py --pytest -m contract -q
```

Direct `python -m pytest` is deliberately refused because it has no guaranteed storage root.

## Test levels

| Marker / command | Scope | Provider policy |
| --- | --- | --- |
| `unit` | deterministic in-process helpers and state transitions | no network or credits |
| `integration` | disposable multi-module chains such as Topics→Scripts, queue persistence, Covers state and Montage planning | mocked/default local behavior |
| `contract` | renderer command type → preload/IPC → current bridge handler and response schema | no provider call |
| `packaged` | frozen core and later packaged desktop checks | disposable data only |
| `slow` | benchmark/render-oriented local suites | selected explicitly |
| `provider_real` | opt-in release smoke only | skipped unless `NEWSFLOW_ENABLE_REAL_PROVIDERS=1` |

Existing `unittest` suites remain valid; pytest classifies them at collection without a broad test rewrite. The focused frozen-core contract executes only safe `snapshot` and idempotent suggestion rejection against an isolated root. It does not call a provider.

## Frontend

Vitest plus React Testing Library cover renderer state, forms, dialogs, selection and UI command wiring. `src/contracts/newsflowCommands.test.ts` is the renderer-side contract gate. It is paired with `scriptor/test_command_contract.py`, `tests/test_runtime_action_map.py`, and the frozen-core contract test.

## Deterministic test tooling

`requirements-test.in` is the human-maintained test-tool declaration. `requirements-test.lock` is the hash-locked resolution for pytest, coverage and Ruff plus the production dependency lock. Install it only into a disposable or development virtual environment:

```powershell
python -m pip install --require-hashes -r requirements-test.lock
```

Ruff is initially run on files changed by an infrastructure phase. Expanding lint scope is a separate cleanup task; a new quality gate must not conceal pre-existing lint debt.

## Golden dataset

`tests.golden_dataset.materialize_golden_dataset()` is the compact, synthetic
cross-pipeline fixture used by every local or CI regression build. It is
versioned as `newsflow-golden-v1` and materializes under an explicit
`NEWSFLOW_TEST_ROOT` only. The fixed manifest contains one Topic, Script,
MP3 voice asset, PNG face reference, PNG cover image, MP4 footage item,
expected Topic/Script/Production mappings, a timeline, and a publication job.

The PNG, MP3, and MP4 assets are generated from a fixed recipe into a temporary
test root instead of being copied from the user's media library. Therefore no
production content, credentials, channel auth, business state, or large media
file is committed to Git. Its contract is run through the normal isolation
boundary:

```powershell
python tests/run_isolated.py tests.test_golden_dataset
```

## Performance regression policy

`tests/performance-baselines.json` records the versioned local budgets. A
metric at or below its warning threshold passes; exceeding that threshold
reports a warning for review; only the deliberately generous hard threshold
fails a regression run. This avoids treating ordinary Windows scheduling or
disk variation as a failure while still stopping a real route change.

`tests.test_performance_paths` measures deterministic local idea/script work,
voice queue scheduling, footage ranking, FastGen prompt assembly, montage
planning and publication-draft preparation. The existing
`tests.test_montage_benchmark` remains the real synthetic FFmpeg render lane.
Electron startup remains exercised by the source Electron E2E lane, rather
than being misrepresented by a Python-only timer. Provider calls are never
made by this performance suite.

```powershell
python tests/run_isolated.py tests.test_performance_baselines tests.test_performance_paths tests.test_montage_benchmark
```

## Resource checks

`tests.test_resource_soak` supplies a quick disposable resource check for
repeated bounded jobs, generated fixture media, temporary-directory cleanup,
and FFmpeg child-process termination. It is marked `slow` and remains
provider-free. The longer 40×100-job run is deliberately opt-in so ordinary
feedback is not stretched into a pseudo-soak test:

```powershell
python tests/run_isolated.py tests.test_resource_soak
$env:NEWSFLOW_RUN_SOAK = '1'
python tests/run_isolated.py tests.test_resource_soak
```

## Controlled failure matrix

`tests/failure-matrix.json` binds each required simulated failure class to a
real, isolated regression test: provider quota/timeout, FastGen transport,
voice retry/idempotency, YouTube downstream failure, invalid audio and footage,
FFmpeg retry classification, interrupted restart, missing output, and partial
provider results. `tests.test_failure_matrix` parses the referenced source
tests, so deleting or renaming a mapped case breaks the infrastructure gate.
No scenario contacts an external service or invokes system-level chaos.

## Structured action trace

Every current bridge command now emits a compact local JSONL lifecycle record
at `NewsFlow/diagnostics/action-trace.jsonl`: `started` and either `succeeded`
or `failed`.  The record carries a generated `actionId`/`correlationId`, the
command, an inferred provider where applicable, elapsed time, and only durable
job/ProductionItem/snapshot/execution identifiers.  The bridge returns the
same opaque identifier as additive `actionTrace.id`; the renderer is not
required to display it.

The trace never stores arbitrary payloads or provider responses.  Secret-like
fields and values are redacted before a write, and a trace I/O failure cannot
alter the command outcome.  Under `tests/run_isolated.py` the trace lives
strictly below `NEWSFLOW_TEST_ROOT`; no test may write a production diagnostic
file.  It is a local provider-neutral boundary for later OpenTelemetry/Sentry
adapters, not an automatic external telemetry integration.

```powershell
python tests/run_isolated.py tests.test_observability
```

## Core contract boundary

Passing source tests does not prove a release. The frozen core test invokes the actual `NewsFlowCore.exe` selected by the package configuration. The release freshness guard remains authoritative: any source module that changes packaged behavior must cause a core-bin rebuild before a package can pass release validation.
