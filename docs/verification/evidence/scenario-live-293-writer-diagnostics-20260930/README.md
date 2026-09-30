# PR #293 — fixed Writer diagnostic matrix D1–D4

This is an opt-in, disposable diagnostic experiment, not a NewsFlow Scenario
acceptance result.  It uses a pre-authored fictional water-restoration fixture
to isolate the Writer's handling of concrete ordered material.  No historical
A1/A2/A3 evidence was changed.

## Frozen inputs

- Source HEAD: `087d41ee076be7537519f40fa0e31ab2a2ef6f6e`
- Fixture: `CONTROL_FIXTURE.json`, SHA-256
  `29d4920f8dbab191f22319e8e0a98b8aeb19a456465bebc969c0104e7be6e53c`
- Full user template: SHA-256
  `3bbd1058e2a7f00613e95680ada44937455f5d7836ad119ae003d49edba3c0e5`
- Short diagnostic template: SHA-256
  `bd0311ee18c180b4157b6108a726a150f4cd9c9c1961421f5976fa5e5720ca1a`
- Model returned by all four calls: `gpt-5.4-mini-2026-03-17`
- Route: `/v1/responses`; `max_output_tokens=5120`; no `tools`,
  `text.format`, or `previous_response_id`.

D1/D2 use exactly the same P1 fixture material; D3/D4 use exactly the same
P3 fixture material and fixed hand-authored P1/P2 prefix.  Within each pair,
the complete manual template is the sole intentional payload difference.  The
machine diffs are `D1-D2-payload.diff` and `D3-D4-payload.diff`.

## Result summary

| Cell | Part / template | Visible chars | Response SHA-256 | Provider status | Editorial result |
| --- | --- | ---: | --- | --- | --- |
| D1 | P1 / full | 2,516 | `d4a99fd9872956110f5647d842647a1b012b8405e6c9e807100cdcc8ccc10827` | completed | Covers all assigned steps; disclosure present; under local length target. |
| D2 | P1 / short | 1,783 | `beeb972db4ce1049ea67e575e12647698fd9079d1ec7d2976b149137db4245a4` | completed | Covers all assigned steps; disclosure present; more concise and also under target. |
| D3 | P3 / full | 3,299 | `7e2e10607721b25f529eafe6cca3c5bffef8366708f0ef87c135fea8b600ccdc` | completed | Covers all assigned steps and terminal result; no repeated opening disclosure; under target. |
| D4 | P3 / short | 2,500 | `3467c878a056c39f744c1d885b129a97ea2a25c96a5a6359377347f333cdf888` | completed | Covers all assigned steps; repeats an unneeded fictional-story notice and has an unnatural phrase; under target. |

The normal local P1/P3 guidance is roughly 3,879–4,119 characters.  All four
responses end with `status=completed`, `incomplete_details=null`, and output
usage of 632 / 442 / 797 / 601 tokens, respectively; the short responses are
not evidence of `max_output_tokens` truncation.

## Budget and safety

The preflight used a mocked transport and records `provider_calls=0` in
`09-preflight.json`.  The live matrix made exactly four logical calls and four
observed HTTP attempts.  The shared stage ledger records `D1…D4` before each
call; SDK-internal retries are `UNKNOWN`, not represented as zero.  This leaves
the task budget at 4/18 logical and 4/24 observed HTTP attempts.

`31-production-write-guard.json` and `32-secret-export-scan.json` are both
PASS.  The disposable `runtime-root` is intentionally absent from this
published directory and from its ZIP archive.  No Planner call, Scenario job,
OAuth, Covers/FastGen, YouTube, publication, Writer regeneration, or
production-state write occurred in D1–D4.

The published archive contains 46 safe evidence files; the only
`secret`-named entry is the result file `32-secret-export-scan.json`, not
secret material.

## Interpretation boundary

The matrix demonstrates that this model can disclose and narrate the supplied
fictional, concrete event chain under the current full template in D1 and D3.
It does not prove that it will create an equally good political Story Map, that
the full template is harmless in every setting, or that the current runtime is
accepted.  The detailed reading, step coverage, and decision not to spend R1
without a demonstrated runtime fix are in
[EDITORIAL_REVIEW.md](EDITORIAL_REVIEW.md).
