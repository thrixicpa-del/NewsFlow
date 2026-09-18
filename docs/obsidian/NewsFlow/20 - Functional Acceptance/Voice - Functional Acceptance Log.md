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

## VOICE-002 — unsafe interrupted TTS resume requires explicit revoice

Status: **FIX VERIFIED LOCALLY; PENDING CI**

### Confirmed restart risk and implemented safety contract

An interrupted Secret Voicer API, Lumean, VoiceGen, or Chrome job could previously be converted back to `queued` and submitted again even when the first paid request might already have reached the provider. Automatic resume now uses the saved job provider and one central safety predicate instead of the later editable Voice profile.

- `queued` means the provider invocation is not known to have started and remains safe to start.
- Before any non-idempotent provider or browser invocation, NewsFlow persists `state=running` and the actual `active_provider`; the same transition is persisted before a cross-service fallback invocation.
- `running`, `interrupted`, and `retrying` work for Secret Voicer API, Lumean, VoiceGen, and Chrome is not automatically resubmitted. It remains `interrupted`, preserves its saved contract and remote metadata, and requires the operator to use `Переозвучить` explicitly.
- WProject durable resume remains supported: an existing `remote_task.task_id` is polled without a new create request, while a saved `provider_idempotency_key` is reused if the POST response/task ID was lost.
- Snapshot rows now expose saved `jobProvider` provenance and `resumeSafe`. `Продолжить очередь` includes only safe work, while unsafe rows show `Требуют явной переозвучки: N` and retain the existing explicit force-revoice action.

### Local GREEN evidence — 18 September 2026

- Confirmed RED: unsafe in-flight non-idempotent snapshots entered provider execution instead of returning safely; Chrome reached the fail-fast provider mock and the three API providers advanced to provider credential/client selection.
- Backend Voice suite: PASS — 58 tests.
- Unsafe resume provider-call count: 0 for Secret Voicer API, Lumean, VoiceGen, and Chrome.
- Queued VoiceGen resume provider-call count: 1.
- Persist-before-call regression: PASS — VoiceGen observed saved `running` / `active_provider=voicegen` before invocation.
- WProject remote-task resume: PASS — 0 create calls, 1 poll of the persisted task ID.
- WProject idempotency-key recovery: PASS — 1 create call with the exact persisted key, followed by polling the recovered task.
- Targeted Voice UI: PASS — 1 file / 16 tests.
- Full frontend suite: PASS — 34 files / 178 tests.
- `pnpm typecheck`: PASS.
- Production integrity/write guard, secret scan, Ruff Voice test-file checks, and `git diff --check`: PASS.
- No real, network, or paid provider calls were made; no production data was touched.
