# Issue #314 — explicit API-key reveal and edit

Canonical repository: `thrixicpa-del/NewsFlow`.
Base: `a2982ba58efb4cd0bc9d7ad795b7067cf40ecaed`.
Branch: `codex/api-key-edit`. No merge, Frozen Core rebuild or EXE packaging.

## Contract and changes

- Existing FastGen, OpenAI, Secret Voicer, Lumean, VoiceGen, WProject and
  YouTube Data API credentials can be opened explicitly in the Keys editor.
- Password masking is the default. Show/hide is an operator action; cancel,
  successful save and leaving the screen discard the secret from component state.
- A dedicated trusted Electron IPC channel returns exactly the selected secret,
  label and revision. It is excluded from the generic renderer command allowlist.
  Ordinary snapshots and action diagnostics do not contain raw credentials.
- Save replaces one encrypted credential, not an appended duplicate. Active flags,
  notes, provider metadata, other credentials and unrelated profile settings survive.
- The selected row is checked by fingerprint and secret/label revision. The
  revision is checked again against the current disk snapshot under the existing
  settings write lock. Stale forms fail without replacing the winning update.
- Credential replacement starts from the current locked disk profile rather than
  serializing an old complete Settings object over concurrent changes.
- Background saves cannot resurrect an observed old credential, reorder rotated
  rows or revert a label-only edit. Duplicate-secret rows remain distinct.
- Renaming a selected FastGen key updates the selected label without selecting
  an unrelated key. Concurrent edits of another service preserve that selection.
- Pending reveal/save operations are locked synchronously. Errors are generic
  local alerts, drafts survive failed saves, and late reveal responses are ignored
  after unmount. Existing dirty-navigation and Ctrl+S behavior is retained.

No Scenario, Planner, Writer, Covers generation/resolution, OAuth or publication
algorithm changed. Existing in-flight clients are not forcibly restarted: the
new credential is used by subsequent newly constructed provider requests.

## RED → GREEN evidence

Initial regressions failed because the reveal/update handlers and editor were
absent. Additional tests reproduced stale-worker resurrection/order issues,
label-only reversion, duplicate-secret row loss and FastGen selection loss.
The final concurrent-update regression reproduced an OpenAI edit overwriting a
concurrent FastGen rename/selection and output path; narrow locked replacement
made the same regression pass. No test was weakened to obtain GREEN.

## Verification (Windows source runtime)

- `python tests/run_isolated.py tests.test_api_keys tests.test_security
  tests.test_covers tests.test_voicer tests.test_observability
  tests.test_runtime_action_map tests.test_bridge_payload_transport
  tests.test_session tests.test_scenarios tests.test_runner
  tests.test_story_planner tests.test_electron_security tests.test_secret_scan -q`:
  **502 passed**; harness production-write guard PASS.
- `tests.test_api_keys`: **16 passed**, including all seven services, encrypted
  persistence, stale CAS, failure cleanup, privacy, metadata and concurrency.
- Real `HybridTextPool` / `OpenAITextClient` request with mocked HTTP transport:
  next Authorization header contains the replacement synthetic key, not the old
  one. No live API call was made.
- `pnpm test:ui`: **40 files / 307 passed** (settings suite: 17 tests).
- `NEWSFLOW_RUN_ELECTRON_E2E=1 python tests/run_isolated.py
  tests.test_electron_e2e.ElectronE2ESmokeTests.test_api_key_edit_reveal_and_reload_through_real_ui_ipc_storage -q`:
  **1 passed**. Real source Electron UI → trusted IPC → Python → encrypted
  disposable profile → reload; synthetic credentials only; guard PASS.
- Ruff on bridge/config/API-key tests/Electron E2E; release lint; typecheck;
  security gate; secret scan; web/desktop/Remotion build; build-runtime verifier;
  diff-check: **PASS**. Build retains the existing large-chunk warning.
- Dependency gate: exit 0 at HIGH threshold, **one MODERATE advisory remains**;
  do not interpret this as zero vulnerabilities.
- Normal scenario/core suite: **154 passed, 1 expected stale-Core failure**.
  `pnpm verify:core-runtime` likewise fails honestly on stale `scriptor/bridge.py`.
  Both `scriptor/bridge.py` and `scriptor/config.py` are modified Core-owned sources.
  r33 lock/package/guard have not been altered; no stale Core acceptance claimed.
- CI and independent Windows-native outcomes are recorded in the PR after push;
  local Windows E2E is not a replacement for remote CI.

## Safety incident and recovery — not hidden by green harness results

A separate reviewer reproducer, outside `tests/run_isolated.py`, incorrectly
redirected TEST_ROOT without redirecting LOCALAPPDATA. It changed actual settings:
two first credential rows, four appended synthetic rows and the FastGen selected
labels. This violated the repository's production-write rule despite the correctly
isolated automated suites having PASS guards. No provider/OAuth/YouTube call or
raw real credential disclosure was observed.

The incident was disclosed to the user. Contaminated primary and LKG copies were
preserved privately and excluded from Git/evidence. A one-time narrow recovery,
checked against the discovery hash under the settings lock, restored only the
affected credential arrays and FastGen selection and removed the four identified
synthetic rows. Other profile fields were preserved. Primary and repaired LKG
now match. Recovery did not alter source business logic.

The original OpenAI row was recoverable from the contemporary preserved LKG.
The FastGen first row and selection were restored from two agreeing earlier
copies. There was no exact immediately-before-incident snapshot for those
FastGen fields, so byte-exact restoration of their newest preincident values
cannot be proved. This confidence limitation must remain visible to the owner.
Private recovery files containing protected credentials must never be uploaded.

The new credential test suite now checks that its settings path lies inside the
explicit TEST_ROOT before removing or writing a file. Future manual reproductions
must use the official isolated harness, not TEST_MODE alone. The broader fallback
storage-boundary issue is not silently refactored as part of this feature.

Overall production-safety status for this entire work session is **INCIDENT,
narrow recovery completed**, not an unqualified PASS. Feature source tests are
green; release/merge readiness is not claimed.
