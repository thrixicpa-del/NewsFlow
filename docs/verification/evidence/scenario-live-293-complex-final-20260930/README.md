# PR #293: bounded Scenario live-acceptance evidence

This directory is a new, immutable publication of the three permitted A-runs
from the PR #293 complex stage.  It is not a release acceptance and it does
not replace the earlier `scenario-live-293-event-spine-*` evidence.

## Safety boundary

- Each run used a fresh disposable `NEWSFLOW_TEST_MODE=1` root.
- The captured files contain only post-adapter request bodies, visible model
  output, safe job projections, hashes and ledgers.  Authorization headers,
  cookies, API keys and runtime/account settings were never exported.
- `runtime-root` is deliberately absent from this repository copy.
- Every source directory passed its capture-time production-write guard and
  export secret scan.  The repository copy was scanned again before commit.
- No Covers, FastGen, OAuth, YouTube, publication or production-state path was
  used.

## Runs and outcome

| run | source SHA | logical / transport calls | result |
| --- | --- | --- | --- |
| A1 `scenario-live-293-complex-a1-live-20260930-150704` | `c28b22288ba4bf59f3b84ea0348b47f2d40913ef` | 5 / 5 | Planner recovery succeeded; P1/P2/P3 were each generated once. Assembled text is 8,165 Python characters, below 11,500, and the editorial review is FAIL. |
| A2 `scenario-live-293-complex-a2-live-20260930-150927` | `a22ac5db20a5940ebafe572d9722af292ec1e5b1` | 2 / 2 | Initial non-JSON response; fresh response used nested `parts[].content_atoms`. That transport shape motivated the bounded normalizer in `8c638c1`; Writer was not called. |
| A3 `scenario-live-293-complex-a3-live-20260930-151124` | `8c638c1b405e884269cbc6b4116c0a7d7af4d66f` | 2 / 2 | Initial non-JSON response; fresh response is syntactically truncated JSON (`16` opening vs `14` closing braces), despite provider status `completed`. Writer was not called. |

The A budget is exhausted: three independent A-runs and nine logical provider
calls total.  No B-run is permitted because no A-run passed both length and
editorial acceptance.  There were no Writer regenerations, no manually edited
Story Maps, no selected "best" output and no cross-run assembly.

## How to inspect each run

Each run directory contains the exact safe material needed for independent
review:

- `00-run-manifest-safe.json`, the frozen request contract and source SHA;
- `01-user-template.txt` and `02-production-item-test-context.json`;
- `request-*-post-adapter-safe.json`, the actual post-adapter payloads;
- `response-*-visible.txt` and `response-*-transport-meta.json`;
- `10-logical-calls.json` and `11-transport-attempts.json`;
- parsed/persisted `20-story-map-persisted.json`, `21-job-safe.json`, accepted
  parts, assembly facts and `scenario.txt` when Writer ran.

The per-run ZIP files preserve exactly the safe directory contents.  The
top-level ZIP is a convenience bundle of this published evidence only.

`A1_EDITORIAL_REVIEW.md` is an audit of the same A1 map, payloads and prose;
it is an evaluation, not a runtime quality gate and did not trigger any
rewrite.

## Acceptance status

`STRUCTURE/TRANSMISSION`: source changes and deterministic tests are evaluated
separately in the PR report.  `LIVE LENGTH ACCEPTANCE`: **FAIL** (A1 is 8,165
characters versus 11,500–12,500).  `LIVE EDITORIAL ACCEPTANCE`: **FAIL**
(A1).  `A2/A3 Writer prose`: **NOT_EVALUABLE**, because Writer was never
called.  This package does not claim merge or release readiness.
