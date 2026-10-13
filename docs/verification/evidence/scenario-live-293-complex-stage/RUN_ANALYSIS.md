# Run 2 / Run 3 transmission and editorial audit

## Scope and evidence rule

This audit covers only `scenario-live-293-12k-live-2-20260930` (Run 2) and
`scenario-live-293-12k-live-3-20260930` (Run 3).  It does **not** use the
older 9,141-character run as evidence.  Every quoted map field is in
`20-story-map-persisted.json`; the full post-adapter Writer input is the
matching `request-0N-captured.json`; the unedited Writer response is the
matching `response-0N-visible.txt` and `part-PN.txt`.

The test input for both runs is the title in
`02-test-production-context.json`, a 12,000 / 11,500–12,500 contract in
`00-run-manifest-safe.json`, and the exact selected manual template in
`01-user-template.txt` (SHA-256 `3bbd1058e2a7f00613e95680ada44937455f5d7836ad119ae003d49edba3c0e5`).
That template asks the final section to fix the current state and the next
question, and also says it must not simply repeat what has already been said.

## Transport and length facts

| Run | Planner / Writer logical calls | Writer part targets | Actual P1 / P2 / P3 | Final stripped Python length | Provider completion evidence |
| --- | --- | --- | --- | --- | --- |
| Run 2 | 1 / 3 | 3999 / 3999 / 3998 | 2637 / 2919 / 2893 | 8453, SHA `b30fa3b29d2a5892439f5d36513a0f5f7ec9762859e055904a42cd45492046f5` | all four transport results `completed`, `incomplete_details: null` |
| Run 3 | 1 / 3 | 3999 / 3999 / 3998 | 2789 / 3466 / 3084 | 9343, SHA `738c140f3084cdcfa76b11a36af9be8ad4e0960c8dba68a798b1a8605ac938b8` | all four transport results `completed`, `incomplete_details: null` |

The per-call output cap was 5,120 tokens for each Writer call.  The ledger
records 637/719/725 output tokens in Run 2 and 678/821/739 in Run 3.  Thus the
saved provider metadata does not demonstrate an output-cap truncation; it
records completed short outputs.  SDK retry count is deliberately `UNKNOWN`:
the captures prove four logical calls and four visible transport attempts in
each completed run, not an unobservable SDK implementation detail.

## Exact material path

The following table identifies the immutable handoff for every Writer part.
Each listed atom's full `WRITER MATERIAL` is preserved verbatim in both the
persisted map and the corresponding captured request.  No field is shortened
in this audit.

| Run / part | Atoms and exact sent material | Unedited answer evidence | Audit result |
| --- | --- | --- | --- |
| Run 2 P1 | A1–A3 in `20-story-map-persisted.json` → `request-02-captured.json` `CURRENT CONTENT` | `response-02-visible.txt`, `part-P1.txt` | Material reached the call.  It was nevertheless compressed: 2,637 against 3,999 target. |
| Run 2 P2 | A4–A6 → `request-03-captured.json` | `response-03-visible.txt`, `part-P2.txt` | Material reached the call.  It was compressed: 2,919 against 3,999. |
| Run 2 P3 | A7–A9 → `request-04-captured.json` | `response-04-visible.txt`, `part-P3.txt` | Material reached the call.  It was compressed: 2,893 against 3,998 and ends in an open analytical question. |
| Run 3 P1 | A1–A3 → `request-02-captured.json` | `response-02-visible.txt`, `part-P1.txt` | Material reached the call.  It was compressed: 2,789 against 3,999. |
| Run 3 P2 | A4–A6 → `request-03-captured.json` | `response-03-visible.txt`, `part-P2.txt` | Material reached the call.  It was compressed: 3,466 against 3,999. |
| Run 3 P3 | A7–A9 → `request-04-captured.json` | `response-04-visible.txt`, `part-P3.txt` | Material reached the call.  It was compressed: 3,084 against 3,998 and replaces map concepts with further interpretation. |

