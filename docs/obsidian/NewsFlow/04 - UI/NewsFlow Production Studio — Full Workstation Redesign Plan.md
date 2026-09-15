# NewsFlow Production Studio — Full Workstation Redesign Plan

**Phase:** 2 — incremental renderer migration.  
**Status:** IMPLEMENTATION COMPLETE — current workstation routes and their acceptance gates were revalidated on 2026-09-15. The intentionally deferred stale-artifact projection remains a separate runtime-review item because the current Montage handoff has no authoritative ProductionItem/revision chain; no heuristic or storage change was introduced. No backend/runtime implementation is part of this phase.  
**Runtime constraint:** Electron, React/TypeScript/Vite, current command names/payloads, IPC, Python bridge/services/workers, provider adapters, FFmpeg path, storage schemas and user-data locations remain unchanged.

## Purpose and acceptance boundary

The Light refresh introduced a shared shell/kit and namespaced styling, but the product still retains large legacy-shaped screen structures and a monolithic route/state owner. This plan makes the next change visibly recognisable as a production workstation without converting NewsFlow into a new backend product or changing a user action's runtime contract.

The redesign will be accepted only when a control can be followed as:

```text
visible UI → existing handler → existing command → current bridge/service/worker → persisted result/status
```

No design work may use the canonical user-data root. Baseline visuals are the 43 original PNGs catalogued in [[NEWSFLOW SCREENSHOT UI ATLAS]]; implementation verification must take new screenshots only on a disposable copy of user data.

## Fixed platform choices

| Area | Decision |
|---|---|
| Renderer | Existing React + TypeScript + Vite inside Electron; no Next.js and no new application state store. |
| Styling | Existing TailwindCSS utilities plus namespaced shadcn-style local primitives. Do not import a second global design framework. |
| Interaction primitives | Radix Dialog, AlertDialog, DropdownMenu, Popover, Tooltip, Select and Tabs where their interaction semantics are needed. |
| Icons | Lucide only. Text labels remain on primary and potentially destructive actions. |
| Tables | TanStack Table for new/migrated dense queues, with existing data/commands kept intact. |
| Forms | Native controlled fields by default; React Hook Form + Zod only for a genuinely complex multi-field form, never as a reason to rewrite persisted DTOs. |
| Optional additions | Resizable panels, drag/drop, subtle Motion animation and charts only after a screen proves the need; they must never create another task/runtime owner. |
| Explicitly excluded | Redux, Next.js, MUI, a second icon set, a parallel command bus, an automatic data migration, and a global CSS replacement. |

## Workstation information architecture

### AppShell

The existing `App.tsx` stays the runtime/state owner during migration. Extract presentation gradually into `AppShell` slots:

```text
App.tsx (snapshot, handlers, command contract, route selection)
  └─ AppShell
      ├─ Sidebar
      ├─ Topbar: breadcrumb, context, global search/action area
      ├─ PageHeader: title, description, primary action, compact stats
      ├─ Workspace: page-specific toolbar + table/card/detail layout
      ├─ Context Inspector: selected item, related artifacts, validation/status
      └─ Task Center: live jobs, retry/cancel links, durable completion receipts
```

The shell must support a narrow window, a collapsed sidebar, and a contextual right panel without moving any command logic from the existing handlers.

### Sidebar and navigation

Group routes by work, not by implementation history:

1. **Control:** Dashboard, Task Center.
2. **Editorial:** Ideas, Scenarios, Finished Scripts, Templates, Agents.
3. **Production:** Covers, Cover Gallery, Voice Queue, Voice Profiles, Ready Audio, Footage, Cutter, Montage, Outputs.
4. **Distribution:** SEO, Tags, Analytics, Publication V2.
5. **System:** API Keys, Sessions, Knowledge, Settings.

Preserve the current page IDs and route destinations. A group item may collapse visually but must not remap an old route to a different feature. Publication, allocation and automation need visibly distinct sub-navigation within `PublicationPage`, even if they retain the current page identifiers.

### Topbar, inspector and task center

* **Topbar:** breadcrumb plus active project/target context; one global primary shortcut only when its target is unambiguous. Do not show a misleading generic “saved” success message.
* **Context inspector:** right-side Sheet/resizable panel for selected topic/script/cover/voice/montage/publication record. It shows source identity, dependencies, last durable artifact, error/retry reason and safe open-location action.
* **Task Center:** one cross-domain status grammar: `Queued`, `Preparing`, `Running`, `Waiting for provider`, `Ready`, `Failed`, `Paused`, `Cancelled`. Progress is paired with terminal artifact/receipt evidence; `100%` alone never means success.

