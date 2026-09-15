# Publication V2 Desktop UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current stretched Publication V2 form with a compact, table-first desktop workspace backed by existing V2 snapshot state.

**Architecture:** Keep publication domain, scheduler, OAuth and upload execution unchanged. Move the view from `App.tsx` into a dedicated `src/ui/publication/` feature, derive view rows from `publication.v2`, and use a single parent refresh/command flow. Channel edits remain drafts inside a right-side sheet until the existing `save-publication-v2-rules` command is called.

**Tech Stack:** React, Vite, TypeScript, Electron, TailwindCSS, local shadcn-style components backed by Radix primitives, TanStack Table, Lucide.

**Spec:** `C:\Users\borov\.codex\attachments\0ff2bafb-c736-4b67-9f41-1aa6ac102d65\pasted-text.txt`

## Global Constraints

- Preserve existing PublicationItem, PublicationSnapshot, PublicationExecution, scheduler, allocation, OAuth, YouTube transport and Studio automation.
- Never create an upload from the UI without the existing confirmation/safe-upload commands.
- Never convert a downstream retry into another MP4 upload.
- Use Russian UI copy, compact desktop density, and the existing dark NewsFlow visual identity.
- Keep channel assignment and manually locked schedule values unchanged until the user explicitly saves or confirms them.
- Do not package an EXE until typecheck, web build, backend regressions, UI tests and visual QA are complete.

---

### Task 1: UI foundation and dependency integration

**Files:**
- Modify: `studio-ui-remotion-verify/package.json`, `pnpm-lock.yaml`, `vite.config.ts`, `src/ui/styles.css`
- Create: `studio-ui-remotion-verify/src/ui/components/{button,badge,dialog,sheet,tooltip,tabs,table}.tsx`
- Test: `studio-ui-remotion-verify/src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- Produces `cn(...classes: string[])`, `Button`, `Badge`, `Sheet`, `Tooltip`, `Tabs`, and `DataTable` primitives.
- `DataTable<T>` consumes TanStack `ColumnDef<T>[]` and `data: T[]`.

- [ ] Add Tailwind Vite integration, Radix Dialog/Tooltip, TanStack Table and test dependencies without replacing Electron or Vite.
- [ ] Add CSS tokens for background, surfaces, borders, foreground, muted, primary, success, warning and destructive states.
- [ ] Write a failing render test proving the primitive table renders a header and no overlapping absolute-positioned form labels are used.
- [ ] Implement local shadcn-style primitives built on Radix and Lucide-compatible class tokens.
- [ ] Run the focused UI test, then `pnpm typecheck`.

### Task 2: Publication view-model and compact shell

**Files:**
- Create: `src/ui/publication/{types,view-model,PublicationPage,PublicationHeader,PublicationStats,PublicationTabs}.tsx`
- Modify: `src/desktop.d.ts`, `src/ui/App.tsx`
- Test: `src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- `buildPublicationView(data: NewsFlowSnapshot): PublicationViewModel` maps real V2 items, channel rules, assignments, queue and receipts into stable rows.
- `PublicationPage({ data, command })` is the sole V2 screen mounted by `App.tsx`.

- [ ] Write a failing test with 84 items, long Russian titles, eight channels and all required status families.
- [ ] Implement readiness derivation independently for MP4, cover, SEO, metadata, channel and schedule.
- [ ] Add compact header, action hierarchy, KPI strip and sticky five-tab navigation.
- [ ] Replace the current `PublicationDashboard` mount with `PublicationPage`, keeping legacy components unused rather than executing them.
- [ ] Run focused tests and typecheck.

### Task 3: Videos registry and details

