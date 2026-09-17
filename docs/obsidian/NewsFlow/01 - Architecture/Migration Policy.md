# Migration Policy

## Current runtime wins

The current verified renderer, IPC contract, bridge, services, workers,
core-bin, and storage schema are authoritative. Legacy implementations can be
read only by an explicit, reviewed migration; they may not automatically
replace current state, handler selection, dependencies, or build contents.

## Rules

- A migration is narrowly scoped, idempotent, version/schema guarded, and
  covered by isolated restart tests.
- Preserve unknown fields and credentials where possible; do not copy old
  settings/session files wholesale when only an auth or path binding is
  required.
- Tombstones and durable ProductionItem IDs outrank title/path/time heuristics.
  A legacy row cannot become active through name/title matching.
- A migration must neither resurrect deleted items nor enqueue provider work
  for stale records.
- A schema-incompatible runtime must reject storage before it reads or writes.
- Backups are used only through [[Backup and Restore]], never as automatic
  fallback storage.

Schema-4 protection for historical Covers is the concrete precedent in
[[ADR-002 Legacy Production Write Isolation]]. Any wider schema change needs
an ADR, a backup/rollback plan, production safety evidence, and explicit user
authorization when it could affect existing data.
