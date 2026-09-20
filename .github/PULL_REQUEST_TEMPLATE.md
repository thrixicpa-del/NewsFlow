## Summary

Describe the user-visible or infrastructure change in one paragraph.

> Repository policy: read `AGENTS.md` and `docs/verification/COMMERCIAL_QA_PROCESS.md` before implementation/review.

## Scope

- [ ] This pull request uses one focused branch and one worktree.
- [ ] Production data, credentials, OAuth, footage and face libraries were not used as fixtures.
- [ ] No unrelated product behavior changed.
- [ ] Root cause and acceptance criteria are documented for bug fixes.

## Verification — issue gate

- [ ] Focused regression test added or updated (or N/A with reason).
- [ ] Relevant Python/backend regression passed.
- [ ] Relevant frontend/contract tests passed.
- [ ] Integration/DEV E2E passed when the changed boundary requires it.
- [ ] Typecheck and Ruff/lint passed.
- [ ] Production integrity/write guard passed when the change can write state.
- [ ] Secret/security checks passed as applicable.
- [ ] `git diff --check` passed.
- [ ] Real isolated smoke/evidence passed when runtime behavior requires it.
- [ ] Complete diff reviewed, including adjacent in-scope fixes.
- [ ] Independent CI passed.
- [ ] Windows-native validation passed or is explicitly N/A with evidence.

## Merge and post-merge

- [ ] All relevant issue gates are GREEN; no required gate is FAIL/UNKNOWN.
- [ ] Ready to merge to `main`.
- [ ] Post-merge verification will be recorded before closing the issue.

## Release-only gate

Do **not** require an EXE after every bug. Check these only for packaging/release-relevant changes or RC/STABLE acceptance.

- [ ] Packaged/core smoke passed, or N/A.
- [ ] Clean Windows/Windows Sandbox passed, or N/A.
- [ ] Controlled real-provider smoke passed, or N/A.
- [ ] Manual exploratory/full real acceptance passed, or N/A.
- [ ] Release manifest/hashes/changelog/rollback point completed, or N/A.

## Risk and rollback

State storage/schema implications, external-provider impact, and the commit/tag to use for rollback. Write `None` only when verified.

## Evidence

Link issue, logs, screenshots, build manifest, test report, or media evidence. Do not paste secrets, tokens, or private media.
