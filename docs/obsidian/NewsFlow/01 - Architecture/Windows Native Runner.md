# Windows Native Runner

## Status

Prepared, not registered. The current user workstation must never be made a public or self-hosted GitHub Actions runner automatically.

## Intended topology

Use a dedicated disposable Windows VM, a separate non-production PC, or a future self-hosted runner with a dedicated local account. The runner has no production NewsFlow user-data, provider credentials, OAuth sessions, footage library, face library, or user media.

GitHub-hosted `windows-latest` executes the source Electron build lane in `.github/workflows/windows-native.yml`. It deliberately does not package a release or run a production credential path.

## Native lane contract

1. Checkout one immutable commit.
2. Create an isolated `NEWSFLOW_TEST_ROOT`; never use `%LOCALAPPDATA%\\NewsFlow`.
3. Install locked Node/Python tooling and build the source desktop app.
4. For a dedicated runner only, execute packaged smoke with a disposable TEST/RC profile.
5. Verify `NewsFlowCore.exe`, FFmpeg, native dialogs, restart, writable test app-data, Cyrillic fonts, output files and process cleanup.
6. Publish screenshots, traces and non-sensitive diagnostics as CI artifacts.

## Runner provisioning plan

- Create a Windows VM or separate device dedicated to CI.
- Create a non-administrator service account with no access to user Documents, AppData production state or removable media.
- Install Git, Node 24.19.x, Python 3.12, pnpm 11.19.x and GitHub Actions runner binaries.
- Configure only a repository-scoped runner label such as `newsflow-native-windows`; do not expose it to unrelated repositories.
- Store runner work directory and temp data on a dedicated disposable volume; revoke credentials when the runner is retired.
- Register the runner only through the GitHub UI/token flow after explicit user approval.

## Required user action before registration

Registration needs a GitHub-generated runner token and authorisation in the repository or organisation. Until that action is supplied, CI uses the hosted Windows source-build lane and packaged-native testing remains explicitly deferred.

## Failure handling

A native lane failure preserves its isolated root and uploads only redacted logs, test screenshots and hashes. It never retries providers with real credentials and never falls back to production storage.
