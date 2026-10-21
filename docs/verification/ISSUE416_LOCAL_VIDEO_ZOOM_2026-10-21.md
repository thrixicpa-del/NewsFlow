# Issue 416: optional local video zoom

Source issue: https://github.com/thrixicpa-del/NewsFlow/issues/416

Base: `ae845075382b588513b2cb6f2b97de6d56086410`. Dedicated branch:
`codex/local-video-zoom-integration`. Owner subsequently authorized source merge
and explicitly deferred Frozen/EXE. No packaging, Frozen build or lock update.

## Cause and scope

Main had no local-video zoom setting or renderer contract. An unfinished draft
in the older `codex/local-video-zoom` worktree was inspected and ported to current
main; that worktree and its FFmpeg binary were not modified/copied wholesale.
Current frame-grid proxy identity and block/overlay integration are preserved.

- Off by default; settings and project persist the flag. Stale progress writers
  cannot revert the operator's preference.
- Central 100 to 108% zoom through the selected local scene, no frame duplication
  or playback-rate change. Stock/photo material, intro and continuity are excluded.
- Off retains the exact existing FFmpeg proxy key and filter path. On adds a
  versioned cache discriminator only to affected local clips.
- FFmpeg, direct-source GPU timeline and Remotion consume the same project choice.
  Remotion's pre-existing OFF animation is preserved; ON applies one transform.
- A separate UI export action sends `renderOnly: true` and an explicit effect
  choice. Saved clips, trims and selection remain unchanged. Re-export without
  an explicit effect override preserves the project's choice, independently of
  the global preference. New queues capture their initial choice.
- DaVinci XML still references editable original footage without baking this
  effect; the UI states this limitation. MP4 receives the effect.

## Regression and review

Initial five targeted regressions: **3 FAIL, 2 ERROR** before implementation,
then **5 PASS**. Errors were the absent new renderer keywords, not setup failures.
Independent read-only review found decorated legacy source labels such as
`local · RELAXED_SEMANTIC` were initially excluded. Added regression: **2 FAIL**
before normalizing the source prefix; fixed without admitting stock/continuity
or ambiguous prefixes. Reviewer confirmed **0 remaining actionable findings**.

Additional tests exercise explicit ON, omitted override, explicit OFF re-exports
with selectors/repair/tail planning forbidden, and the actual UI export payload.

## Source and runtime evidence

- Related backend regression: **209 PASS**, 87.781 s,
  `PRODUCTION_WRITE_GUARD=PASS`:

```powershell
python -B tests/run_isolated.py tests.test_local_video_zoom tests.test_timeline tests.test_montage_queue tests.test_montage_blocks tests.test_overlay_persistence tests.test_overlay_remotion_contract tests.test_overlay_timing tests.test_montage_continuity tests.test_runtime_action_map tests.test_electron_security tests.test_secret_scan -q
```

- First Linux CI stopped in the existing GPU chunk test double: its old
  signature rejected the new keyword (`6 PASS / 1 ERROR`). Reproduced locally
  before changing only that helper to accept and assert the project's choice.
  Complete `python -B tests/run_isolated.py scriptor.test_montage_render -q`:
  **33 PASS**, 32.066 s, production guard **PASS**. Production implementation
  unchanged by this follow-up; exact-head independent gates rerun after push.

- Montage UI: **106 PASS**, eight files, 6.59 s.
- `pnpm typecheck`, `pnpm verify:security`, source `pnpm build`: **PASS**.
- Ruff on all seven changed Python files, workflow YAML parse and diff whitespace:
  **PASS**. No dependency/lock changes.
- Real isolated Electron -> trusted IPC -> Python -> settings -> process restart:
  **PASS**, 14.617 s. Zoom off default and visible/persisted ON checked alongside
  the existing stock controls; no external requests or unexpected commands.
  Evidence: `.superpowers/stock-sources/electron/829ef5fa9d974d019ac17184f5fb6cd9`.
- Real media: four 2.4-second synthetic MP4 comparisons per renderer, ON/OFF in
  16:9 and 9:16. All **12 outputs PASS**. Check exact 72 video frames, HD size,
  moving source time, measured object growth, voiced tail, absence of original
  source audio and unchanged original SHA256. Synthetic visuals/audio use actual
  production renderers, not mocked FFmpeg, GPU or Remotion.

| Renderer | Evidence directory under `.superpowers/local-video-zoom/media/` | Time |
| --- | --- | --- |
| FFmpeg | `2da91c992eb2499bbe68249a0cf40c1f` | 18.677 s |
| GPU timeline / actual NVENC | `9174ef33177641d088d4d500277799f2` | 14.165 s |
| Remotion / actual Chromium | `9270ae96c748407086b51bfd9756da82` | 33.020 s |

Remotion's first comparison failed the original strict audio-container tolerance:
both ON and OFF append 53 ms of AAC padding. Video remains exactly 72 frames and
the voiced tail is intact. The check now allows up to three AAC packets while
still verifying video duration, voice frequency/tail and no source audio. OFF
also intentionally retains Remotion's old slight zoom-out. These are documented
baseline behaviors, not changes to production audio/timing code.

The first hosted Windows comparison also exposed an overly narrow OFF marker
tolerance: 128 to 130 thresholded pixels (1.5625%) exceeded 1.5%. The comparison
now bounds OFF variation to two pixels, one per encoded edge; this is tighter
for the wider horizontal marker and remains below ON's minimum seven-pixel
growth. No production filter/cache code changed. Actual forced-CPU libx264
comparisons in both layouts: **4 outputs PASS**, 21.082 s, production guard PASS;
receipt `.superpowers/local-video-zoom/media/48c530d60e5d4469aac96c3e109d3cec`.
Independent review confirmed the revised measurement preserves effect/timing
coverage. Hosted step had 14 PASS, 1 FAIL, 1 existing profile-reuse SKIP; it is
not reported as PASS. Its actual zoom UI restart and six unit tests did pass.

## Independent gates and limits

CI runs the new unit/regression contract and complete existing source gates.
Windows native additionally runs actual checkbox/restart, FFmpeg comparisons and
the new actual Remotion comparison. Hosted GPU availability is not assumed;
actual local Windows NVENC comparison supplies that hardware evidence.
Final exact-head CI/Windows results, merge SHA and post-merge tests are recorded
in the PR/issue before closure.

Frozen binding remains the previously documented owner-deferred source/runtime
mismatch. It is not silently treated as PASS. This is source issue acceptance,
not a claim that the installed EXE or a release candidate includes the feature.
Paid provider and full production pipeline acceptance are N/A to this local
render effect. Packaging/clean-install acceptance remains deferred by the owner.
