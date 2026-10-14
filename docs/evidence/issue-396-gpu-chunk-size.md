# Issue #396 — manual GPU timeline block size

Issue: https://github.com/thrixicpa-del/NewsFlow/issues/396

Base: `b3eb665298fa5f372687e1a86d5710a942786cd3` (`origin/main`). Branch: `feat/gpu-chunk-size`.

## Approved scope and implementation

Montage → Configure montage → GPU timeline now exposes **Футажей в блоке**, a manual positive-integer input with 12/24 shortcuts. Existing profiles default to 12. Values such as 7, 24, 37 or 100 are not restricted to presets; the technical limit is JavaScript's maximum exactly representable integer, not an artificial footage cap. Larger blocks increase decoder/filter memory demand and do not guarantee faster rendering.

The field flows through the existing settings command and snapshot as `gpuChunkSize`, persists as `montage_gpu_chunk_size`, and reaches `render_project(..., gpu_chunk_size=...)` in both queue and saved-project paths. GPU rendering partitions the existing ordered/trimmed sequence using the captured value. The final remainder is retained. No footage selection, planning, proxy caching, worker-count, audio, FFmpeg, Remotion or DaVinci policy changes.

Invalid/empty/fractional/boolean/non-positive/unsafe-integer values fail before settings are committed. Invalid hidden GPU drafts do not block saving another renderer and are omitted from that payload. Open Sheet drafts survive background refresh. Saved values survive stale progress/project writes using the existing preference ownership mechanism. A running queue keeps its captured settings; save before the next queue/render invocation to apply a new size.

## Regression-first evidence

- Initial RED: settings suite reproduced the missing default, ignored validation and missing saved-project forwarding (10 failure records across 3 new methods); the GPU partition test rejected the missing public keyword for 24/7/100; UI had 5 failing cases because no control existed.
- GREEN: persistence/invalid atomicity, old-profile compatibility, stale-writer protection, queue forwarding, saved-project forwarding, default `[12,12,1]`, custom `[24,1]`, `[7,7,7,4]`, `[25]`, ordering and remainder.
- Independent review found invalid GPU drafts also blocked FFmpeg/Remotion. Two renderer-switch regressions were RED, then GREEN after active-mode validation/payload scoping.
- Real Electron smoke exposed narrow-window clipping: at 390px the input was 405px wide and ended at x455. The configuration grid now uses an explicit shrinkable column and the new field has scoped sizing. Final input widths at viewport 1000/600/390 are 426/426/286; right edges are 964/546/336. Document and dialog widths do not overflow.

## Windows-native verification

```text
python tests/run_isolated.py tests.test_montage_queue scriptor.test_montage_render scriptor.test_config scriptor.test_command_contract -q
178/178 PASS; PRODUCTION_WRITE_GUARD=PASS (final run 83.654s)

python tests/run_isolated.py scriptor.test_montage_render.MontageRenderTests.test_gpu_timeline_renders_disposable_clips_as_1080p_30fps -q
PASS; real NVENC, two mixed-SAR synthetic clips, custom block size 1,
1080p/30 FPS, duration >=1.9s; PRODUCTION_WRITE_GUARD=PASS

node node_modules/vitest/vitest.mjs run src/ui/features/montage/montage-view.test.tsx --maxWorkers=1
35/35 PASS (disposable TEST storage)

# From studio-ui-remotion-verify; NEWSFLOW_TEST_MODE=1, ELECTRON_RUN_AS_NODE unset
node node_modules/electron/cli.js scripts/verify-gpu-chunk-control.mjs
SOURCE_ELECTRON_GPU_CONTROL_SMOKE=PASS
```

The durable Electron smoke uses a hidden development window, real React controls, a test-only allow-listed IPC adapter and the real source Python command/snapshot. It saves 37, reopens and verifies 37, checks 1000/600/390px layout, then enters 0 and verifies Save is disabled and persisted 37 remains unchanged. It does not launch Montage or a provider. Evidence JSON is written under ignored `.artifacts/gpu-chunk-control/`; profile data is in a fresh disposable `D:/NewsFlow-RC/qa-gpu-block-*` root.

During smoke harness development, isolation correctly rejected an initially incomplete environment before any settings write. The final harness explicitly identifies the real production LOCALAPPDATA separately from disposable LOCALAPPDATA. Harness-only ESM readiness/selector issues were also corrected; no application guard was bypassed.

Independent review confirmed the product fix and caught a smoke-harness port-ownership weakness. The durable harness now requires readiness from its own Vite child's output, fails on child exit/error/timeout, and cannot accept another checkout on the same port. A separate occupied-port experiment returned `OCCUPIED_PORT_REJECT=PASS` (smoke exited nonzero, no success marker). The corrected normal smoke passed again. Source/CSS review has no remaining actionable product findings.

```text
python -m ruff check scriptor/config.py scriptor/bridge.py scriptor/timeline.py scriptor/test_montage_render.py tests/test_montage_queue.py
PASS
pnpm typecheck
PASS
pnpm verify:montage-ui
PASS
pnpm verify:security
PASS
python scripts/secret-scan.py
PASS
pnpm build
PASS (web + Electron source + Remotion; existing >500KB Vite warning unchanged)
git diff --check
PASS
```

No dependency changes. Full-project/visual-baseline/packaged release acceptance is not claimed; relevant UI and source Electron layout behavior were checked directly. Independent CI is separate from these local results.

## Frozen/runtime boundary

`tests.test_core_runtime_guard`: **10 PASS / 1 FAIL**, repository binding stale. The accepted base already has `scriptor/media_health.py` absent from the existing r46 lock; this task additionally changes tracked bridge/config/timeline source. Lock/hash/provenance/package binding was not altered to conceal staleness. This is a source-only PR, not a release-ready or packaged-runtime claim. The user's current rc241 does not contain this feature. A separate immutable Frozen + EXE build is required after acceptance.

```text
PAID_CALLS=0
FROZEN_REBUILT=NO
TEST_EXE_BUILT=NO
USER_PROFILE_CHANGED_BY_TESTS=NO
```
