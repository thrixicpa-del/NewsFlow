# Issue 221: voice queue ownership without a global workflow lock

Base: main `c6e0c07aa0047a307e9f7708e0c4f1bd9f6d09d5`.
Companion: PR #428 / `ISSUE221_VOICE_TASK_STATUS_2026-10-21.md`.

## Root cause and behavior

Electron launches separate Core processes for commands. Voice generation had no
cross-process owner before preparing or persisting queue state. A second launch
could submit the same paid request and overwrite voice state from a stale copy.
The renderer's local pending flag cannot protect another window or process.

All three public launch commands (`generate-voice`, `generate-voice-queue`,
`generate-voice-range`) now acquire one nonblocking OS file lock before reading
or mutating their queue. The existing parallel provider workers remain inside
that owner: this does not reduce the configured within-queue concurrency.
Conflicting launches return an explicit Russian reason to wait for the current
queue; the UI displays that reason and permits a later retry. They are rejected
before a second provider request, rather than silently queued for later billing.

The lock is separate from the settings write mutex, so template/preset editing
remains available. Its stable file is never unlinked. Closing the handle releases
ownership after success, exception or process death; recovery does not depend on
PID polling or deleting a stale lock file. Unexpected lock I/O errors propagate.
Internal helpers avoid recursively acquiring the public command lock.

Review also reproduced a lost-update window after the progress worker reloaded
settings but before it acquired the write mutex: an intervening template save
was replaced by the worker's stale template. In the opposite ordering a template
save could clear a newly changed voice pause flag. Settings now remember the
loaded values of the voice and template/preset fields. Under the existing write
mutex, unchanged fields retain the current disk value; intentional edits still
apply. A deep baseline handles nested job/preset objects and repeated progress
publications. This keeps the lock limited to a normal settings write.

## Evidence before push

- RED: the strengthened active-VoiceGen/template regression failed because a
  competing launch did not raise and could invoke the provider a second time.
- GREEN: all three launch methods reject while synthesis is pending, provider
  call count remains one, template saves before voice finishes, and the final
  voice state retains the new template.
- Two additional real-file regressions first failed for both interleavings:
  stale voice progress overwrote the new template/preset, and stale template
  saving cleared the new pause flag. They also cover repeated publications and
  preservation of the running job state. Independent reviewer replay: **2 PASS**,
  `PRODUCTION_WRITE_GUARD=PASS`; the original blocking finding is resolved.
- Real Windows spawned-process test: another process cannot acquire ownership;
  a real settings file accepts and retains the independent template; terminating
  the owned child releases the lock immediately. Separate exception recovery
  also passes. These three focused regressions: **3 PASS, 2.638 s**.
- Related backend/contract/security regression: **96 PASS, 10.457 s** using
  `tests/run_isolated.py`, `PRODUCTION_WRITE_GUARD=PASS`:

```powershell
python -B tests/run_isolated.py tests.test_voicer tests.test_tts_ranges tests.test_voice_queue_owner tests.test_runtime_action_map tests.test_electron_security tests.test_secret_scan -q
```

- After the persistence fix, complete voice/range/map, settings read/write race
  and session regression: **583 PASS, 110.735 s**,
  `PRODUCTION_WRITE_GUARD=PASS`:

```powershell
python -B tests/run_isolated.py tests.test_voice_queue_owner tests.test_voicer tests.test_tts_ranges tests.test_voice_map tests.test_settings_read_race tests.test_session -q
```

- Two App integration tests exercise a busy IPC rejection with the Electron
  error prefix and a template save while voice remains pending, retaining both
  final results. IPC is mocked in those UI tests; the OS/process/settings tests
  above are real. No paid-provider end-to-end run is claimed.
- Full UI regression: **525 PASS, 67 files, 16.17 s**.
- Ruff on changed Python files, workflow YAML parsing, diff whitespace,
  typecheck, UI security, web and Electron source builds: **PASS**.
- Linux CI includes the owner suite; Windows-native CI explicitly runs the real
  ownership/crash/template cases before its existing source Electron gates.
  Exact-head CI/review and post-merge results are recorded in the PR/issue.

During test development, an owned-process fixture initially waited on an event
after killing its waiter; that test harness hung and was corrected to terminate
only the owned child without reusing its synchronization object. An initial UI
test clicked an already-open navigation group closed; its setup was corrected.
Neither failed attempt is counted as successful product evidence.

## Scope and acceptance boundary

Combined with PR #428, evidence covers independent voice/template operations,
conflicting voice starts, visible waiting/error/retry, concurrent task status,
preserved settings and crash recovery. Existing montage ownership remains
separate. This adds no universal scheduler or automatic deferred retry.

No media algorithm, storage schema, migration, packaging or runtime binding
changes: extra rendering/migration/release checks are N/A to this source fix.
Tests use disposable storage only. Frozen/EXE is explicitly owner-deferred;
the known old Frozen binding guard failure is not a PASS or a release waiver.
Hosted checks that skip must be reported as SKIP, not green evidence.
