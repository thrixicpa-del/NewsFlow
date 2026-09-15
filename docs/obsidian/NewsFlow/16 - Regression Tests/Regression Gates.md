# Regression Gates

## Phase-local tests

| Phase | Targeted evidence |
|---|---|
| Persistence/deletion | `scriptor/test_config.py`, `tests/test_ideas.py`, `tests/test_scenarios.py`, new corruption/tombstone tests in isolated `LOCALAPPDATA` |
| Command contract | new contract tests covering renderer registry, preload, IPC and bridge dispatch; TypeScript typecheck |
| Topics/Scripts | `tests/test_ideas.py`, `tests/test_scenarios.py`; Python limits/dedup/length-repair tests |
| Voice | `tests/test_voicer.py`, `tests/test_tts_ranges.py`; provider mocked output, retry/restart/matching tests |
| Covers | `tests/test_covers.py`, `tests/test_cover_queue_tombstones.py`, `scriptor/test_cover_library.py`; single prompt block, exact payload/artifact checks, 84-current/97-history projection, stale job skip and title-resurrection rejection |
| Montage/footage | `tests/test_montage_queue.py`, `scriptor/test_montage_render.py`, `tests/test_timeline.py`, `tests/test_footage.py`, benchmark fixture |
| SEO/Tags | `tests/test_seo.py` plus preserved transfer tests |
| Publication | `tests/test_publication_v2.py`, `tests/test_youtube_publisher.py`, OAuth/persistence tests; all provider calls mocked |
| UI | focused Vitest component tests, `pnpm typecheck`, `pnpm build` only after source-level gates |

## Release gate

Run the compact gate only in an isolated test data root. It verifies settings restart/update/corruption behavior; tombstones; contract/path uniqueness; topic/script measurement; voice artifact mapping; V2 cover payload and file validation; FAST NEWS MONTAGE artifact/duration/benchmark; preserved SEO/tags; publication idempotency; unrelated-worker isolation; and real UI status transitions. External services are reported only as PASS, FAIL, NOT VERIFIED or REAL USER ACTION REQUIRED.

For legacy production-write isolation, additionally run `scriptor.test_config.SchemaVersionSafetyTests`, `tests.test_cover_queue_tombstones`, `scriptor.test_cover_library`, `tests.test_covers`, `pnpm typecheck` and the current-core freshness guard. These tests always run through `tests/run_isolated.py`; no provider request or production storage is permitted.
