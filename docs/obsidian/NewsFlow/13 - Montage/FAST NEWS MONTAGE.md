# FAST NEWS MONTAGE

## Active canonical path — 2026-09-11

`run-montage-queue` → `prepare_montage` → `TimelineProject` → direct FFmpeg proxy/cache renderer → final MP4 validation → `READY` task state.

- **Root cause fixed:** the saved default was Remotion. Electron always supplies a Remotion runner, so ordinary desktop queue renders took the browser compositor path despite the already-available fast FFmpeg cache/proxy pipeline. Unit tests running outside Electron did not expose this divergence because they had no runner and silently fell through to FFmpeg.
- **FAST NEWS default:** new settings use `ffmpeg`. An old `remotion` value without the new `montage_renderer_explicit` marker is treated as a former implicit default and projects to FFmpeg; explicit Remotion selection remains exactly preserved. No MP3, project, footage, cached proxy, output MP4 or queue record is moved or deleted.
- **No hidden renderer fallback:** explicit Remotion now returns a diagnostic error if its runner is unavailable; it cannot silently switch to FFmpeg. The user can explicitly select Remotion for composition/transitions.
- **Terminal validation:** a freshly rendered MP4 is checked once for readable video, audio, positive duration and duration coverage of the voice/intro before the queue records `Готово`. Lightweight header checks remain recovery-only so a large historical queue does not run a probe per dashboard row.
- **Synthetic benchmark:** `tests/test_montage_benchmark.py` uses generated 3-second source/audio media only, direct FFmpeg, a private temporary proxy cache, expected A/V output and a 20-second tolerance. The local baseline passed in about 4.1 seconds; it is a regression guard, not a hardware promise.

No version-136 files were needed: the current source directly showed the Electron-only Remotion route as the regression.

Regression evidence: `scriptor.test_montage_render`, `tests.test_montage_queue`, `tests.test_timeline`, `tests.test_montage_benchmark` — 85 passing tests in the focused montage gate.

## Regression repair — 2026-09-12

- The direct desktop render hand-off now imports `required_video_duration` explicitly before terminal MP4 validation. The missing import was a runtime-only `NameError` after a successful render.
- Cached duration lookup degrades safely to ffprobe when a lightweight/test index does not implement the optional cached-duration method.
- A Remotion manifest keeps every voice frame (`durationInFrames`) even when a legacy visual plan is shorter; the canonical FFmpeg preflight still rejects that visual gap before render, and `visualDurationInFrames` exposes it instead of truncating narration.
- Cover transport retry plans reuse the immutable builder-owned final provider prompt byte-for-byte. This preserves the single prompt authority required by Universal V2; no retry path may append a legacy tail.

Regression evidence: `scriptor.test_davinci`, `scriptor.test_cover_library`, `scriptor.test_montage_render` — 67 passing tests; full direct `scriptor` gate — 81 passing tests.

## Production-recovery validation — 2026-09-14

- **New-folder fallback fixed:** an empty optional AI index previously caused `prepare_montage()` to scan the chosen footage folders but then discard the scan. A bounded filename/tag fallback now feeds those local clips into the existing selector only while `indexed_count == 0`; indexed runs retain the current vector-search fast path.
- **Controlled packaged-path analogue:** current `run_montage_queue → prepare_montage → direct FFmpeg` executed on the isolated WProject MP3 and three disposable local clips. Result: 1 physical MP4, 186,189 bytes, `status=Готово`, FFmpeg renderer, elapsed 9.09 s. Voice duration was 7.58 s; final video duration 7.55 s (frame tolerance); saved timeline 7.663 s. Its only clip was the terminal clip, so the “trim only final footage” invariant held.
- Regression evidence: `test_prepare_montage_uses_local_scan_when_ai_index_is_empty` plus `tests/test_montage_queue.py` and `tests/test_timeline.py`: 67 passing tests in the focused targeted gate.
