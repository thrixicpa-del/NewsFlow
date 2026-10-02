# #316 quality-selection fix (offline only)

## Scope and provenance

This is **offline revalidation**, not a new live acceptance and not a reconstructed
API request. Paid/HTTP provider calls in this stage: **0**. TXT triple importer is
deferred. No Scenario/Writer, identity, FastGen image/recovery, Core lock or EXE changes.

Historical evidence in `../issue-316-live-20261002` and its original-byte ZIP is
unchanged. `replay.json` evaluates **all 17 actual saved visible responses**, verifies
their Python character counts and SHA-256, and uses each request's **original
approved headline context**. New selection would change later request contexts;
the report is therefore not a newly assembled 8-case pipeline run. A response with
no valid candidate is explicitly `NO_VALID_CANDIDATE`, not invented provider success.

Reproduce with the isolated production-write guard:

```powershell
python tests/run_isolated.py tests.test_cover_quality_selection tests.replay_cover_quality_316 -q
```

The regression forbids opening sockets and verifies original evidence bytes remain
unchanged. The report helper writes only this separate evidence directory.

## Root causes and fixes

1. Claim escalation was headline-only. Both lines now enforce action escalation
   and object-bound universal scope. An unrelated source quantifier, negated scope,
   or `всё ещё` cannot license expansion. Saved response 4 rejects
   `Дороже станет весь импорт` and selects `Импортёры платят больше`.
   Source-dependent payment morphology (`оплачивают` / `платят`) avoids rejecting
   that supported narrower candidate, without licensing payments absent from source.
2. Shared words were mistaken for shared grammatical roles. A bounded local relation
   guard compares predicate bearers in source clauses, preserving field/clause
   boundaries, modifiers, explicit item-level names and limited pronoun continuations.
   Saved response 11 rejects `Москва: протест под арестом`. Replay also exposed
   `Помидоры не падают`: the falling quantity is prices, not tomatoes. This role
   transfer is rejected too. Non-political state/action fixtures and supported
   counterpart assertions protect against a phrase blacklist and false positives.
   This conservative guard is **not** a claim of complete natural-language inference;
   unresolved/inverted constructions remain outside it.
3. TABLOID previously ranked emotion ahead of specificity/literal grounding, and
   advertised any winner as strengthened. Both modes now rank factual/grounding,
   naturalness/coherence/clarity, specificity and literalness first. TABLOID compares
   with the safe STANDARD selection **from the same candidate batch**, without an
   extra API request. At least one hook/emotion/directness rubric point must improve,
   with no decrease in the other strength or safe-quality dimensions. Otherwise the
   safe baseline is returned with `tabloid_differentiation=UNAVAILABLE`,
   `degraded_result=true` and a truthful selection reason. Local fallback reports
   unavailable as well. Existing persistence stores these selection diagnostics.

All saved TABLOID batches currently lack this demonstrated differentiation; the
neutral selections are **not** claimed as enhanced. A separate supported, equal-
grounding regression proves a materially stronger hook can still be selected.
This fixes selection; it does **not** prove new live model output quality.

## Checks

- RED: initial scope/state/diagnostic regressions failed on old source; later
  action-role, comma-clause and pronoun regressions reproduced their defects.
- Python: `tests.test_cover_quality_selection`, offline report, `tests.test_covers`,
  Story Planner, Runner, Scenarios and Session: **443 PASS**.
- Native Windows isolated test harness: **PRODUCTION_WRITE_GUARD=PASS**.
- UI: **301 tests / 40 files PASS**; typecheck, Ruff, security, secrets, build,
  diff-check PASS. Dependency gate passes its configured HIGH threshold; audit
  reports one existing MODERATE advisory, not a clean zero-advisory tree.
- Frozen Core guard: **8 PASS / 1 expected stale `scriptor/bridge.py` FAIL**.
  r33 lock/package/guard are not modified and Core is not rebuilt.

## Production safety is not retroactively repaired

The historical live guard remains **FAIL / settings.json / attribution UNKNOWN**.
Current offline checks PASS do not erase it. NewsFlow Studio processes were still
running during this stage. **No further live acceptance is authorized operationally**
until Studio is closed, a clean production-settings snapshot/guard is established,
and a new disposable TEST_ROOT is confirmed. No user settings were restored or
credentials read/copied by this stage.