The payloads contain the full `CURRENT CONTENT`, `WRITER MATERIAL`, previous
semantic memory, seam tail, active part target, part-volume budget, manual
template, and Writer boundary.  Therefore this evidence finds **no silent
truncation of the P3 material at the request boundary** for Run 2 or Run 3.
It does not establish that a model must use every supplied beat.

## P3: whether a terminal event was planned or lost

### Run 2

The map itself has no concrete terminal event.  A7 says its development is
“Последствия атаки переходят из мгновения в режим постоянной готовности.”;
A8 says “Текущий налёт связывается с более широким изменением линии
конфликта.”; and A9 says “После удара не видно окончательного разворота, а
впереди только развилка сценариев.”  A9's last beat is “Финальная развилка
остаётся открытой…”, not an action, decision, result, or changed terminal
state.  These exact fields are sent in `request-04-captured.json`.

The response follows that analytical map: “Этот удар нельзя рассматривать
только как историю одного города”, then ends “остаётся ли у мира шанс на
паузу или конфликт снова уходит в новый виток.”  Thus a concrete terminal
result was absent already in the Story Map; the evidence does not support the
claim that Writer discarded a supplied concrete final event.

### Run 3

Run 3 has the same upstream defect despite all atoms being marked
`DRAMATIZED`.  A7's `development` is “Одна атака начинает восприниматься как
звено в более широком усилении давления”; A8 says “пространство для быстрого
сближения сужается”; A9 says only that it is unclear whether attacks continue
or a response follows.  Its final beat explicitly says the story ends on a
“конкретной незакрытой развилке”, rather than naming a terminal development.

The Writer response contains this map-level analysis nearly verbatim: “И
именно поэтому разговор о мире снова отъезжает на второй план” and closes
with “если давление продолжится, то что первым изменится…?”  The planner
therefore supplied an analytical/open-ended FINAL; Writer did not receive a
specific final event that could be shown to have been dropped.  This is an
editorial planning-quality observation, not a license to rewrite P3 or add a
runtime rejection gate.

## P1 / P2 observations

Run 3's A1–A6 do reach the Writer uncut, but several are already abstract or
conditional.  Examples in the persisted map are A1's “Удар не выглядит
единичным эпизодом”, A2's “Сама структура атаки делает ситуацию сложнее”,
and A6's “любой массированный удар может создать нагрузку”.  Their matching
responses contain the same kind of explanation: P1 says “на первый план
выходит уже не только сам факт атаки”, and P2 says “Даже без точной картины
понятно…”.  This is a plan-content and model-fulfilment issue, not evidence
of a lost beat in the request assembler.

Run 2 has the same pattern: its P3 A7–A9 are predominantly “режим ожидания”,
“общая траектория войны”, and “развилка”, and its P3 responds with “Такой
ритм уже сам по себе меняет повседневную жизнь.”  The map and prose therefore
repeat the meaning of prolonged threat rather than introduce an independently
observable terminal development.

## Separated conclusions

* **Transmission:** the captured Run 2/3 payloads preserve map-owned content
  into the right P1/P2/P3 request.  No evidence supports silent loss of the
  P3 `CURRENT CONTENT` in these runs.
* **Length:** both complete Writer runs are below 11,500 characters.  They
  are honestly `SHORT`; no segment was regenerated, padded, trimmed, or
  selected from alternatives.
* **Editorial quality:** both P3 plans lack a concrete terminal development,
  and both responses foreground analytical interpretation.  This is not
  accepted merely because a call completed.
* **New source defect fixed in this stage:** FACTUAL with no supporting
  context formerly combined “DRAMATIZED forbidden” and “EVERY atom must be
  DRAMATIZED.”  The fix carries trusted `factual_context_available` and
  `dramatized_allowed` through `ScenarioRequest`; Planner no longer derives
  permission from arbitrary manual-template text.  This is deliberately not
  claimed to have repaired the already immutable Run 2/3 output.
