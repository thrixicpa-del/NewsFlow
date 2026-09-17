from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "studio-ui-remotion-verify"


class ReleaseChannelTests(unittest.TestCase):
    def test_stable_channel_requires_release_gate_and_manual_acceptance(self):
        result = subprocess.run(
            ["node", "scripts/describe-release-channel.mjs", "--channel", "STABLE"],
            cwd=APP,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        policy = json.loads(result.stdout)
        self.assertEqual("STABLE", policy["name"])
        self.assertTrue(policy["requiresReleaseGate"])
        self.assertTrue(policy["requiresManualAcceptance"])
        self.assertFalse(policy["allowsAutoUpdate"])
