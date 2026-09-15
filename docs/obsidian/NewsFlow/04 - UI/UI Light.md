# UI Light

## Active foundation

The existing local component layer under `src/ui/components` is the forward-only Light UI kit (`UiButton`, `Badge`, `StatusBadge`, `Progress`, `DataTable`, `Sheet`, `Tabs`, `Tooltip`). Existing untouched legacy screens retain their current controls to avoid a broad App rewrite.

`src/ui/features/task-center` is mounted above the active page. It projects only state already returned in `NewsFlowSnapshot`: scenarios, covers, voice jobs, montage tasks and Publication V2 queue rows. It does not create a task, trigger a retry, or infer READY from an IPC acknowledgement.

## Light refresh — 2026-09-12

`AppShell` and `Sidebar` are the only active outer shell. `App.tsx` continues to own the page ID, snapshot, `command` wrapper and refresh function; no Electron bridge, command payload, worker, provider, persistence or core runtime moved during the visual migration.

Active Light screen layers:

- Dashboard: shared `StatCard` and `Switch`.
- Ideas/Topics: `Toolbar`, `Input`, `Select`, `Textarea`, `Checkbox` and shared empty state.
- Scenarios/Finished Scripts: shared action toolbars and labelled form controls.
- Covers: namespaced Light surface and shared key selection; the primary FastGen action retains the verified current contract.
- Voice/MP3: Light action toolbars and queue/result surfaces.
- Montage: namespaced current FFmpeg/Remotion queue, cards and task surfaces.
- SEO/Tags and Settings: namespaced panels; current secure key, session and Obsidian contracts remain in place.

Publication V2 (`src/ui/publication/PublicationPage.tsx`) remains the visual reference and active route implementation for Publication, Allocation and Automation.

The `Button`/`Empty` compatibility adapters remain intentionally while individual legacy markup still calls them; both now render the shared primitive. Legacy CSS is retained because it still styles unextracted detail controls. It is not removed until a selector has no active consumer and a browser-level visual capture is available.

## Verification — 2026-09-12

- UI suite: 18 files / 35 tests PASS.
- Source type check and Vite renderer build PASS.
- Current build/core guards PASS; Montage UI contract PASS.
- Isolated runtime/migration/session/cover-tombstone/publication tests: 46 PASS.
- Isolated montage benchmark/queue/render tests: 74 PASS.
- Covers regression fixed: synchronisation now depends on the incoming settings snapshot, not a freshly normalised object, so an absent optional key-selection field cannot cause a render loop.

## Next approved planning boundary

The Light implementation is the existing verified visual baseline. The production workstation phase is documented in [[NewsFlow Production Studio — Full Workstation Redesign Plan]]. It is intentionally a plan only: it preserves the current handler/IPC/core paths and starts no UI implementation until the plan is explicitly approved.

## Production Workstation implementation — started 2026-09-14

The approved implementation has started with the shared shell rather than a screen-specific backend change:

- `WorkspaceErrorBoundary` now isolates the app plus Covers, Voice, Montage, Publication and Analytics; recovery refreshes renderer state only.
- Versioned `newsflow.ui-preferences.v1` stores sidebar collapse and reserved inspector/density preferences in browser-local UI storage, separate from production/project data.
- The navigation rail persists collapsed state through those UI-only preferences.
- Task Center now has explicit `PREPARING` and `WAITING` states, selectable rows and a Sheet-based current task Inspector. It never invents missing artifact/provider metadata.
- Dashboard is now wrapped as the named Production Control Room surface while retaining its original navigation and auto-pipeline actions.
- `Ctrl+K` opens a renderer-only Command Palette built from the current snapshot. It searches topics, production items, scripts, MP3, covers, montage tasks and publication receipts, and only navigates; it cannot enqueue or mutate a job.

Focused red/green tests were written for each unit. Current source verification after this foundation: `pnpm test:ui` **24 files / 46 tests PASS**; `pnpm verify:build-runtime`, `pnpm verify:core-runtime` and `pnpm verify:montage-ui` PASS. No backend, IPC, core-bin, provider, storage schema or production user-data was changed.

