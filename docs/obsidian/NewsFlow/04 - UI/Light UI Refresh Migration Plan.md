# Light UI Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a visibly refreshed, compact desktop Light UI while preserving the verified NewsFlow runtime unchanged.

**Architecture:** `App.tsx` retains the current snapshot, command wrapper and route selection. New layout and feature view components receive existing state/callback props and render a shared local UI kit. No component calls the Electron bridge directly unless the legacy component already did so through the unchanged `command` or `refresh` callback.

**Tech Stack:** React, TypeScript, Vite, Electron, TailwindCSS utilities, local shadcn-style primitives, Radix Dialog/Tooltip, Lucide, TanStack Table, Vitest, isolated Python regressions.

**Spec:** [[Light UI Refresh Design]]

## Global Constraints

- Do not modify `scriptor/`, Electron IPC, `src/contracts/newsflowCommands.ts`, command names/payloads, services/workers, persistence or runtime/build guards.
- Do not launch or mutate production user-data; UI tests use jsdom and Python tests use `tests/run_isolated.py`.
- Do not build an EXE in this phase.
- Preserve the current page IDs and sidebar order.
- Keep `PublicationPage` as the active Publication V2 implementation.

---

### Task 1: Establish the shared UI kit and visual tokens

**Files:**
- Modify: `src/ui/components/button.tsx`, `badge.tsx`, `progress.tsx`, `sheet.tsx`, `tabs.tsx`, `tooltip.tsx`, `src/ui/styles.css`.
- Create: `icon-button.tsx`, `input.tsx`, `textarea.tsx`, `select.tsx`, `checkbox.tsx`, `switch.tsx`, `dialog.tsx`, `alert-dialog.tsx`, `dropdown-menu.tsx`, `popover.tsx`, `toast.tsx`, `states.tsx`, `toolbar.tsx`, `page-header.tsx`, `stat-card.tsx`, `components/ui-kit.test.tsx`.

**Interfaces:** Each control remains a controlled React component; visual primitives expose native `onClick`, `onChange`, `disabled`, `aria-*` props and do not import `window.newsflowDesktop`.

- [x] Write tests for focusable Button/IconButton, labelled Input/Select/Textarea, semantic state components, and Dialog/AlertDialog close behavior.
- [x] Run `pnpm vitest run src/ui/components/ui-kit.test.tsx`; verified RED before components existed.
- [x] Implement the smallest namespaced `nf-*` primitive surface, using Radix only for modal/menu/popover behavior and native controls for fields.
- [x] Re-run the focused kit test and `pnpm typecheck`.

### Task 2: Migrate the common application shell

**Files:**
- Create: `src/ui/layout/AppShell.tsx`, `Sidebar.tsx`, `ShellNotice.tsx`, `layout/app-shell.test.tsx`, `layout/app-shell.css`.
- Modify: `src/ui/App.tsx`, `src/ui/styles.css`.

**Interfaces:** `AppShell` consumes `page`, navigation groups, `onNavigate`, page metadata, stat values, notice and existing `TaskCenter`/children slots. It never creates command payloads.

- [x] Write a failing test proving navigation invokes the supplied `onNavigate` with the existing page ID and the active content slot remains visible.
- [x] Run `pnpm vitest run src/ui/layout/app-shell.test.tsx`; verified RED before the shell existed.
- [x] Extract only shell markup from `App.tsx`, using `PageHeader`, `StatCard`, `Toolbar` and `Toast` without changing the `page`, `command`, `refresh` or `data` ownership.
- [x] Verify focused UI test, `src/contracts/newsflowCommands.test.ts`, `pnpm typecheck`, build/runtime guards, isolated topics/scripts tests, and an isolated source renderer launch.

### Task 3: Dashboard and Ideas/Topics

**Files:**
- Create: `src/ui/features/dashboard/DashboardView.tsx`, `dashboard-view.test.tsx`, `dashboard.css`; `src/ui/features/ideas/IdeasView.tsx`, `ideas-view.test.tsx`, `ideas.css`.
- Modify: `src/ui/App.tsx`; retire only selectors no longer used from `dashboard.css` and `ideas.css`.

