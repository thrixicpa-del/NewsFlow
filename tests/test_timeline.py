import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor.timeline import (TimelineClip, TimelineProject, align_timeline_to_audio, fallback_scene_plan,
                               fit_scene_plan_to_voice_duration,
                               fallback_visual_query, parse_agent_scene_plan, split_narration, remotion_payload,
                               required_video_duration, _remaining_source_duration,
                               _proxy_lock, _replace_with_retry)


class TimelineTests(unittest.TestCase):
    def test_remotion_payload_delays_voice_after_intro(self):
        project = TimelineProject("test", clips=[TimelineClip("clip.mp4", "text", "query", 2)],
                                  voiceover_path="voice.mp3", intro_path="intro.mp4", intro_duration=2,
                                  overlay_path="ticker.mp4")
        payload = remotion_payload(project)
        self.assertEqual(payload["voiceover"]["from"], 60)
        self.assertEqual(payload["sequences"][0]["kind"], "intro")
        self.assertEqual(payload["overlay"]["chromaKey"], "#00ff00")
    def test_splits_long_narration_into_short_visual_units(self):
        text = "Первая короткая фраза. Вторая фраза сообщает ещё одну новость!"
        self.assertEqual(len(split_narration(text)), 2)

    def test_voice_duration_includes_intro_before_final_export(self):
        self.assertEqual(required_video_duration(64.5, 2.0), 66.5)

    def test_remaining_source_duration_respects_source_start(self):
        self.assertEqual(_remaining_source_duration(30.0, 24.0), 6.0)
        self.assertEqual(_remaining_source_duration(30.0, -2.0), 30.0)
        self.assertEqual(_remaining_source_duration(5.0, 9.0), 0.0)

    def test_audio_alignment_preserves_existing_source_window(self):
        project = TimelineProject(
            "windowed",
            clips=[TimelineClip("long.mp4", "voice", "query", duration=4.0, source_start=6.0)],
        )
        align_timeline_to_audio(project, 4.0, [], duration_probe=lambda _path: 10.0)
        self.assertEqual(project.clips[0].source_start, 6.0)
        self.assertEqual(project.clips[0].duration, 4.0)

    def test_visual_plan_uses_full_six_second_clips_except_final_tail(self):
        scenes = [
            {"narration": "Первая длинная реплика", "visual_query_en": "news footage", "duration": 4.0},
            {"narration": "Вторая длинная реплика", "visual_query_en": "news footage", "duration": 4.0},
        ]
        result = fit_scene_plan_to_voice_duration(scenes, 18.7, max_clip_duration=6.0)
        self.assertEqual([item["duration"] for item in result], [6.0, 6.0, 6.0, 0.7])
        self.assertAlmostEqual(sum(item["duration"] for item in result), 18.7, places=2)

    def test_fallback_plan_produces_english_visual_query(self):
        plan = fallback_scene_plan("Иран обсуждает танкеры в Ормузском проливе.")
        self.assertIn("Iran", plan[0]["visual_query_en"])
        self.assertIn("oil tanker", plan[0]["visual_query_en"])

    def test_frontline_and_offensive_get_concrete_military_visual_terms(self):
        query = fallback_visual_query("На фронте началось наступление, задействованы танки и артиллерия")
        self.assertIn("frontline battlefield", query)
        self.assertIn("tanks armored vehicles", query)
        self.assertIn("artillery firing", query)

    def test_protest_and_migrant_queries_are_concrete(self):
        protest = fallback_visual_query("Рабочие объявили забастовку и вышли на митинг")
        migrants = fallback_visual_query("Мигрантов задержали на границе")
        self.assertIn("workers labor strike", protest)
        self.assertIn("migrants border crossing", migrants)

    def test_local_visual_associations_stay_concrete(self):
        query = fallback_visual_query("Переговоры России и Украины обсуждают журналисты")
        self.assertIn("diplomatic negotiations", query)
        self.assertIn("journalists cameras", query)

    def test_parses_json_plan_from_code_fence(self):
        value = '```json\n[{"narration":"Текст","visual_query_en":"oil tanker at sea","duration":3}]\n```'
        self.assertEqual(parse_agent_scene_plan(value)[0]["duration"], 3.0)

    def test_project_round_trip(self):
        project = TimelineProject("Новость", "9:16", [TimelineClip("clip.mp4", "Текст", "city", 4)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.newsflow"
            project.save(path)
            restored = TimelineProject.load(path)
        self.assertEqual(restored.aspect_ratio, "9:16")
        self.assertEqual(restored.clips[0].visual_query_en, "city")

    def test_same_proxy_uses_one_worker_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # The lock is a fresh context manager each time, but it resolves
            # the same proxy key to one shared in-process and file lock.
            # Entering it twice sequentially proves the sidecar is reusable.
            with _proxy_lock(root / "same.mp4"):
                pass
            with _proxy_lock(root / "same.mp4"):
                pass
            self.assertTrue((root / ".same.mp4.lock").exists())

    def test_publish_retries_after_a_short_windows_file_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            partial, output = root / "video.partial.mp4", root / "video.mp4"
            partial.write_bytes(b"ready")
            real_replace = __import__("os").replace
            attempts = {"value": 0}
            def transient_replace(source, target):
                attempts["value"] += 1
                if attempts["value"] == 1:
                    raise PermissionError("busy")
                return real_replace(source, target)
            with patch("scriptor.timeline.os.replace", side_effect=transient_replace), \
                    patch("scriptor.timeline.time.sleep"):
                _replace_with_retry(partial, output, timeout=1)
            self.assertTrue(output.exists())
            self.assertFalse(partial.exists())


if __name__ == "__main__":
    unittest.main()
