# Feature Flag Policy

## Purpose

Feature flags are limited to a small number of risky future workflows. They let a future implementation run beside the known-good behavior without silently replacing it.

## Current registry

| Flag | Default | Intended owner | Status |
| --- | --- | --- | --- |
| `montage_v3` | Off | Montage | Reserved; not wired to the current Fast News runtime. |
| `new_cover_workflow` | Off | Covers | Reserved; Universal V2 remains active. |
| `new_publication_scheduler` | Off | Publication | Reserved; Publication V2 remains active. |

Flags are process-local only, supplied through `NEWSFLOW_FEATURE_FLAGS` as comma-separated names. They are not persisted to settings, production storage, migrations, user sessions, build manifests or RC profiles. An omitted variable enables no flags. An unknown requested name fails closed.

## Activation rules

1. Add a flag only for a bounded risky workflow with a named owner, rollback path and regression coverage.
2. Keep stable behavior as the default path.
3. Enable a flag explicitly in a disposable TEST/RC environment first.
4. Document the verification and removal decision when promoting or retiring it.
5. Do not use flags to preserve unowned hidden branches permanently.

No flag currently changes a NewsFlow business/runtime path. Wiring one requires its own focused change, tests, and release-gate evidence.
