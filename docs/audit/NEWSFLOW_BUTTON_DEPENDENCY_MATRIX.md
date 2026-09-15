# NEWSFLOW BUTTON DEPENDENCY MATRIX

## Method and limits

This matrix was produced by static extraction of `command("…")` calls from `src/ui/**/*.tsx` and matching against `scriptor.bridge.main()`. It maps **175 literal UI command names**; the backend dispatcher recognizes **194** names. There are **665** JSX interactive-element occurrences, including repeated row controls and local inputs, so a control-instance-by-instance live-state matrix requires the missing screenshot run. Controls that use direct preload methods are listed separately.

**Common path:** `onClick/onChange` → `App.command()` → `window.newsflowDesktop.command()` → preload IPC `newsflow:command` → Electron `callCore()` → `scriptor.bridge.main()` branch → `load_settings()/save_settings()` and/or external provider.

| UI surface / control family | UI command names evidenced | Backend effect / persistent state | External or destructive side effect |
|---|---|---|---|
| Dashboard / automatic pipeline | `save-settings`, `run-auto-pipeline` | pipeline target and stage flags; orchestrates enabled stages | May start multiple generators/renders. |
| Ideas and source research | `add-topic`, `delete-topics`, `suggest-topics`, `add-suggested-topics-to-favorites`, `clear-suggested-topics`, `add-idea-reference-channel`, `remove-idea-reference-channel`, `save-idea-reference-rules`, `analyze-idea-reference-channels`, `research-youtube-topics`, `clear-youtube-suggested-topics`, `add-session`, `add-topics-to-plan`, `set-idea-route`, `save-idea-route-preset`, `update-idea-plan`, `generate-ideas`, `delete-idea-results`, `regenerate-idea-results`, `add-ideas-to-scenarios`, `transfer-ideas`, `export-ideas` | idea topics, plans, channels, result/source/context records | Provider/web research; deletion/export where selected. |
| Scenarios and scripts | `import-manual-scenario`, `import-manual-scenarios`, `import-voiceover-files`, `import-voiceover-folder`, `remove-voiceovers`, `export-stage`, `export-scenario-titles`, `export-scenarios`, `export-scenarios-separate-txt`, `set-session-active`, `set-session-usage`, `add-scenarios`, `generate-scenarios`, `rename-scenario`, `remove-scenarios`, `save-scenario-text`, `transfer-scenarios`, `enqueue-montage-audio` | session run state, scripts, voice imports, downstream queue references | File reads/exports and provider calls. |
| Covers: setup/text/prompts | `save-cover-settings`, `save-cover-prompt-preset`, `delete-cover-prompt-preset`, `save-cover-headline-preset`, `delete-cover-headline-preset`, `select-cover-prompt`, `refresh-fastgen`, `generate-cover-prompts`, `generate-cover-headlines`, `generate-cover-subheadlines`, `pause-cover-text-generation`, `resume-cover-text-generation`, `generate-cover-texts`, `cancel-cover-subheadlines`, `remove-cover-headlines`, `import-cover-topics`, `save-cover-headline`, `save-cover-subheadline`, `export-cover-prompts` | cover templates, queues, prompt/headline/subheadline fields, FastGen caches | Provider calls; preset/headline removal; export. |
| Covers: images/faces/queue/gallery | `generate-covers`, `reconcile-cover-gallery`, `pause-cover-generation`, `resume-cover-generation`, `prepare-cover-face-library`, `select-cover-face`, `select-cover-face-person`, `clear-cover-face`, `select-cover-visual-reference`, `set-cover-visual-reference-target`, `refine-cover-faces`, `compose-cover-faces`, `regenerate-covers`, `regenerate-cover-with-face`, `regenerate-covers-new-prompts`, `remove-cover-prompts`, `select-cover-variant`, `remove-cover-results`, `remove-cover-image`, `remove-cover-queue`, `export-covers`, `export-cover-images`, `render-cover-text`, `render-cover-text-fastgen` | cover queue plus independent library/tombstones; selected variants; local outputs | FastGen requests, filesystem images, explicit removals/exports. |
| SEO, tags, media | `save-seo-settings`, `save-tags-settings`, `save-tag-limits`, `generate-seo`, `generate-tags`, `remove-seo-packages`, `clear-tags`, `save-tags-text`, `save-seo-text`, `export-seo`, `generate-media` | SEO/tag queue, settings, media output | Provider and exports; removal. |
| Voice / profiles / key pools | `generate-voice`, `generate-voice-range`, `preview-voice-ranges`, `set-voice-queue-paused`, `open-voice-session`, `save-voice-settings`, `save-voice-range-preset`, `apply-voice-range-preset`, `delete-voice-range-preset`, `apply-voice-range-preset`, `add-api-key`, `set-key-active`, `save-api-key-note`, `update-voicer-key-settings`, `refresh-voicer-balances`, `update-lumean-key-settings`, `refresh-lumean-catalog`, `update-voicegen-key-settings`, `refresh-voicegen-catalog`, `update-wproject-key-settings`, `refresh-wproject-catalog` | TTS queue/statuses, profiles/ranges, protected credential pools/caches | TTS provider calls; opens Chrome; credential changes. |
| Footage / cutter / mixer | `add-footage-folder`, `remove-footage-folder`, `save-footage-settings`, `inspect-footage-tree`, `add-cutter-sources`, `run-cutter`, `run-mixer`, `search-web-footage`, `download-web-footage` | configured source/output folders, index and processing records | File write/process; internet search/download. Backend-only `index-footage` exists. |
| Montage / outputs | `save-montage-settings`, `prepare-montage`, `render-montage`, `export-davinci-xml`, `import-davinci-xml`, `run-montage-queue`, `package-outputs` | timeline projects, task statuses, output package records | Long process and MP4/XML/file writes. |
| Publication legacy/allocation | `queue-ready-publication-outputs`, `save-publication-settings`, `save-youtube-engagement-policy`, `run-youtube-engagement`, `queue-existing-youtube-engagement`, `update-channel-allocation`, `refresh-publication-allocation`, `apply-publication-recommendations`, `assign-publication-jobs`, `save-publication-allocation-preset`, `clear-production-queue`, `schedule-publication-jobs`, `save-publication-preset`, `move-publication-job`, `move-publication-job-channel`, `rewrite-publication-title`, `mark-publication-post-done`, `upload-publication-jobs` | jobs, assignments, allocation, schedule, engagement policies | YouTube/studio effects for executed commands; queue clear is destructive. |
| Publication V2 | `migrate-publication-v2`, `save-publication-v2-rules`, `preview-publication-v2-distribution`, `confirm-publication-v2-distribution`, `retry-publication-v2-stage`, `set-publication-v2-paused`, `cancel-publication-v2-execution`, `publication-v2-receipt`, `upload-publication-v2-snapshots`, `reconcile-publication-v2-youtube`, `run-publication-v2-thumbnails` | V2 items, immutable snapshots, stage execution, receipt/status | Upload, metadata/thumbnail change and potential YouTube API effects. |
| Analytics / OAuth / sessions | `add-channel`, `update-analytics-channel-metadata`, `open-analytics-channel`, `remove-analytics-channel`, `connect-youtube-channel`, `reset-youtube-channel-account`, `refresh-analytics`, `open-chrome-session` | analytics channel and OAuth/profile metadata | Opens browser; OAuth/API; explicit channel removal. |
| Knowledge / templates | `save-obsidian-settings`, `test-obsidian-mcp`, `export-obsidian-notes`, `save-template`, `save-template-preset`, `delete-template-preset`, `save-range-preset`, `delete-range-preset` | integration/template/preset settings | Obsidian external call/export; deletion. |

