# Backup and Restore

## Policy

Backups are recovery evidence, not an alternate runtime. Production state is
never a test fixture and no automated test writes the canonical
`%LOCALAPPDATA%\\NewsFlow` root. See [[Environment Isolation Contract]] and
[[ADR-002 Legacy Production Write Isolation]].

## Capture

Before a risky storage operation, record hashes for `settings.json`,
`covers-library.json`, and `footage-index-status.json` with
`scripts/check-production-integrity.ps1 -Mode Capture`. Store recovery copies
outside the active state root, timestamp them, and preserve their source and
schema marker. A disposable-state lifecycle uses `tests/backup_restore.py` and
must run below `NEWSFLOW_TEST_ROOT`.

## Restore procedure

1. Stop NewsFlow processes and capture the current state separately.
2. Compare the candidate recovery copy with current state; identify exact
   records and schema differences before a write.
3. Prefer a surgical restore of the proven damaged rows/fields. Never copy an
   entire historical settings/session file merely to recover credentials or a
   path binding.
4. Verify hashes, current identities/tombstones, restart behavior, and that
   credentials, footage, face-reference bindings, and unrelated business data
   remain intact.
5. Run the matching isolated regression and record the evidence in the
   incident.

If the comparison cannot prove scope, stop for user direction rather than
replacing production data.
