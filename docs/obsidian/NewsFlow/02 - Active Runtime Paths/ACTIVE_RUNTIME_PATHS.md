# ACTIVE RUNTIME PATHS

**Rule:** production defaults to `LEGACY FALLBACK = NO`. A canonical failure returns a diagnosable error/retry state; it does not silently execute an older implementation.

| Feature | Canonical implementation / entry | UI command | Service / worker / provider | Persistence and real result | Legacy alternatives | Fallback |
|---|---|---|---|---|---|---|
| Topics | `Ideas` → `bridge.generate_ideas` → Python title/ProductionItem validation | `generate-ideas` | configured Agent/OpenAI route | `Settings.idea_*`, stable ProductionItems/tombstones; normalized <=100-char, deduplicated topic rows | prior title/ideas parsers | NO |
| Scripts | `Scenarios` → `bridge.generate_scenarios` → `core.build_requests` → `ParallelRunner` | `generate-scenarios` | configured Agent/OpenAI route | durable session range contract, actual chars and bounded-repair status | older scenario templates | NO |
| Voice / WProject | `VoiceQueue` → `bridge.generate_voice[_range]` | `generate-voice`, `generate-voice-range` | provider adapter / bounded voice workers | persisted `production_item_id` snapshot, staged MP3 → FFmpeg duration validation → atomic canonical output, durable READY/artifact metadata | Chrome/other provider routes are explicit selected providers, not fallback | NO implicit |
| Covers | `Covers` → `bridge.generate_covers` → `thumbnail_prompt_v2.build_final_provider_prompt` | `generate-covers` | FastGen pool | cover queue + `covers-library.json`; image existence/validity | `_cover_render_guard` and legacy prompt fragments | NO |
| Montage | `Editor`/outputs → `bridge.run_montage_queue` | `run-montage-queue` | canonical FAST NEWS FFmpeg proxy/cache worker; Remotion is explicit composition mode | `.newsflow`, `montage_task_statuses`, A/V-duration-validated MP4 | prior render paths/presets | NO |
| SEO | `Seo` → `bridge.generate_seo` | `generate-seo` | configured Agent/OpenAI route | `seo_queue`, exported package | old templates | NO |
| Tags | `Tags` → `bridge.generate_tags` | `generate-tags` | configured Agent/OpenAI route | tag settings/manual text/publication metadata | old templates | NO |
| Publication | `PublicationPage` / V2 command set | V2 publication commands | `publication_v2` + YouTube adapters | V2 items/snapshots/executions/receipts and `youtubeVideoId` | legacy jobs retained only for non-destructive projection | NO |
| Settings | `config.load_settings` / `save_settings` | snapshot and save commands | atomic writer + interprocess lock | `%LOCALAPPDATA%\\NewsFlow\\settings.json`, backups | old Scriptor secret import is migration-only | NO |

## Contract enforcement — 2026-09-12

- Renderer `src/contracts/newsflowCommands.ts` enumerates the bridge command vocabulary and supplies generic `command<K extends NewsFlowCommand>` typing. `generate-voice-range` is explicitly typed with its real `rangeId` payload, rather than the unrelated scenario-index shape.
- `scriptor/command_contract.py` is the active Python registration point for Settings, Topics, Scripts, Import/Delete, Voice, Covers, Montage, Export, SEO, Tags and Publication V2/upload actions. Each entry names the canonical handler/service and forbidden legacy family.
- `bridge.main()` validates registered request objects before dispatch and validates their structured response after the canonical handler returns. Existing unmodified commands remain compatible on the generic transport until their own bounded phase.
- Tests prove 175 literal renderer commands have a TypeScript contract and one current bridge dispatch, direct preload IPC has an Electron handler, registrations point to callable current handlers, invalid payloads stop before a handler runs, and the bridge excludes retired desktop modules.
- A packaged build accepts only `resources/core-bin/NewsFlowCore.exe`; it cannot fall back to the nested core layout from an old preview build. A missing current core is a clear startup failure, not a silent behavior regression.
- Evidence: `tests.test_runtime_action_map`, `tests.test_ui_delivery`, `scriptor.test_command_contract`, `src/contracts/newsflowCommands.test.ts`, `pnpm typecheck`, and `pnpm verify:build-runtime` (no production app or provider action).

See [[Button to Runtime Map]], [[16 - Regression Tests/Regression Gates]] and [[FAST NEWS MONTAGE]], [[Cover Pipeline]], [[Settings Persistence]], [[Publication]].

## Cover provider identity gate — 2026-09-14

`Covers UI selection` → `productionItemIds + indices` → Electron command → `bridge._select_current_cover_generation_rows()` → current Cover/Prompt/FastGen worker → canonical `settings.json` + `covers-library.json`.

The selector resolves the current session again immediately before work, rejects a stale index/ID pair, excludes ProductionItem and title tombstones, and never permits `legacy-cover:*` identities. The current worker passes the durable ID to its parallel FastGen child, which repeats the gate after reload. The old 34.6 MB core is an incompatible schema-3 runtime once the current storage fence is sealed; it has no automatic write path to the schema-4 canonical state. See [[18 - Decisions/ADR-002 Legacy Production Write Isolation]].

## Voice artifact gate — 2026-09-11

`generate_voice` writes a new provider response into `.newsflow-voice-staging` beneath the configured output folder. It validates file existence and positive FFmpeg duration before atomically promoting the candidate. A malformed response therefore becomes the item error state and cannot replace an older READY MP3. Manual imports follow the same validation gate. WProject remote IDs remain persisted before poll/download, so resume uses the accepted task rather than submitting a duplicate.

Evidence: `tests.test_voicer`, `tests.test_tts_ranges` (47 focused tests; no live provider action). See [[Voice Engine]].

## Topics and script-length contract — 2026-09-11

Ideas are accepted only through Python normalization/validation, bounded recent deduplication and ProductionItem event/context validation. Scripts retain `target_chars`, `allowed_min` and `allowed_max` from the selected saved range through the final provider request. The runner calculates character count after each response, repairs an opted-in out-of-range response at most twice, and persists `READY` or a visible `FAILED` error state. Snapshot and UI consume those backend fields; no client-side success inference is used.

Evidence: `tests.test_ideas`, `tests.test_scenarios`, `tests.test_runner`, `pnpm typecheck`. See [[Topic Engine]] and [[Script Engine]].

## Preservation gates — 2026-09-11

Covers, footage, SEO/tags and Publication V2 were regression-tested without activating provider, OAuth, render or queue work. The cover V2 prompt remains the sole FastGen payload. Footage uses path/size/mtime incremental indexing and removes missing paths. Publication retry preserves an existing `youtubeVideoId`; its explicit cleanup requires a UI-supplied confirmation phrase and preserves channels/OAuth/analytics/settings.

Evidence: `tests.test_covers`, `scriptor.test_cover_library`, `tests.test_cover_queue_tombstones`, `tests.test_footage`, `tests.test_seo`, `tests.test_publication_v2`, `tests.test_youtube_publisher`, OAuth persistence tests. See [[Cover Pipeline]], [[Footage Index]], [[SEO and Tags]] and [[Publication]].
