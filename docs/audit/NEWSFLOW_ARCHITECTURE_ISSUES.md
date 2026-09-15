# NEWSFLOW ARCHITECTURE ISSUES

## Severity scale

`Critical` = likely data loss/security or irreversible external effect; `High` = system correctness/operability; `Medium` = meaningful reliability/maintainability risk; `Low` = cleanup/clarity. Findings are static unless noted.

| ID | Severity | Finding | Evidence / consequence | Recommended next action |
|---|---|---|---|---|
| ISS-01 | High | Corrupt/unreadable `settings.json` loads as `{}` | `load_settings()` catches broad errors then constructs defaults. A subsequent save can replace state; backup only protects readable prior JSON. | Quarantine invalid file, load last-known-good, show blocking recovery UI; test corrupt JSON → no overwrite. |
| ISS-02 | High | Snapshot has mutation side effects | `snapshot()` hydrates and may save recovery/migration/normalization results. Simple UI refresh is not safely read-only. | Split `read_snapshot` from explicit recovery/migrate command; add invariant test that read endpoint writes no file. |
| ISS-03 | High | `App.tsx` is a giant cross-domain orchestrator | 13k+ lines, 646 interactive occurrences, route/state/commands mixed. | Extract screens and typed feature controllers incrementally; retain behavior tests per extracted screen. |
| ISS-04 | High | Command contract is stringly typed and duplicated | 175 UI literals vs 194 Python branches; generic IPC accepts any name. | Generate a shared manifest/schema, validate payloads at boundary, contract-test every exposed action. |
| ISS-05 | Medium | Development runtime uses user-specific cached Python absolute path | `electron/main.ts` contains a `C:\\Users\\…\\.cache\\…python.exe` fallback. | Use explicit development setup/env configuration; remove personal absolute fallback. |
| ISS-06 | Medium | Build/package configuration contains machine-specific output and staging references | `package.json` has a D-drive build output and core staging resource path. | Parameterize release artifact root and verify package manifest on clean machine. |
| ISS-07 | Medium | Publication legacy and V2 paths coexist | Legacy components/commands plus V2 migration/projection are both live. | Define one authoritative UI and deprecation plan; migration status must be visible and reversible. |
| ISS-08 | Medium | Generic success feedback can mask partial/background failure | `App.command()` treats any state payload as “Сохранено…”, while many actions are asynchronous or return partial data. | Standardize operation result schema: accepted/running/succeeded/partial/failed with task ID/progress. |
| ISS-09 | Medium | Channel research is only partially wired | Model/import/tests exist, but no evidenced executor/page/run-pause-stop/export commands in dispatcher/UI. | Mark feature unavailable in UI or finish bounded executor, status, UI and tests before claiming it. |
| ISS-10 | Medium | Hourly FastGen resume swallows errors | Electron catch block intentionally silent and retries at minute 01. | Keep retry but persist/redact diagnostic state visible in Covers. |
| ISS-11 | Medium | Cover state has two durable stores | Settings queue and `covers-library.json` require hydration, merges and tombstones. | Document ownership rules, version schemas and crash-recovery tests; consider one canonical store. |
| ISS-12 | Medium | Detached montage worker receives only a delayed snapshot refresh | `run-montage-queue` starts `stdio: ignore`, returns snapshot after 180 ms. | Use worker identity/status channel and liveness heartbeat instead of fixed delay. |
| ISS-13 | Medium | Tests were not run in the audit | Test files are present but active state safety was prioritized. | Run isolated test environment with a temporary `LOCALAPPDATA`, capture full output. |
| ISS-14 | Low | UI has parallel legacy / modern analytics/publication components | Names `Legacy…` remain in source beside modern components. | Remove dead surfaces after route/feature-flag verification. |
| ISS-15 | Low | Screenshot/UI proof absent | No running native app was safely available. | Perform controlled test-root launch and screenshot atlas; do not use production data. |

## Positive safeguards observed

* Settings writes use interprocess lock, unique temporary file, atomic replace and pre-write backup.
* Release-state and cover-queue merge logic attempts to prevent stale workers emptying user state.
* Cover generation uses an interprocess lock plus bounded ten-topic concurrency.
* Channel research export excludes profile identity and secret/cookie fields by design and test.
* Publication V2 migration is explicitly documented as non-destructive.
* Preload isolates renderer from Node; core response is JSON parsed.

## Priority remediation sequence

1. Separate snapshot read from recovery writes and implement corrupt-settings recovery (ISS-01/02).
2. Add a shared typed command/payload contract and status protocol (ISS-04/08).
3. Stabilize one publication UI/data authority and make channel research status honest (ISS-07/09).
4. Break `App.tsx` into tested screen modules and eliminate environment-specific build/runtime paths (ISS-03/05/06).
5. Run a controlled non-production UI and provider-mocked integration suite, then close screenshot and runtime-trace gaps (ISS-13/15).

No remediation was made in this audit.