## Design language

### Tokens and layout grammar

* Dark neutral canvas with a small elevation scale: app background, sidebar, panel, raised panel, input and overlay. Preserve existing blue primary and semantic green/amber/red meanings; do not encode status solely in colour.
* Use one spacing rhythm: 4/8/12/16/24/32 px, 8 px field gaps, 16 px standard cards, 24 px page sections. Avoid giant empty cards and unbounded stacked forms.
* Compact desktop type scale: 12 metadata, 13–14 controls/body, 16 section headings, 20–24 page headings. Numerical counters use tabular figures.
* Controls have three deliberate heights: 28 compact/table, 34 normal toolbar, 40 primary/form. Icon-only controls require Tooltip and accessible name.
* A page has exactly one primary action group, secondary actions in toolbar or overflow, and destructive actions behind AlertDialog. Busy actions lock only their own action scope and show a local state.

### Shared UI kit to complete before page migration

| Primitive | Required role |
|---|---|
| Button / IconButton | clear primary, secondary, quiet, danger and loading variants; no custom one-off button colours |
| Input / Textarea / Select / Checkbox / Switch | label, description, validation message and disabled/read-only states |
| Tabs / Badge / StatusBadge | local navigation and a single semantic status vocabulary |
| Progress / TaskProgress | task phase, percent and terminal result/receipt, not percent alone |
| DataTable | compact headers, empty/loading/error rows, sort/filter/pagination affordance and row selection |
| Sheet / Dialog / AlertDialog | details, forms, confirmation; focus return and explicit close behavior |
| DropdownMenu / Tooltip / Popover | secondary/overflow actions and concise help |
| Toast | short notification only; never proof that a queued operation completed |
| EmptyState / ErrorState / LoadingState | consistent explanation and next safe action |
| Toolbar / PageHeader / StatCard | every page shares header/action/metric hierarchy |

## Screen-by-screen migration plan

Every screen below is a visual extraction/migration only. The listed runtime actions are preserved exactly; no new direct bridge call may be introduced.

## Current migration state — 2026-09-15

| Area | Active visual route | Gate | Next state |
|---|---|---|---|
| Foundation / navigation / task center | `AppShell`, `Sidebar`, current task inspector and command palette | UI-only preferences; current snapshot/command owner remains `App.tsx` | COMPLETE for this increment |
| Dashboard | Production Control Room | current navigation and auto-pipeline contract | COMPLETE for this increment |
| Ideas / Topics | Editorial Workspace: compact topic table, plan panel and generation Sheet | existing topic selection, `add-topics-to-plan` and `generate-ideas` payloads; 53 isolated idea/scenario regressions | COMPLETE for this increment |
| Scenarios / Scripts | Scenario queue and ready-script workbench use active `DataTable` routes; the text editor is a Sheet with existing dirty-draft protection | existing generation, transfer and `save-scenario-text` handlers | COMPLETE for this increment |
| Templates / Agents | Template prompt desk and editorial capability routing workspace | existing template/range commands; navigation only for agents | COMPLETE for this increment |
| Covers | Current ProductionItem queue table, Sheet-based item inspector, and separate Studio Configuration Sheet | existing cover settings, Universal V2 prompt/text generation, FastGen generation, rate/retry and queue commands | COMPLETE for this increment |
| Cover Gallery | Result index table and selected-result inspector | existing reference/face, regenerate, remove and export commands | COMPLETE for this increment |
| Voice Queue | Current voice queue table and selection-driven action toolbar | existing generate, pause/resume, import, transfer and delete commands | COMPLETE for this increment |
| Voice Profiles / Ready Audio | Dedicated provider/profile settings and ready-audio artifact review | existing settings, profile, export and delete commands | COMPLETE for this increment |
| Footage / Cutter | Media-ingest and focused cutter workspaces | existing folder, index, web-search/download, cutter and mixer commands | COMPLETE for this increment |
| Montage / Outputs | Fast Editing workspace and durable output index | existing queue, settings, FFmpeg/Remotion and artifact commands | COMPLETE for this increment |
| SEO / Tags | Distribution production desks | existing metadata generation, export and edit commands | COMPLETE for this increment |
| Analytics | Channel portfolio table with expandable metadata/details | existing add, refresh, OAuth, Studio, remove and metadata commands | COMPLETE for this increment |
| Publication V2 | Existing V2 visual reference and active distribution workspace | existing publication, allocation, queue and receipt commands | COMPLETE for this increment |
| API Keys / Sessions / Knowledge / Settings | Structured system configuration | existing secret, session, knowledge and persistence commands | COMPLETE for this increment |

