"""Non-flaky policy tests for NewsFlow performance regression budgets."""
from __future__ import annotations

import unittest


class PerformanceBaselinePolicyTests(unittest.TestCase):
    def test_baselines_cover_each_current_local_regression_lane(self):
        from tests.performance_baselines import load_performance_baselines

        baselines = load_performance_baselines()
        self.assertEqual({
            "app-startup", "idea-local-processing", "script-validation",
            "voice-queue-scheduling", "footage-search-selection", "montage-planning",
            "ffmpeg-fast-news-render", "cover-local-processing", "publication-preparation",
        }, set(baselines))
        self.assertTrue(all(item.warning_seconds < item.hard_seconds for item in baselines.values()))
        self.assertTrue(all(item.known_good_seconds < item.warning_seconds for item in baselines.values()))

    def test_budget_policy_warns_before_it_blocks_a_true_hard_regression(self):
        from tests.performance_baselines import (
            classify_duration,
            load_performance_baselines,
        )

        baseline = load_performance_baselines()["montage-planning"]
        self.assertEqual("PASS", classify_duration(baseline, baseline.warning_seconds))
        self.assertEqual("WARNING", classify_duration(baseline, baseline.warning_seconds + 0.01))
        self.assertEqual("HARD_REGRESSION", classify_duration(baseline, baseline.hard_seconds + 0.01))


if __name__ == "__main__":
    unittest.main()
