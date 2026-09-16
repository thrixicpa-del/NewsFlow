"""Read-only secret scan for tracked NewsFlow source files.

This lightweight local gate complements Gitleaks in GitHub Actions.  It never
prints a matched value, so a failed scan does not copy a credential into logs.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 2 * 1024 * 1024
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI-like key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
)


def tracked_files() -> Iterable[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    )
    for item in result.stdout.split(b"\0"):
        if item:
            yield ROOT / item.decode("utf-8", errors="surrogateescape")


def scan(paths: Iterable[Path]) -> list[tuple[Path, int, str]]:
    findings: list[tuple[Path, int, str]] = []
    for candidate in paths:
        try:
            if not candidate.is_file() or candidate.stat().st_size > MAX_TEXT_BYTES:
                continue
            raw = candidate.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append((candidate, line_number, label))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan tracked files without echoing credential values.")
    parser.add_argument("--path", action="append", type=Path, help="scan one explicit file (test-only support)")
    args = parser.parse_args()
    findings = scan(args.path if args.path else tracked_files())
    if findings:
        for path, line, label in findings:
            try:
                display = path.resolve().relative_to(ROOT.resolve())
            except ValueError:
                display = path.name
            print(f"SECRET_SCAN=FAIL {display}:{line} [{label}]")
        return 1
    print("SECRET_SCAN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
