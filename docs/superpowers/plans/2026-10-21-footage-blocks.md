# Footage Blocks Implementation Plan

> **For agentic workers:** Use subagent-driven-development for independent domain, UI and selection tasks; controller integrates/reviews each and performs final acceptance.

**Goal:** Manual footage folders assigned to durable topics and enabled explicitly for montage.
**Architecture:** Existing Settings owns named blocks, per-Product-ID assignments and an off-by-default toggle. A small block service validates CRUD/import; a selector consumes the existing scene list. Bridge snapshots persist policy to jobs/projects; UI reuses existing IPC and folder dialog. Normal montage remains unchanged when disabled.
**Tech Stack:** Python, SQLite usage history, React/TypeScript, Electron, existing FFmpeg/NVENC/Remotion.
**Spec:** ../specs/2026-10-21-footage-blocks-design.md (owner-approved issue417).

## Global Constraints

Separate codex/footage-blocks branch based on43eb999; separate stacked PR against codex/montage-stock-sources. Main, user data, original media, credentials, Frozen/EXE and locks unchanged. Test storage only; preserve prior integrity failures. No provider/download/model calls needed for this feature. Current Story Map and narration remain authoritative. Test resource/storage bounds inherited24GiB total known media,4CPU/4GiB.

### Task1: Domain, configuration and import validation
Files: scriptor/footage_blocks.py, scriptor/config.py, tests/test_footage_blocks.py.
Consumes Settings and explicit canonical topics[{id,title}]. Produces upsert_block/delete_block/list_blocks; parse_topic_block_pairs; resolve_assignments/apply_assignments/assign_block; get_block_snapshot; block_files. Controller owns creation of native ProductionItems.
- [x] RED tests: stable ID across rename; nofiledelete; exact paragraph pairs; errors atomic; conflicting manual override; canonical containment; stale settings writers cannot undo operator choices.
- [x] Add settings footage_blocks, footage_block_assignments, montage_use_footage_blocks=False with per-ID baseline merge.
- [x] Implement validation before mutation, reuse scan_folders with resolved-root containment; cache counts on edits rather than scan allroots in snapshot.
- [x] GREEN isolated domain tests and config regressions; review diff and tests.

### Task2: UI and transport
Files: studio-ui-remotion-verify/src/ui/components/FootageBlocks.tsx (or established component location), App.tsx, desktop.d.ts, contracts/newsflowCommands.ts, electron/allowed-core-commands.ts, UI tests.
Consumes footageBlocks, footageBlockTopics, footageBlockImportPreview/conflicts snapshots and montageSettings.useFootageBlocks.
Commands: save-footage-block{blockId?,name,root}; delete-footage-block{blockId}; preview-footage-block-import{text}; import-footage-block-pairs{text,confirmOverwrite?}; assign-footage-block{productionItemId,blockId}; save-montage-settings{useFootageBlocks?}.
- [x] RED UI tests for manual creation/edit, TXT preview, stable-ID assignment, render toggle save and cancellation.
- [x] Implement named block form/count/path, native folder browse, TXT preview before commit and explicit conflict confirmation. Mount management in Index and individual assignments in Index/Montage. Toggle never implicitly enabled.
- [x] GREEN relevant Vitest/typecheck and review frontend→transport payloads.

### Task3: Curated random selection
Files: scriptor/montage_blocks.py, tests/test_montage_blocks.py.
Produces build_block_clips(scenes,policy,*,unique_percent,history_root,batch_usage,scenario_index,checkpoint,duration_probe,source_allowed,family_of)→list[TimelineClip]. Scene data is consumed verbatim, no planner. Use StockUsageHistory and existing continuity resolver; controller records usage after project publication.
- [x] RED tests for outside-folder exclusion, uniqueness/rotation/window history, exact voice beat metadata, shortage hold/background and cancellation.
- [x] Implement finite randomized eligible file order, history/position/batch reservations; durable project order; no semantic reranking of curated manual block. Technical health and text filter remain.
- [x] GREEN isolated selection tests; independently review accounting and no silent global fallback.

### Task4: Bridge integration and immutable project policy
Files: scriptor/bridge.py, scriptor/command_contract.py, tests/test_footage_block_pipeline.py, applicable CI suite list.
- [x] RED bridge tests: existing Product ID survives import/manual edit, newtopic gets native ID, badbatch no writes; disabled montage never invokes block selector; active block consumes native scenes only; queued policy cannot be changed mid-task.
- [x] Add canonical handlers registered on all boundaries and projection. Preview uses native-topic creation on disposable in-memory copy; commit reruns validation and returns actual IDs. Preserve explicit user confirmation for conflicting manual assignment.
- [x] In prepare_montage resolve policy after native ProductItem/VoiceMap; early block route consumes scenes and normal project publication. Persist enabled/blockid/name/root/productid/seed/uniqueness to source_policy, selected clips unchanged on plain export. Pass snapshot at planner start; pending work reads current policy.
- [x] Scope repair paths and continuity anchors to savedroot; no global or stock escapes. Off mode uses original source logic.
- [x] GREEN targeted and related contracts/queue/reuse/source-policy regression; root review.

### Task5: Runtime QA and delivery
- [ ] Build source UI/desktop/Remotion only, security/type/lint/secrets/diff gates.
- [ ] Isolated real Electron UI: create/edit blocks, import valid/error TXT, manual per-topic change, toggle save/restart. Prepare/render both aspects from approved copied licensed footage or synthetic technical fixture (label explicitly); confirm path family isolation, normal source path when off, native beat IDs and full audio PCM. No production writes, downloads or reindexing27k.
- [ ] Record exact commands/counts/times/media hashes and every FAIL/NOT RUN; Docker if engineavailable. Independent full diff review, commit/push, draft stacked PR, attach, inspect new CI/Windows. Do not merge/closeissue/buildFrozen.
