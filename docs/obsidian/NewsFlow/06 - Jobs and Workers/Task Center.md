# Task Center

## Contract

The UI DTO is `QUEUED`, `RUNNING`, `PAUSED`, `RETRYING`, `READY`, `FAILED` or `CANCELLED` plus source, title, detail and optional progress. `buildTaskCenterEntries()` maps existing durable backend snapshots without writing data:

`scenario session → scenarios`, `cover_queue → covers`, `voice task snapshot → voiceItems`, `montage_task_statuses → montageTasks`, `Publication V2 execution snapshot → publication.v2.queue`.

The center exposes active/failed rows and ready count. It leaves provider, worker, retry and artifact ownership with the existing canonical feature modules.

## Isolation evidence

Current targeted regressions cover bounded scenario workers, independent cover worker pool, WProject neighbor-failure isolation, montage worker limits/stale-state protection and Publication V2 lease/concurrency handling. Cross-pool live contention remains **NOT VERIFIED** because no production worker or external provider was started.
