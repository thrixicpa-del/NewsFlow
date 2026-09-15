import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from scriptor.config import (ChromeSession, FastGenKey, LumeanKey, OpenAIKey, SecretVoicerKey, Settings, VoiceGenKey,
                             load_settings, save_settings)


class SettingsTests(unittest.TestCase):
    def test_parallel_saves_keep_settings_json_valid(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            def save_one(number: int):
                save_settings(Settings(idea_custom_text=f"parallel-{number}"))
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(save_one, range(16)))
            restored = load_settings()
            self.assertTrue(restored.idea_custom_text.startswith("parallel-"))
            settings_folder = Path(folder) / "NewsFlow"
            self.assertFalse(list(settings_folder.glob("*.tmp")))

    def test_sessions_round_trip(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            settings = Settings(
                chrome_sessions=[ChromeSession("Основная", "profile-one", True, "exhausted")],
                idea_topics=["Мифология", "История"],
                idea_prompts=[{"name": "Обложки", "topic": "Мифология", "prompt": "Короткие названия"}],
                idea_chat_bindings=[{"topic": "Мифология", "profile_id": "profile-one",
                                     "chat_url": "https://claude.ai/chat/example"}],
                seo_chat_bindings=[{"profile_id": "profile-one", "chat_url": "https://claude.ai/chat/seo"}],
                cover_chat_bindings=[{"profile_id": "profile-one", "chat_url": "https://claude.ai/chat/covers"}],
                media_chat_bindings=[{"profile_id": "profile-one", "mode": "video",
                                      "chat_url": "https://claude.ai/chat/video"}],
                media_styles=[{"mode": "image", "name": "Кино", "style": "Драматичный свет"}],
                scenario_templates=[{"name": "Документальный", "topic": "Мифология", "template": "Текст {title}"}],
                range_templates=[{"name": "Два блока", "topic": "Мифология", "ranges": [
                    {"start": 1, "end": 5, "prompt": "Коротко"}
                ]}],
                cover_api_keys=[FastGenKey("Основной", "fastgen-secret", True)],
                openai_api_keys=[OpenAIKey("Резерв", "sk-test-secret", True)],
                secret_voicer_keys=[SecretVoicerKey("Озвучка", "secret-voicer-test", True)],
                lumean_api_keys=[LumeanKey("Lumean", "lumean-test", True)],
                voicegen_api_keys=[VoiceGenKey("VoiceGen", "voicegen-test", True)],
                voice_profiles=[{"name": "Диктор", "voice_id": "voice-news", "stability": .2, "style": .7}],
                idea_plan=[{"topic": "Тема", "count": 12, "provider": "openai", "key_label": "Резерв"}],
                idea_target_count=100,
                idea_include_custom=True,
                idea_custom_text="Моя первая идея",
                auto_montage_enabled=True,
                openai_model="gpt-5.6",
            )
            save_settings(settings)
            restored = load_settings()
            self.assertEqual(restored.chrome_sessions[0].label, "Основная")
            self.assertEqual(restored.chrome_sessions[0].profile_id, "profile-one")
            self.assertTrue(restored.active_sessions)
            self.assertEqual(restored.chrome_sessions[0].limit_status, "exhausted")
            self.assertEqual(restored.idea_topics, ["Мифология", "История"])
            self.assertEqual(restored.idea_prompts[0]["topic"], "Мифология")
            self.assertEqual(restored.idea_chat_bindings[0]["profile_id"], "profile-one")
            self.assertEqual(restored.seo_chat_bindings[0]["chat_url"], "https://claude.ai/chat/seo")
            self.assertEqual(restored.cover_chat_bindings[0]["chat_url"], "https://claude.ai/chat/covers")
            self.assertEqual(restored.media_chat_bindings[0]["mode"], "video")
            self.assertEqual(restored.media_styles[0]["name"], "Кино")
            self.assertEqual(restored.scenario_templates[0]["template"], "Текст {title}")
            self.assertEqual(restored.range_templates[0]["ranges"][0]["end"], 5)
            self.assertEqual(restored.cover_api_keys[0].secret, "fastgen-secret")
            self.assertEqual(restored.openai_api_keys[0].secret, "sk-test-secret")
            self.assertEqual(restored.secret_voicer_keys[0].secret, "secret-voicer-test")
            self.assertEqual(restored.lumean_api_keys[0].secret, "lumean-test")
            self.assertEqual(restored.voicegen_api_keys[0].secret, "voicegen-test")
            self.assertEqual(restored.voice_profiles[0]["voice_id"], "voice-news")
            self.assertEqual(restored.idea_plan[0]["count"], 12)
            self.assertEqual(restored.idea_target_count, 100)
            self.assertTrue(restored.idea_include_custom)
            self.assertEqual(restored.idea_custom_text, "Моя первая идея")
            self.assertTrue(restored.auto_montage_enabled)
            self.assertEqual(restored.openai_model, "gpt-5.6")


if __name__ == "__main__":
    unittest.main()
