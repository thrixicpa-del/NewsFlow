# Build Manifest and Verification

## Authority

Every immutable TEST, RC, or STABLE artifact contains `build-manifest.json`
and `artifact-hashes.json`. The package wrapper writes them only after it has
reserved the commit-addressed destination described in [[Release Artifact
Policy]]. `studio-ui-remotion-verify/scripts/verify-immutable-rc.mjs`
independently checks them before packaged smoke.

## Manifest contract

The manifest identifies the application version, full Git revision and branch,
storage schema, lockfile hash, selected current core-bin hash, build timestamp,
and channel. The hash inventory records every delivered file's relative path,
byte size, and SHA-256.

Verification rejects a missing EXE, an unsafe/non-relative delivered path, a
missing listed file, a byte-size mismatch, a SHA mismatch, or disagreement
between artifact identity and manifest identity. A successful source build is
not a substitute for this verification.

## Operator procedure

1. Run [[Release Gate]] with a clean worktree and an explicit non-production
   output root.
2. Retain the candidate directory and its manifests as evidence; never replace
   it in place.
3. Run packaged smoke with an explicit disposable `NEWSFLOW_TEST_ROOT`.
4. If verification fails, keep the artifact for diagnosis, fix the root cause
   in source, and create a new candidate number.

Build preparation never imports production settings, credentials, media,
business state, or old core binaries.
