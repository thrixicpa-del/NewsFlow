# Issue #412 — browser scenario completion and document readiness

Task: <https://github.com/thrixicpa-del/NewsFlow/issues/412>.
Branch: `codex/issue-412-chatgpt-document-readiness`, based on
`43dd0709d7341eb79b308303031b5f3a47fd3ebc` (`origin/main`).
This is separate from footage PR #403 and covers PR #411. No merge, issue
closure, installed application update, Frozen build or lock refresh is included.

## Root cause and resulting behavior

The browser adapter had a 900-second generation deadline, accepted four seconds
of unchanged prose without Stop as completion, and closed the tab before the
bridge committed the downloaded scenario. File selection was treated as upload
success; settings and the native chooser supported only one requirement file.

- Production generation now waits without a fixed composition deadline for a
  new assistant turn with a downloadable TXT. An active generation marker or
  visible Stop prevents completion. Old turns, user attachments and other tabs
  cannot provide this task's result. Finite deadlines remain available for tests.
- A nonempty UTF-8 TXT must be downloaded and committed/exported for its
  ProductionItem ID before closing its tab and releasing its concurrency slot.
  Storage failures retain the tab and retry persistence without another send or
  duplicate export. Existing manual results and explicit deletions retain priority.
- **Owner-approved exception:** a created file that cannot be downloaded gets at
  most three download attempts, then its tab closes, the topic receives an error,
  and subsequent topics continue. Generation is never resubmitted. Invalid,
  empty or ambiguous output is also an explicit topic error, never a successful
  scenario.
- The UI adds/removes multiple TXT/Markdown paths and retains them after restart.
  There is no application file-count cap. An explicit empty list overrides the
  old single-path fallback; legacy settings still load.
- Upload proof is limited to the composer and exact expected filenames. Error,
  busy, progress and processing states block Send. File-input success alone is
  insufficient. Original UTF-8 bytes are frozen for upload; duplicate basenames
  receive unique aliases without changing source files.
- Only unconfirmed documents receive bounded automatic selection retries (two
  attempts, at least 30 seconds apart). Failed cards must have a real remove
  control to retry. Otherwise the visible tab waits for manual attachment or a
  full-content paste. A paste must add the complete document beyond occurrences
  already in the automation-prefilled prompt. Proof is checked again immediately
  before Send; Enter fallback is disabled when documents are required.
- Cancel is available during waiting and after restoring an active UI. A launch
  UUID and owner-lock-protected cancellation record cover cancellation before
  the Python worker claims its batch. A delayed cancellation cannot cancel an
  unrelated identified batch. Abandoned launch cancellation records expire after
  24 hours; records are consumed when their matching launch claims ownership.
- A downloaded result with a TXT export error stays visibly in error instead of
  showing ready. Its text remains protected against accidental regeneration;
  historical manual results with unrelated old status retain existing behavior.

## Verification evidence

Commands ran from this isolated worktree on native Windows. All Python suites
used `python -B tests/run_isolated.py`; each completed run reported
`PRODUCTION_WRITE_GUARD=PASS`. Private logs are retained in
`.superpowers/issue412/`; no account data or requirement documents were committed.

| Check | Result |
| --- | --- |
| Browser DOM/readiness, document settings, queue, command contracts and runtime action map | 95 PASS, 136.633 s (`full-related2.log`) |
| Story planner, runner, scenarios, session and actual offline browser pipeline | 149 PASS, 57.071 s (`related-storage-pipeline.log`) |
| Offline production bridge → Chromium upload/download → durable job/export → close | 2 PASS; included above; separate run 9.608 s |
| React/IPC full regression | 424 PASS / 55 files, 11.08 s (`full-ui-final.log`) |
| Final actual source Electron UI → trusted IPC → Python → four cold restarts, plus offline browser pipeline | 3 PASS, 18.349 s (`system-final.log`) |
| Electron security and secret scanner suites | 9 PASS, 0.515 s (`security-green.log`) |
| FAST local gate: secret scan, changed Python Ruff, Electron security, TypeScript | PASS (`fast-final.log`) |
| Web and desktop source builds | PASS (`build-web-final.log`, `build-desktop-final.log`); Vite chunk-size warning retained; no packaging |
| Production dependency audit | PASS, no known vulnerabilities (`dependency-audit.log`); no dependency changes |
| Independent source review | Three concrete findings reproduced/fixed; second review found no remaining definite P1/P2 |
| Frozen source lock | **FAIL**, 10 PASS / 1 FAIL, 0.523 s (`frozen-guard.log`) |
| Docker | **NOT RUN/BLOCKED**, Docker Desktop Linux engine pipe unavailable |
| Live authenticated ChatGPT, real model output/large-document quotas | **NOT RUN**, only offline DOM and controlled failure fixtures |
| Packaged EXE, clean Windows/Sandbox, RELEASE | **NOT RUN**, outside this task and owner prohibition |

