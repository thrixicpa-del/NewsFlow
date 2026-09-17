# NewsFlow Production-Grade Engineering Infrastructure Implementation Plan

> **For agentic workers:** Execute on one dedicated branch/worktree. Commit each completed phase only after its stated evidence is collected.

**Goal:** Establish a reproducible, isolated and release-gated engineering workflow without changing NewsFlow business behavior.

**Architecture:** Infrastructure is layered around the current Electron → IPC → bridge → frozen core → storage runtime. Production storage remains external and read-only to automated checks; all tests receive an explicit disposable root. Git baseline/tag and immutable artifact metadata provide rollback and traceability.

**Tech stack:** Git/GitHub, PowerShell, Python 3.12/pytest, pnpm/Vitest, Electron, Playwright, PyInstaller, GitHub Actions.

**Spec:** `C:\Users\borov\.codex\attachments\e1fd57cb-2392-415b-b3d4-9e6662ee2266\pasted-text-1.txt`

## Global constraints

- Do not modify product business logic, production storage schema, providers, bridge/core contracts, or production credentials for infrastructure-only phases.
- Every automated test must set an explicit non-production test root and fail hard if it resolves to the production root.
- Build and provider-real tests are opt-in; ordinary local and CI tests never consume provider credits.
- `main` stays at the baseline until a future reviewed merge; active work stays on `engineering/infrastructure` or a dedicated `infra/*` branch.
- Each phase records evidence, runs targeted checks, performs a secret/path scan, and creates one logical commit.

## Execution sequence

1. Capture current safety baseline and repository evidence.
2. Add repository governance, templates, ownership and documented protection limitation.
3. Add safe linked-worktree commands and move engineering work to one isolated worktree.
4. Lock Node/Python toolchains and verify a clean disposable install.
5. Centralize production/test/disposable storage resolution and protect production hashes.
6. Layer test taxonomy, command/core contract validation, integration fixtures and opt-in provider-real smoke.
7. Add Electron/packaged E2E, component stories, visual comparisons and accessibility/UX guards.
8. Add a small deterministic golden dataset, benchmark/resource/migration/backup/failure suites.
9. Add redacted structured observability, provider-neutral tracing and security gates.
10. Add local gate, GitHub CI, Windows clean-test strategy, manifest/immutable RC/channel/feature-flag/release-gate/reporting workflow.
11. Document, pilot one safe regression flow, run final engineering audit and smoke current NewsFlow.

## Evidence gates

| Gate | Required evidence |
| --- | --- |
| Production safety | Pre/post SHA-256 equality for authoritative production files. |
| Test isolation | Explicit test root rejected when missing, production, or outside permitted test area. |
| Source/core parity | Command registry and frozen `NewsFlowCore.exe` command probe agree. |
| Packaged parity | Packaged artifact contains verified core hash, manifest and required native binaries. |
| Visual | Deterministic local screenshots compare against approved baselines. |
| Release | One orchestrated script emits `RELEASE GATE — PASS` only after all required gates succeed. |

## Phase completion policy

Each phase is independently committed with the commit subject mandated by the goal. Deferred hosted features remain explicitly documented and must retain a local/open-source fallback.
