# Issue417 — manual footage blocks and explicit montage activation

Branch: `codex/footage-blocks`, based on43eb9998802dff1018d17fbe92a73dedf42b2aa1.
Separate stacked PR targets `codex/montage-stock-sources` (PR415), not main.
Approved requirements: ../superpowers/specs/2026-10-21-footage-blocks-design.md.
No merge, issue closure, Frozen/EXE build or lock rewrite.

## Delivered behavior

«Футажи / Индекс» contains manual named blocks, root-folder selection, cached
video count, rename/root editing and removal of the registry entry only.
Subfolders participate; canonical paths escaping the root are rejected.
Snapshots do not rescan27k files. Creation/import never enables montage mode.

TXT alternates paragraphs: topic, blank line, block name, blank line, next
topic/block. UTF-8/BOM/CRLF and multiple separators work. Native file selection
uses strict decoding and no arbitrary prompt-file1MiB cap. A preview shows
Product ID/name/root; its durable token protects exact new native IDs, topic
row order/content, block edits and production-generation changes. Validation
is atomic and repeated imports are idempotent. Existing IDs remain; new topics
use the current native ProductionItem path. Ambiguous titles fail explicitly.

Each topic has manual block editing by Product ID. Individual choices survive
restart, sorting and stale worker writes; conflicting reimport requires explicit
confirmation. Rename preserves block ID and bindings. Removing a block leaves
its old bindings visibly unavailable instead of silently selecting another.

In montage settings, «Использовать блоки футажей при монтаже» defaults off.
Off retains normal configured local/hybrid/stock selection. On uses only the
assigned curated root, in randomized history-aware order. Missing assignment
is explicit. No second Story Map, provider/download call or global search is
introduced. The existing native beat list/voice IDs/timing remain authoritative.

The selector checks only candidates it needs, memoizing screen/health verdicts.
An actual100-file/3-beat regression proves it does not probe all100 files.
Family/window/position history and in-batch coordination favor varied choices;
the existing uniqueness slider controls reuse. Shortages use permitted still
holds/neutral background, never an unrelated directory. Holds do not invent
unique footage or selected-source seconds. Saved seed/order/clips and root
policy make repeat export stable. Already-started jobs retain their snapshot;
pending preparations see current assignments. Product-ID filenames prevent
same-title output collisions. Saved-plan repair remains within its saved root.

Reusable block originals are protected from production cleanup, including when
their roots overlap generated/output folders. Commands share the production
reset fence. Reset removes per-production assignments but keeps reusable blocks.

## Defects reproduced and fixed

- Missing block persistence and stale-writer ownership; actual RED storage and
  manual-conflict/schema tests precede fixes.
- Old ID-less topics were appended again during preview commit: RED2!=1;
  migrate the existing row once. A later reorder/content change invalidates
  its preview before positional migration; separate RED/atomic GREEN.
- Production cleanup omitted manual block roots, and commands could read
  production during reset: actual preflight assertion and cross-process fence
  REDs; block-root protection and ordered shared fence fix both.
- A private in-flight block snapshot could carry another Product ID: real
  preparation RED, then reject it before using the snapshot.
- React stopped polling when the owner probe became false before its final
  task snapshot arrived, leaving42% after MP4 completion. Real UI FAIL plus
  deterministic RED; observe current-session unfinished tasks until terminal,
  retaining live-owner launch guards and ignoring abandoned previous sessions.
- Independent inspection of actual UI outputs found video177frames/5.9s while
  sound continued6s. Focused no-hold block regression89!=90 confirmed copied
  `-shortest` mux loss. Block projects now use the existing exact proxy budgets
  and narration-bounded CFR mux even without shortage holds. Ordinary off-mode
  stream-copy behavior stays unchanged. Both saved plans were re-exported
  through real preload/Electron/Python without new selection; see media below.

## Executed verification

Results below separate functional success from the outer integrity gate.
Counts overlap and are not summed as unique tests.

- Broad backend/media/queue/VoiceMap/security set:280tests PASS243.642s,
  guardFAIL/exit91; this began before final identity/tail follow-ups.
- Final new domain/selection/pipeline/media set:
  `python -B tests/run_isolated.py --pytest tests/test_footage_blocks.py tests/test_montage_blocks.py tests/test_footage_block_pipeline.py tests/test_footage_block_media.py -q`
  →70PASS33.81s, guardFAIL/exit91, four-core/4GiB launcher.