## Direct preload controls (not represented as `command()` literals)

| Method | IPC | Source role |
|---|---|---|
| `snapshot()` | `newsflow:snapshot` | Refreshes the full UI DTO; recovery/migration that persists data is available only through explicit `reconcile-runtime-state`. |
| `saveSettings(patch)` | `newsflow:save-settings` | Saves generic settings patch. |
| `startYoutubeOAuthHandoff`, `youtubeOAuthHandoffStatus`, `cancelYoutubeOAuthHandoff` | dedicated OAuth IPC | Local orchestration of Google/Tinkbro handoff; actual OAuth state **NOT VERIFIED**. |
| `chooseFolder/Videos/Images/Audio/AudioFiles/Json/PromptText/ScenarioTexts` | native dialogs | Selects local paths / reads limited text. |
| `chooseSavePath/ZipSavePath/AudioSavePath` | native dialogs | Selects export destination. |
| `openPath` | `shell.openPath` | Opens local file/folder with associated OS application. |

## Known behavior of the “Создать обложки” primary action

The `generate-covers` backend path claims `%LOCALAPPDATA%/NewsFlow/cover-generation.lock`, selects missing-image rows by default (or supplied indices), uses up to ten parallel topic workers, persists row status/progress and releases its lock in `finally`. A duplicate click returns a snapshot with a “generation already running” result. It does **not** replace existing valid images unless an explicit regeneration route is used. Actual FastGen provider execution was not invoked in this audit.

