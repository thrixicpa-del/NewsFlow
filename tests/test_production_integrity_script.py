from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-production-integrity.ps1"


@unittest.skipUnless(os.name == "nt", "Windows PowerShell runner contract")
class ProductionIntegrityScriptTests(unittest.TestCase):
    def test_file_mode_explicitly_loads_the_hash_cmdlet_for_a_child_process(self) -> None:
        with tempfile.TemporaryDirectory(prefix="newsflow-integrity-script-") as directory:
            root = Path(directory) / "state"
            root.mkdir()
            (root / "settings.json").write_text("{}", encoding="utf-8")
            snapshot = Path(directory) / "inventory.json"
            host = Path(os.environ["WINDIR"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

            result = subprocess.run(
                [
                    str(host),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-Mode",
                    "Capture",
                    "-ProductionRoot",
                    str(root),
                    "-SnapshotPath",
                    str(snapshot),
                ],
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertTrue(snapshot.is_file())

    def test_hashing_does_not_depend_on_a_lazy_powershell_cmdlet(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("System.Security.Cryptography.SHA256", script)
        self.assertNotIn("Get-FileHash", script)
