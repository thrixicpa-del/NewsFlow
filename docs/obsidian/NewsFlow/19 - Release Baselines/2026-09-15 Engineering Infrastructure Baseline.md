# Engineering Infrastructure Baseline — 2026-09-15

## Safety reference

- Git baseline commit: `fe30f9b4d05a73162225a5eeb744c4e23fb34f48`
- Git baseline tag: `baseline-pre-hardening-2026-09-15`
- GitHub repository: `borovojarkadij-png/NewsFlow` (private)
- Active engineering branch: `engineering/infrastructure`
- Application version: `2.1.152`
- Storage schema: `4`
- Current frozen core: `D:\NewsFlow-RC\core-bin-2.1.152-idea-headlines-r10\NewsFlowCore\NewsFlowCore.exe`
- Current frozen core SHA-256: `ED0F5839894E8F978169A373AB4AD67E7DB7E717321DC67B6BC8B327F06DC704`

## Authoritative storage boundaries

| Environment | Root | Rule |
| --- | --- | --- |
| Production | `C:\Users\borov\AppData\Local\NewsFlow` | Never used as a test fixture or test root. |
| Test RC | `D:\NewsFlow-RC\2.1.152-publication-range-test-rc9\test-profile\NewsFlow` | Manual RC testing only; isolated from production. |
| Disposable | `D:\NewsFlow-RC\diagnostics` | Automated probes and temporary validation only. |

## Production integrity snapshot

Captured before engineering-infrastructure changes. Hashes are evidence only; this document contains no production content.

| File | SHA-256 |
| --- | --- |
| `settings.json` | `D2BBEA909CDAE376B46F81B26F257847E2446D45625746B38D559F134EBB8C20` |
| `covers-library.json` | `A68C0905C8347527080703683E02FA451D7B56D45A2FEA67E389AE8C5366BD7C` |
| `footage-index-status.json` | `821597260CEEB8099D36B8AE7110E450FCDD9448FE7D6DD877CDF782DEA24211` |

## Current tooling inventory

- Desktop: Electron 43.4.1, React/TypeScript/Vite, pnpm lockfile.
- Core: Python 3.12.10, PyInstaller 6.22.2, `requirements.txt`; no Python lockfile yet.
- Tests: pytest and Vitest/React Testing Library; current isolation helpers exist in `tests/run_isolated.py` and `studio-ui-remotion-verify/electron/test-user-data.ts`.
- Packaging: `studio-ui-remotion-verify/package.json` uses electron-builder portable packaging and an external frozen core path.
- CI: no tracked GitHub Actions workflow at this baseline.

## Known infrastructure gaps at capture

1. GitHub private-repository branch protection is unavailable on the current plan (GitHub API returns HTTP 403); do not make the repository public as a workaround.
2. No committed worktree helper workflow, unified release gate, build manifest, or CI workflow exists yet.
3. Lockfile determinism is present for pnpm, but Python dependency locking and toolchain policy are not yet formalized.
4. Production hashes must be rechecked after every infrastructure phase; hash changes alone are treated as incidents until explained.

## Rollback

To inspect the pre-hardening source without changing production data:

```powershell
git show baseline-pre-hardening-2026-09-15
git switch engineering/infrastructure
```

Never use a source rollback as a reason to restore or alter production storage.
