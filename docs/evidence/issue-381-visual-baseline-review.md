# Issue #381: proposed visual references for accepted main

## Scope

Reference-only release unblock proposal based on accepted source
`850f4c62749b2e5833d7fad87be0737a1b79f042`.
No application, Electron, Python, capture harness, tolerance, Core binding,
dependencies or immutable-artifact changes. No Core rebuild or packaging.
The references are proposed for reviewer acceptance, not an independent
assertion that every existing UI behavior is defect-free.

## RED reproduction

Canonical `scripts/release-gate.ps1 -Channel TEST -Rc 240 -OutputRoot D:\NewsFlow-RC`
failed before packaging at `dashboard-empty`: 0.565% exceeds 0.200%.
An isolated repeat with `NEWSFLOW_VISUAL_CASES=dashboard-empty` returned the
same fraction and bounds `27,33–1396,624`.

Original reference was committed in `59cf37f` (2026-09-17). It predates the
accepted `ChatGPT — темы` navigation entry (`731d47d`, 2026-10-05).
Dashboard has 7806 changed pixels: sidebar 6640, main/inspector 1166.

## Reviewed expected change groups

- All expanded desktop navigation: accepted ChatGPT topic entry shifts later
  entries and changes sidebar scrolling when expanded groups exceed height.
- Covers configuration and inspector: accepted manual import/editor,
  FastGen documented catalog including Nano Banana 2, routing and diagnostics.
  Current references still show local catalog as requiring API verification;
  capture does not pretend to obtain a live provider response.
- Footage: accepted managed proxy cache panel (`d63bc1d`) adds vertical content.
- Montage: accepted GPU timeline (`d023439`), single-column renderer selection
  and draft-save controls, and truthful historical/runtime diagnostics
  (`4170a4b`, `ac8b763`, `1bd6893`, `6472f70`).
- Voice: accepted refresh control and queue snapshot changes (`e37f712`) add
  toolbar rows and shift content vertically.
- Key discard dialog: accepted key editor/provider catalog changes alter its
  background; only the synthetic `visual-fixture-key` input is used.

Dashboard, Covers inspector/configuration/narrow, Footage, Montage
configuration/inspector, Voice empty/84 and key discard captures were directly
inspected alongside the previous references where relevant. Existing internal
horizontal scrolling in settings sheets and synthetic legacy/queue-status
presentation remain visible; no UI repair or removal of a visual case is
hidden in this reference change. Reviewer should evaluate these captures
before acceptance.

## Regeneration and verification

The existing Electron synthetic capture matrix was run in isolated TEST
storage with `NEWSFLOW_UPDATE_VISUAL_BASELINES=1`, producing all 47 cases.
Only 44 references exceeding the existing tolerance are proposed for change.
The prior `topics-narrow`, `publication-narrow` and `sidebar-collapsed`
references remain byte-for-byte unchanged: their differences were below
0.200% (0.019%, 0.082%, 0.149%).

A separate ordinary compare-mode run (update flag unset, full case matrix,
unchanged 0.200% tolerance) completed: **47/47 PASS**. The 44 proposed
references matched with zero changed pixels. The three unchanged references
matched with 0.019%, 0.082%, and 0.149% difference respectively.
Capture success in update mode alone was not used as a regression PASS.

Security/secrets and release-gate contract verification run independently.
Production integrity is checked against the pre-release capture. User
credentials, sessions and media are not included in this evidence or Git.

### Executed verification

| Check | Result |
| --- | --- |
| `pnpm run verify:workstation-visuals` ordinary full compare | PASS, 47/47 |
| `python tests/run_isolated.py tests.test_release_gate -v` | PASS, 9/9 |
| `python tests/run_isolated.py tests.test_core_runtime_guard -v` | PASS, 10/10 |
| `pnpm typecheck` | PASS |
| `pnpm verify:security` | PASS |
| `pnpm verify:secrets` | PASS |
| `scripts/release-lint.ps1` | PASS |
| Independent production-integrity verify | PASS |
| Old immutable EXE/manifest/hash inventories, including rc239 | unchanged |
| `git diff --check` | PASS |

The full Python/UI suites passed on the accepted source before the original
release gate reached its visual failure; those prior results are not
presented as a successful full release run on this branch. Fresh CI is
required on this PR. No Portable EXE or packaged title smoke ran here.

## Release boundary

User explicitly requested that the PR remain unmerged for review. rc240 must
not be built from this unaccepted branch, nor should the failed release gate
on the previous main be bypassed. After review/merge, package from the newly
accepted exact main SHA with the unchanged r45 via the full release gate.
