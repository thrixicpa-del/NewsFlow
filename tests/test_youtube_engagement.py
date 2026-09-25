import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import config
from scriptor.config import Settings
from scriptor import bridge
from scriptor.youtube_engagement import (
    build_engagement_plan,
    new_engagement_state,
    transition_engagement_step,
)


class YouTubeEngagementPlanTests(unittest.TestCase):
    def test_long_video_uses_relevant_then_latest_public_video_for_cards(self):
        plan = build_engagement_plan(
            {
                "id": "new-job",
                "channelId": "channel-a",
                "videoId": "current-video",
                "durationSeconds": 600,
            },
            [
                {
                    "videoId": "current-video",
                    "channelId": "channel-a",
                    "privacyStatus": "public",
                    "publishedAt": "2026-09-01T10:00:00+00:00",
                    "score": 1.0,
                },
                {
                    "videoId": "relevant-video",
                    "title": "Актуальный опубликованный ролик",
                    "channelId": "channel-a",
                    "privacyStatus": "public",
                    "publishedAt": "2026-08-31T10:00:00+00:00",
                    "score": 0.90,
                },
                {
                    "videoId": "latest-video",
                    "title": "Последний опубликованный ролик",
                    "channelId": "channel-a",
                    "privacyStatus": "public",
                    "publishedAt": "2026-08-30T10:00:00+00:00",
                    "score": 0.10,
                },
                {
                    "videoId": "private-video",
                    "title": "Приватный ролик",
                    "channelId": "channel-a",
                    "privacyStatus": "private",
                    "publishedAt": "2026-08-29T10:00:00+00:00",
                    "score": 0.99,
                },
            ],
            [],
        )

        self.assertEqual(
            plan["cards"],
            [
                {"videoId": "relevant-video", "videoTitle": "Актуальный опубликованный ролик", "atSeconds": 102},
                {"videoId": "latest-video", "videoTitle": "Последний опубликованный ролик", "atSeconds": 198},
            ],
        )
        self.assertEqual(plan["endScreen"]["startSeconds"], 580)

    def test_public_video_without_a_display_title_is_not_planned_for_studio(self):
        plan = build_engagement_plan(
            {"id": "new-job", "channelId": "channel-a", "videoId": "current-video", "durationSeconds": 600},
            [{"videoId": "public-without-title", "channelId": "channel-a", "privacyStatus": "public", "score": 1.0}],
            [],
        )
        self.assertEqual(plan["cards"], [])

    def test_plan_uses_at_most_five_unique_cards_and_four_unique_end_screen_elements(self):
        catalog = [{"videoId": f"video-{index}", "title": f"Опубликованный ролик {index}", "channelId": "channel-a", "privacyStatus": "public", "score": 10 - index} for index in range(6)]
        plan = build_engagement_plan({"channelId": "channel-a", "videoId": "current", "durationSeconds": 600}, catalog, [{"channelId": "channel-a", "playlistId": "playlist-1", "public": True}])
        self.assertEqual(len(plan["cards"]), 5)
        self.assertEqual(len({item["videoId"] for item in plan["cards"]}), 5)
        self.assertEqual(len(plan["endScreen"]["items"]), 4)

    def test_completed_post_cannot_return_to_pending(self):
        state = new_engagement_state("job-a", "channel-a")
        completed = transition_engagement_step(state, "post", "scheduled")

        with self.assertRaises(ValueError):
            transition_engagement_step(completed, "post", "pending")

    def test_policies_and_engagement_tasks_survive_settings_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(
                youtube_engagement_policies=[{
                    "channelId": "channel-a",
                    "enabled": True,
                    "postsEnabled": True,
                    "cardsEnabled": True,
                    "endScreensEnabled": True,
                }],
                youtube_engagement_tasks=[{
                    "jobId": "job-a",
                    "channelId": "channel-a",
                    "post": {"status": "pending"},
                }],
            )
            with patch.object(config, "config_path", return_value=path):
                config.save_settings(settings)
                restored = config.load_settings()

        self.assertEqual(restored.youtube_engagement_policies, settings.youtube_engagement_policies)
        self.assertEqual(restored.youtube_engagement_tasks, settings.youtube_engagement_tasks)

    def test_operator_can_disable_only_cards_for_one_channel(self):
        settings = Settings(analytics_channels=[{"profile_id": "channel-a", "name": "Канал A"}])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.save_youtube_engagement_policy({
                "channelId": "channel-a", "enabled": True,
                "postsEnabled": True, "cardsEnabled": False, "endScreensEnabled": True,
            })

        self.assertEqual(settings.youtube_engagement_policies, [{
            "channelId": "channel-a", "enabled": True,
            "postsEnabled": True, "cardsEnabled": False, "endScreensEnabled": True,
        }])

    def test_running_selected_task_updates_only_confirmed_studio_steps(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_engagement_tasks=[{
                "jobId": "job-a", "channelId": "channel-a", "videoId": "video-a",
                "post": {"status": "pending"}, "cards": {"status": "pending"},
                "endScreen": {"status": "pending"}, "postDraft": {"text": "Текст"},
                "plan": {"cards": [], "endScreen": {"items": []}},
            }],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task", return_value=["post", "end-screen"]):
            bridge.run_youtube_engagement({"jobIds": ["job-a"]})

        task = settings.youtube_engagement_tasks[0]
        self.assertEqual(task["post"]["status"], "scheduled")
        self.assertEqual(task["cards"]["status"], "pending")
        self.assertEqual(task["endScreen"]["status"], "done")

    def test_existing_uploaded_video_can_be_adopted_without_repeating_its_post(self):
        settings = Settings(
            youtube_publication_jobs=[{
                "id": "old-job", "title": "Уже загружен", "status": "uploaded", "channelId": "channel-a",
                "videoId": "video-a", "videoUrl": "https://www.youtube.com/watch?v=video-a",
                "post": {"status": "prepared", "text": "Старый пост"},
            }],
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.queue_existing_youtube_engagement({"jobIds": ["old-job"]})

        task = settings.youtube_engagement_tasks[0]
        self.assertEqual(task["post"]["status"], "scheduled")
        self.assertEqual(task["cards"]["status"], "skipped")

    def test_duplicate_uploaded_publication_creates_a_new_scheduled_draft(self):
        settings = Settings(youtube_publication_jobs=[{
            "id": "uploaded-job", "title": "Исходный ролик", "status": "uploaded",
            "channelId": "channel-a", "videoId": "already-uploaded",
            "videoUrl": "https://www.youtube.com/watch?v=already-uploaded",
            "videoPath": "D:/videos/source.mp4", "packageFolder": "D:/videos",
            "seoDescription": "Описание", "tags": ["новости"], "durationSeconds": 381,
        }])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.duplicate_publication_job({
                "jobId": "uploaded-job", "publishAt": "2026-09-02T11:00:00+03:00",
            })

        self.assertEqual(len(settings.youtube_publication_jobs), 2)
        clone = settings.youtube_publication_jobs[-1]
        self.assertNotEqual(clone["id"], "uploaded-job")
        self.assertEqual(clone["status"], "scheduled")
        self.assertEqual(clone["channelId"], "channel-a")
        self.assertEqual(clone["publishAt"], "2026-09-02T11:00:00+03:00")
        self.assertNotIn("videoId", clone)
        self.assertNotIn("videoUrl", clone)

    def test_task_records_why_cards_are_not_available_without_public_targets(self):
        settings = Settings(youtube_publication_jobs=[{
            "id": "new-job", "title": "Новый ролик", "status": "uploaded",
            "channelId": "channel-a", "videoId": "new-video", "durationSeconds": 381,
            "youtubePrivacyStatus": "private",
        }])

        task = bridge._queue_youtube_engagement_task(settings, settings.youtube_publication_jobs[0], {
            "text": "Текст", "status": "prepared",
        })

        self.assertEqual(task["cards"]["status"], "skipped")
        self.assertEqual(task["cards"]["reason"], "Нет другого доступного публичного ролика для подсказки")
        self.assertEqual(task["endScreen"]["status"], "pending")

    def test_existing_task_marks_empty_card_plan_as_skipped_when_reconciled(self):
        task = {
            "cards": {"status": "pending"},
            "endScreen": {"status": "pending"},
            "plan": {"cards": [], "endScreen": {"items": [{"kind": "subscribe"}]}},
        }

        reconciled = bridge.reconcile_youtube_engagement_task(task)

        self.assertEqual(reconciled["cards"]["status"], "skipped")
        self.assertEqual(reconciled["endScreen"]["status"], "pending")

    def test_reconcile_command_persists_the_explanation_in_task_history(self):
        settings = Settings(youtube_engagement_tasks=[{
            "jobId": "job-a", "channelId": "channel-a",
            "cards": {"status": "pending"}, "endScreen": {"status": "pending"},
            "plan": {"cards": [], "endScreen": {"items": [{"kind": "subscribe"}]}},
        }])
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.reconcile_youtube_engagement_tasks({"jobIds": ["job-a"]})

        self.assertEqual(settings.youtube_engagement_tasks[0]["cards"]["status"], "skipped")
        self.assertEqual(settings.youtube_publication_activity[-1]["kind"], "youtube-engagement-reconciled")

    def test_run_can_apply_only_end_screen_without_creating_post(self):
        settings = Settings(
            analytics_channels=[{"profile_id": "channel-a", "channel_id": "UC-a", "name": "Канал A"}],
            youtube_engagement_tasks=[{
                "jobId": "job-a", "channelId": "channel-a", "videoId": "video-a",
                "post": {"status": "pending"}, "cards": {"status": "skipped"},
                "endScreen": {"status": "pending"}, "postDraft": {"text": "Текст"},
                "plan": {"cards": [], "endScreen": {"items": [{"kind": "subscribe"}]}},
            }],
        )
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings"), \
             patch.object(bridge, "snapshot", return_value={}), \
             patch.object(bridge, "_youtube_channel_profile_dir", return_value=Path("C:/profiles/channel-a")), \
             patch.object(bridge, "execute_studio_task", return_value=["end-screen"]) as execute:
            bridge.run_youtube_engagement({"jobIds": ["job-a"], "steps": ["end-screen"]})

        self.assertEqual(settings.youtube_engagement_tasks[0]["post"]["status"], "pending")
        self.assertEqual(settings.youtube_engagement_tasks[0]["endScreen"]["status"], "done")
        self.assertEqual(execute.call_args.kwargs["action_kinds"], {"end-screen"})