**Interfaces:** Views consume the existing Dashboard/Ideas props and forward current `command`, `go`, target and state setters unchanged.

- [x] Add RED tests that click dashboard pipeline/route actions and Ideas generation/selection actions and assert the original callback receives the same arguments.
- [x] Keep the controlled screen JSX in `App.tsx` for this small step, but put the Dashboard stats/toggle and the Ideas action toolbar, labelled fields, route fields, checkboxes and empty state on the shared primitives. This avoids a behavior-only extraction while `App.tsx` still owns state and commands.
- [x] Run focused view tests, command-contract test and a production renderer build. Legacy selectors remain deliberately: no selector has been removed before a complete screen replacement and browser-level visual evidence.

**Evidence (2026-09-12):** `dashboard-view.test.tsx`, `ideas-view.test.tsx`, shell and kit tests: 6/6 PASS; command-contract tests: 9/9 PASS; `pnpm typecheck`, `pnpm build:web` and `pnpm verify:build-runtime` PASS. The browser automation surface did not expose the isolated Electron window, so the visual gate is deferred to the local-browser evidence run in Task 10; this does not affect the source/runtime contract gate.

### Task 4: Scenarios and Finished Scripts

**Files:**
- Create: `src/ui/features/scenarios/ScenariosView.tsx`, `ScriptsView.tsx`, focused tests and namespaced CSS.
- Modify: `src/ui/App.tsx`, `src/ui/scenarios.css`.

- [x] RED-test scenario selection, generation and script navigation, plus ready-script transfer, against the existing callbacks.
- [x] Apply the shared Toolbar, Select, Input, Textarea and EmptyState to the active in-place Scenario/Finished Scripts JSX without moving scenario data transforms or command names.
- [x] Run focused UI tests, `src/contracts/newsflowCommands.test.ts`, isolated ideas/scenarios regression and a production renderer build. Legacy selectors remain until a later complete visual replacement and browser visual gate.

**Evidence (2026-09-12):** scenario view tests: 2/2 PASS; combined shell/kit/dashboard/ideas/scenario/contract set: 12/12 PASS; isolated ideas/scenarios: 52/52 PASS; `pnpm typecheck` and `pnpm build:web` PASS.

### Task 5: Covers and gallery

**Files:**
- Create: `src/ui/features/covers/CoversView.tsx`, `CoverGalleryView.tsx`, tests and namespaced CSS.
- Modify: `src/ui/App.tsx`, `src/ui/covers.css`.

- [x] RED-test that the primary `Создать обложки` action and the current Universal V2 prompt action preserve the existing FastGen command contracts.
- [x] Move the active Covers surface into a namespaced Light wrapper, use shared Checkbox controls for FastGen keys, retain existing `thumbnail-word-actions.ts` and all FastGen payload builders.
- [x] Correct an active UI stability defect discovered by the new render test: a normalised `coverSettings` object was used as an effect dependency and could loop forever when optional `selectedKeyLabels` was absent. Synchronisation now keys off the incoming snapshot, so it cannot overwrite a local draft on a local rerender. No command payload, provider, queue or core logic changed.
- [x] Run focused covers UI tests, `thumbnail-word-actions.test.ts`, type check and current build/core runtime guards. Legacy selectors remain until the entire gallery/settings surface has browser-level evidence.

**Evidence (2026-09-12):** covers/thumbnail action tests: 7/7 PASS; `pnpm typecheck`, `pnpm verify:build-runtime` and `pnpm verify:core-runtime` PASS.

### Task 6: Voice, profiles and ready audio

**Files:**
- Create: `src/ui/features/voice/VoiceQueueView.tsx`, `VoiceProfilesView.tsx`, `AudioView.tsx`, tests and namespaced CSS.
- Modify: `src/ui/App.tsx`, `src/ui/voice.css`.