The offline pipeline uses real Chromium File objects and an actual attachment
download with original bytes, real scheduler/bridge/storage and Product IDs.
It injects a single storage failure and separately a completed-file download
failure; the latter proves exactly three attempts, one send per topic, failed
tab closure before the next send, ERROR for the first topic and DONE for the
second. The >15-minute wait uses a fake clock (ready at 1,300 seconds), not a
15-minute live provider run. The native UI test stubs only the OS file dialog,
blocks external requests and generation, and validates real persistence/cancel
through the source Python bridge. Its queue-owner fixture is test-owned.

## RED records and historical failures

All failures remain in the private log directory; later PASS is not a claim that
old evidence never failed.

- `browser-red.log`: five failures and three errors for missing readiness/save
  behavior before implementation. A legacy test class was also collected by an
  initial fixture import; the final suite imports its module only.
- `settings-baseline-red2.log`: immutable base-source check reproduced the old
  early-completion behavior and absent multiple-file/cancel contract. The first
  wrapper attempt (`settings-baseline-red.log`) failed module registration and
  is harness evidence, not a valid product RED.
- `attachment-boundary-red.log`, `status-storage-red.log`, `review-red.log`,
  `ui-cancel-red.log`, `ui-batch-cancel-red.log`: upload-name boundary, status
  storage exception, prompt prefill false proof, empty-list revival and launch
  cancellation defects, followed by GREEN regressions.
- `ui-export-status-red.log`: nonempty downloaded text hid the new TXT export
  failure behind a ready label. Added a precise error-state regression and
  preserved the historical manual-result behavior; 22 focused UI/IPC tests passed.
- `full-related1.log`: 92 tests, one failure and one error. A failed download
  navigation removed the DOM control, masking the original download error; fixed
  by retaining that error without another generation. The former test accepting
  completed prose without TXT was replaced by the stricter required assertion:
  no completed result, no callback and no tab close without a file.
- `full-ui1.log`: 422 PASS / one missing-approved-PNG failure. Native checkout
  contained Git LFS pointers; fetched existing approved PNGs without replacing
  baselines. Full UI then passed.
- `pipeline-integration1.log`: harness export path relocated by TEMP migration;
  corrected to an independent test profile and separate `io` directory.
- `ui-runtime1.log` / `ui-runtime2.log`: harness startup failed to progress.
  Moved the harness beside UI dependencies and removed the Electron ESM
  top-level readiness await, which blocked its own bootstrap. Only the exact
  spawned test Electron process was terminated. Subsequent native smoke passed.
- `security-integrity.log`: a CRLF-ending edit broke the existing security
  scanner's literal allow-list terminator parsing. Restored the repository's LF
  convention; security then passed. The separate Frozen lock failure remains.
- `ruff.log` / `fast-gate.log`: new-code timezone/import formatting findings;
  fixed without disabling rules, then FAST passed.

Frozen failure is preserved: the tracked lock references the previously frozen
bridge source, while this branch changes source behavior. No runtime was built
and no lock/hash was updated to create a false PASS. This task is **not
release-ready**. Earlier footage/media integrity failures are outside #412 and
have not been cleared by these browser tests.

## Limits and follow-up acceptance

The current live ChatGPT DOM, authentication, platform upload caps and actual
long thinking are unverified. Unknown attachment layouts conservatively wait
for operator repair/cancel. Use a disposable authorized ChatGPT profile and
synthetic TXT documents for live acceptance before merging. Manual source-file
aliases with duplicate basenames can require pasting complete content for manual
repair if only the original filenames are available; original files remain untouched.

Preflight, login and browser startup failures remain explicit errors. Ordinary
waiting for generation/upload is indefinite until success, manual tab closure or
Cancel; this can intentionally hold a queue slot. Source cancellation does not
update the installed Frozen application. CI and the Windows-native workflow must
be assessed on the pushed PR; a local PASS is not independent CI acceptance.
