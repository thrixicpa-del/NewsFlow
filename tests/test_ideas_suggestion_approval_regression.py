import unittest
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings


class IdeasSuggestionApprovalRegressionTests(unittest.TestCase):
    def test_main_approval_moves_only_requested_suggestion_to_favourites(self):
        settings = Settings(
            idea_topics=[],
            idea_suggested_topics=["A", "B"],
            idea_plan=[{"topic": "Existing plan", "count": 3, "provider": "agent"}],
        )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_suggested_topics_to_favorites({"topics": ["A"]})

        self.assertEqual(settings.idea_topics, ["A"])
        self.assertEqual(settings.idea_suggested_topics, ["B"])
        self.assertEqual(
            settings.idea_plan,
            [{"topic": "Existing plan", "count": 3, "provider": "agent"}],
        )
        save.assert_called_once_with(settings)

    def test_youtube_approval_moves_only_requested_suggestion_to_favourites(self):
        settings = Settings(
            idea_topics=[],
            idea_suggested_topics=["Main A"],
            youtube_suggested_topics=["YT A", "YT B"],
            idea_plan=[{"topic": "Existing plan", "count": 3, "provider": "agent"}],
        )

        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "save_settings") as save, \
             patch.object(bridge, "snapshot", return_value={}):
            bridge.add_suggested_topics_to_favorites({
                "topics": ["YT A"],
                "source": "youtube",
            })

        self.assertEqual(settings.idea_topics, ["YT A"])
        self.assertEqual(settings.youtube_suggested_topics, ["YT B"])
        self.assertEqual(settings.idea_suggested_topics, ["Main A"])
        self.assertEqual(
            settings.idea_plan,
            [{"topic": "Existing plan", "count": 3, "provider": "agent"}],
        )
        save.assert_called_once_with(settings)


if __name__ == "__main__":
    unittest.main()
