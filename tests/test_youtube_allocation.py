import unittest

from scriptor.youtube_allocation import allocate_ready_jobs


class YouTubeAllocationTests(unittest.TestCase):
    def test_longest_video_is_reserved_for_monetized_channel_even_if_listed_last(self):
        result = allocate_ready_jobs(
            [
                {"channelId": "fresh", "monetized": False, "quota": 1, "quotaLocked": True, "minDurationSeconds": 60, "maxDurationSeconds": 1800},
                {"channelId": "monetized", "monetized": True, "quota": 1, "quotaLocked": True, "minDurationSeconds": 60, "maxDurationSeconds": 1800},
            ],
            [
                {"id": "long", "status": "ready", "durationSeconds": 1200},
                {"id": "short", "status": "ready", "durationSeconds": 120},
            ],
        )

        self.assertEqual(result["assignments"]["monetized"], ["long"])
        self.assertEqual(result["assignments"]["fresh"], ["short"])
