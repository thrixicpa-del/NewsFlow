# Security Gates

## Local and release controls

- `python scripts/secret-scan.py` scans tracked text files and reports only a path, line and rule — never a matched value.
- `.gitleaks.toml` extends the upstream default rules. CI should run Gitleaks against the checked-out commit history as well as the local source scan.
- `pnpm audit --prod --audit-level=high` is the Node production dependency policy. Phase 19 pins the audited safe transitive versions `js-yaml@4.3.2` and `fast-uri@3.1.6` in `studio-ui-remotion-verify/pnpm-workspace.yaml`; direct dependency majors remain unchanged.
- `scripts/audit-python-dependencies.ps1` requires `pip-audit` and evaluates `requirements.txt` with `--strict`. CI installs the auditor as a tooling dependency, not into NewsFlow user data.

`verify:security` is a release prerequisite. It checks Electron source settings, renderer-to-core allow-list parity, trusted IPC handling, navigation control, CSP and the filesystem-open capability boundary. `verify:secrets` is added by the local quality gate in Phase 20.

## Electron boundary

The renderer is sandboxed, has context isolation, and receives only the documented preload API. Every invoke handler verifies that it came from the current local `file:` window. Generic bridge commands are rejected unless listed in both the renderer contract and Electron allow-list.

`openPath` is not a generic renderer filesystem primitive. The main process records only existing absolute paths emitted by the current core response, then permits opening exactly those recorded values. Dialogs remain user-initiated native operations. Remote navigation is denied; HTTP(S) new-window attempts are delegated to the platform browser rather than a privileged Electron child window.

## Hosted controls

- `codeql.yml` scans Python and JavaScript/TypeScript on pull requests, main pushes and a weekly schedule when GitHub code scanning is available. The hosted upload is non-blocking on this private repository because the entitlement is unavailable; local security gates remain required and fail closed in CI/release gate.
- `dependency-review.yml` checks newly introduced high-severity runtime dependency vulnerabilities on pull requests when GitHub Advanced Security is available. The hosted action is non-blocking on this private repository because GitHub reports it unsupported without that plan; local dependency audits remain required and fail closed in CI/release gate.
- `dependabot.yml` opens reviewable weekly dependency pull requests and ignores automatic SemVer-major version updates. No bot is allowed to merge directly to `main`.

GitHub repository branch protection must mark the applicable workflow checks as required; this is a repository-admin action and is tracked by the CI/operations phase.