**Visual gate (disposable renderer, 2026-09-14):** Vite source renderer was opened without Electron/core and therefore used its fallback snapshot only. The visual tree confirmed the Production Control Room, Editorial Workspace, collapsible navigation rail and `Ctrl+K` palette. Selecting a palette Topic navigated to Ideas; no command was fired. This is source-renderer visual evidence, not a production-provider run.

## Production Workstation implementation — Editorial writing desk

Finished Scripts now protects an edited scenario before its editor is closed. The user can keep editing, discard the local draft, or explicitly save through the unchanged `save-scenario-text` command. `Ctrl+S` is active only while this current editor is open and saves through that same command; the save control is disabled while its request is in flight, preventing a duplicate renderer submission. This is renderer-local dirty state only: it does not create an autosave, alter the snapshot schema, or bypass the current Electron/bridge/core path.

Focused regression coverage is in `src/ui/features/scenarios/scenarios-view.test.tsx`: the unsaved-change dialog, discard path and `Ctrl+S` command payload all pass. `pnpm typecheck` and `pnpm verify:build-runtime` also pass after this change.

## Production Workstation implementation — named production workspaces

The active root surfaces now identify the intended workstation rather than presenting an anonymous collection of legacy panels:

- Templates: **Writing prompt studio**; its baseline prompt, preset library and scenario-range controls retain `save-template` and all current preset/range contracts.
- Covers: **Visual Production Studio**; the existing four-step FastGen workflow, Universal V2 prompt path and verified cover-start payload remain untouched.
- Voice: **Audio Production Console**; queue, pause/resume and WProject/current provider actions remain on their existing commands.
- Montage: **Fast Editing workspace**; the current Fast News FFmpeg/Remotion selection and Montage queue contract remain untouched.
- SEO and Tags: **Distribution workspace**; generation and editable output retain the current `generate-seo`/`generate-tags` and save commands.
- Keys and Chrome Sessions: **Structured settings**; secret handling and persistent session commands remain unchanged.

Each named workspace received a focused UI assertion in the corresponding feature test before its root was added. Targeted tests, `pnpm typecheck`, runtime/core guards and the Montage UI contract passed. The full UI suite after the Scripts/Template stage was **25 files / 49 tests PASS**; the later focused workspace tests also pass. The Vite build continues to pass with an existing 500 kB chunk-size warning, recorded as a performance follow-up rather than masked or treated as a passing performance gate.

## Production Workstation implementation — context workspace

`AppShell` now accepts a caller-owned right-side Context Inspector and a versioned UI-only width preference. `App` supplies the inspector with the selected Task Center entry and persists only `inspectorWidth` in `newsflow.ui-preferences.v1`; it does not write task, queue, project or provider state. The inspector renders only snapshot-backed source, task ID, status/detail and progress, and explicitly refuses to invent artifact paths or provenance. At narrower layouts the inspector slot is intentionally hidden rather than crowding the active production workspace.

Focused red/green coverage now checks the AppShell slot/width variable and Context Inspector selection/width callback. The current full UI suite is **26 files / 56 tests PASS**; TypeScript, current build-runtime guard and source build pass. The source build's existing large-chunk warning remains an explicit performance follow-up.

## Production Workstation implementation — Ideas / Topics editorial workspace

Ideas/Topics now uses the active shared `DataTable` for manually saved directions, while maintaining the existing ctrl-click multi-selection behavior and all original callback payloads. The long provider/preset/requirements form moved into a named **Маршрут генерации** Sheet, so the primary editorial surface is a compact planning table and output workspace rather than a stacked configuration form. Reference-channel and YouTube research behavior remains on its current renderer-local state and command path.

