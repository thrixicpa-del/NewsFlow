# Issue 431: configurable stock download queue

Stock selection used to download each candidate synchronously inside a planning
worker. A download semaphore limited work but could not keep a larger transfer
pool busy. Selection and downloading now overlap through one bounded queue shared
by all planners and stock repairs within the montage invocation.

The existing `downloadWorkers` setting controls simultaneous transfers; the UI
calls it **Одновременные скачивания**. There is no fixed 30-worker cap. A saved
change applies to the next montage launch. At most twice that number of unique
transfers are admitted at once, including running transfers. The rolling prefetch
window replenishes throughout candidate batches, including with a single planner.
Matching source/cache/provider/kind/asset identities share in-flight futures.

Search and download limits are separate. Provider JSON requests are limited to
three simultaneous requests per provider within the Core process. File transfers
use the operator's download limit. Cache, URL/SSRF, licensing, integrity, semantic,
HD, visual uniqueness and final candidate selection gates remain in effect.
Prefetch may cache candidates later rejected by visual checks; it does not make
them eligible for montage. Candidate order and selection ranking are preserved.

## Persistent timeline

`NewsFlow/stock-download-status.json` contains the latest run and
`NewsFlow/stock-download-status.jsonl` retains event history across launches.
They contain queued/active/ready/failed/cancelled counters, received bytes,
elapsed time, average bytes/second since launch, and cumulative worker seconds
for provider search and media preparation/scoring. Parallel worker seconds can
exceed elapsed wall time. Ready files include verified cache hits; ready does not
mean selected for montage. Only discovered/admitted files are counted: future
scenes do not imply a known number of downloads.

The UI displays the last 12 persisted events, including after restart. Full event
history remains on disk for throughput comparisons. It contains no URLs, keys,
raw provider asset identifiers or exception messages. Creation-time owner tokens
and exit-state checks distinguish source Python, Frozen, dead owners and reused
PIDs. Counters of a dead owner are labeled historical rather than live.

Transfers have thread-local pause/stop checkpoints. Shared control polling is
limited to four checks per second instead of parsing settings per chunk. Closing
the queue cancels pending work, interrupts paused/active transfers at checkpoints
and retains already published immutable originals. Existing HTTP timeouts bound
an in-flight socket read. A stopped queue does not automatically resume rendering;
the next launch reuses completed cache entries and repeats incomplete selection.

## Verification scope

- Windows-native isolated transfer/concurrency/cache tests; one planner filling
  multiple download slots; bounded backlog; duplicate in-flight identity; errors;
  pause/close; byte telemetry; later-wave refill; rejected metadata; real cache
  publication; thread-local checkpoint restoration; separate process reader;
  PID reuse and exited Windows owner with a retained process handle.
- The refill regression fails with refill disabled and passes with refill enabled.
  The retained-handle regression was reproduced RED and fixed GREEN.
- Relevant existing stock preparation/selection/source/settings/queue-lock checks.
- React settings and persisted timeline tests, TypeScript, web/Desktop source build.
- Real source Electron -> preload -> trusted IPC -> Python settings persistence and
  process restart, including the saved download timeline. Offline fixtures only.
- Scoped Windows CI workflow and independent code review. Full NewsFlow acceptance,
  provider throughput, Frozen rebuild, portable EXE and release gates are outside
  this source-feature task; do not describe the existing r51 EXE as containing it.

## Independent review, 2026-10-22

Reviewed PR #432 at `30a926828e04f211656242a184a9e6f0907ee26a`, stacked on
PR #430 at `ae95228f26539c70d2a2be053c93081bfecbbe7b`. The original scoped
[Windows CI run](https://github.com/thrixicpa-del/NewsFlow/actions/runs/39675997837)
was independently inspected: 92 Python regressions, 21 React tests and one real
source Electron/IPC/Python persistence/restart test passed. This evidence did
not cover the following independently reproduced defects, now corrected:

- A Windows reader holding the timeline status file could make `os.replace`
  fail. The exception could reject an admitted download, leave an active count,
  or turn a successful transfer into an error. Status publication now retries
  transient `PermissionError` for at most eight seconds. Permanent failures
  remain errors. Three deterministic queued/active/completed RED cases pass
  after the change; a native Windows sharing regression is also in scoped CI.
- Independent manual and queue preparation used the same temporary status
  filename. An overlapping writer could remove the other writer's staging file.
  A two-writer RED reproduction now passes with per-run temporary names and
  cleanup restricted to the writer's own file.
- Requests waiting for a provider API slot had already selected their key and
  checked cooldown. They could send a newly rejected key or ignore a newly
  recorded 429. HTTP failure state was also recorded after releasing the slot.
  Key/cooldown admission and failure-state publication now happen inside the
  slot. Three deterministic RED cases pass; interruption, missing credentials
  and closing HTTP error bodies remain covered. Transport is mocked and SQLite
  storage is disposable.
- The new `stock_downloads.py` module was missing from the Frozen verifier's
  mandatory source list. A changed queue module or missing identity was accepted
  by the isolated verifier fixture. Both RED cases now fail closed. The runtime
  verifier and its test fixture require the new module's identity.

Only focused local checks were run: five provider-admission regressions and
seven relevant existing provider tests; two cross-platform persistence tests;
nine existing queue cases; and two new Frozen-identity tests. The native Windows
reader test is intentionally skipped on Linux and is mandatory in the scoped
Windows workflow. One existing process-lifecycle test initially failed in a
Linux sandbox whose PID namespace did not match mounted `/proc`; only that test
was repeated outside the sandbox and passed. Production-write guards passed.
Results overlap and must not be summed into a full-suite claim. The new tests
are explicitly wired into the existing scoped Windows workflow.

The published r51 changes on the exact PR #430 base were separately reviewed:
both dependency locks, both package resource paths and all 27 source identities
are consistent; the twelve source/runtime-guard tests passed without skips.
The Windows binary/ZIP on the owner's D: drive was not independently accessible.
PR #432 changes `bridge.py`, `stock_selection.py`, `stock_sources.py`, and adds
`stock_downloads.py`; it therefore requires a new Frozen before packaging this
feature. The r51 lock and artifact assertions are deliberately preserved until
a genuine replacement is built. No main merge, provider run, production queue
restart, Frozen build or EXE packaging was performed during this review.

## Owner state preservation

Before implementation, the owner-authorized RC01 queue was paused through the
real Frozen settings command and its application closed. A complete profile copy
and a consistent stock-cache SQLite backup were saved outside the immutable EXE
artifact. Critical settings/session/library backup bytes matched the stopped
profile. Ninety tasks, their inputs and existing media remain; 11 assets were
cached (2 video, 9 image), and 78 tasks were waiting. No project had yet completed.
The old implementation had no pending-file queue and did not persist in-memory
partial scene selection, so neither an exact pending-file count nor that partial
selection can be recovered. No real queue was used in automated tests.
