# ADR — TEST AND BUILD ISOLATION POLICY

**Status:** accepted 2026-09-12  
**Decision:** production persistence is never a test input/output, and a package may be produced only after its current runtime contract passes.

## Test boundary

- Python tests run through `python tests/run_isolated.py …`. The runner creates one disposable temporary root, sets `NEWSFLOW_TEST_MODE=1`, `NEWSFLOW_TEST_ROOT`, `LOCALAPPDATA`, `TEMP` and `TMP` for its child process, and retains the caller's `%LOCALAPPDATA%` only as `NEWSFLOW_PRODUCTION_LOCALAPPDATA`.
- `scriptor.config.app_data_root()` refuses a test process with no explicit test root, or one whose effective `LOCALAPPDATA`/test root is the declared production location. It fails before creating a directory or file.
- Test media defaults also live below `NEWSFLOW_TEST_ROOT/Media`; test fixtures and SQLite state therefore cannot use production folders.
- A direct `unittest` process without the isolation variables fails safe whenever it reaches persistence. It must be rerun through the isolated runner.
- Tests may use their own nested `TemporaryDirectory` fixtures, but never the user’s canonical `%LOCALAPPDATA%/NewsFlow` path.

## Runtime and legacy boundary

- Normal `load_settings()` reads only canonical current NewsFlow settings. It does not read legacy Scriptor settings or backup snapshots as fallbacks.
- Normal `load_session()` reads current NewsFlow session data and its own last-known-good backup only. Legacy Scriptor session data is excluded.
- `migrate_legacy_session()` is the explicit, opt-in legacy-session migration path. It never replaces a current NewsFlow session; a current session wins.
- Settings carry `schema_version`. A runtime refuses a file with a newer schema version and leaves its bytes intact rather than silently downgrading/re-writing it.
- Backup files are recovery evidence only. They are not normal runtime authority and are never used to overwrite current data automatically.

## Build boundary

- `pnpm verify:build-runtime` is required by both `package:preview` and `package:release`, before Electron Builder is invoked.
- The guard verifies the package version marker, Settings schema/downgrade guard, current Universal V2 prompt source, explicit legacy-session policy, bridge entry point, core-bin version marker, and all direct lockfile importer resolutions.
- `verify:core-runtime` remains a separate freshness check for the packaged Python core. A stale core or changed active source prevents packaging.
- Source builds and verification scripts do not read or write user storage. Packaging/launch remain separately authorized release operations and require the preservation protocol in [[19 - Release Baselines/2026-09-11 Pre-Light Backup]].

## Regression evidence

- `scriptor.test_config.TestStorageIsolationTests`: production-path access fails before write; isolated path receives the test write.
- `scriptor.test_config.CurrentRuntimePriorityTests`: current settings win over a present legacy profile.
- `tests.test_session`: legacy sessions are ignored by ordinary restart and imported only through explicit migration.
- `scriptor.test_config.SchemaVersionSafetyTests`: newer settings are not downgraded; current settings/scripts/covers survive restart in isolated storage.
- `tests.test_ui_delivery.ActiveInterfaceTests.test_packaging_requires_current_runtime_contract_verification`: both package commands require the build-runtime guard.