The focused UI test was first RED for the missing table and Sheet, then PASS with the existing `add-topics-to-plan` and `generate-ideas` assertions. TypeScript, Vite source build and 53 isolated idea/scenario runtime regressions passed. An isolated Vite renderer showed the named table and Sheet; the browser console had no errors. No production user-data, provider, OAuth flow, Electron core, IPC command, queue, or storage schema was changed by this screen migration.

## Production Workstation implementation — Scenarios / Scripts writing desk

The current scenario queue and ready-script list are now shared `DataTable` workbenches. Selection, generation, transfer, export, deletion and save continue through their supplied current callbacks. Opening a finished script moves the editor into a **Рабочий текст сценария** Sheet; its existing dirty-state dialog and `Ctrl+S → save-scenario-text` path remain intact, so opening/closing the presentation layer neither auto-saves nor changes the business item.

Both table/Sheet assertions were written RED first and are covered with the unchanged selected-generation, transfer, dirty-close and Ctrl+S command tests. Full renderer suite after this increment: **26 files / 62 tests PASS**; typecheck, source build, current build/runtime guards and the 53 isolated idea/scenario backend tests PASS. The Vite build retains its pre-existing large-chunk warning as a recorded performance follow-up; no production user-data, provider, IPC, core-bin or storage was touched.

## Production Workstation implementation — Templates / Agents editorial routing

Agents is now a compact editorial routing workspace: the active capability map is a shared `DataTable`, and each route action calls only the existing renderer navigation callback. No agent action dispatches a command, provider request, or hidden fallback path. Templates retain their existing prompt-library/editor controls and command contracts.

The focused renderer test was RED before the capability table existed and then PASS, alongside the current UI command-contract suite. The isolated source renderer confirmed the named editorial agent workspace, table, and route actions without touching a core or production snapshot.

## Production Workstation implementation — Covers production queue

The active Covers route now separates its three responsibilities: the four-step FastGen run workflow remains the primary operational surface; `CURRENT PRODUCTION ITEMS` is a compact shared `DataTable`; and a selected row opens a Sheet inspector for only that current cover’s text, face, references, prompt choices and result variants. The large FastGen/prompt/reference/text configuration remains available through a separate **Настроить студию** Sheet, rather than competing with the production queue. Cover Gallery follows the same ownership rule: a `Галерея результатов` index opens one result inspector, retaining its current select, face, rerender, remove and export commands.

No cover command or payload changed. In particular, Universal V2 prompt creation still calls the current `generate-cover-prompts` route, and the verified FastGen start payload remains unchanged. The focused test was RED for the missing queue/inspector/configuration separation, then PASS. Current checks: **26 UI files / 66 tests PASS**, `pnpm typecheck`, source build, build/runtime guards, and 109 isolated cover/tombstone regressions PASS. Source-renderer visual verification confirmed the compact primary queue, configuration Sheet, and empty result index. The build retains the pre-existing large-chunk warning; it is recorded for later performance work, not hidden by a dependency or runtime change. Production data, IPC, core-bin, provider/OAuth paths, and storage were not touched.

## Production Workstation implementation — Voice queue

The active Audio Production Console now renders its current queue through the shared **Очередь озвучки** table. Row selection remains renderer-local and drives the unchanged generate, restart, resume, transfer, export and deletion actions; it does not create another worker or route. The provider/profile configuration remains on the existing current settings and Profiles paths.

The focused queue-table assertion was first RED then PASS together with the existing selected/all generation tests and the current command-contract suite. `tests.test_voicer` passes in isolated storage (**29 tests**); no WProject/Voice API call, production storage, core-bin or Electron command was launched by this presentation-only change.

Ready Audio now uses the shared **Готовые MP3** artifact index. Selection and the explicit open action remain renderer-local / desktop-shell actions; destructive removal remains on the unchanged `remove-voiceovers` and `remove-scenarios` commands. The table assertion was RED then PASS with the existing voice view tests.

## Production Workstation implementation — Voice profiles and provider readiness

