# PR #293: immutable test-only evidence package

This directory publishes the original safe evidence from the bounded Scenario
acceptance work.  It is evidence, not a claim that either generated scenario
passed editorial acceptance.  No new API call was made while preparing it.

Every run directory contains the input ProductionItem, the selected manual
template, captured post-adapter payloads, visible responses where captured,
the persisted map/job, accepted parts, assembled scenario, metrics, the
logical/transport ledgers, the test-only capture harness, production-write
guard result, and secret-export scan.  HTTP headers and key material were not
captured (`REDACTED_NOT_CAPTURED` / `NOT_CAPTURED_MEMORY_ONLY`).  Runtime
directories, account settings, OAuth material, and production state are not
included.  The extracted harness is named `00-capture-harness.py.txt` so the
repository's source-file linter does not lint a historical artifact; its
original `.py` filename and bytes are also preserved inside the matching ZIP.

| Directory / archive | Classification | Source SHA | Provider calls | Outcome |
| --- | --- | --- | ---: | --- |
| `scenario-live-293-12k-attempt-1-20260930/` | Harness preflight, not a paid run | `5b96e90ad5ec67806e96e9409af012fb034437f8` | 0 | harness shape error; retained for provenance |
| `scenario-live-293-12k-live-1-20260930/` | Live run 1 | `a38bd29` | 2 Planner calls, 0 Writer calls | `SCHEMA_RECOVERY_EXHAUSTED`; raw visible responses are `MISSING` because this first capture harness only recorded metadata/hashes |
| `scenario-live-293-12k-live-2-20260930/` | Live run 2 | `6b4a16fe1de248ee45111ca4feb451fd54aea50d` | 1 Planner + P1/P2/P3 | 8,453 stripped Python characters, `SHORT` |
| `scenario-live-293-12k-live-3-20260930/` | Live run 3 | `b96fd6255cdf2859e7aef3be01bd790c7050743b` | 1 Planner + P1/P2/P3 | 9,343 stripped Python characters, `SHORT`; not editorially accepted |

## Archive integrity

The original archives are committed next to their extracted source evidence.
Their SHA-256 values are:

```text
scenario-live-293-12k-attempt-1-20260930.zip  77A3944BA944C7F8484E25D9FF0DEC8E7DB21BE75A8A012B7507A1CFC4D94646
scenario-live-293-12k-live-1-20260930.zip     6D8C7F746A26642325FBCA20D4DFA26AFF60AA084A1598CBA9693654EC9EF8C5
scenario-live-293-12k-live-2-20260930.zip     968530B15FD19ED8CC4CCAB25C0E43C47EF9934D6894666D4E1C7BB5C000B60F
scenario-live-293-12k-live-3-20260930.zip     A84C1D5A0095C60EB01CE3E07253C929A583D21069B0F9FB9A926A535139E70A
```

`RUN_ANALYSIS.md` separates transport facts, material transmission, length,
and editorial observations for the two completed Writer runs.  It does not
turn those observations into a runtime quality gate or a request to rewrite a
Writer segment.
