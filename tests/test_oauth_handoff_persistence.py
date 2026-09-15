import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import config


class OAuthHandoffPersistenceTests(unittest.TestCase):
    def test_pending_handoff_survives_settings_reload(self):
        settings = config.Settings()
        settings.youtube_oauth_pending_handoffs = {
            "profile-a": {
                "sessionId": "a" * 32,
                "pollCapability": "b" * 32,
                "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?state=x",
                "expiresAt": "2026-09-01T00:00:00+00:00",
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        pending = getattr(restored, "youtube_oauth_pending_handoffs", {})
        self.assertIn("profile-a", pending)
        self.assertEqual(pending["profile-a"]["pollCapability"], "b" * 32)