- [x] RED-test the current voice queue generation callback and ready-MP3 display path against the existing props.
- [x] Move the active Voice Queue and Ready Audio action areas to shared Toolbars and namespaced Light styling, retaining all WProject/voice commands and profile data paths.
- [x] Run focused UI tests and type check. Profile editor selectors and legacy voice CSS remain while profile/detail visual migration is still deliberately incremental.

**Evidence (2026-09-12):** voice UI tests: 2/2 PASS; `pnpm typecheck` PASS.

### Task 7: Montage

**Files:**
- Create: `src/ui/features/montage/MontageView.tsx`, focused tests and namespaced CSS.
- Modify: `src/ui/App.tsx`, `src/ui/editor.css`, `src/ui/montage-recommendations.css`.

- [x] RED-test that the selected MP3 launches the current `run-montage-queue` contract only after the existing settings-save acknowledgement.
- [x] Namespace the active Montage shell, status/configuration cards, queue and task surfaces without touching FFmpeg selection, timing, cache or queue logic.
- [x] Run focused UI test plus isolated benchmark/queue/render regressions. `pnpm verify:montage-ui` remains in the end-to-end consolidation gate.

**Evidence (2026-09-12):** montage UI test: 1/1 PASS; isolated montage benchmark/queue/render: 74/74 PASS; `pnpm typecheck` PASS.

### Task 8: SEO and Tags

**Files:**
- Create: `src/ui/features/seo/SeoView.tsx`, `TagsView.tsx`, tests and namespaced CSS.
- Modify: `src/ui/App.tsx` and only relevant old selectors.

- [x] RED-test SEO and tags generation actions against the original `command` callback.
- [x] Namespace the active SEO/Tags panels for the Light visual system while retaining current tables, editor state and command payloads.
- [x] Run focused UI tests, type check and renderer build. Full browser visual evidence remains an end-of-refresh gate.

**Evidence (2026-09-12):** SEO/Tags UI tests: 2/2 PASS; `pnpm typecheck` and `pnpm build:web` PASS.

### Task 9: Settings surfaces

**Files:**
- Create: `src/ui/features/settings/SettingsViews.tsx`, focused tests and namespaced CSS.
- Modify: `src/ui/App.tsx`, `sessions.css`, `agents.css`, `templates.css` only when their active settings markup moves.

- [x] RED-test secure API-key creation and Chrome-session creation against their existing command names and payloads.
- [x] Namespace active API keys, sessions and Obsidian/knowledge settings surfaces for the Light visual system. Existing confirmation semantics and encrypted-storage runtime are unchanged.
- [x] Run focused UI tests and type check. Existing isolated persistence/production-path protection suite remains the final cross-screen gate; no production storage was opened.

**Evidence (2026-09-12):** settings UI tests: 2/2 PASS; `pnpm typecheck` PASS.

### Task 10: Consolidation and release-ready source gate

**Files:**
- Modify: `src/ui/App.tsx`, migrated legacy CSS, `docs/obsidian/NewsFlow/04 - UI/UI Light.md`.
- Test: all UI tests and existing runtime guards.

- [x] Search active shell/compatibility paths. `AppShell`/`Sidebar` are active; `Button` and `Empty` are intentional compatibility adapters over shared primitives. No CSS selector was proven unused, so no legacy CSS was deleted.
- [x] Verify Publication V2 remains mounted for publication/allocation/automation through the unchanged `PublicationPage` route condition; no parallel publication UI was introduced.
- [x] Run `pnpm typecheck`, `pnpm test:ui`, `pnpm verify:build-runtime`, `pnpm verify:core-runtime`, `pnpm verify:montage-ui`, relevant isolated Python regressions and `pnpm build:web`.
- [x] Update UI Light documentation with active screens, retained CSS rationale and test evidence. No EXE was created.

**Final source-gate evidence (2026-09-12):** 18 UI files / 35 tests PASS; build/core/montage UI guards PASS; isolated runtime/migration/session/cover/publication: 46 PASS; isolated montage: 74 PASS; Vite renderer build PASS. Computer-use inventory exposed no native NewsFlow window, so browser-level screenshots were not fabricated; code, UI tests and isolated renderer build are the verified evidence for this source-only phase.
