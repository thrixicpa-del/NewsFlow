## Summary

Describe the user-visible or infrastructure change in one paragraph.

## Scope

- [ ] This pull request uses one focused branch and one worktree.
- [ ] Production data, credentials, OAuth, footage and face libraries were not used as fixtures.
- [ ] No unrelated product behavior changed.

## Verification

- [ ] Focused regression test added or updated.
- [ ] Relevant Python tests passed.
- [ ] Relevant frontend/contract tests passed.
- [ ] Production integrity guard passed, when the change can write state.
- [ ] Packaged/core verification passed, when runtime packaging changed.

## Risk and rollback

State storage/schema implications, external-provider impact, and the commit/tag to use for rollback. Write `None` only when verified.

## Evidence

Link issue, logs, screenshots, build manifest, or test report. Do not paste secrets, tokens, or private media.
