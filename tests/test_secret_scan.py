from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SecretScanTests(unittest.TestCase):
    def test_rejects_a_realistic_openai_key_without_echoing_the_value(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "provider.txt"
            fake_key = "sk-proj-" + "abcdefghijklmnopqrstuvwxyz012345"
            candidate.write_text(f"OPENAI_API_KEY={fake_key}\n", encoding="utf-8")
            result = subprocess.run(
                ["python", "scripts/secret-scan.py", "--path", str(candidate)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("SECRET_SCAN=FAIL", result.stdout)
        self.assertNotIn(fake_key, result.stdout)

    def test_tracked_source_scan_passes_without_printing_sensitive_content(self):
        result = subprocess.run(
            ["python", "scripts/secret-scan.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("SECRET_SCAN=PASS", result.stdout)
