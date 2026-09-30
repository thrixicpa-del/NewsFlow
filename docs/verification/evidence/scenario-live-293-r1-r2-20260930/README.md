# PR #293 — R1/R2 controlled Scenario evidence

This directory publishes the two permitted, unedited full Scenario runs after
the D1–D4 diagnostic. Both ran in disposable `NEWSFLOW_TEST_MODE` roots. The
runtime roots themselves are deliberately excluded: they can contain test
session/configuration state. No API key, Authorization header, cookie, account
setting, or production state is present here.

Each run contains the exact safe post-adapter request payloads, visible provider
responses, persisted Story Map, accepted P1/P2/P3 text, assembled scenario,
transport and logical-call ledgers, lengths/hashes, and production/secret
guards. `response-*-visible.txt` and `part-P*.txt` are not edited.

| Run | Source | Calls | Result |
| --- | --- | ---: | --- |
| R1 `scenario-live-293-r1-20260930-174500` | `e2bf924919deccd2ad88e46647973d983fddc7a2` | 6: Planner, structural repair, fresh Planner, P1–P3 | `SHORT`, 9,752 Python characters; editorially not accepted |
| R2 `scenario-live-293-r2-20260930-182100` | `1370871698d3c64179b9478f87bcbee7836bee14` | 4: Planner, P1–P3 | `LONG`, 13,344 Python characters; editorially not accepted |

R1 shows the first hypothesis: the Writer receives one non-duplicated current
event sequence instead of the previous competing current metadata. R2 tests the
subsequent, part-tagged event-spine preparation and per-event-record allocation.
Neither result is presented as a quality acceptance. `EDITORIAL_AUDIT.md`
records the reading-based evaluation and the concrete limits of the evidence.

The shared budget ledger is included in each run as
`13-budget-ledger-safe.json`. D1–D4 consumed four logical/HTTP calls; R1
consumed six and R2 consumed four. Writer regeneration is zero in both full
runs: each accepted P1/P2/P3 has exactly one Writer call.