Voice Profiles is now a compact master/detail workspace: **Профили голосов** is a shared table, and the current profile editor remains beside it with the unchanged `save-voice-settings` contract. Provider key/catalog/limit panels no longer occupy the profile editor by default; the renderer-local **Проверить готовность провайдеров** control opens them in a Sheet. The existing `go("keys")`, catalog-refresh and key-setting commands are rendered unchanged inside that Sheet, so opening it does not create a provider job or switch to another runtime path.

The new provider-readiness behavior was covered RED before the component existed and then PASS in `src/ui/features/voice/voice-view.test.tsx`. Visual validation in the disposable Vite renderer confirmed the compact profile/table/editor surface and the opened readiness Sheet. No provider command was pressed. Full UI suite: **26 files / 68 tests PASS**; TypeScript, command-contract checks, current build/core guards, Vite source build, and isolated `tests.test_voicer` (**29 tests**) PASS. The source build retains the known Vite chunk-size warning (705 kB minified JS); no dependency/runtime workaround was introduced. The production settings, covers and footage-index SHA-256 values remain identical to the schema-seal baseline.

## Production Workstation implementation — Media ingest and footage cutter

The Footage route is now named **Media Ingest Workspace**. Its existing folder library renders as **Источники футажей**, while returned web matches render as a structured result table with the unchanged source/open/download actions. The index progress, manual semantic-index action, tree inspection and folder/search controls remain on their existing callbacks; this screen creates no new worker or storage path.

The Cutter route is now the focused **Footage Cutter Workspace**. Source videos use a structured **Исходники для нарезки** index before the unchanged cut/mix parameter controls. `add-cutter-sources`, `run-cutter` and `run-mixer` therefore retain their current contracts and FFmpeg runtime.

The screen assertions were RED before the exported workspace/table routes existed and then PASS in `src/ui/features/footage/footage-view.test.tsx`. Disposable source-renderer validation confirmed the empty-state ingest and cutter workspaces without calling a provider, picker or worker; a clean local renderer startup had no console errors. Isolated `tests.test_footage` and `tests.test_cutter` passed (**7 tests**), and TypeScript passed. Production user-data was not opened or written.

## Production Workstation implementation — Montage, outputs, SEO and tags

Fast Editing now keeps one current live-status ribbon inside its workspace and moves the advanced FFmpeg/Remotion/DaVinci, footage, resource and planner controls into **Настроить монтаж**. The render queue, status cards and project timeline remain primary. A visual check found two identical montage-status ribbons; the redundant outer route mount was removed, with regression coverage ensuring exactly one ribbon for the active route. Outputs now presents completed result packages as the **Output Artifact Index** table, with the unchanged package action.

SEO and Tags are now result-first production desks: their current prompts, providers, limits, ranges and export controls open through **Настроить SEO** / **Настроить теги**, leaving each queue/editor work area uncluttered. Their existing `generate-seo` and `generate-tags` contracts were rechecked from inside the Sheet; no command payload, provider, storage or worker changed.

Focused UI tests were RED then PASS for configuration separation, single montage ribbon and the output index. Isolated montage/fast-reuse/timeline/benchmark tests passed (**71 tests**) and isolated SEO passed. The major renderer gate is currently **27 files / 74 tests PASS**, with TypeScript, command contracts, build/core runtime guards and Vite source build all PASS. The source build retains the known 708 kB minified renderer chunk warning; it is documented as a follow-up rather than masked by a runtime or dependency change.

## Evidence — 2026-09-11

`task-model.test.ts` covers RUNNING, FAILED, READY, PAUSED and RETRYING projection from backend fixtures. `npm run test:ui` passed (8 files / 17 tests) and `npm run typecheck` passed. No desktop application or provider was launched.

## Production Workstation implementation — analytics, publication and system area

Analytics now exposes its active channel registry as the **Channel Portfolio Workspace**: a shared **Каналы YouTube** table holds channel identity, pace, 48-hour signal, revenue-access state and the unchanged OAuth / revenue / Studio / removal actions. Per-channel OAuth state and the existing metadata editor are table detail rows, not an alternate service or hidden write path. The focused test was deliberately RED for the missing workspace/table before the route exported the active component, then PASS; TypeScript and the current command-contract suite pass.

