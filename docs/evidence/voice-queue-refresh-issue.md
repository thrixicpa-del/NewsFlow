Issue: https://github.com/thrixicpa-del/NewsFlow/issues/369

Voice queue stops displaying progress and completed MP3 while WProject continues working.

Acceptance:
- Opening/reopening the Voice queue refreshes existing work without submitting a generation command.
- Slow snapshots do not cause overlapping periodic reads.
- New MP3/status/progress appear from authoritative snapshots; selection remains usable with 84 topics.
- Polling recovers after read errors and stops on unmount.
- No changes to Core, providers, queue persistence, settings or user files.

Root cause: VoiceQueue polls only while its local `generating` flag is true. Leaving the workspace loses that flag despite the still-running external worker. The existing 900 ms interval can also overlap slow snapshot requests (observed snapshot duration about 0.8–1 s). Window responding and worker activity alone do not prove renderer CPU overload; the missing polling lifecycle is reproduced independently.

Implementation: observe the nonempty queue while its workspace is mounted; schedule the next read 3 seconds after completion; stop the timer on unmount; retain the latest callback without restarting the timer on snapshots. App shares an outstanding refresh across workspace navigation/manual refreshes, releasing it after success/error.

RED: four VoiceQueue regressions failed because no background read occurred; App navigation regression failed with three snapshot calls instead of startup plus one outstanding read.

GREEN: targeted Voice UI 25/25; full UI 374/374 (52 files); typecheck; production build; security; secrets; release lint; diff check. Core runtime guard tests 10/10 passed. Core source/bindings remain unchanged (r42).

Windows Electron smoke against the built renderer and synthetic 84-topic snapshot: PASS. Reopening queue shows completed MP3, maximum concurrent snapshots = 1, total snapshots = 2 (startup plus slow refresh), selecting topic 84 while snapshot is pending took 35 ms. Provider commands = 0. No application worker or real provider was launched by smoke. Disposable Electron userData, with network disabled.

Production-integrity caveat: the live profile hash guard detected settings.json changing while the user's existing WProject worker was running. This observation cannot attribute writes to tests and is not reported as a clean live-profile guard. The live worker/settings were not stopped or restored. Repeat tests with the standard isolated CI storage boundary; keep this separate from live-profile acceptance.
