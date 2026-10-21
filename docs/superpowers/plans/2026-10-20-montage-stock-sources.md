# Montage stock sources implementation plan

> For agentic workers: use dispatching-parallel-agents for disjoint provider,
> UI and media helpers; integrate and review centrally. Use RED → GREEN.

**Goal:** Fill existing NewsFlow visual scenes from operator-permitted stock
sources, preserving voice timing, identity, manual choices and uniqueness.

**Architecture:** Keep VoiceMap/Story Map/JSON and TimelineProject as canonical.
Extend selection with provider adapters and a persistent immutable original cache.
Selected stock videos and animated image derivatives enter the existing render
and proxy routes as ordinary video clips; no new scene planner or renderer.

**Tech stack:** Existing Python standard library/SQLite/DPAPI, CLIP, FFmpeg,
React/TypeScript/Electron and the existing offline test launcher; no new dependencies.

**Spec:** Owner's updated 14-point request in this chat, 2026-10-20. This replaces
the earlier keyless-only restriction and approves Pexels/Pixabay/Coverr key inputs.

## Global constraints

- Dedicated branch `codex/montage-stock-sources` from `origin/main` 43dd0709.
- Main, PR403/413, installed NewsFlow, production data, Frozen/EXE and lock unchanged.
- Never create a second scene map or call a text/voice provider for stock search.
- Modes: local, hybrid, stock. Sources are an explicit permission allow-list.
- CLIP/safety failures reject candidates; never fill gaps with unrelated material.
- Keys: unlimited append/dedupe per provider, protected storage, safe UI metadata,
  fair automatic request rotation, bounded concurrency, respect provider cooldowns.
- Trim controls derivative creation, never modification of downloaded originals.
  Timeline display ends at voice/scenes; all original stock audio is excluded.
- Preserve existing fast reuse, percentage/ranges/history; no silent override.
- Exhaustion is a saved manual-replacement scene status, not false render success.
- All tests use disposable storage and intercepted network responses only.

## Task 1 — providers, keys and original cache

Files: `scriptor/stock_sources.py`, `tests/test_stock_sources.py`.
Interface: `StockService(root, keys=dict[str,list[str]], enabled=list[str], checkpoint=None)`;
`search(query, kind='video', limit=6)`, `cached(query, kind='video')` return
`StockCandidate`; `fetch(candidate)->Path`. Candidate carries provider/id/title,
download URL (not logged/manifested), source page, license/URL/author/kind/tags,
dimensions/duration and optional immutable local path.

- [x] RED: adapter fixtures for five sources, permission filtering, auth headers,
  invalid license rejection, media URL validation, rotation/cooldown, bounded
  download, atomic publication and byte-hash dedup after service restart.
- [x] Implement official endpoints only; isolate provider errors and preserve
  attribution. Cache search metadata according to source rules; no secret URLs.
- [x] GREEN: `python -B tests/run_isolated.py tests.test_stock_sources -q`.

## Task 2 — source settings and protected key storage

Files: config, bridge settings/snapshot, new `tests/test_stock_settings.py`.
Interface: `montage_source_mode`, `montage_stock_sources`, `montage_stock_trim`,
`stock_api_keys` records with stable ID/provider/label/active and protected secret.
UI command `save-montage-stock-keys`: `{provider,keys}` or `{id,active/remove}`.

- [x] RED: mode/source validation, unlimited keys, per-provider dedup, no secret in
  snapshot/plain settings, restart, stale-worker writes preserving edits/removals.
- [x] Implement three-way settings merge and key tombstones; preserve legacy
  autoWeb/externalOnly interpretation until operator saves explicit mode.
- [x] GREEN: isolated settings/contracts plus relevant config/session regressions.

## Task 3 — silent, immutable stock derivatives

Files: `scriptor/stock_media.py`, `tests/test_stock_media.py`.
Interface: `prepare_stock_media(source, output_root, duration, trim=True,
kind='video', aspect_ratio='16:9', source_start=0)->Path` (keyword args).

- [x] RED synthetic videos with tone and still images: no source mutation,
  no audio in derivatives, correct duration/dimensions, trim-off original path,
  deterministic content-key cache and corrupt cache rejection.
- [x] Implement using existing FFmpeg, atomic derivative publication and locks.
- [x] GREEN via canonical isolated launcher and actual FFprobe/decoded samples.

## Task 4 — selection integration without new planning

Files: bridge preparation/replacement hooks; `scriptor/stock_selection.py` and
`tests/test_stock_selection.py` if needed to keep provider policy out of bridge.

- [x] RED tests feeding fixed existing scenes and local indexed hits: local never
  accesses stock, hybrid uses local exact before stock and related local fallback,
  stock excludes local; synonym expansion, wrong visual rejection, image fallback,
  percentage-constrained reuse, permission-filtered cache and no-results marker.
- [x] Use current query ladder, semantic guards, CLIP `score_file`, source-family
  history and project serialization. Save licensing and source mode in project.
- [x] Resume existing projects directly; changes do not overwrite manual clips.
- [x] GREEN targeted + full related montage/voice/footage regressions together.

## Task 5 — UI and end-to-end acceptance

Files: Montage App controls, desktop/command contracts, source security allow-list,
new stock UI tests and isolated Electron smoke; CI and verification report.

- [x] RED: modes, source checkboxes/all, trim, protected multi-key editor, save/reload.
- [x] Implement inside existing montage settings, no redesign or new studio.
- [x] GREEN UI/contracts; build web/desktop source; actual disposable UI round trip.
- [x] Render synthetic MP4 through existing routes: duration/voice integrity,
  source hash unchanged, stock tone absent, animated still dimensions and cache reuse.
- [x] FAST/Ruff/type/security/secret gates, dependency audit, independent diff review.
- [ ] Publish draft PR and inspect independent CI on its exact commit. Local
  evidence and unavailable gates recorded; no merge/issue close/Frozen build.

## External references

- MoneyPrinterTurbo MIT: https://github.com/harry0703/MoneyPrinterTurbo
- Pexels: https://www.pexels.com/api/documentation/
- Pixabay: https://pixabay.com/api/docs/
- Coverr: https://api.coverr.co/docs/videos/ and /auth/
- Commons: https://www.mediawiki.org/wiki/API:Imageinfo
- NASA: https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf

MoneyPrinterTurbo is an architectural reference for staged search/download/cache,
not a reason to import another scene planner, LLM/TTS stack or MoviePy renderer.
