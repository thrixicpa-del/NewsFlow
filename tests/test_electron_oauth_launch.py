import unittest
from pathlib import Path


class ElectronOAuthLaunchTests(unittest.TestCase):
    def test_oauth_handoff_core_is_not_started_hidden(self):
        main = Path(__file__).resolve().parents[1] / "studio-ui-remotion-verify" / "electron" / "main.ts"
        source = main.read_text(encoding="utf-8")

        self.assertIn(
            "const windowsHide = command !== 'start-youtube-channel-handoff';",
            source,
        )
        self.assertIn("windowsHide,", source)
