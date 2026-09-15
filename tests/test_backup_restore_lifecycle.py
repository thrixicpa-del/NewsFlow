"""Disposable end-to-end backup/restore lifecycle for NewsFlow state."""
from __future__ import annotations

import hashlib
import os
import unittest
from pathlib import Path


class BackupRestoreLifecycleTests(unittest.TestCase):
    def test_restore_replaces_corrupt_test_state_with_the_exact_captured_snapshot(self):
        from tests.backup_restore import (
            capture_disposable_state,
            restore_disposable_state,
        )

        root = Path(os.environ["NEWSFLOW_TEST_ROOT"]) / "backup-restore-lifecycle"
        root.mkdir(parents=True, exist_ok=True)
        state = {
            "settings.json": b'{"schema_version":4,"idea_results":["Current"]}',
            "session.json": b'{"version":2,"titles":["Current"],"jobs":[]}',
            "covers-library.json": b'{"format":1,"items":[{"production_item_id":"current-cover"}]}',
        }
        for name, value in state.items():
            (root / name).write_bytes(value)

        backup = capture_disposable_state(root)
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in state.items()}
        for name in state:
            (root / name).write_bytes(b"corrupt")

        restored = restore_disposable_state(root, backup)
        self.assertEqual(expected, restored)
        self.assertEqual(expected, {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in state
        })

    def test_backup_utility_rejects_any_root_outside_test_storage(self):
        from tests.backup_restore import BackupRestoreError, capture_disposable_state

        with self.assertRaises(BackupRestoreError):
            capture_disposable_state(Path(os.environ["NEWSFLOW_TEST_ROOT"]).parent / "not-test-owned")


if __name__ == "__main__":
    unittest.main()