Publication V2 remains the one active `PublicationPage` implementation and the visual benchmark for the distribution surface. Its Videos, Channels, Allocation, Queue and History tabs, readiness/distribution controls and current disabled-safe start action are present in the disposable source renderer. API keys retain their structured inventory: the fallback source renderer showed masked provider-state rows and only existing `Управлять` controls; no key, OAuth, external URL, storage write or provider action was invoked.

The source-renderer visual pass opened Analytics, Publication V2 and API Keys through normal navigation with the fallback/disposable snapshot. Analytics rendered the intentional empty state cleanly; populated-channel table coverage comes from the focused UI fixture. Browser console error output was empty. These captures validate renderer composition only, never a production/OAuth/provider run.

## Historical workstation verification snapshot — 2026-09-15

All approved workstation routes are now marked COMPLETE in [[NewsFlow Production Studio — Full Workstation Redesign Plan]]. The final non-production gate passed: `pnpm test:ui -- --run` (**28 files / 75 tests**), command-contract tests (**5 tests**), TypeScript, source build, current build-runtime guard, r4 core-runtime guard and Montage UI contract (**12 controls/types**). The source build emits the already-known 708.93 kB minified renderer-chunk warning; it remains a performance follow-up and is not hidden by a runtime/dependency change.

Isolated publication, OAuth handoff, allocation, engagement, publisher and cover-tombstone regression runs passed (**120 tests**). Static route inspection confirms `PublicationPage` and `AnalyticsDashboard` are active; the remaining `LegacyPublicationDashboard*` and `LegacyAnalyticsDashboard` definitions have no active route references. Legacy CSS remains only where active detailed controls still consume its selectors; it was not deleted blindly and it is not a legacy runtime path.

The production schema-seal baseline is unchanged after the gate: `settings.json` `8B65292DA4553BA42F90A7CF34124AD0E0A0E2174D6444576A2AB5EB05E0FB04`, `covers-library.json` `E34FFDBE11EA32D9F035C3690E3EB13C3B67216F2FCC48EB9E62F52889AA126D`, and `footage-index-status.json` `821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211`. No EXE was built.

## Continuation evidence — 2026-09-15

The earlier route-migration snapshot did not by itself prove every acceptance requirement in the approved workstation plan; the redesign remains in progress. Current follow-up work is presentation-only and continues through the existing bridge/core contracts.

- The source-renderer visual gate now uses a disposable Electron user-data root, asserts its requested viewport, verifies the expected active workspace title, and contains baseline cases for default/empty views plus Cover failure, Voice waiting, Montage ready, Publication paused and selected-task Inspector states. A separate 84-current-Cover fixture records route navigation timing without opening a provider or production data.
- Topics now has a verified narrow (390×844) baseline. The current AppShell overrides legacy global canvas rules only for the active shell; its compact navigation rail scrolls locally, Topics collapses to one column, and the topic-entry action stacks without document-level horizontal overflow. The normal Topics publication plan also no longer collapses its summary text into a narrow second column.
- `Ctrl+S` saves only an active dirty Template editor through the existing `save-template` command and respects IME composition. `Escape` closes only the current Task Inspector’s renderer-local selection. The primary Cover start sequence rejects repeat clicks while its current command is pending; its persisted settings and `generate-covers` payload are unchanged.

Focused UI tests, TypeScript and the current build-runtime guard pass for these increments. The final, full acceptance gate is intentionally still pending; no EXE has been built and no production storage has been used.

### Continuation evidence — provenance and measured heavy queues

