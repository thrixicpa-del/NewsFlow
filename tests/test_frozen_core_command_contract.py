from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _frozen_core() -> Path:
    package = json.loads((ROOT / "studio-ui-remotion-verify" / "package.json").read_text(encoding="utf-8"))
    resource = next(item for item in package["build"]["extraResources"] if item["to"] == "core-bin")
    root = (ROOT / "studio-ui-remotion-verify" / resource["from"]).resolve()
    candidates = (root / "NewsFlowCore.exe", root / "NewsFlowCore" / "NewsFlowCore.exe")
    return next(candidate for candidate in candidates if candidate.is_file())


class FrozenCoreCommandContractTests(unittest.TestCase):
    def test_frozen_core_accepts_current_safe_command_contract(self):
        """Source support alone is insufficient: the frozen core must accept the command too."""
        core = _frozen_core()
        environment = os.environ.copy()
        for command, payload in (
            ("snapshot", {}),
            ("reject-suggested-topics", {"topics": ["nonexistent-contract-fixture"]}),
        ):
            result = subprocess.run(
                [str(core), command, json.dumps(payload)],
                cwd=core.parent,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
