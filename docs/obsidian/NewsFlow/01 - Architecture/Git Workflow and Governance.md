# Git Workflow and Governance

## Branch policy

| Prefix | Purpose |
| --- | --- |
| `feature/` | Bounded user-facing capability. |
| `fix/` | Product defect with a regression test. |
| `infra/` | Tooling, CI, test and release infrastructure. |
| `test/` | Test-only or fixture work. |
| `release/` | Immutable candidate preparation. |
| `engineering/` | Transitional engineering-wide initiatives; the current baseline branch is `engineering/infrastructure`. |

`main` is the known-good baseline. Changes are developed in a dedicated branch and linked worktree, verified, reviewed through a pull request, and merged linearly where repository policy permits.

## Commit policy

Use Conventional Commit-style prefixes:

- `feat:` user-visible capability
- `fix:` product defect
- `test:` regression or test infrastructure
- `chore:` repository/tooling maintenance
- `build:` packaging or build metadata
- `ci:` hosted automation
- `security:` security controls
- `docs:` documentation only

Each commit must be focused, have a matching test/evidence boundary, and exclude credentials, production state, generated media and local builds.

## Required pull-request evidence

The PR template requires runtime scope, tests, storage safety and rollback evidence. A bug report cannot close without a regression-test location or an explicit documented reason why testing is impossible.

## Main protection limitation

On 2026-09-15 GitHub returned HTTP 403 for private-repository branch protection on the current account plan. The repository remains private; it must not be made public to work around this limitation. Until an eligible plan is available, follow the policy manually:

1. Never force-push or delete `main`.
2. Work only on a prefixed branch in a linked worktree.
3. Open a PR before merging to `main`.
4. Require the relevant local/CI gates and a recorded rollback commit or tag.

When GitHub plan support is available, configure PR-required merging, no force-push, no deletion, linear history and real CI checks only.

## Linked worktree workflow

One task uses one branch and one linked worktree. Never run two Codex sessions against the same physical checkout.

```powershell
# Create a new isolated task checkout from main.
.\scripts\worktree-new.ps1 -Kind fix -TaskName cover-retry

# List registered checkouts and their branches.
.\scripts\worktree-list.ps1

# Safe removal refuses arbitrary paths and dirty worktrees by default.
.\scripts\worktree-remove.ps1 -WorktreeName fix-cover-retry
```

The helper only permits the branch categories in this document and places worktrees in the Git-ignored `.worktrees` directory. `-Force` is explicit and must not be used for a worktree containing uncommitted work.