The active Cover, MP3, MP4 and Publication receipt inspectors now show only provenance that the current snapshot actually exposes. Cover shows its `production_item_id`, prompt provider, last event and selected artifact; MP3 shows its ProductionItem, provider/profile, job snapshot, update time and path; MP4 shows the saved task's input/output/project paths and phase; a receipt shows its snapshot ID, ProductionItem, channel, times and duration. Each explicitly marks unavailable durable job identity or stale relationship rather than inferring it from title or file name. This remains renderer-only and changes no bridge, IPC, storage schema or core projection.

The current snapshot has no safe cross-artifact version/revision relation for the required `STALE` state. Per the approved plan, that persistence/runtime addition remains deferred for explicit runtime review; the UI does not fabricate stale/ready semantics.

The disposable Electron visual matrix now includes 84-row Voice and Montage fixtures alongside the prior 84-current-Cover fixture. Their 2026-09-15 measured route navigation captures remained below the temporary 3 s budget (Voice 1,760 ms and Montage 2,131 ms on the verification capture); no provider, OAuth session or production user-data was opened. Route navigation also clears a previously selected global Task Inspector entry so context from the prior workspace cannot appear current after a route change.

The API-key creation form now distinguishes its clean draft from an edited secret: cancelling an edited form opens an explicit Save / Discard / Continue dialog and performs no command until Save is chosen. The secret remains renderer-local until the already-existing `add-api-key` command succeeds; no plaintext is persisted by the UI preference store or any other frontend state.

Publication V2 now makes its existing `upload-publication-v2-snapshots` launch locally idempotent across immediate double-clicks: an in-flight ref rejects a second renderer submission before React state has had time to repaint, and both header and queue launch controls show their busy state. The existing snapshot IDs and command payload remain the only source of queue identity; no frontend-generated job ID was introduced.

### Continuation evidence — visual-baseline stability and Obsidian draft safety

The disposable Topics renderer was recaptured at its normal desktop viewport and at 390×844. Both current captures matched their approved baseline with zero changed pixels; the capture uses `NEWSFLOW_TEST_MODE=1` and a temporary Electron user-data root only.

The first Inspector baseline set had been generated before the portal transition had settled, so it recorded a partially transparent Sheet rather than the stable visual state. The capture gate now waits for the renderer transition state. Fresh captures of Cover, MP3 and MP4 Inspectors were repeatable and their reviewed stable baselines now match with zero changed pixels. This changes only disposable PNG test artifacts and the visual-capture harness; it cannot reach a provider, core or production storage.

The Obsidian connection editor now follows the same renderer-local clean/dirty/saving/save-failed convention as the existing template editor. Leaving **База проекта** with an edited vault/MCP configuration opens the existing Save / Discard / Continue navigation guard. Save and `Ctrl+S` invoke only the existing `save-obsidian-settings` command; an unresolved/failed command leaves the draft open. The password token remains local to the form until that current command returns a snapshot, and no new persistence path or UI-preference write was added. `knowledge-empty` extends the disposable visual matrix for this Settings route.

The visual performance metric now measures completed route navigation before the independent screenshot-animation settling phase. This avoids treating a stable modal-capture wait as user-visible route work. Focused source coverage locks that boundary. Full renderer verification after this increment: **33 files / 113 tests PASS**; TypeScript, source build, current build-runtime guard, r4 core-runtime guard and the Montage UI contract PASS. The source build still emits the known 726 kB minified renderer-chunk advisory; it remains a recorded performance follow-up. The canonical production SHA-256 values still match the schema-seal baseline for `settings.json`, `covers-library.json` and `footage-index-status.json`.

The API-key editor is now registered with the same active-draft navigation guard. An immediate route change after entering a secret is blocked synchronously; the root cause was a missing `keysDirty` dependency in the current navigation callback, not a bridge or secure-storage path. Save through the dialog or `Ctrl+S` retains `add-api-key`; discard sends no command. The modal is captured in the disposable visual matrix as `keys-discard-dialog`; the capture input is test-only and contains a non-secret fixture value.

### Continuation evidence — visual matrix completion work

