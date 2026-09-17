"""Run NewsFlow Python tests with a disposable, fail-safe storage boundary.

Use from the repository root:
``python tests/run_isolated.py discover -s tests -q``.
The child test process cannot resolve the user's `%LOCALAPPDATA%/NewsFlow`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

_CRITICAL_PRODUCTION_FILES = (
    "settings.json",
    "covers-library.json",
    "footage-index-status.json",
)


def _critical_storage_hashes(production_local_appdata: str) -> dict[str, str | None]:
    """Read-only inventory used to detect any accidental test write to production."""
    root = Path(production_local_appdata).expanduser() / "NewsFlow"
    hashes: dict[str, str | None] = {}
    for name in _CRITICAL_PRODUCTION_FILES:
        path = root / name
        hashes[name] = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashes


def main(arguments: list[str]) -> int:
    production_local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not production_local_appdata:
        raise RuntimeError("LOCALAPPDATA is required to establish the production integrity boundary.")
    runner = "unittest"
    if arguments[:1] == ["--pytest"]:
        runner = "pytest"
        arguments = arguments[1:]
    before = _critical_storage_hashes(production_local_appdata)
    # Electron/Chromium can release an isolated cache handle a moment after its
    # process exits on Windows. The directory is test-owned OS temp state, so a
    # delayed OS cleanup is safe; a lock must not mask a passed test result.
    with tempfile.TemporaryDirectory(prefix="newsflow-test-", ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        environment = os.environ.copy()
        environment.update({
            "NEWSFLOW_TEST_MODE": "1",
            "NEWSFLOW_TEST_ROOT": str(root),
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": production_local_appdata,
            "LOCALAPPDATA": str(root),
            "TEMP": str(root),
            "TMP": str(root),
        })
        if runner == "pytest":
            command = [sys.executable, "-m", "pytest", *(arguments or ["-q"])]
        else:
            command = [sys.executable, "-m", "unittest", *(arguments or ["discover", "-s", "tests", "-q"])]
        result = subprocess.run(command, env=environment, check=False).returncode
    after = _critical_storage_hashes(production_local_appdata)
    if after != before:
        changed = ", ".join(name for name in _CRITICAL_PRODUCTION_FILES if before[name] != after[name])
        print(f"PRODUCTION_WRITE_GUARD=FAIL changed={changed}", file=sys.stderr)
        return 91
    print("PRODUCTION_WRITE_GUARD=PASS")
    return result


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
