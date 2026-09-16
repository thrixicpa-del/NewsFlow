from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"


class BuildManifestTests(unittest.TestCase):
    def test_manifest_has_traceable_release_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "build-manifest.json"
            result = subprocess.run(["node", "scripts/write-build-manifest.mjs", "--output", str(target), "--type", "TEST"], cwd=APP, capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            manifest = json.loads(target.read_text(encoding="utf-8"))
        for key in ("appVersion", "gitSha", "gitBranch", "coreBinSha256", "buildTimestamp", "storageSchemaVersion", "lockfileSha256", "buildType"):
            self.assertIn(key, manifest)
        self.assertEqual("TEST", manifest["buildType"])

