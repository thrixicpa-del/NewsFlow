# Electron E2E Strategy

`tests/test_electron_e2e.py` drives a real Electron process through Playwright CDP, not a JSDOM mock. It always inherits the isolated root from `tests/run_isolated.py`, opens no provider workflow, navigates to Ideas, and saves an E2E screenshot only below that test root.

## Source lane

Build source Electron first, then opt in:

```powershell
pnpm --dir studio-ui-remotion-verify build:web
pnpm --dir studio-ui-remotion-verify build:desktop
$env:NEWSFLOW_RUN_ELECTRON_E2E = '1'
$env:NEWSFLOW_E2E_TARGET = 'source'
python tests/run_isolated.py tests.test_electron_e2e
```

This lane was validated on 2026-09-15 with Electron `43.4.1` and isolated storage.

## Packaged lane

Packaged testing is deliberately separate. It is opt-in and receives the exact immutable RC EXE:

```powershell
$env:NEWSFLOW_RUN_ELECTRON_E2E = '1'
$env:NEWSFLOW_E2E_TARGET = 'packaged'
$env:NEWSFLOW_PACKAGED_EXE = 'D:\path\to\immutable-rc\NewsFlow Studio.exe'
python tests/run_isolated.py tests.test_electron_e2e
```

The test connects only through Electron's explicitly supplied `--remote-debugging-port`; it never falls back to source Electron. A packaged launch that does not expose CDP is a packaged-E2E failure, not a source-test pass. The current pre-infrastructure r10 portable artifact did not expose CDP within the test deadline, so it is not accepted as packaged-E2E evidence. The next immutable RC must pass this lane or provide an equally real, auditable packaged automation adapter.

Failure artifacts live solely under `<NEWSFLOW_TEST_ROOT>/artifacts`; production user-data remains outside the test process.

## Accessibility and UX lane

The source-Electron accessibility test is also opt-in and uses the pinned local
`axe-core` asset; it does not call a hosted service or any provider. In addition
to WCAG 2 A/AA violations, it verifies modal keyboard focus, a readable input
name, and that the opened Sheet and document have no meaningful horizontal or
off-screen overflow.

```powershell
pnpm --dir studio-ui-remotion-verify build:web
pnpm --dir studio-ui-remotion-verify build:desktop
$env:NEWSFLOW_RUN_ELECTRON_E2E = '1'
$env:NEWSFLOW_E2E_TARGET = 'source'
python tests/run_isolated.py tests.test_electron_e2e.ElectronE2ESmokeTests.test_accessibility_and_ux_guards
```

The 20px Sheet edge allowance is only the native Windows scrollbar gutter,
which Electron excludes from `window.innerWidth`; any document-level horizontal
overflow remains a failure.