The disposable matrix now additionally covers a publication receipt Inspector, collapsed navigation rail, and the current Analytics OAuth waiting presentation. The OAuth case installs a test-only local adapter in the disposable renderer only; it never starts Google, a provider, or an external browser. All three states preserve the current renderer handlers and command contracts.

Visual capture was hardened against cold Electron compositor frames that could render a Radix portal before its fully composed first frame. The harness primes overlay cases and requires a sustained sequence of identical compositor captures. It also clears only disposable renderer layout preferences between cases. This fixed an obsolete partial API-key dialog baseline without changing the app UI, IPC, core, storage, or production state. The final focused Settings visual sequence (`knowledge-empty`, `keys-discard-dialog`, `task-states-inspector`) now matches approved baselines. Full renderer suite after this increment: **33 files / 120 tests PASS**; TypeScript and the current build-runtime guard pass.

### Continuation evidence — heavy-workspace profiler gate

React `Profiler` coverage now opens the real current Covers, Voice Queue and Montage workspaces against separate 84-item disposable fixtures. Each route performs the expected finite five commits (mount, fixture hydration and the two navigation transitions); no repeated commit cycle occurs. The capture-performance cases remain below their 3 s route-navigation limit, and this evidence executes only in Vitest/JSDOM with no desktop bridge, provider, core, queue or production storage available.

### Continuation evidence — safe desktop close guard

An unsaved Template, Obsidian connection or API-key draft now registers the standard renderer `beforeunload` guard. Electron maps that established browser contract to its native close confirmation, so an operating-system window close cannot silently discard the active draft. The guard is renderer-local: it neither saves automatically nor introduces IPC, core, storage or command changes. The focused Template integration test verifies that an unsaved draft prevents the close event; its existing Ctrl+S test was also made fully awaited so the focused gate completes without React `act` warnings.

The consolidated renderer gate after the profiler and close-guard work is **33 UI files / 123 tests PASS** with TypeScript and a source renderer build. The bundle continues to emit the pre-existing 726 kB minified renderer-chunk advisory; it has not been suppressed or addressed through an unrelated runtime/dependency change.

The full disposable visual matrix then matched every approved screenshot. A capture-only cleanup step now discards the synthetic API-key draft after its confirmation-dialog screenshot, preventing a later fixture navigation from asking Electron for a `beforeunload` confirmation without a user gesture. The image itself is captured before that cleanup; no UI, command, core, provider or production-data behavior is changed.

### Open acceptance dependency — artifact staleness

The current `bridge.snapshot()` proves IDs and limited task metadata for Covers and Voice, but the current Montage task projection has no `ProductionItem` identity and no durable upstream version/time relationship. The renderer therefore must not infer **STALE** from titles, filenames or ordering: that would violate the current-runtime-only rule and could falsely mark historical output. Implementing the approved stale-artifact model needs an explicitly reviewed, non-destructive current snapshot projection (identity plus upstream revision/updated markers) across Script, Voice, Cover, Montage and Publication. This remains deferred rather than silently changing storage schema or bridge semantics during visual work.

**2026-09-15 authoritative recheck:** Voice jobs already persist `production_item_id` plus immutable `script_revision`/`script_hash`. The Montage handoff/task state, however, preserves only its scenario index, title and voice path; it has no authoritative ProductionItem ID nor immutable source revision. Per the approved constraint, no renderer heuristic, storage write, schema migration or core-bin change was introduced. The stale-artifact model is therefore explicitly deferred to the future runtime review while the remaining redesign acceptance gates continue.

The core-runtime guard confirms the active r4 binary at `.core-bin-2.1.152-write-isolation-r4`; the Montage UI contract confirms all 12 expected current controls/types. Read-only production SHA-256 checks remain the schema-seal baseline: settings `8B65292D…E0FB04`, covers `E34FFDBE…9AA126`, footage status `82159726…A24211`.

### Continuation evidence — Topics narrow rail and final isolated validation

