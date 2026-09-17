# Environment Isolation Contract

## Identities

| Environment | Purpose | Storage rule |
| --- | --- | --- |
| Production | Operator's normal NewsFlow session | Canonical `%LOCALAPPDATA%\\NewsFlow`; never a fixture or automated-test target. |
| Test / RC | Manual validation of a release candidate | Explicit `NEWSFLOW_TEST_ROOT`; separate Electron profile and no production business state. |
| Disposable | Automated unit, contract, integration and visual checks | A fresh temporary root, removed by the test runner or OS cleanup. |

## Non-negotiable contract

When `NEWSFLOW_TEST_MODE=1`, `NEWSFLOW_TEST_ROOT` is mandatory. The runtime fails before any persistence is resolved when it is missing, equals the production local-app-data root, or lies in its canonical `NewsFlow` storage tree. There is no fallback from test mode to production storage.

The Python storage resolver in `scriptor/config.py` owns the test-root decision for settings, sessions, cover library, production items, jobs and media defaults. `tests/run_isolated.py` creates a temporary disposable root and exports all required variables to child Python tests. The Electron resolver uses the same explicit root and stores its profile at `<NEWSFLOW_TEST_ROOT>/electron-user-data`.

An Electron process in test mode uses the native title `NewsFlow Studio [TEST]`. A normal launch remains `NewsFlow Studio`; setting the title alone never enables a test profile.

## Approved commands

Automated Python tests must be launched through the isolated runner:

```powershell
python tests/run_isolated.py discover -s tests -q
```

For a manual test/RC launch, set a newly created non-production root explicitly in the launch environment:

```powershell
$env:NEWSFLOW_TEST_MODE = '1'
$env:NEWSFLOW_TEST_ROOT = 'D:\NewsFlow-RC\disposable\my-test-run'
$env:NEWSFLOW_PRODUCTION_LOCALAPPDATA = $env:LOCALAPPDATA
$env:LOCALAPPDATA = $env:NEWSFLOW_TEST_ROOT
```

The test root must never be `%LOCALAPPDATA%` itself or `%LOCALAPPDATA%\\NewsFlow` (including any child). It must contain no copied production credentials, topics, cover registry, sessions, queues, footage index, or face library unless a separately approved test fixture explicitly supplies safe synthetic values.

## Artifact boundary

In test mode, `storyflow_documents_root()` resolves to `<NEWSFLOW_TEST_ROOT>/Media`. This keeps generated MP3/MP4/covers, footage metadata and temporary output out of both production storage and the operator's configured output folders.

## Verification

The Python and Electron regression tests cover missing test roots, a declared production local-app-data root, a root nested within canonical production storage, and the `[TEST]` native identity. Any failure is a safety failure and blocks test execution or RC validation.
