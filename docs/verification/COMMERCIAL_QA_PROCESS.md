# NewsFlow Commercial QA Process

This document is the canonical commercial QA/release policy for NewsFlow. It is referenced by the root `AGENTS.md` and must be followed by Codex and human reviewers.

## Three verification levels

```text
FAST
source / unit / service / storage / contract / integration
        ↓
SYSTEM
DEV E2E / regression / visual / accessibility / media / performance / safety / CI
        ↓
RELEASE
packaged EXE / clean Windows / real providers / full acceptance / STABLE
```

A normal bug or feature does **not** require a packaged EXE after every change. Package/release checks are concentrated at RC/release time unless the specific change touches packaging, bundled runtime/resources, frozen core, installer behavior, or another release-only surface.

## 1. Development-time fast tests

Run fast source-level tests during implementation:

- Python/core: `pytest` and the relevant unit/service/storage suites.
- React: Vitest + React Testing Library.
- Prefer a regression test for a bug before the fix.
- Keep the implementation minimal and scoped.

## 2. Contract tests

Verify the boundary:

`React -> IPC -> Electron bridge -> Python/Frozen Core`

New UI must not accidentally call legacy handlers, and frontend/backend contracts must remain aligned.

## 3. Integration tests

Exercise multiple real components together, for example:

`UI action -> backend -> service/worker -> storage -> result`

## 4. DEV E2E

Use Playwright + Electron against the development application without packaging an EXE. Exercise real controls, forms, process launches, and state transitions such as:

`IDLE -> LOADING/RUNNING -> SUCCESS/ERROR`

## 5. Regression testing

Every discovered bug should leave a durable regression test when technically practical. Regressions apply across Ideas, Scripts, Voice, Covers, Montage, Publication, storage, migrations, packaging, and shared infrastructure.

## 6. Visual regression

For approved UI surfaces, keep screenshot baselines and use Playwright/visual comparison to detect unintended pixel differences. This is especially important during UI/UX rebuilds.

## 7. Accessibility and UX automation

Automate baseline checks for:

- focus and keyboard navigation;
- disabled/loading/error states;
- readable and reachable primary actions;
- absence of dead UI;
- applicable accessibility rules.

## 8. Golden dataset tests

Use fixed known inputs with expected outputs for deterministic or semi-deterministic behavior, including scripts, montage decisions, file processing, and other functions where an accepted reference can be defined.

## 9. Media tests

Use FFmpeg/FFprobe to verify media output, including as applicable:

- video and voice duration;
- streams and codecs;
- resolution/frame properties;
- no truncated voice;
- correct terminal clip;
- montage integrity.

## 10. Performance regression

Track meaningful regressions in startup, large lists, file processing, montage, and other expensive paths. A new version must not silently become materially slower without an understood trade-off.

## 11. Soak and resource-leak tests

Run long/repeated workloads where relevant and check memory, child processes, file handles, stuck workers, and resource accumulation.

## 12. Migration tests

Verify storage/settings/schema migration from old supported data to the new version without silent loss or corruption.

## 13. Backup / Restore tests

Do not treat the existence of a backup file as sufficient. Exercise actual restore/recovery behavior and verify the restored state.

## 14. Failure / Chaos tests

Inject realistic failures such as:

- missing files;
- FFmpeg failure;
- unavailable provider;
- timeout;
- inaccessible disk/path;
- worker/process termination.

Verify NewsFlow reaches a controlled `ERROR`/recoverable state instead of corrupting data or hanging indefinitely.

## 15. Production-safety tests

Automated tests must use disposable/test storage. Verify the production-write guard and ensure tests cannot modify real:

- settings;
- sessions/queues;
- covers;
- footage/media;
- credentials/tokens/OAuth state.

## 16. Security tests and gates

Run the applicable security gates:

- secret scanning;
- dependency audit;
- CodeQL or equivalent static analysis where configured;
- Electron security checks;
- unsafe dependency/configuration review.

## 17. CI testing

After push/PR, critical checks must run again in GitHub Actions or the project's independent CI environment. A local or Codex-reported PASS is not a substitute for CI evidence.

## 18. Release Gate

The release gate (including `release-gate.ps1` where applicable) aggregates critical release checks. A required `FAIL` or `UNKNOWN` blocks RC/release acceptance.

## 19. Packaged smoke tests

Only after source-level gates are green, or when packaging itself changed, build the EXE/RC and validate the packaged runtime:

- bundled/frozen core;
- Electron/Python bridge;
- FFmpeg/resources;
- startup;
- primary packaged actions.

## 20. Clean Windows / Windows Sandbox

Validate the build outside the developer machine. Check installation/first run and prove there is no accidental dependency on local developer paths (for example `C:\\Users\\... `), locally installed Python/Node, dev tools, or unbundled files.

## 21. Real-provider smoke tests

Run controlled real checks for OpenAI, YouTube, or other providers when relevant. These are not required after every commit, especially when they consume money or quota.

## 22. Manual exploratory testing

Use NewsFlow as a real user, moving through:

`Ideas -> Scripts -> Voice -> Covers -> Montage -> Publication`

Look for failures that deterministic automation may not anticipate.

## 23. Full real acceptance

Before STABLE, run the genuine end-to-end pipeline:

`Topic -> Script -> Voice -> Cover -> Montage -> SEO/Tags -> YouTube private/unlisted`

This is real acceptance, not a mock-only substitute.

## 24. Release acceptance

For the final candidate, require:

- packaged EXE;
- clean environment validation;
- release manifest;
- hashes;
- changelog;
- rollback point.

Only then may the release be declared `STABLE`.

---

# Normal issue merge gate

A normal issue/bug/feature can merge to `main` after all **relevant** FAST + SYSTEM checks are green. The expected flow is:

1. issue + acceptance criteria;
2. dedicated branch;
3. root-cause analysis;
4. RED regression test when practical;
5. minimal implementation/fix;
6. targeted tests;
7. relevant full backend regression;
8. relevant frontend/contract tests;
9. typecheck;
10. Ruff/lint;
11. production/integrity guards when state can be written;
12. secret scan;
13. `git diff --check`;
14. real isolated smoke when the behavior needs runtime evidence;
15. evidence/manifest/logs/screenshots/media as applicable;
16. full diff review;
17. documentation/issue update;
18. commit + push;
19. PR;
20. independent CI;
21. Windows-native validation;
22. merge to `main`;
23. post-merge verification;
24. close the issue.

A gate that genuinely does not apply may be marked N/A, but the PR must state why.

# Release gate

RC/STABLE is a separate stricter gate:

`main green -> release-gate -> packaged EXE -> clean Windows -> controlled real providers -> manual exploratory -> full real acceptance -> release artifacts -> STABLE`

Do not turn the release gate into a per-bug packaging tax. Conversely, do not use a green source-level issue as evidence that a release candidate is STABLE.

# Evidence rules

- Report exact commands, counts, failures/skips, artifacts, and commit SHA where possible.
- Do not report tests as PASS if they were skipped, not run, or blocked by an earlier RED.
- A tool/agent summary is not evidence by itself; reviewers must inspect the relevant diff and actual gate results.
- Preserve evidence for real media/acceptance smokes in the project's established artifact/manifest location.
- Never include secrets, access tokens, private credentials, or private production media in evidence.
