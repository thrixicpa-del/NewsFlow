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

    def test_frozen_core_returns_the_electron_correlation_id(self):
        """A rebuilt core must retain the bridge trace contract used by IPC."""
        core = _frozen_core()
        result = subprocess.run(
            [
                str(core), "add-topic",
                json.dumps({"topic": "Frozen trace fixture", "_actionTrace": {"id": "frozen-action-17"}}),
            ],
            cwd=core.parent,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual("frozen-action-17", json.loads(result.stdout)["actionTrace"]["id"])

    def test_frozen_core_trace_never_writes_a_payload_secret(self):
        from scriptor.observability import action_trace_path

        core = _frozen_core()
        action_id = "frozen-redaction-17"
        result = subprocess.run(
            [
                str(core), "add-topic",
                json.dumps({
                    "topic": "Frozen secret fixture", "apiKey": "sk-frozen-secret",
                    "_actionTrace": {"id": action_id},
                }),
            ],
            cwd=core.parent,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        records = [
            line for line in action_trace_path().read_text(encoding="utf-8").splitlines()
            if action_id in line
        ]
        self.assertEqual(2, len(records))
        self.assertNotIn("sk-frozen-secret", "\n".join(records))
