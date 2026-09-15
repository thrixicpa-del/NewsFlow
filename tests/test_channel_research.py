from __future__ import annotations

import unittest
import os
import tempfile
from unittest.mock import patch

from scriptor.channel_research import (
    dedupe_sources,
    channel_research_state,
    recover_research_state,
    new_task,
    parse_txt_sources,
    public_result,
    serialize_results,
    transition_task,
)
from scriptor.config import Settings, load_settings, save_settings
from scriptor import bridge


class ChannelResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        # These tests create a disposable NewsFlow root.  The production auth
        # recovery library is intentionally outside that root, so allowing it
        # into the fixture would make test rows depend on a real user's backup.
        self.auth_library = patch("scriptor.config._newsflow_auth_library_candidates", return_value=[])
        self.auth_library.start()

    def tearDown(self) -> None:
        self.auth_library.stop()

    def test_import_command_adds_only_valid_sources_to_selected_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            bridge.add_channel({"name": "First", "channel": ""})
            bridge.add_channel({"name": "Second", "channel": ""})
            snapshot_data = bridge.import_channel_research_txt({
                "index": 1,
                "text": "https://example.org/a\ninvalid\nhttps://example.org/a\n",
            })

        first, second = snapshot_data["research"]["channels"]
        self.assertEqual(first["tasks"], [])
        self.assertEqual([task["url"] for task in second["tasks"]], ["https://example.org/a"])
        self.assertIn("1", snapshot_data["operationResult"]["message"])

    def test_added_channel_is_projected_as_an_isolated_research_agent(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            bridge.add_channel({"name": "Research channel", "channel": ""})
            snapshot_data = bridge.snapshot()

        agent = snapshot_data["research"]["channels"][0]
        self.assertEqual(agent["name"], "Research channel")
        self.assertEqual(agent["status"]["state"], "idle")
        self.assertNotIn("token", str(agent).casefold())
    def test_new_profile_receives_an_isolated_research_state(self) -> None:
        settings = Settings()
        first = channel_research_state(settings, "profile-a")
        second = channel_research_state(settings, "profile-b")

        first["config"]["queries"].append("news")

        self.assertEqual(second["config"]["queries"], [])
        self.assertEqual(set(settings.channel_research), {"profile-a", "profile-b"})

    def test_recovery_requeues_only_unfinished_tasks(self) -> None:
        recovered = recover_research_state({
            "tasks": [
                {"id": "one", "status": "running"},
                {"id": "two", "status": "completed"},
                {"id": "three", "status": "skipped"},
            ],
            "status": {"state": "running"},
        })

        self.assertEqual([item["status"] for item in recovered["tasks"]], ["waiting", "completed", "skipped"])
        self.assertEqual(recovered["status"]["state"], "paused")

    def test_research_state_survives_settings_reload_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            settings = Settings()
            settings.channel_research["profile-a"] = {
                "config": {"queries": ["latest news"], "languages": ["ru"], "regions": ["BY"]},
                "tasks": [{"id": "task-a", "url": "https://example.org", "status": "waiting"}],
                "results": [],
                "status": {"state": "paused"},
                "updatedAt": "2026-09-01T10:00:00+00:00",
            }
            save_settings(settings)
            restored = load_settings()

        self.assertEqual(restored.channel_research["profile-a"]["status"]["state"], "paused")
        self.assertNotIn("youtube_oauth_tokens", restored.channel_research["profile-a"])

    def test_txt_import_normalizes_valid_http_lines_and_retains_line_errors(self) -> None:
        sources, errors = parse_txt_sources(
            "https://www.youtube.com/@news\nnot a url\nhttps://example.org/story\n"
        )

        self.assertEqual(sources, ["https://www.youtube.com/@news", "https://example.org/story"])
        self.assertEqual(errors, [{"line": "2", "message": "Нужна HTTP(S)-ссылка"}])

    def test_dedupe_sources_keeps_first_normalized_url_only(self) -> None:
        self.assertEqual(
            dedupe_sources([
                "https://example.org/story/",
                "https://example.org/story",
                "https://example.org/next",
            ]),
            ["https://example.org/story", "https://example.org/next"],
        )

    def test_result_export_never_contains_task_profile_identifier(self) -> None:
        task = new_task("profile-a", "https://example.org/story", "txt")
        completed = transition_task(transition_task(task, "running"), "completed")
        result = public_result(
            completed,
            title="Story",
            summary="Summary",
            topic="News",
            hook="Hook",
            idea="Idea",
        )

        content_type, body = serialize_results([result], "json")

        self.assertEqual(content_type, "application/json")
        self.assertNotIn("profile-a", body)
        self.assertNotIn("token", body.casefold())
        self.assertNotIn("cookie", body.casefold())


if __name__ == "__main__":
    unittest.main()
