# NewsFlow Agent Rules

These instructions apply to the entire repository. Codex and any other coding agent must read this file before changing code, tests, workflows, build logic, or release documentation.

The canonical QA and release process is documented in:
`docs/verification/COMMERCIAL_QA_PROCESS.md`

## Non-negotiable development rules

1. Work from a focused issue/task and a dedicated branch. Do not make unrelated product changes.
2. Understand and document the root cause before broad fixes.
3. For every reproducible bug, add a regression test first when practical, prove it fails for the defect (RED), then make the smallest correct fix and prove it passes (GREEN).
4. A Codex/local PASS is not sufficient evidence. Run the relevant independent gates described in the commercial QA process.
5. Tests must use disposable/test storage only. Automated tests must never mutate real NewsFlow settings, sessions, covers, footage/media libraries, credentials, OAuth state, or other production/user data.
6. Preserve and verify the React -> IPC -> Electron bridge -> Python/Frozen Core contract whenever a change crosses that boundary.
7. Review the complete diff, including adjacent defects or regression tests discovered while working in scope. Agents may fix adjacent defects only when they are clearly within the same task and are covered by tests/evidence.
8. Do not build a packaged EXE after every bug fix. Use source-level FAST/SYSTEM verification until a change actually requires packaging validation or the project is entering RC/release acceptance.
9. A normal issue may merge to `main` only after all relevant issue gates are GREEN: targeted/regression tests, applicable FAST/SYSTEM checks, lint/type/security/integrity gates, real isolated smoke/evidence when applicable, review, CI, and Windows-native validation.
10. After merge, verify `main` is healthy and close the issue only after post-merge verification.
11. RC/STABLE requires the separate RELEASE gate. Packaged EXE, clean Windows/Windows Sandbox, real-provider smoke, manual exploratory testing, full real pipeline acceptance, release manifest/hashes/changelog/rollback point are release requirements, not per-bug requirements.
12. If a required gate is FAIL or UNKNOWN, do not call the task release-ready and do not bypass the gate silently. Mark genuinely irrelevant gates N/A with a reason and evidence.

## Required issue flow

`issue/acceptance -> branch -> root cause -> RED regression -> minimal fix -> targeted tests -> relevant full regression -> applicable FAST/SYSTEM gates -> evidence -> full diff review -> commit/push -> PR -> CI + Windows-native -> merge main -> post-merge verification -> close issue`

## Required release flow

`main GREEN -> release-gate.ps1 -> packaged EXE/RC -> clean Windows -> controlled real providers -> manual exploratory -> full real acceptance -> release manifest/hashes/changelog/rollback -> STABLE`

When this file and a task description differ, follow the stricter safety/verification requirement unless the repository owner explicitly changes the policy.

## Footage relevance policy (owner clarification, 2026-10-20)

- For neutral illustrative footage, match the objects and actions in the narrated
  scene. The country where the stock was filmed is secondary: a suitable pier,
  warehouse, pump or similar object may come from another country. Do not reject
  such footage solely because of its filming location.
- Keep exact identity when the scene specifically names a person, flag, place
  or event. Do not present a generic or archival illustration as recording of
  that specific event. A politician's portrait does not illustrate an unrelated
  object merely because that politician appears in the overall topic.
- This clarification preserves licensing checks, visual relevance validation,
  diversity/history and the user's uniqueness settings.
