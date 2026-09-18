# Voice — Functional Acceptance Log

## VOICE-001 — explicit Voice All and bounded scenario-level concurrency

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### Operator contract and implemented UI fix

The operator requires one unambiguous idle action, `Озвучить всё`. It sends the existing exact command `generate-voice-queue` with `{}`. Source had a queue-wide action, but the operator reported it absent in the current build; the source/DEV contract now exposes the exact required idle label. Packaged EXE visibility remains deferred to the next packaged checkpoint.

All Voice generation actions share one synchronous `voiceGenerationLock`; while a request is pending, conflicting selected, queue-wide, revoice, and resume actions cannot start another request. `Переозвучить все` remains a distinct force/regeneration action.

### Parallelism contract

Saving Voice Profiles with `Одновременных TTS-задач = 10` persists `queueConcurrency: 10` together with the active profiles, ranges, and default profile. The UI explains the real limit: effective concurrency is `min(global queue limit, provider slots, eligible jobs)`.

Deterministic no-network WProject fakes measured real scenario-level work:

- global limit 10 / provider streams 10: `max_active = 10`;
- global limit 10 / provider streams 3: `max_active = 3`.

Chrome remains intentionally limited to one browser stream.

### Local recovery and GREEN evidence — 18 September 2026

The temporary backend test blocker was a dehydrated Git LFS pointer at `assets/ffmpeg.exe` (133 bytes), not a Voice runtime regression. Hydrating only that tracked LFS asset restored the expected 87,638,016-byte executable and successful `ffmpeg -version`; it was not staged as a source change.

- Legacy FFmpeg-backed audio validations: PASS — 2 tests after LFS hydration.
- Full backend Voice suite: PASS — 32 tests.
- Targeted Voice UI: PASS — 1 file / 12 tests.
- Full frontend suite: PASS — 34 files / 174 tests.
- `pnpm typecheck`: PASS.
- Production integrity/write guard, secret scan, Ruff test-file check, and `git diff --check`: PASS.
- No real, network, or paid provider calls were made; no production data was touched.
