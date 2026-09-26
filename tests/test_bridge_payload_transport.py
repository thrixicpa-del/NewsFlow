"""Regression coverage for long Electron-to-Core command payloads."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BridgePayloadTransportTests(unittest.TestCase):
    def test_large_template_payload_uses_the_short_environment_file_transport(self):
        """A long template must not be placed on the Windows process command line."""
        template = "Правило сценария {title}. " + ("Контекст без потери смысла. " * 4_000)
        payload_path = Path(os.environ["NEWSFLOW_TEST_ROOT"]) / "bridge-payload.json"
        payload_path.write_text(json.dumps({"template": template}, ensure_ascii=False), encoding="utf-8")
        environment = os.environ.copy()
        environment["NEWSFLOW_BRIDGE_PAYLOAD_FILE"] = str(payload_path)

        result = subprocess.run(
            [sys.executable, "-m", "scriptor.bridge", "save-template"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        settings_path = Path(os.environ["NEWSFLOW_TEST_ROOT"]) / "NewsFlow" / "settings.json"
        persisted = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertEqual(template.strip(), persisted["template"])

    def test_electron_core_transport_keeps_json_payload_off_the_command_line(self):
        source = (ROOT / "studio-ui-remotion-verify" / "electron" / "main.ts").read_text(encoding="utf-8")

        self.assertIn("NEWSFLOW_BRIDGE_PAYLOAD_FILE", source)
        self.assertNotIn("command, JSON.stringify(payload)", source)
        self.assertNotIn("'scriptor.bridge', command, JSON.stringify(payload)", source)


if __name__ == "__main__":
    unittest.main()
