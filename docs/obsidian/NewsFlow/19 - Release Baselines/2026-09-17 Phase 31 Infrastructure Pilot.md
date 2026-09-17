# 2026-09-17 Phase 31 Infrastructure Pilot

## Scope

This pilot exercised the delivery system itself rather than changing NewsFlow
business logic. It started from the isolated
`engineering/infrastructure` worktree and used only disposable test roots and
external candidate staging.

## Scenario and regressions

The pilot found three release-path failures and turned each into a focused
regression before retrying the authoritative gate.

| Finding | Root cause | Protection | Commit |
| --- | --- | --- | --- |
| Portable build failed at NSIS include resolution | The real `StdUtils.nsh` file sat at a 273-character pnpm/worktree path, beyond NSIS `MAX_PATH`. | Packaging maps only the electron-builder step through a disposable, free `subst` drive; cleanup is in `finally`. | `0af8f6d` |
| Packaged smoke could not open CDP | The portable NSIS bootstrapper does not forward arbitrary Chromium CLI flags. | Gate launches the `win-unpacked` Electron executable from the immutable portable package for CDP smoke. | `6476f39` |
| Earlier pilot attempts exposed nested-shell, integrity-hash, pnpm-shim, visual-process and audit-tooling faults | Release orchestration assumptions did not hold under the actual Windows worktree. | Each failure has a narrow test and fix in the preceding Phase 31 commits. | `c60fd86` through `d4c8d65` |

The final candidate is bound to `6476f391`, branch
`engineering/infrastructure`, application version `2.1.152`, channel `TEST`,
and RC number `04`.

## Machine evidence

| Evidence | Result |
| --- | --- |
| Authoritative `scripts/release-gate.ps1` | `RELEASE GATE - PASS` |
| Immutable candidate verifier | `IMMUTABLE_RC_VERIFY=PASS` |
| Candidate | `D:\NewsFlow Studio\Candidates\NewsFlow-2.1.152-test-rc04-6476f391` |
| Candidate contents | 6,409 files; build manifest and artifact hashes recorded |
| Packaged Electron smoke | Passed against the candidate's `win-unpacked/NewsFlow Studio.exe` with an isolated test root |
| Allure unified report | `ALLURE_REPORT=PASS` |
| Allure lanes | Python, frontend, integration, source E2E, packaged smoke: all passed |
| Production write guard after gate and Allure | `PRODUCTION_WRITE_GUARD=PASS` |

Allure artifacts are intentionally ignored and local to this worktree:
`.artifacts/allure/20260917-173845/`.

## Hosted CI status

The GitHub Actions workflow is configured for pull requests to `main` and has
not been run by a hosted PR at the time of this local pilot. This is not a
local-gate substitute: hosted CI remains **PENDING PR** until this branch is
opened for review. The local release gate and its production checks passed.

## Safety result

No production storage, credentials, provider state, footage, face library, or
current core-bin was used as a fixture or changed by the pilot. Failed
candidate directories remain retained as immutable diagnostic evidence under
the candidate output policy; they are not release-ready artifacts.

## Follow-on

Proceed with Phase 32 current-runtime smoke and Phase 33 final engineering
audit. Do not promote this TEST candidate to `RC` or `STABLE` without the
separate manual acceptance process.
