# Clean Windows Smoke

## Purpose

Validate an immutable TEST/RC package on fresh Windows without production state, credentials, OAuth, footage, face PNGs or any developer checkout dependency.

## Disposable environment

Use Windows Sandbox, a Hyper-V VM snapshot, or a dedicated runner VM. Copy only the approved package, its build manifest and non-sensitive golden fixtures. Before launch set `NEWSFLOW_TEST_ROOT` to a new writable directory inside the disposable VM. Never map host production `%LOCALAPPDATA%\\NewsFlow` into the guest.

## Procedure

1. Start fresh Windows and record OS, architecture and locale.
2. Copy the immutable TEST/RC package; verify its SHA-256 and manifest Git SHA before execution.
3. Launch the package with `NEWSFLOW_TEST_ROOT`; confirm first-run app-data is created there.
4. Verify the app launches, `NewsFlowCore.exe` is bundled, FFmpeg is available, and no source checkout path is required.
5. Navigate basic UI, restart once, and confirm settings persist only under the disposable root.
6. Exercise synthetic fixture paths only: no credentials, external providers or production output folders.
7. Confirm Cyrillic labels/fonts render, native dialogs open, and an output directory can be created under the test root.
8. Preserve redacted logs/screenshots and hashes on failure; do not copy user data out of the guest.
9. uninstall the package or discard the entire Sandbox/VM snapshot after the run.

## Pass criteria

- app starts without missing DLL/runtime errors;
- core-bin and FFmpeg are usable;
- first-run storage is writable and isolated;
- restart preserves only test state;
- no production paths, credentials or host libraries are referenced.

## Boundaries

This is a packaged smoke strategy, not a real-provider acceptance test. Real provider, OAuth and user-media validation belongs to a separately authorised TEST/RC acceptance environment.
