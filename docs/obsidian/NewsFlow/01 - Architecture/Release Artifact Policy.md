# Release Artifact Policy

## Immutable candidates

Every TEST, RC, or STABLE package is created under a commit-addressed directory:

```text
NewsFlow-<version>-<channel>-rc<NN>-<short-git-sha>
```

The directory is reserved before any build work starts. A duplicate reservation fails; a candidate is never overwritten in place. A failed candidate remains inspectable instead of being silently replaced.

Each artifact directory contains:

- `build-manifest.json`: application version, full Git SHA and branch, current core-bin SHA-256, storage schema version, lockfile SHA-256, build timestamp and channel;
- `artifact-hashes.json`: SHA-256 and byte size of the packaged EXE and every delivered file;
- the packaged application and its `win-unpacked` runtime when produced.

## Creating a candidate

Use a deliberately chosen output root on a non-production volume. The package wrapper refuses to build without one:

```powershell
pnpm --dir studio-ui-remotion-verify package:preview -- --output-root 'D:\NewsFlow Studio\Candidates'
pnpm --dir studio-ui-remotion-verify package:release -- --output-root 'D:\NewsFlow Studio\Candidates'
```

The wrapper reserves the immutable destination, runs the applicable source/runtime/security checks, packages into a disposable sibling staging directory, verifies native portable resources, copies successful results into the reserved destination and writes the final artifact hashes. The staging directory is removed after the attempt; the immutable candidate directory is retained for evidence.

`NEWSFLOW_RC_OUTPUT_ROOT` may be used instead of `--output-root` in controlled CI. The package configuration's `release-staging` directory is never a deliverable and must not be shared as a release candidate.

## Safety boundary

Artifact preparation and packaging do not launch NewsFlow, read production settings, credentials, media indexes or user data. Production integrity verification remains a separate release gate before and after any future packaging action.
