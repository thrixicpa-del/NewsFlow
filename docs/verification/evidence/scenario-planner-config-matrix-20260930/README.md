# PR #293 — Planner configuration matrix and R1/R2 acceptance

This is a safe, immutable copy of disposable TEST evidence. It contains no API keys, Authorization headers, cookies, account settings, hidden reasoning, or `runtime-root`.

## Fixed experiment

- Topic: `МИР ОПЯТЬ ОТКЛАДЫВАЕТСЯ? — РОССИЯ УСИЛИЛА УДАРЫ ПО УКРАИНЕ — КИЕВ СНОВА ОКАЗАЛСЯ ПОД МАССИРОВАННОЙ АТАКОЙ`.
- Contract: target `12000`, minimum `11500`, maximum `12500` characters.
- Material: headline-only, no supplied factual context, DRAMATIZED allowed; the title is not factual evidence.
- Selected full template is `01-user-template.txt`, SHA-256 `3bbd1058e2a7f00613e95680ada44937455f5d7836ad119ae003d49edba3c0e5`.
- Planner instructions/input/schema hashes before M calls: `3a4fd359486e79a5fa9ad16ca1b04a640a2feec36b1a0c7a1cafa06bc66db6a2`, `379c7aaec902545e2c08db25e1669e828671b326ae2821f1ff2d07c4dd9974e5`, `47b255f4254228f61ebb591de14ff24f7d7a13ca2390acf258fcbffb80f5b037`.
- M0/M1 source: `73ff54f929d7de74ac1b25064017b222425d107a`; R2 source: `ea0bf4bd7550c9b1482b1066e09b35afed7a6783`.

## Matrix

| Cell | Requested route | Returned route | Outcome |
| --- | --- | --- | --- |
| M0 | `gpt-5.4-mini`, `none` | `gpt-5.4-mini-2026-03-17` | completed, parser PASS; editorially weak P2/P3 abstractions. |
| M1 | `gpt-5.4-mini`, `medium` | `gpt-5.4-mini-2026-03-17` | completed, parser PASS; selected only for one bounded full test because actions/results were more concrete. |
| M2 | `gpt-5.4`, `medium` | MISSING | one POST then `TimeoutError`; no response, no retry, no third model. |

Every M post-adapter payload has the same projection after removing **only** `model` and `reasoning`: SHA-256 `e3dbde9b0cf99c026d9a7d3189ca3910f4e2451a572db72801a62505ec380d39`.

## Full runs

R1 (`scenario-live-293-config-r1-20260930-200101`) used M1 but the old ordinary Planner cap of 6,144. The response consumed 5,967 reasoning tokens and ended `incomplete/max_output_tokens`; no Writer was called and no prose was created. This is technical, not editorial.

R2 (`scenario-live-293-config-r2-20260930-200201`) used the same M1 route with a TEST-only Structured-Output Planner cap of 32,768. It made Planner + P1 + P2 + P3 exactly once: 4 logical / 4 HTTP calls and Writer regeneration `0`. Writer calls record `model_override: NONE`, `reasoning_effort: NONE`, and `max_output_tokens: 5120`; only Planner was overridden.

- P1: 3,913 chars; SHA-256 `b7e5ee94c32a922c5f85ac190590e16bf05b5465ac5a5c88284d16cb7c3b0618`.
- P2: 4,688 chars; SHA-256 `99e566bc2ac68347cd855a15284a5c2e1cda9b9abd1ecd79b44e94793bb19037`.
- P3: 4,541 chars; SHA-256 `d0bf9dfa9026c81968ee41575cb11df8bc17d88822ad37ff782bd9ae50ce094a`.
- Assembly: 13,146 Python chars, `LONG` advisory; SHA-256 `b9999398d0dc8d6da8b0384c91bd7efbf1d832d4cc4ce1083d1cd62cf5377888`.

R2 is `DONE` at runtime but **fails editorial acceptance**. The unedited plan, requests, visible responses, all parts and `scenario.txt` are retained in its child directory. See `EDITORIAL_AUDIT.md`.

## Calls, cost estimate, safety

Physical stage total: 8 logical/HTTP attempts — M0, M1, M2, R1 Planner, R2 Planner/P1/P2/P3. The original M2 harness logical field is zero because it appended its logical record after a successful response; saved request + exception prove one sent attempt. `LEDGER_ADDENDUM.md` preserves that discrepancy and the later tested harness correction.

Conservative reservations (one input character treated as one token): M0 $0.185308, M1 $0.185308, M2 $0.617695, R1 upper bound $0.396768; below the $5 ceiling. Returned-usage estimates: M0 $0.029907, M1 $0.059607, R1 $0.037130, R2 $0.086811; M2 has no response usage. These are rate-based estimates, not billing records; reasoning is already inside output tokens and is not counted twice.

All run-level `31-production-write-guard.json` and `32-secret-export-scan.json` results are `PASS`. No Covers, FastGen, OAuth, YouTube, or production data was used.
