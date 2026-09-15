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

## Core contract boundary

Passing source tests does not prove a release. The frozen core test invokes the actual `NewsFlowCore.exe` selected by the package configuration. The release freshness guard remains authoritative: any source module that changes packaged behavior must cause a core-bin rebuild before a package can pass release validation.
