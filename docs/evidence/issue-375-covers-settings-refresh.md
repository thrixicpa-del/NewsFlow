# Issue 375 — Covers settings access, durable refresh and identity

Repository: `thrixicpa-del/NewsFlow`.
Base: `ac06705d6ac8ccad9bdc363daef5678475d89b0e`.
Branch: `codex/issue-375-covers-settings-race`.
Date: 2026-10-09. Source fix only; no merge or packaged release.

## Evidence and failure boundaries

Read-only inspection of the existing rc238 TEST profile found 84 topics and
78 ready covers. All 78 recorded ready paths existed. Five other rows retained
accepted FastGen IDs requiring recovery; one row waited for quota. These six
rows were not falsely relabelled ready. The original operator's UI report is
not treated as proof that those six images exist.

The settings JSON was readable and valid during inspection. The failure class
was independently reproduced on Windows using synthetic JSON, ten readers and
one atomic-replacement writer: 1,576 committed replacements, 9,197 successful
reads, 149 PermissionError reads and 11 FileNotFoundError reads, with valid final
JSON. Previously these access failures were reported as corrupt JSON.

Covers and Gallery did not poll durable snapshots, and a rejected cover
command did not refresh already committed results. Reconciliation guessed file
ownership from queue position/title prefixes. Settings merge also used a
title/scenario key even when durable ProductionItem IDs were present.

## Fix

- Shared settings reader retries transient access/replacement errors at most
  20 times with 50 ms waits. Malformed JSON/UTF-8 remains fail-closed; persistent
  access errors have a distinct diagnostic and do not overwrite existing data.
  A genuinely absent initial profile is allowed only after bounded retries
  under the writer lock. A retained lock file alone cannot block first save.
- Covers/Gallery poll read-only snapshots every three seconds, serialize
  overlapping refreshes, retry after transient failure and stop on unmount.
  Cover command rejection refreshes durable results without repeating create.
- Settings merge and current inspectors/variant selection use ProductionItem
  ID. Manual text saves resolve ID in the backend, not a stale renderer index.
  Reorder preserves draft ownership; removal closes the corresponding inspector.
- Reconciliation includes a row's recorded prompt-variant paths. It does not
  assign an unowned disk file to a current ID by title/position. Legacy filename
  fallback requires exactly one possible owner across all title prefixes;
  ambiguous/reused-title files remain unassigned and counted as orphans.
  Legacy settings rows are never promoted to a new ID by title alone.
- Studio and AI-reference drafts survive equivalent polling snapshots and
  background updates while Studio is open. Gallery face drafts stay keyed by ID.
- Both automatic-resume senders mark their request automatic. Core checks the
  current persisted auto-resume/pause flags without clearing manual pause.
  Explicit operator Continue retains its existing behavior.

## Regression-first evidence

New tests reproduced transient read errors, retained initial locks, stale-save
loss of a concurrent manual row, wrong same-title ID/path merge, reused legacy
title adoption, prefix-ambiguous reconciliation, draft loss, inspector reorder,
Gallery selection and automatic unpause before the corresponding fixes.
An independent diff review found additional boundary cases; all Critical/
Important findings were fixed and re-reviewed with no remaining findings.

Five pre-existing Covers test failures were reproduced against the untouched
base implementation. Only fixtures/assertions were corrected: provider scene
facts must be present in their source; stale explicit IDs must reject rather
than produce the old generic-selection result; an ID tombstone, not a reused
title, must remove a current ID. No editorial/quality fallback logic changed.
A concurrency test's 10 ms sleep was replaced by a ten-worker barrier so peak
parallelism is proved without depending on scheduler speed under build load.
Manual-save/route test expectations now include the added ID/refresh contract.

## Executed verification

| Check | Result |
| --- | --- |
| Related isolated Python suite | PASS, 381 tests |
| Full UI suite | PASS, 393 tests / 55 files |
| Windows source Electron / IPC / Python smoke | PASS, one real app test |
| Typecheck and web/desktop/Remotion source build | PASS |
| Ruff and release lint for changed Python files | PASS |
| Security and secret gates | PASS |
| Python and production JS dependency audits | PASS |
| Production-write guard | PASS in isolated runners and original-profile hash verification |
| Diff check | PASS |
| Existing Frozen runtime guard | 9 PASS / 1 expected FAIL: changed Core-owned source, stale binding |

The native source smoke seeds a disposable 84-topic queue without credentials,
writes 78 synthetic images while Covers remains open and verifies their durable
IDs and visible ready results, plus five recovery/one quota statuses. It then
writes a 79th synthetic result while Gallery remains open and verifies automatic
refresh. No generation/provider/recovery request is used. Screenshots are local
external evidence under `D:/NewsFlow-RC/rc238-validation/issue-375-source-e2e/`;
test media and profile are disposable, not a copy modified in place.

## Release boundary

GitHub CI is required on the PR and is reported separately from local PASS.
The optional new Python Covers workflow step was not published: the existing
repository account's OAuth token lacks `workflow` scope, and the other already
connected account has no repository access. No permissions were changed.
Existing CI still runs the full UI suite and its existing Python/security/build
steps; the new Python race/identity suites were run locally on Windows, not
misreported as independently executed by GitHub CI.
The existing Frozen lock/package binding was deliberately not changed or
forged. Since both `scriptor/bridge.py` and `scriptor/config.py` changed, a new
immutable Frozen Core is required after source acceptance, followed by a new
TEST EXE in a separate release task. This PR is not release-ready while the
mandatory Frozen binding gate is stale.

Existing rc238/r43 artifacts, production settings, sessions, queues, API keys,
OAuth, media, footage index and the completed montage videos were not modified.
Live/paid calls: 0. Frozen Core builds: 0. TEST EXE builds: 0.
