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
from pathlib import Path


def main(arguments: list[str]) -> int:
    production_local_appdata = os.environ.get("LOCALAPPDATA", "")
    with tempfile.TemporaryDirectory(prefix="newsflow-test-") as temporary:
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
        command = [sys.executable, "-m", "unittest", *(arguments or ["discover", "-s", "tests", "-q"])]
        return subprocess.run(command, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