The 390×844 Topics workspace had one remaining responsive-density defect: after the topic entry itself stacked, its adjacent primary/secondary actions could still compete for a row. The current responsive AppShell layer now stacks direct Topics toolbar actions at this width. This is CSS-only; it retains the existing `Ideas` component, every current handler/command and the existing bridge/core contract. The focused test was deliberately RED for the missing 600px toolbar rule and then PASS. The reviewed narrow screenshot now shows a full-width topic entry followed by one readable action per row, without document-level overflow.

The explicit stale-artifact review remains deferred by design. Voice has authoritative `production_item_id` and immutable script hash/revision, but the current Montage task/handoff has only a scenario index, title and voice path, with no authoritative ProductionItem/revision chain. No `bridge.snapshot()` projection, schema, core-bin, IPC command or production provenance was changed, because the approved additive scope forbids filling that missing authority with a heuristic.

Fresh final isolated checks after this screen increment: full renderer suite **33 files / 124 tests PASS**; TypeScript, Vite source build, current build-runtime guard, r4 core-runtime guard and the Montage UI contract PASS; isolated command/config/montage runtime tests **40 PASS**. The disposable Electron visual matrix matched all approved Dashboard, Topics normal/narrow, Scripts, Covers, Voice, Montage, Publication, Analytics, Settings, task Inspector and collapsed-navigation baselines. The existing Vite 726.43 kB renderer chunk advisory remains recorded; it was not hidden through a dependency or runtime change. Read-only production SHA-256 values still exactly match the schema-seal baseline. No EXE was built.

### Continuation evidence — complete active-route visual matrix and inspector containment

The disposable Electron visual matrix now has an explicit baseline for every active workstation navigation route, including previously uncovered Scenarios, Templates, Agents, Cover Gallery, Media, Footage, Cutter, Voice Profiles, ready MP3, Outputs and Chrome Sessions. SEO and Tags have both empty and snapshot-backed ready-item cases. The matrix still contains the relevant non-empty operational states: failed Covers, waiting and 84-row Voice, ready and 84-row Montage, paused Publication, OAuth waiting, configuration Sheets, selected artifact Inspectors, the discard dialog, collapsed navigation and narrow Topics. Every capture sets `NEWSFLOW_TEST_MODE=1` and a temporary Electron user-data root; fixtures never invoke a provider, queue worker, picker, OAuth browser or production storage.

Final visual review discovered two real presentation defects rather than merely missing screenshots. Cover Gallery was using a viewport breakpoint even though the live content column was narrowed by the persistent rail and Context Inspector; its title was compressed by a six-card metrics row. Its gallery hero now uses a readable two-column/grid metric composition. Footage, Cutter and Voice Profile controls could also exceed the actual content column and be hidden behind the inspector. `AppShell` now exposes the true main-column width as a CSS container, and scoped current-workspace rules reflow only those forms/profile master-detail layout under 920px of available workspace width. The existing controls, handlers, commands, services, workers, IPC, bridge, core-bin and storage contracts are unchanged. Focused red/green assertions cover the containment rule, and reviewed post-fix captures show every control inside the active workspace.

Final verification after the fixes: **33 renderer test files / 130 tests PASS**, TypeScript PASS, production source build PASS, build-runtime guard PASS (`2.1.152`, current schema/runtime paths), r4 core-runtime guard PASS, Montage UI contract PASS (12 current controls/types), and isolated command/config/Montage runtime tests **40 PASS**. The complete reviewed visual matrix matches its approved baselines; 84-item Cover, Voice and Montage routes remain within the 3s navigation budget. The pre-existing Vite 726.43kB renderer-chunk advisory remains explicitly recorded and was not masked by dependency or runtime changes. Read-only production hashes still equal the schema-seal baseline: settings `8B65292DA4553BA42F90A7CF34124AD0E0A0E2174D6444576A2AB5EB05E0FB04`, covers `E34FFDBE11EA32D9F035C3690E3EB13C3B67216F2FCC48EB9E62F52889AA126D`, footage status `821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211`. No EXE was built.