The Ideas screen has no direct bridge import: selection remains renderer-local and every mutation still uses the supplied current `command` callback. Source-renderer visual verification used only the fallback/disposable renderer state; no provider or production data was opened.

| Screen | Current structure / problem | New workstation structure | Shared components | Preserve runtime actions |
|---|---|---|---|---|
| Dashboard | Pipeline toggles, cards and counters compete in an overview shell. | Command-center overview: target context, pipeline readiness, one “start/resume” primary action, active jobs and recent durable outputs. | PageHeader, StatCard, TaskProgress, Toolbar, EmptyState. | save settings; run/resume pipeline; route navigation. |
| Ideas / Topics | Generation configuration, imports and topic rows are a long form. | Split view: compact route/filters toolbar, selectable topic table, right inspector for source/plan/details; generation in Sheet. | DataTable, Sheet, Select, Checkbox, EmptyState, StatusBadge. | idea generate/import/apply/transfer/delete/export. |
| Scenarios / Scripts | Scenario controls and ready scripts are visually separate but operationally connected. | Editorial workbench: topic/script master list, editor/detail center, downstream “send to voice/covers/montage” action strip. | DataTable, Textarea, Tabs, Dialog, TaskProgress. | generate/save/delete/import/export/transfer and current script selection. |
| Templates / Agents | Settings-like forms mixed with navigation cards. | Two stable configuration pages: template library table/editor and agent capability/route cards. | Tabs, DataTable, Textarea, Dialog, EmptyState. | template/range save/delete/preset; existing navigation only for agents. |
| Covers | FastGen settings, queue, counters and execution controls form a dense single surface. | Production queue workbench: top readiness/provider strip, current cover table, inspector with prompt/text/reference evidence, explicit create/resume/pause primary group. Universal V2 debug sources live in inspection, not an always-visible paragraph. | DataTable, TaskProgress, StatusBadge, Sheet, AlertDialog, Tooltip. | all existing cover settings, text/prompt generation, FastGen generation, rate/retry and queue commands. |
| Cover Gallery | Configuration, reference faces and results are intermixed; keep/delete/retry compete. | Gallery as a results table/grid with selection inspector; a separate configuration Sheet; destructive/remove and rerender actions clearly isolated. | DataTable/grid, Sheet, AlertDialog, DropdownMenu, Empty/Error/Loading states. | reference/face selection, regenerate, remove, export/open local result. |
| Voice / Profiles / Ready Audio | Queue, Chrome/provider configuration and output browsing are fragmented. | Voice workspace with queue table, provider/profile readiness drawer, selected/all generation toolbar and artifact inspector/player. Profiles move to a dedicated setting subpage. | DataTable, Toolbar, Sheet, StatusBadge, TaskProgress, Dialog. | generate selected/all, pause/retry/import/range/profile/settings/open output. |
| Footage / Cutter | Folder configuration, indexing and cutting are disjointed long forms. | Media-ingest workbench: source folders and index status above searchable clip table; cutter is a selected-clip tool panel. | DataTable, Progress, Sheet, Empty/Error states, Dialog. | folder/index/inspect/search/download and cutter commands. |
| Montage / Outputs | Queue, diagnostics, settings and render output can show contradictory state. | Montage workbench: selected script/voice/footage readiness ribbon, editable plan/configuration panel, render queue and final artifact panel. Only task terminal receipt marks completion. Outputs is a filter of completed artifacts, not a second workflow. | TaskProgress, StatusBadge, DataTable, Sheet, AlertDialog. | save montage settings; prepare/run/retry/cancel queue; open/export output. Preserve current FFmpeg fast path. |
| SEO / Tags | Similar metadata tools use separate visual patterns. | Shared metadata workbench with topic/script selection, generator toolbar, editable result, table of packages/tags and export action. | Tabs, Textarea, DataTable, Toolbar, EmptyState. | SEO/tag generation, clear, export and settings. |
| Analytics | OAuth/channel cards and refresh/removal controls are dense, with insufficient status meaning. | Channel portfolio table plus channel inspector: connection state, last refresh, safe external links and data tabs. OAuth is a focused Dialog with clear external-state handoff. | DataTable, Badge, Sheet, Dialog, AlertDialog. | add/refresh/OAuth/revenue/Studio/remove/channel metadata. |
| Publication V2 | Strongest current visual reference but allocation, scheduling and queue views need clearer context. | Keep as visual reference: worklist table, allocation rules/presets, schedule, execution queue and receipt inspector as one coherent sub-navigation model. | Existing UiButton/DataTable/Sheet/Tabs plus StatusBadge/TaskProgress alignment. | current V2 allocation/rules/start/pause/retry/cancel/upload/receipt commands. |
| API Keys / Sessions / Knowledge / Settings | Security-sensitive forms vary in density and feedback. | System area with dedicated sub-navigation, provider/key inventory, session/OAuth diagnostics and searchable setting groups. Secrets stay masked; destructive edits always confirm. | DataTable, Dialog, AlertDialog, Input, Switch, Tooltip, ErrorState. | encrypted key/session/knowledge/settings commands and current confirmation semantics. |

