"""Explicit per-layer schedules on the final MP4 clock, including its intro."""
import copy
import tempfile
import unittest
from pathlib import Path

from scriptor.overlays import (
    normalize_overlay_template,
    overlay_intervals,
    resolve_overlay_template,
)
from scriptor.timeline import TimelineProject


def row(**kw):
    return {"id": "logo", "path": "logo.png", "kind": "image", **kw}


def template(layer):
    return {"version": 1, "layouts": {"16:9": [layer], "9:16": []}}


class OverlayTimingTests(unittest.TestCase):
    def test_manual_ranges_are_independent_sorted_clipped_and_half_open(self):
        value = row(mode="intervals", ranges=[{"start": 80, "end": 88}, {"start": 6, "end": 12}, {"start": 180, "end": 200}])
        saved = normalize_overlay_template(template(value))["layouts"]["16:9"][0]
        self.assertEqual(overlay_intervals(saved, 190), [(6, 12), (80, 88), (180, 190)])
        self.assertEqual(overlay_intervals(saved, 10), [(6, 10)])
        self.assertEqual(overlay_intervals(saved, 5), [])

    def test_count_distributes_whole_shows_in_window_or_actual_mp4_length(self):
        value = row(mode="count", start=6, duration=2, repeatCount=4, rangeEnd=32)
        saved = normalize_overlay_template(template(value))["layouts"]["16:9"][0]
        self.assertEqual(overlay_intervals(saved, 300), [(6, 8), (14, 16), (22, 24), (30, 32)])
        saved["rangeEnd"] = None
        self.assertEqual(overlay_intervals(saved, 32), [(6, 8), (14, 16), (22, 24), (30, 32)])
        self.assertEqual(overlay_intervals(saved, 62), [(6, 8), (24, 26), (42, 44), (60, 62)])
        saved["repeatCount"] = 1
        self.assertEqual(overlay_intervals(saved, 62), [(6, 8)])

    def test_count_refuses_impossible_distinct_shows_instead_of_silent_overlap(self):
        value = normalize_overlay_template(template(row(mode="count", start=6, duration=5, repeatCount=4)))["layouts"]["16:9"][0]
        with self.assertRaisesRegex(ValueError, "не помещаются"):
            overlay_intervals(value, 20)

    def test_impossible_explicit_window_is_rejected_before_saving(self):
        with self.assertRaisesRegex(ValueError, "не помещаются"):
            normalize_overlay_template(template(row(mode="count", start=6, duration=5, repeatCount=4, rangeEnd=20)))

    def test_invalid_ranges_counts_and_windows_are_rejected(self):
        invalid = [row(mode="intervals", ranges=[]), row(mode="intervals", ranges=[{"start": 6, "end": 6}]),
                   row(mode="intervals", ranges=[{"start": -1, "end": 6}]),
                   row(mode="intervals", ranges=[{"start": 6, "end": 12}, {"start": 10, "end": 20}]),
                   row(mode="intervals", ranges=[{"start": True, "end": 12}]),
                   row(mode="count", repeatCount=2.5), row(mode="count", repeatCount=True),
                   row(mode="count", repeatCount=0), row(mode="count", start=10, rangeEnd=9),
                   row(mode="count", rangeEnd="end")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_overlay_template(template(value))

    def test_project_and_random_choice_preserve_per_file_schedule_and_no_aliases(self):
        original = template(row(mode="intervals", ranges=[{"start": 6, "end": 12}, {"start": 30, "end": 40}], randomGroup="logos"))
        saved = resolve_overlay_template(original)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing.newsflow"
            TimelineProject("Timing", overlay_template=saved).save(path)
            loaded = TimelineProject.load(path)
        self.assertEqual(loaded.overlay_template, saved)
        original["layouts"]["16:9"][0]["ranges"][0]["end"] = 99
        self.assertEqual(saved["layouts"]["16:9"][0]["ranges"][0]["end"], 12)
        self.assertEqual(overlay_intervals(loaded.overlay_template["layouts"]["16:9"][0], 300), [(6, 12), (30, 40)])

    def test_reactivation_budget_applies_to_all_schedule_modes(self):
        value = row(mode="intervals", ranges=[{"start": i * 2, "end": i * 2 + 1} for i in range(514)])
        with self.assertRaises(ValueError):
            normalize_overlay_template(template(value))
        with self.assertRaises(ValueError):
            normalize_overlay_template(template(row(mode="count", repeatCount=514)))

    def test_until_end_remains_dynamic_without_mutating_layer_or_other_layout(self):
        value = row(mode="until-end", start=6)
        before = copy.deepcopy(value)
        self.assertEqual(overlay_intervals(value, 20), [(6, 20)])
        self.assertEqual(overlay_intervals(value, 300), [(6, 300)])
        self.assertEqual(value, before)
