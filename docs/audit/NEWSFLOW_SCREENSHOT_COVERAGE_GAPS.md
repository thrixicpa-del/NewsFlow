# NEWSFLOW SCREENSHOT COVERAGE GAPS

## Evidence rule

The supplied DOCX provides 43 real static screenshots, extracted to `screenshots/docx-evidence-20260911/`. A screenshot proves appearance only. Source code proves intended route/handler only. No screenshot proves provider completion, queue execution, persistence write, OAuth or publication.

## Missing important states

| Screen / control / state | Expected | Found in screenshot? | Missing? | Why important | Capture later |
|---|---|---:|---:|---|---|
| Global | loading/skeleton/initial snapshot | No | Yes | establishes safe-mode/read failure UX | launch controlled test root before/after snapshot. |
| Global | command failure toast | No | Yes | generic success copy can hide partial failure | force mocked command rejection. |
| Global | native folder/file/save dialogs | No | Yes | paths/import/export are high-risk inputs | capture only redacted test paths. |
| Covers | provider/model selector open | No | Yes | model health/deprecation/disabled logic is source-only | open selector with no credentials. |
| Covers | FastGen waiting/rate limit | No | Yes | auto-resume/pause and queue status need proof | mock rate-limit response. |
| Covers | generation running/progress | No | Yes | primary action state and duplicate-click guard | mocked worker with controlled progress. |
| Covers | paused/resume | No | Yes | user explicitly relies on pause/continue | capture paused queue and resume confirmation. |
| Covers/gallery | remove image/result/queue confirmation | No | Yes | destructive data state | controlled fake row + confirmation. |
| Covers | face/reference file chooser | No | Yes | reference target and source path state | redacted controlled file selection. |
| Ideas/scenarios | provider failure / retry | No | Yes | completion vs partial result ambiguity | mocked provider failure. |
| Voice | active queue/progress/paused/failed/retry | No | Yes | high-volume queue path is only static | test TTS job lifecycle. |
| Footage | SQLite locked/index active/resume/error | No | Yes | source has special recovery UI | controlled locked/stale worker states. |
| Montage | worker running, render failed, retry, recovery | No | Yes | Electron returns snapshot after 180 ms only | controlled fake worker. |
| Publication V2 | allocation preview vs confirmation | No | Yes | immutable snapshot boundary must be visible | controlled sample records. |
| Publication V2 | queue running, failed stage, retry/cancel confirmation | No | Yes | external side-effect safety | mocked API execution records. |
| Publication V2 | receipt/detail sheet | No | Yes | final evidence/UNVERIFIED state | completed test record. |
| Analytics | OAuth waiting/succeeded/failed/cancelled | No | Yes | critical channel access state | mocked local handoff only; do not authenticate. |
| Analytics | revenue access/no-access transitions | Partly no-access label | Yes | distinguishes unavailable from zero | mocked metadata result. |
| Settings/keys | provider selector and secret redaction state | No | Yes | privacy and configuration UX | test-only blank keys. |
| Channel research | page, run/pause/stop/results/export | No | Yes | source model is partial and route absent | first implement/route feature, then capture. |

## Control coverage result

The earlier button matrix represents 175 literal UI commands and 665 JSX interactive occurrences. Visual evidence covers navigation and static/default surfaces for the major current modules, but it does not cover every row-level control, modal, menu, chooser or stateful control. Therefore **no interactive command is marked runtime-proven from screenshots**. Visual-only matches are recorded in the atlas; all other commands remain `NO VISUAL EVIDENCE` rather than assumed absent.

### Quantified result

| Metric | Count | Counting rule |
|---|---:|---|
| Total screenshots/pages analyzed | 43 | Original inline PNGs extracted from the supplied DOCX. |
| Total logical screens identified | 23 | Long top/bottom continuations are combined, as required. |
| Total visible controls identified | 268 | Conservative count of readable visible action, input, selection, navigation and row-control instances; unreadable micro-labels excluded. |
| Total visible controls mapped to code | 210 | Matched at component/handler family level in atlas/matrix. |
| Total visible controls without a code match | 58 | Mostly navigation, presentational counters, generic input/change controls, overflow controls or labels too generic for a one-to-one command match. Not a defect by itself. |
| Static code interactive occurrences without screenshot evidence | 455 | `665` static JSX occurrences minus `210` visually mapped instances; includes repeated rows and hidden/modal/conditional controls. |
| Important UI states missing | 20 | The state rows in the table above. |

The numbers deliberately distinguish **visible instances** from **static JSX occurrences**. They must not be used to assert that 455 unique user actions are absent from the UI.

## High-priority capture order

1. Covers: ready → running → paused → rate limit → failed → retry → remove confirmation.
2. Publication V2: allocation preview → confirm → uploading → failed stage → receipt/detail.
3. OAuth: configured/no-token/waiting/success/failure without exposing credentials.
4. Voice, footage and montage queues: empty/running/paused/error/recovered.
5. Every dialog/sheet/dropdown/provider selector and destructive confirmation.
