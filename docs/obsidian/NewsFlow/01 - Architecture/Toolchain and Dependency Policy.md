# Toolchain and Dependency Policy

## Pinned runtime

- Node.js: `24.19.0` (`.nvmrc`)
- pnpm: `11.19.0` (declared by each pnpm workspace package)
- Python: `3.12.10` (`.python-version`)
- PyInstaller: `6.22.2` (verified build environment)

`studio-ui-remotion-verify` and `oauth-site/worker` are independent pnpm projects. Each must retain its own `pnpm-lock.yaml`; installs for verification and CI use `pnpm install --frozen-lockfile` in that directory.

## Python dependencies

`requirements.txt` documents the supported dependency ranges. `requirements.lock` is the hash-locked reproducible resolution generated with `pip-tools 7.5.3` on Windows/Python 3.12.10. Regular clean-environment installation must use:

```powershell
python -m pip install --require-hashes -r requirements.lock
```

Regenerate the lock only in a disposable virtual environment, after an intentional dependency review:

```powershell
python -m pip install pip-tools==7.5.3
pip-compile --generate-hashes --strip-extras --output-file requirements.lock requirements.txt
```

The lock is source-controlled. Virtual environments, package caches, frozen core binaries, production settings, credentials, media, and user data are not.

## Verification

Run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify-toolchain.ps1
pnpm --dir studio-ui-remotion-verify install --frozen-lockfile
pnpm --dir oauth-site/worker install --frozen-lockfile
```

The toolchain guard is intentionally exact. A tool upgrade is an explicit dependency change: update the marker, affected manifests and locks together, validate clean installs, and record the reason in the pull request.

## Safety boundary

Toolchain work uses disposable environments only. It must not start NewsFlow, open production storage, read provider credentials, mutate footage indexes, or rebuild `NewsFlowCore.exe` without a separately approved release task.