## Legacy CSS retirement protocol

No global stylesheet is removed by assumption. For each migrated page:

1. Add one namespaced feature stylesheet and replace the active markup with the shared primitives.
2. Search the old selector throughout the renderer and verify no active component needs it.
3. Run focused visual/component tests, the affected command-contract test and isolated backend regression.
4. Capture default, loading/running, error, empty, selected and destructive-confirmation states from the disposable user-data run.
5. Only then delete that page’s orphaned selectors. Keep a short removal entry in `UI Light.md`.

`App.tsx` is not rewritten wholesale. It gives up page-local visual markup in stages but continues to own the existing snapshot, state and handlers until every target page is migrated and its contracts are verified.

## Implementation sequence and gates

1. **Foundation:** design tokens, full shared kit audit, AppShell/sidebar/topbar/Task Center/inspector slots. Gate: primitives keyboard tests; route/action contract tests; isolated source render.
2. **Editorial:** Dashboard, Ideas, Scenarios/Scripts, Templates/Agents. Gate: component UI actions and topic/script isolated regression.
3. **Production media:** Covers/Gallery, Voice/Profiles/Audio, Footage/Cutter, Montage/Outputs. Gate: current cover/voice/montage commands; isolated provider-safe tests; montage timeline/terminal-trim checks.
4. **Distribution/system:** SEO/Tags, Analytics, Publication V2, API Keys/Sessions/Knowledge/Settings. Gate: current command contracts, persistence isolation, OAuth/UI safe-state checks.
5. **Visual completion:** compare new isolated screenshots against the baseline atlas, perform responsive/keyboard/accessibility sweep, confirm no legacy CSS remains on migrated pages, run full UI suite + relevant isolated Python suite + typecheck + source build/runtime guards.

Each individual screen uses: **small UI change → focused UI test → contract/runtime regression → isolated visual verification → next screen**. A failing runtime test stops that screen and is fixed at root cause before visual polish continues.

## Engineering UX requirements — mandatory before implementation

These are acceptance requirements for the workstation migration, not authorisation to alter the current core or to add every optional dependency immediately.

### 1. Visual regression baselines

Create automated screenshot-baseline coverage on a disposable test state for the primary workstation screens: **Voice, Covers, Montage and Publication**, then extend it to Dashboard, Topics and Scripts as their layouts stabilise. Baselines cover default, selected, empty, loading, running, failed and ready states where those states can be constructed safely from fixtures.

Manual before/after comparison remains useful for visual direction, but it cannot be the only regression evidence. A deliberate visual change updates a reviewed baseline; an accidental shift fails the visual gate. No provider, OAuth or production user-data is used to obtain a baseline.

### 2. Error isolation

Add one app-level Error Boundary and a feature-level boundary around each heavy workspace: Covers, Voice, Montage, Publication and Analytics. A boundary must show an ErrorState with safe retry/reload-context instructions and diagnostic correlation information; it must not submit a command or reset storage on its own.

An exception or render-loop in Covers must not take the rest of the shell to a blank screen. Boundary recovery is limited to renderer-local state and then returns to the current snapshot/handler path.

### 3. Large-list performance and virtualization

TanStack Table provides table state and rendering grammar, not row virtualization. Instrument real representative fixture sizes first. Add `@tanstack/react-virtual` (or an equivalent local implementation) only once Topics, Covers, Voice or Task Center demonstrably reaches a size where normal table rendering breaks the UI performance budget.