## Final runtime audit update — 2026-09-12

The static map is now enforced by `tests/test_runtime_action_map.py`: all 175
literal renderer commands must exist in the TypeScript contract and resolve to
one current `scriptor.bridge.main()` dispatch branch. Every direct preload IPC
channel must have a current Electron handler. The current bridge is rejected
if it imports either retired desktop runtime (`scriptor.app`) or a legacy
bridge. The dedicated protected-action registrations, active services,
migration-only paths and status/error rules are documented in
`docs/obsidian/NewsFlow/02 - Active Runtime Paths/Button to Runtime Map.md`.

The audit found and fixed current-path defects with red/green regressions: a
voice-range TypeScript payload declared an obsolete `indices` shape instead of
`rangeId`; a montage spawn failure could be mistaken for a successful snapshot;
a packaged build could select a nested old preview core; and the active
Analytics OAuth direct IPC start/poll path did not project failures into the
visible row error state. Fast News FFmpeg rendering now loops an explicitly
selected short moving source as a bounded proxy rather than truncating the
narration; its cache generation was advanced so old truncated proxies cannot
mask the repair.

The prior legacy render guard was removed from the current code path. Topic
specialisation now enters only semantic fields in the Final Prompt Builder;
the Universal V2 core is the sole provider-style and negative-rule source.

## Coverage caveat

This matrix identifies handler-level dependencies, not final UI enablement for each row/selection/state. Screenshot/AX validation remains required to prove labels, disabled states, modals and all repeated gallery/table controls.

## Visual evidence cross-check (user-supplied DOCX)

The supplied visual pack now proves the **appearance** of the following command families on named screens: dashboard/pipeline (V-01), ideas (V-02), scenarios/scripts (V-03/V-07), templates (V-04), covers/gallery (V-06/V-08/V-09), media (V-10), footage/cutter (V-11/V-12), voice/profiles/audio (V-13–V-15), montage (V-16), SEO/tags (V-17/V-18), analytics/keys (V-19/V-21), outputs (V-20), and Publication V2 (V-22/V-23). Page IDs are defined in `NEWSFLOW_SCREENSHOT_UI_ATLAS.md`.

`VISIBLE ON SCREENSHOT = YES` applies only to a visually identifiable control family, never to its runtime success. `NO / NOT EVIDENCED` applies to every command absent from those static/default screens, including provider-selector menus, destructive confirmation dialogs, retries in a failed provider request, OAuth waiting/failure/cancel states, active queue states and publication receipts. The complete gap set is `NEWSFLOW_SCREENSHOT_COVERAGE_GAPS.md`.

| Matrix family | Visible on screenshot? | Page/screenshot evidence | Runtime interpretation |
|---|---|---|---|
| Dashboard/pipeline | Yes | V-01 | handler state/outcome not proven. |
| Ideas/scenarios/scripts/templates | Yes | V-02–V-04, V-07 | provider execution and errors not proven. |
| Covers/galleries | Yes | V-06, V-08, V-09 | FastGen dispatch, rate limit and destructive confirms missing. |
| Media/SEO/tags | Yes | V-10, V-17, V-18 | provider result path not proven. |
| Footage/cutter/montage | Yes | V-11, V-12, V-16 | screenshot proves one montage error/retry presentation; no active worker proof. |
| Voice/profile/audio | Yes | V-13–V-15 | provider selector is closed; active/pause/error/retry not captured. |
| Analytics/keys/OAuth | Yes, static actions | V-19, V-21 | OAuth/data refresh outcomes not captured. |
| Publication V2 | Yes, record/allocation surfaces | V-22, V-23 | queue running, receipt, retry/cancel confirmations absent. |
| Channel research | No | none | model/import source exists; no routed current screen evidence. |
