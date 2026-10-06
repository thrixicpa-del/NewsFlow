"""Static regression gate for renderer → IPC → current Python action paths.

It intentionally does not call providers or workers.  The goal is to make a
dead button, unregistered command, or accidental legacy import fail before a
desktop package is created.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "studio-ui-remotion-verify" / "src"
APP_ROOT = ROOT / "studio-ui-remotion-verify"


def _literal_renderer_commands() -> set[str]:
    commands: set[str] = set()
    for source_path in UI_ROOT.rglob("*.ts*"):
        source = source_path.read_text(encoding="utf-8")
        commands.update(re.findall(r'command\("([^"]+)"', source))
    return commands


class RuntimeActionMapTests(unittest.TestCase):
    def test_every_literal_renderer_command_has_current_contract_and_bridge_dispatch(self):
        """A visible UI action cannot become a string-only/dead control."""
        commands = _literal_renderer_commands()
        self.assertGreaterEqual(len(commands), 175)
        contract = (APP_ROOT / "src" / "contracts" / "newsflowCommands.ts").read_text(encoding="utf-8")
        bridge = (ROOT / "scriptor" / "bridge.py").read_text(encoding="utf-8")
        dispatched = set(re.findall(r'(?:if|elif) command == "([^"]+)"', bridge))

        self.assertFalse(commands - dispatched, f"UI commands without bridge handler: {sorted(commands - dispatched)}")
        missing_contract = [command for command in commands if f'"{command}"' not in contract]
        self.assertFalse(missing_contract, f"UI commands without TypeScript contract: {sorted(missing_contract)}")

    def test_direct_preload_actions_have_electron_handlers_and_current_core_routes(self):
        """Dialog, snapshot, settings and OAuth APIs cannot bypass the current runtime."""
        preload = (APP_ROOT / "electron" / "preload.cts").read_text(encoding="utf-8")
        main = (APP_ROOT / "electron" / "main.ts").read_text(encoding="utf-8")
        channels = set(re.findall(r"ipcRenderer\.invoke\('([^']+)'", preload))
        handled = set(re.findall(r"handleTrusted\('([^']+)'", main))

        self.assertFalse(channels - handled, f"Preload channels without Electron handler: {sorted(channels - handled)}")
        self.assertIn("preload.cjs", main)
        self.assertIn("require('electron')", preload)
        self.assertNotIn("from 'electron'", preload)
        self.assertIn("assertTrustedIpcSender(event)", main)
        self.assertIn("assertAllowedCoreCommand(command)", main)
        self.assertIn("callCore('snapshot')", main)
        self.assertIn("callCore('save-settings', patch)", main)
        self.assertIn("callCore('start-youtube-channel-handoff'", main)
        self.assertIn("callCore('finish-youtube-channel-handoff'", main)

    def test_montage_worker_inherits_desktop_runtime_provenance(self):
        """Detached Montage and short Core calls must share one desktop runtime ID."""
        main = (APP_ROOT / "electron" / "main.ts").read_text(encoding="utf-8")

        self.assertIn("const runtimeSessionId = crypto.randomUUID()", main)
        self.assertGreaterEqual(
            main.count("NEWSFLOW_RUNTIME_SESSION_ID: runtimeSessionId"),
            2,
        )

    def test_desktop_ui_does_not_use_unsupported_browser_prompt_dialogs(self):
        """Electron does not provide browser prompt(); use NewsFlow-owned dialogs."""
        source = (APP_ROOT / "src" / "ui" / "App.tsx").read_text(encoding="utf-8")
        self.assertNotIn("window.prompt(", source)

    def test_current_bridge_path_excludes_legacy_app_and_prompt_fallbacks(self):
        """Current UI commands must not import retired desktop/prompt implementations."""
        bridge = (ROOT / "scriptor" / "bridge.py").read_text(encoding="utf-8")
        self.assertIn("from .thumbnail_prompt_v2 import", bridge)
        self.assertNotIn("from .app import", bridge)
        self.assertNotIn("from .legacy_bridge import", bridge)
        self.assertNotIn("import scriptor.app", bridge)


if __name__ == "__main__":
    unittest.main()
