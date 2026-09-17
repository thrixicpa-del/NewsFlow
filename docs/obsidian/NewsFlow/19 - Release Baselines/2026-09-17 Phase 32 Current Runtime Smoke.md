# 2026-09-17 Phase 32 Current Runtime Smoke

## Scope

This is a post-infrastructure smoke of the current NewsFlow runtime. It is not
a provider acceptance test and does not use production content, credentials,
or external provider calls.

## Fresh evidence

| Check | Result |
| --- | --- |
| Source desktop build | `pnpm build` passed: web, Electron and Remotion bundles built |
| Build/runtime guard | Passed current version, lock resolution, schema markers and current paths |
| Core-bin guard | Passed against `core-bin-2.1.152-observability-r11` |
| Frozen core contract | 3/3 passed, including correlation-id and secret-redaction contracts |
| Current UI → IPC → core runtime map | 3/3 passed; no legacy app/prompt fallback detected |
| Storage / backup lifecycle | 2/2 passed on isolated roots only |
| Source Electron launch, navigation and accessibility | 2/2 passed on an isolated profile |
| Latest portable packaged runtime | Passed in the Phase 31 release gate as `TEST RC04` |
| Production write guard | Passed after all checks |

## Candidate reference

The latest verified portable TEST candidate remains
`D:\NewsFlow Studio\Candidates\NewsFlow-2.1.152-test-rc04-6476f391`.
It was built before this documentation-only record; no runtime source, lock,
core-bin, build configuration, or package input changed afterwards.

## Result

Current source launch, navigation, isolated storage, frozen core response,
build, and packaged runtime evidence remain healthy. Production data was not
changed.
