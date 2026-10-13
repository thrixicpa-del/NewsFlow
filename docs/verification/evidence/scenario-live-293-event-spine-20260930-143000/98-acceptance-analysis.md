# PR #293 Event-Spine live acceptance — 2026-09-30

## Scope and isolation

- `RUN_SOURCE_SHA`: `2894a720b962912240b592a782cb695a231bb7be`
- Run ID: `scenario-live-293-event-spine-20260930-143000`
- Provider route: OpenAI Scenario; configured model: `gpt-5.4-mini`; returned model: `gpt-5.4-mini-2026-03-17`.
- Topic: `МИР ОПЯТЬ ОТКЛАДЫВАЕТСЯ? — РОССИЯ УСИЛИЛА УДАРЫ ПО УКРАИНЕ — КИЕВ СНОВА ОКАЗАЛСЯ ПОД МАССИРОВАННОЙ АТАКОЙ`.
- Contract: target `12000`, minimum `11500`, maximum `12500`; expected part targets `3999 / 3999 / 3998`.
- Trusted material policy: `factual_context_available=false`, `dramatized_allowed=true`; this is headline-only editorial input, not supplied factual evidence.
- Test storage used `NEWSFLOW_TEST_MODE=1` and a fresh disposable `NEWSFLOW_TEST_ROOT`. The production-write guard passed. Captured requests redact credentials and do not capture headers.

`00-preflight-safe.json` records the zero-call preflight. It verified the route, the isolated root and the test length contract before this paid run.

## Call ledger

| Logical call | Phase | Transport attempts observed | Result | Visible response |
| --- | --- | --- | --- | --- |
| 1 | PLANNER | 1 | schema invalid | `response-01-visible.txt` |
| 2 | FRESH_PLANNER | 1 | schema invalid | `response-02-visible.txt` |
| 3 | WRITER_P1 | 0 | MISSING — no valid plan | MISSING |
| 4 | WRITER_P2 | 0 | MISSING — no valid plan | MISSING |
| 5 | WRITER_P3 | 0 | MISSING — no valid plan | MISSING |

`logical_calls=2`; observed `transport_attempts=2`; SDK retry count is `UNKNOWN`. No Writer content was generated, regenerated, edited, trimmed, or assembled.

## Planner outcome

The existing bounded recovery route ran exactly once: `FRESH_DIRECT`.

| Response | Part allocation returned by model | Runtime parser result |
| --- | --- | --- |
| Initial Planner | P1=`A1,A2,A3`; P2=`A4,A5`; P3=`A6,A7,A8` | `SEMANTIC_DENSITY`: P2 has 2 atoms but a ~3999-character part requires 3. |
| Fresh Planner | P1=`A1,A2,A3,A4`; P2=`A5,A6,A7,A8`; P3=`A9` | `SEMANTIC_DENSITY`: P3 has 1 atom but a ~3998-character part requires 3. |

The accepted plan/session projection is therefore `{}` and `accepted_story_parts=[]`. The job correctly ended in `SCHEMA_RECOVERY_EXHAUSTED` / `Нужно действие`, with `actual_chars=0` and `length_status=FAILED`.

This is **not** a length acceptance. It is also not an editorial acceptance: there are no Writer P1/P2/P3 paragraphs or assembled scenario to evaluate. The visible Planner outputs are preserved verbatim in this directory for independent inspection. They remain editorial evidence only; no new parser veto, Writer retry, manual Story Map edit, provider/model selection, or second live run was used.

## Editorial review of every planned part

This is a post-run reading aid only. It changes no runtime outcome and is not a quality gate.

| Visible map / part | Concrete planned progression | Editorial observation |
| --- | --- | --- |
| Initial P1 | `A1` starts the attack; `A2` moves to checking damage; `A3` says the attacks “выглядят как усиление давления”. | The first two are event-shaped, but `A3` changes the interpretation of the attack rather than recording a new action or result. |
| Initial P2 | `A4` assigns damage and infrastructure checking; `A5` turns safety into recurring routine. | Both can be developments, but there are only two allocated atoms for a ~4k part, so this map never reached Writer. |
| Initial P3 | `A6` moves peace further away; `A7` broadens the conflict; `A8` asks whether recovery or another strike comes first. | These are primarily framing, expectation and an open question. There is no independently planned terminal concrete result before the question. |
| Fresh P1 | `A1` alarm; `A2` explosions/air defence; `A3` visible infrastructure effects; `A4` says peace discussion recedes. | The first three provide a chronological event chain. `A4` is a broader interpretation, not the next observable event. |
| Fresh P2 | `A5` emergency assessment; `A6` service/transport limits; `A7` systemic pressure; `A8` peace expectations recede. | `A5` and `A6` advance the aftermath. `A7` and `A8` again turn the chain into interpretation, including a repeated peace/pressure frame. |
| Fresh P3 | `A9` says Kyiv remains in a state of checking and waiting for a new wave. | This is a status/expectation, not a separately developed terminal result; it is also the only atom allocated to the part. |

There are no prose paragraphs to quote: P1/P2/P3 were never called. Consequently, `PART EVENT SEQUENCE`, beat-to-paragraph coverage, analytical/literary prose, disclosure placement, repetition in prose and final-question placement are all `MISSING`, not inferred from this Planner-only result.

## Requested same-run evidence fields

- Parsed/persisted Story Map: `20-story-map-persisted.json` is `{}` because no map passed the existing parser.
- PART EVENT SEQUENCE for P1/P2/P3: `MISSING` — Writer prompt construction is reached only after a valid Story Map.
- P1/P2/P3 and `scenario.txt`: `MISSING` / empty — no Writer invocation was permitted.
- Safe post-adapter request bodies: `request-01-captured.json` and `request-02-captured.json`.
- Visible responses: `response-01-visible.txt` and `response-02-visible.txt`.
- Model IDs, usage, status and finish information: corresponding `response-*-transport-meta.json` files.
- Production-write and secret-export checks: `31-production-write-guard.json` and `32-secret-export-scan.json`.

No keys, Authorization values, cookies, account settings or hidden model reasoning are included.
