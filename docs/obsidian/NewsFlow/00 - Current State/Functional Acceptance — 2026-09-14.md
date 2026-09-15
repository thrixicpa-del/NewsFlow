# Functional Acceptance — 2026-09-14

## Decision

**Functional runtime acceptance: PASS on isolated data.** This is acceptance of the current, verified implementation and its physical artifacts; it is not a claim that every production queue item has already been sent to a paid external provider.

No desktop EXE was built or launched in this acceptance phase. No automatic action used the canonical production user-data root.

## Evidence hierarchy

| Claim | Evidence | Result |
|---|---|---|
| Current source tests do not write to production state | `python tests/run_isolated.py discover -s tests -q` with fail-safe test-root guard | 490 tests PASS |
| Renderer contracts remain current | `pnpm test:ui`, `pnpm typecheck`, runtime/build and montage guards | PASS; 37 UI tests across 18 files |
| WProject voice is a real artifact, not a mocked READY state | Controlled WProject request on isolated root | `001 — Проверка WProject.mp3`, 116,289 bytes, 7.58 s, durable `Готово` |
| Fast News montage is a real artifact | Isolated current FFmpeg pipeline following the real MP3 | `Проверка WProject.mp4`, 186,189 bytes, 7.55 s video / 7.58 s voice, 9.09 s elapsed |
| Cover text path reaches the configured provider and persists returned text | Current staged `NewsFlowCore.exe` on a disposable data root | `generate-cover-headlines` and `generate-cover-subheadlines` returned READY with actual persisted text |
| Empty indexes do not block montage | Isolated montage fallback and queue/render suite | 74 relevant montage tests PASS |
| CRUD/reset does not resurrect deleted work | Current staged core on isolated root, restart included | add topic, delete topic, delete-all/restart and durable direction preservation PASS |
| Manual cover visual references survive runtime reconciliation | Current staged core on isolated root | manual reference action, prepared reference and `Референс загружен` state PASS |
| Existing state remains protected | SHA-256 before/after each isolated run | production settings, cover library, session and footage-index state unchanged |

## Current staged core

* **Core:** `.core-bin-2.1.152-real-acceptance-r3/NewsFlowCore/NewsFlowCore.exe`
* **Packaging selection:** `studio-ui-remotion-verify/package.json` selects that core as Electron `extraResources`.
* **Boundary:** this is a staged internal core, not a desktop/portable release. It uses the current `bridge.py` path and does not reintroduce a nested or legacy core.

## Production data integrity baseline

The following canonical files remained byte-identical while all validation ran below disposable test roots:

| File | SHA-256 |
|---|---|
| `%LOCALAPPDATA%/NewsFlow/settings.json` | `1D1AC559888215D4DAF9B40650FCADF7E0D439381D19D77847998FA8C0EB84CB` |
| `%LOCALAPPDATA%/NewsFlow/covers-library.json` | `DE0D86AFB1FB37F9D84D0AF04F537C8D438AF234AFE848514E8DC4D9D5CA414F` |
| `%LOCALAPPDATA%/NewsFlow/session.json` | `B3EF62C0CB7A2F798B330D893EB387DCC224D0D812E755DF04B8178DE760F570` |
| `%LOCALAPPDATA%/NewsFlow/session.backup.json` | `B3EF62C0CB7A2F798B330D893EB387DCC224D0D812E755DF04B8178DE760F570` |
| `%LOCALAPPDATA%/NewsFlow/footage-index-status.json` | `821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211` |

## Recovery retrospective

| Incident | Why prior checks did not expose it | Current prevention |
|---|---|---|
| 84 active scenarios appeared as 97 unrelated covers | Earlier tests used coherent in-memory queues and did not reproduce a persisted legacy gallery whose IDs did not match the active session context. | Runtime projects current `ProductionItem` IDs first, filters durable gallery rows to those IDs, and migrates exact-title legacy identity before filtering. |
| Deleted scenarios/covers could return after restart | A normal save intentionally protects a non-empty queue from a stale empty save; the explicit release reset had not been distinguished from that safeguard. | Typed explicit clear is allowed only for the confirmed reset action; tombstones block backup recovery. |
| WProject produced no usable voice despite a valid task request | Adapter tests mocked the transport and did not verify the live contract requirement for `Idempotency-Key`. | Persistent retry key is forwarded through both request layers; adapter test checks the actual header path and a controlled MP3 artifact verifies the provider flow. |
| The UI lacked a usable “voice all queued” action | Existing coverage focused on per-item actions and did not assert a visible bulk action through the typed command registry. | Current UI handler, typed command and `generate-voice-queue` dispatcher are covered together. |
| Montage stalled with a fresh footage folder | Tests exercised an already-indexed lookup and did not model an empty optional AI index. | Bounded local filename/tag `SearchHit` fallback feeds candidate selection only when the index is empty; indexed path remains unchanged. |
| New topic prompts contained generic planner wording | Prompt tests proved Universal V2 block uniqueness but did not require semantic values for under-enriched topic families. | Deterministic planner fallback fills subject/action/evidence/environment/emotion before the single Prompt Builder; V2 style/negative rules are still emitted once. |
| A cover-reference action regressed during recovery work | First targeted coverage focused on hydration from persistent state; it did not model an intentional in-memory manual row with no active session IDs. | Full isolated discovery caught the regression. Reconciliation now leaves manual transient rows alone if no active IDs exist, while persisted stale rows remain blocked. |

## Residual operational state — not a code regression

The current production session contains **84 active scenarios**. Its durable cover gallery/queue still contains **97 older, unrelated rows**; current projection correctly shows exactly the 84 active identities rather than reviving stale work. On a disposable copy, all 84 current rows surface explicit `Ожидает генерации` statuses for headline and subheadline.

Those 84 text jobs have not been bulk-submitted automatically because doing so would incur external provider calls and should be an operator-controlled production action. A single controlled current-provider text run proves the path. This is an intentional content backlog, not a hidden failure or a permission to write production state.

## Fixed runtime invariants

1. Current source/runtime wins over legacy modules and state. Legacy is migration-only and cannot silently overwrite current state.
2. Tests reject production storage paths and use isolated roots.
3. Final FastGen provider payload is exactly Prompt Builder output; Universal V2 owns style and negatives once.
4. Current Fast News montage selects the FFmpeg fast path; only terminal footage is trimmed to match voice duration.
5. A durable result requires a real validated artifact, not merely a status label.

See also: [[Open Root Causes]], [[Cover Pipeline]], [[Voice Engine]], [[FAST NEWS MONTAGE]], and [[ADR - TEST AND BUILD ISOLATION POLICY]].
