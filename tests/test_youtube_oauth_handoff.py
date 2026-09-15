import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from scriptor.youtube_oauth import open_channel_authorization, start_cloudflare_channel_authorization
from scriptor.config import Settings
from scriptor import bridge, youtube_oauth


class CloudflareOAuthHandoffTests(unittest.TestCase):
    def test_start_persists_handoff_session_for_recovery_after_restart(self):
        settings = Settings(
            youtube_oauth_service_url="https://a.tinkbro.online",
            analytics_channels=[{"profile_id": "profile-a", "name": "Канал"}],
        )
        session = youtube_oauth.CloudflareOAuthSession(
            session_id="a" * 32,
            poll_capability="b" * 32,
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth?state=x",
            expires_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "start_cloudflare_channel_authorization", return_value=session), \
             patch.object(bridge, "open_channel_authorization"), \
             patch.object(bridge, "chrome_path", return_value=Path("C:/Chrome/chrome.exe")):
            bridge.start_youtube_channel_handoff({"index": 0, "includeMonetary": False})

        pending = getattr(settings, "youtube_oauth_pending_handoffs", {})
        self.assertIn("profile-a", pending)
        self.assertEqual(pending["profile-a"]["sessionId"], "a" * 32)

    def test_recovery_collects_ready_handoff_into_local_oauth_token(self):
        settings = Settings(
            youtube_oauth_service_url="https://a.tinkbro.online",
            analytics_channels=[{"profile_id": "profile-a", "name": "Ожидает", "status": "Ожидает подтверждение в Google"}],
            youtube_oauth_pending_handoffs={"profile-a": {
                "sessionId": "a" * 32,
                "pollCapability": "b" * 32,
                "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?state=x",
                "expiresAt": "2026-09-01T00:00:00+00:00",
            }},
        )
        with patch.object(bridge, "wait_for_cloudflare_credentials", return_value={"refresh_token": "fresh"}), \
             patch.object(bridge, "fetch_google_account_email", return_value="owner@example.com"):
            recover = getattr(bridge, "recover_pending_youtube_handoffs", lambda _settings: 0)
            recovered = recover(settings)

        self.assertEqual(recovered, 1)
        self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"refresh_token": "fresh"}')
        self.assertNotIn("profile-a", settings.youtube_oauth_pending_handoffs)
        self.assertEqual(settings.analytics_channels[0]["oauth_account_email"], "owner@example.com")

    def test_recovery_preserves_consumed_credentials_before_channel_lookup(self):
        settings = Settings(
            youtube_oauth_service_url="https://a.tinkbro.online",
            analytics_channels=[{"profile_id": "profile-a", "name": "Ожидает"}],
            youtube_oauth_pending_handoffs={"profile-a": {
                "sessionId": "a" * 32,
                "pollCapability": "b" * 32,
                "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?state=x",
                "expiresAt": "2026-09-01T00:00:00+00:00",
            }},
        )
        with patch.object(bridge, "wait_for_cloudflare_credentials", return_value={"refresh_token": "fresh", "token": "short"}), \
             patch.object(bridge, "fetch_google_account_email", return_value="owner@example.com"):
            self.assertEqual(bridge.recover_pending_youtube_handoffs(settings), 1)

        self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"refresh_token": "fresh", "token": "short"}')
        self.assertNotIn("profile-a", settings.youtube_oauth_pending_handoffs)

    def test_finish_persists_credentials_before_a_channel_lookup_failure(self):
        session_payload = {
            "sessionId": "a" * 32,
            "pollCapability": "b" * 32,
            "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?state=x",
            "expiresAt": "2026-09-01T00:00:00+00:00",
        }
        settings = Settings(
            youtube_oauth_service_url="https://a.tinkbro.online",
            analytics_channels=[{"profile_id": "profile-a", "name": "Ожидает"}],
            youtube_oauth_pending_handoffs={"profile-a": dict(session_payload)},
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "wait_for_cloudflare_credentials", return_value={"refresh_token": "fresh", "token": "short"}), \
             patch.object(bridge, "fetch_google_account_email", return_value="owner@example.com"), \
             patch.object(bridge, "fetch_current_channel", side_effect=ValueError("YouTube не вернул канал")):
            with self.assertRaisesRegex(ValueError, "YouTube не вернул канал"):
                bridge.finish_youtube_channel_handoff({"index": 0, "session": session_payload})

        self.assertEqual(settings.youtube_oauth_tokens["profile-a"], '{"refresh_token": "fresh", "token": "short"}')
        self.assertNotIn("profile-a", settings.youtube_oauth_pending_handoffs)
        self.assertEqual(settings.analytics_channels[0]["oauth_account_email"], "owner@example.com")

    def test_finish_clears_the_persisted_handoff_after_token_collection(self):
        session_payload = {
            "sessionId": "a" * 32,
            "pollCapability": "b" * 32,
            "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth?state=x",
            "expiresAt": "2026-09-01T00:00:00+00:00",
        }
        settings = Settings(
            youtube_oauth_service_url="https://a.tinkbro.online",
            analytics_channels=[{"profile_id": "profile-a", "name": "Ожидает"}],
            youtube_oauth_pending_handoffs={"profile-a": dict(session_payload)},
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "wait_for_cloudflare_credentials", return_value={"refresh_token": "fresh"}), \
             patch.object(bridge, "fetch_google_account_email", return_value="owner@example.com"), \
             patch.object(bridge, "fetch_current_channel", return_value=({
                 "channelId": "UC-ready", "name": "Подключённый", "subscribers": 15, "viewsTotal": 120,
             }, {"refresh_token": "renewed"})):
            bridge.finish_youtube_channel_handoff({"index": 0, "session": session_payload})

        self.assertNotIn("profile-a", settings.youtube_oauth_pending_handoffs)

    def test_service_url_is_saved_without_creating_a_token(self):
        settings = Settings()
        with patch.object(bridge, 'load_settings', return_value=settings), patch.object(bridge, 'save_settings'):
            bridge.save_youtube_oauth_service({'serviceUrl': 'https://a.tinkbro.online'})

        self.assertEqual(settings.youtube_oauth_service_url, 'https://a.tinkbro.online')
        self.assertEqual(settings.youtube_oauth_tokens, {})

    def test_start_uses_only_profile_id_and_boolean_scope_choice(self):
        response = type('Response', (), {
            '__enter__': lambda self: self,
            '__exit__': lambda self, *_: None,
            'read': lambda self: json.dumps({
                'sessionId': 'a' * 32,
                'pollCapability': 'b' * 32,
                'authorizationUrl': 'https://accounts.google.com/o/oauth2/v2/auth?state=x',
                'expiresAt': '2026-08-31T12:10:00+00:00',
            }).encode(),
        })()
        with patch('scriptor.youtube_oauth.urllib.request.urlopen', return_value=response) as urlopen:
            session = start_cloudflare_channel_authorization(
                'https://a.tinkbro.online', 'profile-a', include_monetary=False,
            )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, 'https://a.tinkbro.online/oauth/youtube/sessions')
        self.assertEqual(session.session_id, 'a' * 32)
        self.assertIn(b'"channelProfileId": "profile-a"', request.data)
        self.assertIn(b'"includeMonetary": false', request.data)
        self.assertNotIn(b'refresh_token', request.data)
        self.assertEqual(request.get_header('User-agent'), 'NewsFlow Studio OAuth/1.0')

    @unittest.skipUnless(os.name == "nt", "Windows startup behavior")
    def test_channel_authorization_shows_the_dedicated_chrome_window(self):
        chrome = r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
        profile = Path(r'C:\\Users\\tester\\AppData\\Local\\NewsFlow\\YouTubeChannelProfiles\\profile-a')
        authorization_url = 'https://accounts.google.com/o/oauth2/v2/auth?state=test-state'

        with patch.object(youtube_oauth.subprocess, 'Popen') as popen:
            open_channel_authorization(chrome, profile, authorization_url)

        self.assertEqual(popen.call_args.args, ([
            chrome,
            f'--user-data-dir={profile}',
            '--no-first-run',
            '--no-default-browser-check',
            '--new-window',
            '--start-maximized',
            authorization_url,
        ],))
        startupinfo = popen.call_args.kwargs['startupinfo']
        self.assertEqual(startupinfo.dwFlags & youtube_oauth.subprocess.STARTF_USESHOWWINDOW,
                         youtube_oauth.subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(startupinfo.wShowWindow, 3)  # SW_SHOWMAXIMIZED


if __name__ == '__main__':
    unittest.main()
