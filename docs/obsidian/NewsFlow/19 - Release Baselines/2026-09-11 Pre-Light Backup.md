# 2026-09-11 pre-Light backup

- Backup: `D:\\NewsFlow Studio\\Backups\\pre-stable-news-light-20260911-161027`.
- Source root: `%LOCALAPPDATA%\\NewsFlow`.
- Backup completed before Light code changes.
- Robocopy verification: 33,223 directories and 71,640 files matched; zero mismatch and zero failures. The only destination extra is the backup’s own `robocopy.log`.
- SHA-256 equality checked for settings, cover library, footage index/status and last-known-good settings.

This baseline is read-only. It must not be used as an input that overwrites production state.

## Phase 1 verification

After the persistence boundary changes, `python -m unittest scriptor.test_config tests.test_channel_research tests.test_montage_queue tests.test_publication_v2 -v` passed **94 tests**. The suite used temporary application roots for the new persistence tests; no production settings, provider, OAuth, render, queue or publication action was executed.

## Final Light source gate — 2026-09-12

- The full `tests/` discovery gate passed under a unique temporary `%LOCALAPPDATA%` root. It cannot create or overwrite `%LOCALAPPDATA%\\NewsFlow`.
- Direct `scriptor` gate passed: **81 tests** (`test_montage_render`, `test_davinci`, `test_cover_library`, `test_config`, `test_command_contract`).
- UI gate passed: **8 files / 17 tests**. TypeScript typecheck passed.
- Source build passed: Vite web bundle, Electron TypeScript and Remotion bundle. This was a source verification only: no portable/EXE packaging, production application launch, provider, OAuth, queue, render or publication action occurred.
- The Vite bundle emitted a non-blocking chunk-size advisory (main JS ≈683 kB; gzip ≈182 kB). It is recorded as a future performance optimization, not a Light runtime blocker.

Before any future user-authorized EXE distribution, repeat the preservation protocol against the live canonical root: fresh backup → source/result migration verification → test-build launch → visible confirmation that existing user data is present. This source gate does not substitute for that release procedure.

## Isolation incident remediation — 2026-09-12

- A pre-isolation test run rewrote the byte order of `covers-library.json`; structural comparison showed the 97 cover records and every value intact. The exact file was restored from this backup and its SHA-256 now matches the backup again.
- The project now requires [[00 - Current State/ADR - TEST AND BUILD ISOLATION POLICY]] for all Python test execution and any future package command.
