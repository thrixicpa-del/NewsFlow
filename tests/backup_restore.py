"""Test-only, filesystem-safe backup helpers for disposable NewsFlow state."""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

_STATE_FILES = ("settings.json", "session.json", "covers-library.json")


class BackupRestoreError(RuntimeError):
    pass


def _test_owned(root: Path) -> Path:
    test_root = Path(os.environ.get("NEWSFLOW_TEST_ROOT", "")).resolve()
    if os.environ.get("NEWSFLOW_TEST_MODE") != "1" or not str(test_root):
        raise BackupRestoreError("disposable backup requires NEWSFLOW_TEST_MODE and NEWSFLOW_TEST_ROOT")
    try:
        return root.resolve().relative_to(test_root)
    except ValueError as error:
        raise BackupRestoreError("backup root must be inside NEWSFLOW_TEST_ROOT") from error


def capture_disposable_state(root: Path) -> Path:
    _test_owned(root)
    backup = root.parent / f"{root.name}-backup"
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True)
    for name in _STATE_FILES:
        source = root / name
        if not source.is_file():
            raise BackupRestoreError(f"required state file is missing: {name}")
        shutil.copy2(source, backup / name)
    return backup


def restore_disposable_state(root: Path, backup: Path) -> dict[str, str]:
    _test_owned(root)
    _test_owned(backup)
    hashes: dict[str, str] = {}
    for name in _STATE_FILES:
        source = backup / name
        if not source.is_file():
            raise BackupRestoreError(f"backup state file is missing: {name}")
        shutil.copy2(source, root / name)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    return hashes