Virtualization must preserve keyboard row navigation, selection, screen-reader labels, table actions and the current command/handler contract. It is not a reason to paginate away current queue visibility by default.

### 4. Unsaved-change protection

Scripts, template/prompt text and Settings forms maintain explicit `clean`, `dirty`, `saving` and `save-failed` states. Moving to another item/route or closing a relevant Sheet while dirty opens a focused **Save / Discard / Cancel** confirmation. Browser/window close handling uses the same rule where Electron permits it.

The guard prevents navigation only; saving continues through the existing command and persistence flow. It must never auto-save partial edits or mutate a selected production item merely because Inspector focus changed.

### 5. Keyboard-first workflow and command palette

The desktop product receives a documented keyboard map:

| Shortcut / key | Behaviour |
|---|---|
| `Ctrl+K` | Command/search palette: find Topic, Script, ProductionItem, MP3, Cover, Montage and Publication receipt; execute only safe navigation/open actions directly. Mutating actions still surface their normal confirmation/readiness UI. |
| `Ctrl+S` | Save only the active dirty editor/form through its current save handler. |
| `Escape` | Close the topmost Dialog, Sheet or Inspector and return focus to its invoker. |
| Arrow keys | Move table selection without starting a job. |
| `Enter` | Open the selected row in the Inspector or the screen's existing primary-detail action. |
| `Delete` | Never deletes directly; opens the current destructive confirmation path. |

All shortcuts respect text-input composition and native accessibility behavior. The palette is a route/search layer over the current snapshot; it is not a second data index or command runtime.

### 6. Layout preferences, isolated from business state

Persist sidebar collapse, Inspector width, workspace density, visible table columns and safe local sort/filter preferences under a versioned **UI-preferences** namespace separate from project/production business state. Preferences may be reset independently and must be schema-validated.

They must not enter `ProductionItem`, settings/queue merge logic or migration paths that can influence topics, scripts, covers, jobs or outputs. A corrupted layout preference falls back to defaults without touching canonical production data.

### 7. Idempotent UI actions

Busy buttons disable their local action scope, but button disabling alone is insufficient. The UI must retain the returned/current `actionId` or `jobId` and reconcile it from snapshot after reopen or restart. Repeated click, rerender, reload or reopen must not enqueue duplicate Voice All, Covers Generate, Montage or Publication work.

The redesign reuses the current core idempotency and queue semantics. If an existing command has no stable job identity, the migration records that as a targeted runtime contract blocker rather than inventing a frontend-only duplicate guard.

### 8. Artifact provenance

Every MP3, Cover, MP4 and publication receipt Inspector includes, where the current snapshot already exposes it or a non-breaking projection can expose it:

* source `ProductionItem` / scenario identity;
* provider/runtime and selected profile where appropriate;
* created time, size, duration and physical path/open action;
* current versus obsolete/stale relationship;
* task/job identity and durable result/receipt reference.

The presentation does not fabricate provenance. Missing metadata is explicitly marked rather than inferred from a filename.

### 9. Stale-artifact model

Introduce a renderer-visible derived status distinct from `READY`: **STALE — upstream changed after generation**. Initial required relationships are:

```text
Script changed       → Voice stale
Script or Topic changed → Cover stale
Voice or Timeline changed → Montage stale
Metadata changed / video changed → Publication preparation stale
```

Staleness is an explainable dependency indicator in the Inspector, queue and readiness ribbon; it is not deletion and it does not overwrite a valid historical artifact. The plan first inventories current version/time/identity fields. If a safe current-state projection is insufficient, any persistence/schema work is deferred for explicit runtime review rather than hidden inside UI redesign.

### 10. UI performance gate

For each migrated heavy page, establish and verify a performance budget on disposable representative data:

* route navigation has no noticeable blocking delay;
* large-table scrolling is smooth at the measured production-representative row count;
* selecting a row does not rerender the entire `App.tsx` workspace unnecessarily;
* heavy Inspector panels are lazy-rendered and unloaded when not needed;
* no render loops, duplicate action firing or stale selection survives route changes;
* React Profiler evidence is recorded for Covers, Voice and Montage before their final screen gate.

Performance changes stay presentation-local unless evidence proves an existing current runtime contract is the root cause.

### 11. Migration exclusivity

At the close of each screen gate, record an explicit routing decision:

```text
NEW UI = ACTIVE
OLD UI = INACTIVE
OLD UI cannot be reached by normal navigation or fallback routing
```

Legacy source may remain temporarily for comparison and recovery, but only one active route implementation owns a feature. This is especially strict for Publication, Covers, Voice and Montage. Legacy CSS is retired on the existing selector-evidence protocol; legacy renderer components are not deleted merely because they are inactive.

## Required safe visual capture matrix

For every major screen, capture at least default, empty, loading/running, success/ready, provider/network error, paused/retry and confirmation dialog where applicable. In addition, capture: provider selector open, settings modal, OAuth handoff state, publication receipt/detail, selected row inspector and collapsed sidebar. Record app build marker and disposable test-root identity, never secrets or personal paths.

## Non-regression safeguards

* Existing handler signatures and `NewsFlowCommand` payloads are snapshot-tested before and after each migration.
* The renderer continues through current `window.newsflowDesktop` → Electron → `bridge.py`/current core only; a UI component cannot import legacy services directly.
* Keep `PublicationPage` as the only active publication implementation; legacy publication components are read-only comparison candidates until deliberately retired after full validation.
* Tests use `NEWSFLOW_TEST_MODE=1` plus a disposable root. A production path is fail-safe rejected.
* Do not update Node, Python, Electron, FFmpeg, provider packages or persistence schemas as part of the redesign.
* No EXE is built until a separate post-implementation final regression gate passes.

## Completion definition

The redesign is complete only when all listed screens use the workstation shell and shared grammar, every preserved action is demonstrated through its current handler/command path on isolated data, the task/status model never treats a percentage as proof of success, error isolation and dirty-state guards are covered, all migration routes are exclusive, performance/visual regression gates pass, legacy CSS has been retired only where proved unused, and screenshot comparison covers the required states.

## Completion evidence — 2026-09-15

| Requirement | Current evidence |
|---|---|
| Workstation shell and screen migration | The current route map has `AppShell`/Navigation Rail, Page Header, Task Center and Context Inspector around every named area. The migration-state table above marks all routes complete. Visual captures cover every active navigation destination. |
| Preserved current runtime path | Active `App.tsx` routes render `PublicationPage` and `AnalyticsDashboard`; legacy publication/analytics definitions have no active JSX route. Current command-contract and isolated runtime suites passed. |
| Visual and responsive validation | The disposable Electron matrix (`NEWSFLOW_TEST_MODE=1`, temporary user-data root) covers empty/default, fixture ready/waiting/failed/paused, inspectors, configuration Sheets, OAuth waiting, receipt/detail, discard confirmation, collapsed navigation and narrow Topics. All reviewed captures matched their approved baseline. |
| Error, dirty and keyboard safety | App/heavy-workspace boundaries, dirty-draft guards, window-close protection, Ctrl+S, Ctrl+K, Escape and table keyboard-selection behavior are covered by renderer tests. No guard auto-saves or writes a production item. |
| Heavy-route performance and no render loops | Covers, Voice and Montage 84-item fixture captures stayed below the 3s navigation budget; React Profiler coverage records finite commits. Current Covers render-loop and duplicate-submit regressions are in the renderer suite. |
| Production isolation | Visual captures and runtime tests use only isolated roots. Read-only production SHA-256 values remain the schema-seal baseline: settings `8B65292DA4553BA42F90A7CF34124AD0E0A0E2174D6444576A2AB5EB05E0FB04`; covers `E34FFDBE11EA32D9F035C3690E3EB13C3B67216F2FCC48EB9E62F52889AA126D`; footage state `821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211`. |
| Final checks | `pnpm test:ui -- --run`: 33 files / 130 tests PASS; TypeScript PASS; source build PASS; current build/runtime guard PASS; r4 core guard PASS; Montage UI contract PASS; isolated command/config/Montage runtime suite: 40 PASS. |

The source build still emits Vite’s 726.43kB renderer-chunk advisory. It predates this completion gate and is recorded as a future performance optimisation, not masked by a dependency or runtime change. No EXE was built.

## References

* [[Functional Acceptance — 2026-09-14]]
* [[Light UI Refresh Design]]
* [[Light UI Refresh Migration Plan]]
* [[NEWSFLOW SCREENSHOT UI ATLAS]]
* [[NEWSFLOW UI DESIGN SYSTEM MAP]]
* [[NEWSFLOW DEEP SYSTEM MAP]]
* [[ADR - TEST AND BUILD ISOLATION POLICY]]