- Tail/MP3/GPU/timeline follow-up:19PASS17.285s, guardFAIL; final canonical
  command contract:15PASS24.559s, guardFAIL. Pipeline/reset follow-up23PASS.
- Full Vitest after polling fix:445tests/60files PASS60.18s in a four-core/4GiB job (peak1819963392bytes). A separate observation run outside that job is not the resource-bound receipt. Source web/desktop/
  Remotion build, typecheck and security PASS; Ruff, secrets, whitespace and
  both workflow YAML syntax checks PASS. No new dependencies.
- Broad gate job peak1277939712bytes, four CPU affinity/4GiB total job cap.
- Real isolated Electron journey:1functional PASS72.37s, guardFAIL/exit91.
  Actual DOM controls, native chooser responses, renderer→preload→trusted IPC→
  Python→storage, manual cancel/change/conflict, off/on fresh-process
  persistence, normal16:9 queue and explicit9:16 repeat all checked. The
  corrected harness forbids activating controls behind a dialog and requires
  actual React «Готово» before accepting completion.
- After tail fix, saved-plan real preload exports:1functional PASS18.58s,
  guardFAIL. Original failed MP4s/plans remain byte-identical, and new plans
  retain clips/source policy/aspects. This is labeled transport-driven export,
  not a nonexistent direct-export UI button.

Final private profile:
`.superpowers/footage-blocks/ui-runtime/a98d84b226e444c2b54f7539e01bed69`.
Independent FFmpeg9/FFprobe receipt and contact sheets:
`artifacts/after-tail-fix/independent-postflight/`.

| Output | Pixels | Video | Decoded sound at24kHz | Correlation | SHA256 |
| --- | --- | --- | --- | --- | --- |
| landscape |1920x1080|180frames/CFR30/6.0s|144000samples/6.0s|0.9999991104|df96d95c636bda53087948520882131bef57c235473bbb6a8c9a89d6deb6234c|
| portrait |1080x1920|180frames/CFR30/6.0s|144000samples/6.0s|0.9999991104|8284b67e0aaabf9102b25f688bc2d40ba94228c67c4f22e05436e5e340615ebd|

Maximum decoded frame interval0.033334s. Beginning/middle/end sound correlations
pass without shifting or dropping samples; interior/terminal color frames match
only assigned blockB (green/blue), never blockA or unused global black/white.
All five fixture originals retain their SHA. Native VoiceMap legitimately
coalesces two3s segments into one6s visual beat with segment IDs[1,2]; the test
does not force a new map. Separate selection tests cover multi-beat diversity.

## Preserved failures and limits

The media are explicitly SYNTHETIC solid colors plus sine sound, proving folder
routing, storage, UI and encoding. They are not real Aliyev/Armenia/protest or
real speech quality acceptance. Curated block content is operator-provided;
this mode deliberately randomizes that prepared collection rather than
performing ordinary semantic search again. Actual NVENC/Remotion block render
and a12-planner/4-render load run are NOT RUN; existing contracts/regressions
are preserved. No new real-source analyses or downloads.

Every failing attempt is retained: initial too-short4s fixture honestly produced
neutral background for the native6s beat; an observer initially could click
behind the settings sheet; strict corrected observer then exposed polling FAIL;
original177-frame outputs and tail RED remain. An initial media test launch
accidentally collected imported unrelated render cases; its owned process was
stopped and the exact intended test rerun, preserving its89!=90 RED. Initial
four media errors and one UI-baseline failure were missing LFS checkout assets:
only matching-OID approved FFmpeg/PNG bytes were hydrated, without changing
baselines/assertions; tracked pointer contents are restored after verification.

Working settings.json changes during tests: required production-write guard
remains FAIL; writer UNKNOWN, working NewsFlow processes untouched. No working
settings/media/session/credentials are intentionally changed or restored to
manufacture PASS. Parent Frozen/source-lock FAIL remains, no lock waiver or
build. Docker BLOCKED: missing Desktop Linux engine pipe. Fresh PR CI and
Windows-native results must be inspected separately; pending is not PASS.

All known test roots, including this entire worktree .superpowers and previous
roots/junction targets counted once:18.1901GiB/24GiB,5.8099GiB spare at final
inventory; originals and failed evidence were not deleted. Independent scoped
review found the reset/legacy issues above; fixes and final timing/CI changes
were reviewed. The final source change is not an all-green release declaration.
