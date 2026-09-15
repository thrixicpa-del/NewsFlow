# ADR-002 — Legacy Production Write Isolation

**Status:** accepted 2026-09-14  
**Scope:** canonical `%LOCALAPPDATA%/NewsFlow` cover state only. This decision does not alter providers, IPC transport, core architecture, Montage, Voice, FFmpeg, or storage locations.

## Incident evidence

The canonical production session represented 84 current scenario/ProductionItem identities. The durable cover registry retained 97 historical rows with `legacy-cover:*` identities. Those historical rows received a tightly clustered set of prompt/headline/subheadline status, text and timestamp writes.

The installed 34.6 MB core and the staged 33.3 MB core both reported the release version `2.1.152`, but are not the same executable. A snapshot of a disposable copy through the installed core returned the 97 legacy rows as active Covers; the current source projects current IDs only. Field/timeline shape establishes the old bridge command chain as `generate-cover-prompts` → `generate-cover-headlines` → `generate-cover-subheadlines` → settings/library persistence. The original PID/window cannot be attributed after the fact because no Windows process audit retained it. This ADR does not claim a stronger attribution than the evidence supports.

## Decision

1. `schema_version=4` is the runtime write fence. A pre-fence schema-3 core rejects the file before a load/save operation. `seal_current_runtime_storage()` operates on raw JSON and changes only this marker; it preserves all other parsed data, including unknown and encrypted fields, and saves the pre-seal raw file as recovery evidence.
2. The current Covers runtime uses one authority: a durable current ProductionItem ID. Titles are display data only. A `legacy-cover:*` registry identity is history, never an active identity and never a title-match migration input.
3. Explicit selected provider actions carry `productionItemIds` with their UI indices. Before provider execution, the bridge re-resolves the current queue, requires both index and ID to agree, excludes ProductionItem and legacy-title tombstones, and skips stale work without changing text/status/timestamps.
4. Bulk actions derive their selection at execution time from current session IDs. Parallel FastGen children receive the durable ID for their single row and repeat the same gate after reload.
5. A manual direct row with no scenario session receives a new `production:manual:*` identity in the current core before provider work. It is never derived from title and cannot become a `legacy-cover:*` identity.
6. Historical rows are retained in `covers-library.json`; they are not deleted, re-baselined, provider-processed, or automatically reconciled into active Covers.

## Rejected alternatives

- Deleting the 97 historical rows: loses recovery/history evidence and does not close the writer path.
- Mapping title/name to current IDs: a reused title resurrects stale provider text and state.
- Trusting executable version text: the incident demonstrated two different cores carrying the same version.
- Allowing old core fallback: turns a package/launch mismatch into a production write.

## Required verification

- Isolated 84-current/97-history restart and batch projection remains exactly 84 current Covers and byte-equivalent historical registry rows.
- A stale queued legacy ID is skipped even if its old index now points at a current cover.
- A schema-3 binary rejects a schema-4 sealed copy before write.
- New staged `core-bin` passes `verify:core-runtime`; no desktop EXE is produced by this decision.
- Production storage is sealed only after an independent raw backup and a final before/after SHA-256 check. The mutated data is not accepted as a new business-data baseline by this ADR.

## Production seal verification — 2026-09-15

With every NewsFlow process stopped, the pre-seal recovery copy was written to `%LOCALAPPDATA%/NewsFlow/state-backups/legacy-write-isolation-preseal-20260915-000042`. Its settings, cover registry, session, session backup, and footage-index status files were hashed before the seal.

`seal_current_runtime_storage()` then changed `settings.json` only from schema `3` to `4`. Parsed settings excluding `schema_version` are identical to the raw recovery copy. `covers-library.json` remains byte-identical (`E34FFDBE11EA32D9F035C3690E3EB13C3B67216F2FCC48EB9E62F52889AA126D`), as does the footage-index status (`821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211`). The registry still contains its 97 historical `legacy-cover:*` rows; they were neither deleted nor treated as a new business-data baseline.

The staged r4 core projects 84 current Covers and zero legacy Covers from a disposable production-state copy. On the same copy after sealing, the installed schema-3 core exited with rejection before changing settings or the registry. Full isolated Python regression (497 tests), renderer tests (59 tests), TypeScript typecheck, and both build/core runtime guards passed. No desktop EXE was created.
