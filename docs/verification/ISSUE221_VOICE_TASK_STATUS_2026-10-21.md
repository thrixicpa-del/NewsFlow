# Issue 221: preserve voice state in concurrent task display

Focused follow-up to #221, base main `07ccdb40939131bce392fc8210b6a95a7f0fdd30`.

## Defect

`bridge.snapshot()` exposes `voiceItems.state` as the source scenario's state.
For legacy/imported rows without a TTS job snapshot, Task Center used that field
before `voiceStatus`. A ready script therefore made waiting, active or failed
voice work appear READY; Task Center then hid the voice entry from active work.

The voice projection now uses voice errors, canonical TTS state and voice-specific
progress labels. A persisted audio path supplies the fallback READY state;
script readiness never determines voice readiness. Provider preparation and
execution labels are handled locally to voice; other workflow mappings are
unchanged. No queues, storage schema, IPC actions or provider behavior changed.

## Verification

- RED: six real backend-shape status cases and one rendered concurrent
  voice/montage case FAIL before the fix; three existing cases PASS.
- Targeted Task Center/voice suites: **36 PASS**, 2.66 s.
- Full UI regression: **523 PASS**, 66 files, 17.14 s.
- Typecheck, UI security, source web build and diff whitespace: **PASS**.
- Existing isolated voice+template concurrency and multiprocess montage owner
  protection: **4 PASS**, 1.776 s, `PRODUCTION_WRITE_GUARD=PASS`:

```powershell
python -B tests/run_isolated.py tests.test_voicer.VoicerTests.test_template_save_survives_an_independent_running_voice_job tests.test_montage_queue_lock -q
```

No extra media rendering, paid provider calls, user-data changes, Frozen or EXE
build. Media/migration/packaging checks are N/A to this pure UI state projection;
existing independent CI and Windows-native gates remain required before merge.
Exact-head review/CI and post-merge results are recorded in the PR.

## Remaining issue scope

This fixes one concrete concurrency-display defect. It does not close #221 or
claim a new general serialization policy across all conflicting workflows.
Remaining conflict/waiting UX acceptance stays explicitly open. The existing
old Frozen binding FAIL remains owner-deferred; no release-ready claim.
