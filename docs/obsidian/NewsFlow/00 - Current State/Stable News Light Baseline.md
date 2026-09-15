# Stable News Light baseline

**Baseline date:** 2026-09-11  
**Mode:** source analysis plus protected production-state backup. No provider, OAuth, queue, rendering, publication, or packaged-application action was run.

## Safety baseline

- Canonical persistent root: `%LOCALAPPDATA%\\NewsFlow`.
- Safe full backup before code changes: `D:\\NewsFlow Studio\\Backups\\pre-stable-news-light-20260911-161027`.
- Backup verification: all source files are present with no Robocopy mismatch/failure; `settings.json`, `covers-library.json`, footage index database/status, and last-known-good settings have matching SHA-256 digests.
- The configured external Obsidian vault was empty. This `docs/obsidian/NewsFlow` tree is the single project-local, Obsidian-compatible engineering vault. It does not alter the application’s Obsidian setting.

## Module freeze classification

| Module | Status | Evidence / rule for Light |
|---|---|---|
| Topics | IMPROVE | Generation and ProductionItem scaffolding exist; add deletion, length, dedup and provider truthfulness without touching downstream stable modules. |
| Scripts | IMPROVE | Existing scenario workflow exists; add configured character ranges and measured repair. |
| Voice / WProject | FIX | Existing provider routes, queues and MP3 registry exist; verify long-script, retry, restart and ProductionItem ownership. |
| Covers | STABLE / FIX | Universal V2 path and regression suite are current; preserve it and only add integrity protections. |
| Montage | FIX | Existing queue, timeline and renderer paths exist; establish one measured FAST NEWS MONTAGE path and no silent fallback. |
| Footage index | IMPROVE | SQLite index exists; add incremental/cache guarantees without redesign. |
| SEO | STABLE | Preserve generation, persistence and publication transfer; regression-check only unless a dependency break requires a narrow fix. |
| Tags | STABLE | Preserve generation, limits, manual edits and transfer; regression-check only unless a dependency break requires a narrow fix. |
| YouTube publication | STABLE / FIX | V2 registry/execution exists; make canonical routing explicit, retain OAuth/channels and prohibit duplicate upload after a video ID. |
| Settings / persistence | FIX | Canonical root, locking, merge and backups exist; corrupt JSON and write-on-snapshot behavior need hardening first. |
| UI foundation | IMPROVE | Preserve React + TypeScript + Vite + Electron; add shared primitives and feature-local code only for changed surfaces. |
| Channel research | EXPERIMENTAL | Data/import model exists, but no source-proven dedicated run/pause/stop UI executor. It must not be promoted silently. |
| Legacy alternatives | LEGACY | Retain for evidence/recovery only; never select as an implicit production fallback. |

## Non-negotiable preservation set

Never reset, overwrite, relocate or silently reconstruct: provider/API settings and protected credentials; OAuth and channel profiles; all user paths; topics, scenario text and production relationships; voice profiles, MP3 mappings/jobs/statuses; cover prompts, words, images, references, galleries and queues; footage index; montage projects/statuses/MP4s; SEO/tags; publication registries, snapshots, receipts and video IDs; presets, history and UI preferences.

The required migration protocol is: **backup → validate source → migrate a copy/in memory → validate result → atomically commit**. Invalid settings must leave the original file untouched and yield a visible recovery error, never `{}` followed by a save.

## Final source-gate state — 2026-09-12

All bounded Light implementation tasks have passed their focused and aggregate source gates. The only unresolved items are intentionally external or release-only: live provider/OAuth behavior remains unverified, and no EXE/package launch or migration of production data was performed. See [[19 - Release Baselines/2026-09-11 Pre-Light Backup]].
