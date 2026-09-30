# PR #293 — bounded final-stage Scenario acceptance evidence

This is an immutable, secret-scanned copy of the three independently run
12k acceptance attempts from the final permitted A budget.  Each directory
contains the safe post-adapter requests, visible responses, parsed/persisted
Story Map, accepted parts, assembled scenario, logical and transport ledgers,
and production/secret guard reports.  The runner used a disposable
`NEWSFLOW_TEST_MODE` root; it did not call Covers/FastGen, OAuth, YouTube, or
production storage.

The records are evidence, not a claim of acceptance.  All three runs used the
same title and `target=12000`, `minimum=11500`, `maximum=12500`.  There was one
Planner and one Writer call per P1/P2/P3 in every completed run: no Writer
regeneration, replacement, trim, padding, provider fallback, or model switch.

| Run | Source HEAD | Calls / HTTP | Python chars | Runtime length | Editorial verdict |
| --- | --- | ---: | ---: | --- | --- |
| A1 `scenario-live-293-a1-20260930-134000` | `a066bf6eb1ca73e88cc104fbabf38e2ccc0efd66` | 4 / 4 | 10,331 | SHORT | FAIL: analytic/repetitive plan and no independent final result |
| A2 `scenario-live-293-a2-20260930-135000` | `87892f681c7b2c067d7e58d661c98f289129bcf9` | 4 / 4 | 12,226 | READY | FAIL: the length passed but P2/P3 mainly develop the same abstract peace/escalation conclusion |
| A3 `scenario-live-293-a3-20260930-140000` | `2e991a59b9b6ea82253944e3db33062db25e89cd` | 4 / 4 | 10,496 | SHORT | FAIL: P2/P3 receive one atom each and P3 is an analytic conclusion, not a terminal event |

The stage ledger consumes 12 logical calls and 12 HTTP attempts.  The allowed
three A runs are exhausted; the 30k B run is intentionally **not run** because
no A satisfies both length and full editorial acceptance.

## Artifact integrity

| Bundle | SHA-256 |
| --- | --- |
| `scenario-live-293-a1-20260930-134000-safe.zip` | `7d39fd132c6003e00c424b79a604fab3cbd851a7e6ff007e865e21a67488fc05` |
| `scenario-live-293-a2-20260930-135000-safe.zip` | `21e06ad4a281254750f013f2420d056b5c7e5688d4b007e7383c52f3d97db974` |
| `scenario-live-293-a3-20260930-140000-safe.zip` | `648065fc9838e267e7a0d142646e45f1c5e2d054927f1aa33a787ca5e0576f6b` |

Each `*-safe.zip` is freshly packaged from its published directory after
omitting the disposable `runtime-root`; the original local bundle was never
published. `30-assembly.json` is authoritative for the runtime Python-length and
assembled-string SHA.  A1 predates the LF-only capture fix: its copied
`scenario.txt` has a different raw-file SHA because of CRLF serialisation,
while its assembly SHA still identifies the original runtime string.  A2 and
A3 `scenario.txt` bytes match their assembly SHA exactly.

The complete paragraph-by-paragraph editorial audit and map-to-prose coverage
are in [EDITORIAL_AUDIT.md](EDITORIAL_AUDIT.md).  No credentials, account
settings, Authorization headers, cookies, or hidden reasoning are included.
