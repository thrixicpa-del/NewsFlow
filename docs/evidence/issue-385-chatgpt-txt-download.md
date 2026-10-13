# Issue #385 — ChatGPT TXT download and topic filenames

Base: `cb0993c626f8f0371129feb384eccbe5af2b7235` (accepted main).
Branch: `fix/issue-385-chatgpt-txt-download`. Windows-native validation: 2026-10-13.

## Root cause and scope

Read-only observation of one completed operator chat found a real TXT download
button, but no legacy `data-message-author-role=assistant` element. The current
assistant boundary used `data-chatgpt-search-unit-key` /
`data-content-search-unit-key` ending in `:assistant`. Waiting exclusively for
the legacy marker never reached the download. This observation is not a claim
about every ChatGPT layout.

Two additional defects were reproduced offline: page-wide last-download
selection could choose a user's requirements attachment, and results were only
published after the entire browser batch completed. The browser-topics screen
also lacked periodic snapshots while its command was pending.

## Fix

- Recognize current and legacy assistant boundaries; retain outer-owned sibling
  file cards without double-counting nested markers. Existing chats must still
  be replaced by a confirmed fresh chat before submission.
- Keep the response locator local to each task/tab. Download only within that
  new response; ambiguous files fail closed. Require an actual browser download,
  a suggested `.txt` filename, strict UTF-8 and nonempty content. No extraction
  of prose as a substitute, no provider repair and no automatic second send.
- Export literal UTF-8 text as `Название темы.txt` in the configured scenario
  output's `ChatGPT браузер` subdirectory. Windows-unsafe names are sanitized;
  long names respect a UTF-8/UTF-16 filename budget. Only collisions receive an
  ID-derived suffix/counter. Exclusive creation never overwrites an old file.
  File names do not determine identity: persistence uses ProductionItem ID.
- Publish each completed item immediately, reloading the authoritative session
  and resolving a unique ID. Manual/ready text wins; deleted items stay deleted.
  Session conflicts retry only the commit (three attempts), not generation or
  download. Export once, count only a successful session commit, and allow other
  already-submitted tabs to settle before surfacing a persistence failure.
- Sequential snapshot polling updates the browser-topics screen while the batch
  is pending. Identical saved-settings snapshots do not reset unsaved drafts;
  polling stops on completion/unmount. Concurrency policy from #383 is unchanged.

## RED evidence

Before implementation: 7 targeted regressions, 5 failures, 1 error, 1 pass.
Reproduced current-DOM recognition failure, wrong user attachment, existing-chat
misclassification, non-topic filename and delayed per-item publication.

Review exposed and reproduced nested sibling-card exclusion, long emoji
collision filenames, callback failure cancelling siblings and a concurrent
manual-edit/session-save conflict. UI RED confirmed missing live snapshots.
Each was corrected without weakening a guard or replacing expected behavior.

## Verification

- `python tests/run_isolated.py tests.test_chatgpt_browser tests.test_browser_topic_scenarios scriptor.test_command_contract -v`
  — 60 tests PASS; includes real headless Chrome DOM/download fixtures on Windows.
- `python tests/run_isolated.py tests.test_session tests.test_scenarios -v`
  — 57 tests PASS.
- `pnpm test:ui` — 399 tests PASS, 55 files.
- `pnpm typecheck`, `pnpm build` — PASS (existing Vite chunk-size warning).
- Ruff for all five changed Python files and `git diff --check` — PASS.
- `pnpm verify:security`, `pnpm verify:secrets`, `pnpm verify:dependencies` — PASS.
- Isolated Python runs — `PRODUCTION_WRITE_GUARD=PASS`.
- `tests.test_core_runtime_guard` — 9/10 PASS, 1 expected stale-source failure.
  r45 already differs from accepted main; this source fix also changes the
  bridge/runtime. Binding/lock/binary remain untouched. This is NOT a claim that
  the existing Frozen Core or installed EXE contains this fix.

Browser test networking is intercepted completely. Tests use ephemeral Chrome
contexts and disposable storage, never an authenticated/operator profile.
Fixtures cover distinct concurrent tab payloads, literal Cyrillic/emoji/CRLF,
legacy/current/nested DOM, old/user attachments, missing/ambiguous/non-TXT files,
invalid UTF-8/empty/download failure, filename collisions, queue reorder,
manual edits/deletion, incremental persistence and bounded storage conflict.

Local raw logs: `D:/NewsFlow-RC/rc240-validation/issue-385-*.log` (not committed).
Independent CI status belongs to the PR; local PASS is not a substitute for CI.
Frozen guard blocks release until a separately authorized Frozen build/binding.

## Safety and release boundary

No user queue stopped, no user Chrome tabs closed/reloaded, no production
settings/session/keys/OAuth changed, no real messages sent, no provider calls.
Frozen Core and TEST EXE were not built or patched. No merge is performed.
