# Issue #390 — invalid footage/proxy quarantine

Base: `8eabe4321d16c95c561f2ce921f2d415470bba7b`.
Branch: `fix/issue-390-media-quarantine`.

## Root cause and bounded fix

Two failed Montage jobs reused the same truncated full-source proxy. Its large
size satisfied the old presence/size-only cache gate, but its MP4 had no readable
video (`moov atom not found`). The original remained readable at both offsets.

- Shared identity-scoped media health storage is separate from the embedding DB:
  validation writes do not invalidate the large semantic search matrix.
- Definite unreadable/no-video originals are logically quarantined, never moved
  or rewritten. Selection excludes them even from a previously loaded corpus.
  A changed/repaired identity is revalidated and can return under the same path.
- Managed bad proxies move under the existing per-proxy lock to unique,
  recoverable quarantine entries with hash, reason and source identity metadata.
  A stale verdict, symlink, non-managed path or original-as-cache is not moved.
- A healthy original replaces an unusable full-source cache at render-time;
  validation is on demand even with no prior indexing. Warm-up and fragment
  publication validate partial output before atomic replacement.
- Permission/sharing/offline/timeout/resource errors remain retryable and are
  not persisted as corruption. Original changes during key creation/encoding
  prevent publication under an obsolete cache identity.
- Unchanged index scans read health identities in one batch, with no new
  decoding, embeddings or encoding. UI quarantine counters/reasons remain
  separate from OCR/Latin-text exclusion and preserve old snapshots.

## RED → GREEN and independent review corrections

Initial regressions reproduced large invalid cache reuse, invalid publication,
missing logical quarantine and missing no-index validation. Existing fake-byte
"MP4" render fixtures were replaced with real tiny H.264 media, not an exception
to validation.

Independent review found and subsequent failing regressions proved:

1. Low-FPS and longer-audio tracks falsely failed the endpoint seek. Validation
   now uses frame-aware video duration, per-video (not audio) duration metadata,
   plus bounded video-only windows when optional tags/frame counts are unreliable.
   The fallback has a shared 12-second budget, at most twelve 2-second windows,
   at most 240 frames/window. Uncertainty is retryable, never permanent quarantine.
2. Incremental scans opened the health database twice per healthy file. A real
   100-file regression measured 200 opens before the fix and one batch read after.
3. A repaired cache could be moved using an obsolete corruption verdict. The
   validated size/mtime identity is now carried into relocation and checked.

Additional regressions cover concurrent cache lookup (one quarantine), valid
cache reuse without decoding/encoding, short readable cache fallback, transient
cache unavailability, manifest hash/source identity, repaired source eligibility
and stale search corpus exclusion. Real MP4, MKV, WebM, 1/2-FPS and unequal
audio/video durations are exercised, including removal of optional video tags.

## Verification

All Python media tests use `tests/run_isolated.py`, disposable synthetic media
and storage. The wrapper reported `PRODUCTION_WRITE_GUARD=PASS`.

- Relevant Python command:
  `python tests/run_isolated.py tests.test_ai_index tests.test_montage_queue tests.test_montage_index_integrity scriptor.test_montage_render scriptor.test_command_contract -q`
  — **224/224 PASS**, 96.452 seconds on Windows, no skips.
- Additional real bridge snapshot integration regression — **1/1 PASS**:
  persisted quarantine count/path/reason and separate OCR counter, no source move.
- Native synthetic FFmpeg output/audio and GPU/NVENC mixed-SAR/1080p/30fps
  smokes are included in the passing Montage suite (not skipped on this host).
- UI: `pnpm exec vitest run --maxWorkers=1` — **400/400 PASS**, 55 files.
- Targeted Footage/Montage UI: **39/39 PASS**.
- `pnpm typecheck`, `pnpm build` — PASS.
- `pnpm verify:security`, `pnpm verify:secrets`, `pnpm verify:dependencies` — PASS.
- Montage UI, Remotion runtime and native-assets contracts — PASS.
- Ruff on changed Python files and `git diff --check` — PASS.
- Independent read-only review: all Critical/Important findings closed after
  RED/GREEN fixes; focused verification repeated by the reviewer.

One initial UI invocation forwarded `--` through pnpm, unintentionally starting
the full suite with default parallelism and exhausting Windows commit memory.
That run also disrupted concurrent synthetic FFmpeg tests. Full UI was rerun
with one worker, and the affected Python checks were rerun successfully. A short
fixture duration argument was corrected from `.3` to FFmpeg's accepted `0.3`.
No test assertion, guard or tolerance was weakened.

## Frozen/release boundary

The new `scriptor/media_health.py` is included in required Frozen provenance,
with a RED/GREEN executable guard regression for a changed validator. The r46
lock/package/artifacts are deliberately untouched: the old Frozen is stale and
the repository runtime guard must fail until a separately authorized rebuild.
`tests.test_core_runtime_guard`: **10/11 PASS**, the one repository-binding
failure is expected; `pnpm verify:core-runtime` also fails closed for the missing
new module identity. Neither failure is reported as PASS or bypassed.
This is source verification, not release acceptance. No Core/EXE was rebuilt,
no merge performed, and no provider/OAuth/paid calls were made.

Pause/renderer ownership changes are separate issue #391, not part of this fix.
