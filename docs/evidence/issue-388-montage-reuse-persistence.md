# Issue #388: Montage reuse preference persistence

Base: `88eb8572a4e8a69925aa3fdd5027ac690ccb1d90`.

## Root cause and scope

Long-running Montage workers keep a Settings instance. Progress, project and
queue saves serialize that whole instance, replacing a newer operator edit of
`montage_fast_reuse_enabled`, `montage_unique_footage_percent` or
`montage_fast_reuse_ranges`. A synthetic reproduction saved enabled/50%, then
an old worker's progress save restored disabled/100%.

The operator's historical command trace confirms successful save commands but
does not record their payloads. This does not prove exactly which historical
click changed or restored the value.

The fix keeps a memory-only deep-copy baseline of exactly these three fields.
Inside the existing exclusive write lock, unchanged preferences use the latest
disk value. Explicit operator commands own only the submitted reuse fields.
Successful writes refresh the object's baseline without replacing the running
preparation's captured parameters. No footage selection, planning or rendering
algorithm changes; no migration or schema change; no pause contract changes.

Credential replacement already starts from authoritative disk data and bypasses
the reuse merge. This preserves older profiles without optional reuse fields.

## Verification

- Initial RED: all seven original persistence regressions failed on the stale
  overwrite, including repeated progress, topic ranges, explicit edits and lock
  ordering.
- Final focused persistence regressions: 10/10 PASS, with real disposable
  settings IO and bridge commands. Full snapshot generation alone is mocked to
  avoid unrelated provider/media probing.
- Independent review: no remaining findings; independently reran 10/10 PASS.
- Compatibility regression: RED reproduced `KeyError` during synthetic key
  replacement on a legacy profile; GREEN preserves its missing optional fields
  and unknown operator field.
- Persistence + API-key suite: 26/26 PASS, synthetic credentials only.
- Montage regressions: 151/151 PASS before the compatibility-only correction
  (including nine persistence regressions); related suites rerun after correction.
- Settings read/archive race: 17/17 PASS.
- Command contract + Montage render: 38/38 PASS.
- Final combined rerun after the compatibility correction and moving the ten
  regressions into the existing CI-loaded Montage module: 194/194 PASS
  (`test_montage_queue`, `test_montage_queue_lock`, `test_montage_index_integrity`,
  `test_settings_read_race`, `scriptor.test_command_contract`,
  `scriptor.test_montage_render`, `test_api_keys`).
- Montage UI: 26/26 PASS; UI contract: 12 controls/types PASS.
- Typecheck, source production build, security gate, secret scan, Ruff/release
  lint and diff check: PASS. Build emitted its existing large-JS-chunk warning.
- Native Windows smoke: separate operator process saves enabled/50% plus ranges
  and manual pause, old worker performs repeated progress saves; preferences,
  pause, progress and ProductionItem ID remain correct. No real media rendered.
- Production integrity capture/verify and isolated runner write guards: PASS.

One overly broad test assertion initially expected union merging of independent
nonempty output lists. That is not the existing storage contract and is unrelated
to reuse preferences; it was corrected to verify that each ordinary output save
still persists. No output-list business logic was changed.

GitHub rejected the initial push because this account cannot modify workflows.
No permissions were expanded and no other account was used. The new test class
was moved into the existing CI-loaded Montage test module; the workflow edit was
reverted completely before publication.

## Deliberate release boundary

Frozen Core r46 and all artifacts are unchanged. Core-owned bridge/config source
changed, so `verify:core-runtime` FAILs on stale source identity and runtime guard
is 9 PASS / 1 FAIL (repository binding check). This is intentional evidence, not
a bypass: no lock/hash/test expectation is adjusted. A new immutable Frozen and
TEST Portable build remain separate follow-up work; this source PR is draft and
must not be called release-ready while that gate is red.

No user settings, queue, sessions, keys, indexes, proxies or media were changed
by the verification. No application restart, provider call or OAuth operation.
PAID_CALLS=0. No Core or TEST EXE build.