**Files:**
- Create: `src/ui/publication/{VideosTable,VideoDetails}.tsx`
- Modify: `src/ui/publication/PublicationPage.tsx`, `src/ui/publication/publication-ui.css`
- Test: `src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- `VideosTable` consumes `PublicationVideoRow[]`, selection callbacks and filters.
- `VideoDetails` shows artifacts, metadata, assignment and schedule for one row.

- [ ] Write a failing test for search, readiness/status filtering, selected row count and one expanded row.
- [ ] Implement a memoized TanStack registry table with compact status badges and horizontal table scrolling only below available desktop width.
- [ ] Implement artifact and metadata detail expansion without an additional page-level scroll region.
- [ ] Verify 84 rows render with long titles and rows do not claim an absent MP4 is ready.

### Task 4: Channels table and saved rule sheet

**Files:**
- Create: `src/ui/publication/{ChannelsTable,ChannelSettingsSheet}.tsx`
- Modify: `src/ui/publication/PublicationPage.tsx`, `src/ui/publication/types.ts`
- Test: `src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- `ChannelSettingsSheet({ channel, draft, onSave, onClose })` emits the existing V2 rule shape.
- Uses existing `save-publication-v2-rules({ rules })` command only after Save.

- [ ] Write a failing test that clicking a compact channel row opens one sheet and labels remain above their inputs.
- [ ] Implement quota, monetization, enabled, first publication, interval + unit, timezone, weekdays, publication window, daily cap, mode and privacy controls.
- [ ] Implement clear validation and tooltips for quota, daily cap, window, lock and unverified state.
- [ ] Save only the edited rule through the existing command; do not mutate current assignment/schedule automatically.
- [ ] Run focused tests and typecheck.

### Task 5: Distribution preview and manual locks

**Files:**
- Create: `src/ui/publication/DistributionTable.tsx`
- Modify: `src/ui/publication/PublicationPage.tsx`, `src/ui/publication/view-model.ts`
- Test: `src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- `DistributionTable` consumes preview assignments and emits existing `preview-publication-v2-distribution` and `confirm-publication-v2-distribution` payloads.

- [ ] Write a failing test proving preview remains non-uploading and a locked/manual row displays its channel, time and warning.
- [ ] Implement compact distribution counters, conflict badges, TanStack table, inline channel/time edit draft and explicit confirmation action.
- [ ] Visibly explain `Longest → monetized` using the backend reason without changing allocation logic.
- [ ] Ensure confirmation sends only assigned preview rows and existing locked assignments stay locked.
- [ ] Run focused tests and typecheck.

### Task 6: Live queue, granular retry and history

**Files:**
- Create: `src/ui/publication/{PublicationQueue,PublicationQueueRow,PublicationExecutionDetails,PublicationTimeline,PublicationHistory,PublicationReceiptSheet}.tsx`
- Modify: `src/ui/publication/PublicationPage.tsx`, `src/desktop.d.ts`
- Test: `src/ui/publication/publication-ui.test.tsx`

**Interfaces:**
- Queue uses existing `upload-publication-v2-snapshots`, `set-publication-v2-paused`, `reconcile-publication-v2-youtube`, `retry-publication-v2-stage`, `cancel-publication-v2-execution`, `run-publication-v2-thumbnails`, and `publication-v2-receipt` commands.

- [ ] Write failing tests for partial success, failed Cards retry, known YouTube ID visibility and absence of a re-upload action once `youtubeVideoId` exists.
- [ ] Implement concurrency toolbar, active/queued/processing/error counters, queue status/filtering, safe start and pause/resume controls.
- [ ] Implement expanded execution checklist, compact real timeline, stage durations when provided, explicit `UNVERIFIED`, and real-only upload progress fields.
- [ ] Implement receipt history table and right-side detail sheet with confirmed/requested schedule, stage result and YouTube identity.
- [ ] Run focused tests and typecheck.

### Task 7: Density, responsive desktop QA and integration verification

**Files:**
- Modify: `src/ui/publication/publication-ui.css`, `src/ui/styles.css`, `src/ui/App.tsx`
- Test: `src/ui/publication/publication-ui.test.tsx`, backend publication tests

- [ ] Add compact desktop grid constraints for 1280×720, 1366×768, 1440×900 and 1920×1080, with sticky header/tabs and safe table overflow.
- [ ] Verify no nested vertical scroll bodies and no label/control overlap in channel sheet and toolbars.
- [ ] Run `pnpm typecheck`, `pnpm build:web`, frontend tests and existing Publication V2 backend regressions.
- [ ] Open the Electron app at 1366×768 and 1920×1080, inspect all five tabs, 84-row fixture, long titles, sheet, expanded queue row and receipt sheet; fix visual defects.
- [ ] Only after all checks pass, resume the portable packaging task and verify the packaged executable separately.
