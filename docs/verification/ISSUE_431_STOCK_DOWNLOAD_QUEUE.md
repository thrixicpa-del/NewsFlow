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
