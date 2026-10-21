"""Materialize random overlay groups once, before a project reaches render."""
import copy
import importlib
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import timeline


def candidate(identifier, group="", **values):
    return {"id": identifier, "path": f"{identifier}.png", "kind": "image",
            "randomGroup": group, **values}


def preset():
    return {"version": 1, "libraryRoot": "local-library", "layouts": {
        "16:9": [candidate("permanent", x=3), candidate("a0", "A", x=10),
                  candidate("b0", "B", y=30),
                  candidate("a1", "A", path="a1.mp4", kind="video", x=20, start=6,
                            mode="until-end", duration=.1, chromaEnabled=True, opacity=.7),
                  candidate("b1", "B", y=40), candidate("disabled", "A", enabled=False)],
        "9:16": [candidate("u0", "A"), candidate("u1", "A")],
    }}


def source_preset():
    return {"version": 1, "librarySources": [
        {"id": "subscribe", "name": "Subscribe", "root": "subscribe-library", "enabled": True, "mode": "random", "kind": "all"},
        {"id": "pictures", "name": "Pictures", "root": "pictures-library", "enabled": True, "mode": "random", "kind": "image"},
        {"id": "disabled-source", "name": "Disabled", "root": "disabled-library", "enabled": False, "mode": "random", "kind": "video"},
    ], "layouts": {"16:9": [
        candidate("manual-logo"),
        candidate("permanent-video", path="permanent.mp4", kind="video", librarySourceId="subscribe"),
        candidate("picture0", "pictures-pool", librarySourceId="pictures"),
        candidate("subscribe0", "videos", path="subscribe0.mp4", kind="video", librarySourceId="subscribe"),
        candidate("permanent-image", librarySourceId="subscribe"),
        candidate("subscribe1", "images", librarySourceId="subscribe"),
        candidate("picture1", "pictures-pool", librarySourceId="pictures"),
        candidate("disabled-member", "videos", path="missing.mp4", kind="video", librarySourceId="disabled-source"),
    ]}}


class OverlayRandomTests(unittest.TestCase):
    def setUp(self):
        self.overlays = importlib.import_module("scriptor.overlays")

    def test_optional_metadata_survives_normalization_and_empty_fields_stay_omitted(self):
        value = self.overlays.normalize_overlay_template(preset())
        self.assertEqual(value["libraryRoot"], "local-library")
        self.assertEqual(value["layouts"]["16:9"][1]["randomGroup"], "A")
        self.assertNotIn("randomGroup", value["layouts"]["16:9"][0])
        empty = self.overlays.normalize_overlay_template({"version": 1, "libraryRoot": "", "layouts": {}})
        self.assertEqual(empty, {"version": 1, "layouts": {"16:9": [], "9:16": []}})
        value = self.overlays.normalize_overlay_template({"version": 1, "layouts": {
            "16:9": [candidate("plain", "   ")]}})
        self.assertNotIn("randomGroup", value["layouts"]["16:9"][0])

    def test_metadata_rejects_nonlocal_root_and_invalid_group_values(self):
        for root in ("https://example.com/media", "file:///somewhere", 123):
            with self.subTest(root=root), self.assertRaises(ValueError):
                self.overlays.normalize_overlay_template({"version": 1, "libraryRoot": root, "layouts": {}})
        for group in ("x" * 129, True, ["A"], "unsafe\nname"):
            with self.subTest(group=group), self.assertRaises(ValueError):
                self.overlays.normalize_overlay_template({"version": 1, "layouts": {"16:9": [candidate("a", group)]}})

    def test_seeded_resolution_selects_each_group_per_layout_in_original_order(self):
        first = self.overlays.resolve_overlay_template(preset(), rng=random.Random(7))
        second = self.overlays.resolve_overlay_template(preset(), rng=random.Random(7))
        self.assertEqual(first, second)
        self.assertEqual([row["id"] for row in first["layouts"]["16:9"]], ["permanent", "b0", "a1"])
        self.assertEqual([row["id"] for row in first["layouts"]["9:16"]], ["u1"])
        chosen = first["layouts"]["16:9"][-1]
        self.assertEqual((chosen["kind"], chosen["x"], chosen["start"], chosen["duration"], chosen["mode"]),
                         ("video", 20, 6, .1, "until-end"))
        self.assertEqual(chosen["randomGroup"], "A")
        self.assertTrue(chosen["chromaEnabled"])
        self.assertEqual(chosen["opacity"], .7)

    def test_many_seeds_reach_all_image_video_candidates_and_keep_permanent_layers(self):
        seen = set()
        for seed in range(128):
            value = self.overlays.resolve_overlay_template(preset(), rng=random.Random(seed))
            rows = value["layouts"]["16:9"]
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["id"], "permanent")
            self.assertEqual(sorted(row.get("randomGroup", "") for row in rows), ["", "A", "B"])
            seen.update(row["id"] for layout in value["layouts"].values() for row in layout)
        self.assertEqual(seen, {"permanent", "a0", "a1", "b0", "b1", "u0", "u1"})

    def test_resolution_does_not_mutate_preset_or_share_selected_row_data(self):
        value = preset()
        before = copy.deepcopy(value)
        resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
        resolved["layouts"]["16:9"][0]["x"] = 900
        resolved["layouts"]["16:9"].clear()
        self.assertEqual(value, before)

    def test_default_resolution_uses_system_random_and_skips_disabled_group_candidates(self):
        value = {"version": 1, "layouts": {"16:9": [candidate("on", "group"),
            candidate("off", "group", enabled=False), candidate("off-only", "disabled-group", enabled=False),
            candidate("permanent-off", enabled=False)]}}
        with patch.object(self.overlays.random, "SystemRandom", return_value=random.Random(1)) as generator:
            resolved = self.overlays.resolve_overlay_template(value)
        generator.assert_called_once_with()
        self.assertEqual([row["id"] for row in resolved["layouts"]["16:9"]], ["on", "permanent-off"])

    def test_unresolved_duplicate_enabled_group_fails_before_render_or_composition(self):
        value = preset()
        project = timeline.TimelineProject("unresolved", overlay_template=value)
        with patch.object(timeline, "_render_project_base") as base, \
                self.assertRaisesRegex(ValueError, "случайн|randomGroup"):
            timeline.render_project(project, Path("out.mp4"))
        base.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, "случайн|randomGroup"):
            root = Path(temporary)
            self.overlays.compose_overlays(root / "base.mp4", root / "out.mp4", value,
                "16:9", total_duration=20, ffmpeg="unused", encoder_args=["-c:v", "libx264"])

    def test_saved_project_and_repeated_render_never_reroll_chosen_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = preset()
            value["libraryRoot"] = str(root)
            for rows in value["layouts"].values():
                for row in rows:
                    source = root / Path(row["path"]).name
                    source.write_bytes(b"disposable media boundary fixture")
                    row["path"] = str(source)
            resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
            saved = root / "project.newsflow"
            timeline.TimelineProject("stable", overlay_template=resolved).save(saved)
            def base(clean, destination, *args, **kwargs):
                destination.write_bytes(b"base")
                return destination
            def finish(source, destination, template, *args, **kwargs):
                self.assertEqual(template, resolved)
                destination.write_bytes(b"finished")
                return destination
            with patch.object(self.overlays, "resolve_overlay_template", side_effect=AssertionError("reroll")), \
                    patch.object(self.overlays.random, "SystemRandom", side_effect=AssertionError("reroll")), \
                    patch.object(timeline, "_render_project_base", side_effect=base), \
                    patch.object(timeline, "probe_media_duration", return_value=20), \
                    patch.object(timeline, "video_encoder_args", return_value=["-c:v", "libx264"]), \
                    patch.object(timeline, "compose_overlays", side_effect=finish), \
                    patch.object(timeline, "validate_rendered_montage", return_value=20):
                for index in range(2):
                    project = timeline.TimelineProject.load(saved)
                    self.assertEqual(timeline.remotion_payload(project)["overlayTemplate"], resolved)
                    timeline.render_project(project, root / f"output-{index}.mp4")
                    project.save(saved)
            self.assertEqual(timeline.TimelineProject.load(saved).overlay_template, resolved)

    def test_sources_preserve_metadata_and_choose_independently_with_permanent_video_and_image(self):
        value = source_preset()
        before = copy.deepcopy(value)
        resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
        self.assertEqual(resolved["librarySources"], value["librarySources"])
        self.assertEqual([row["id"] for row in resolved["layouts"]["16:9"]],
                         ["manual-logo", "permanent-video", "subscribe0", "permanent-image", "picture1"])
        self.assertEqual(self.overlays.overlay_layers(resolved, "16:9"), resolved["layouts"]["16:9"])
        self.assertEqual(value, before)

    def test_source_all_keeps_every_checked_member_and_disabled_source_omits_members(self):
        value = source_preset()
        value["librarySources"][0]["mode"] = "all"
        value["librarySources"][1]["mode"] = "all"
        value["layouts"]["16:9"].append(candidate("unchecked", librarySourceId="subscribe", enabled=False))
        resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
        expected = ["manual-logo", "permanent-video", "picture0", "subscribe0", "permanent-image", "subscribe1", "picture1"]
        self.assertEqual([row["id"] for row in resolved["layouts"]["16:9"]], expected)
        self.assertEqual([row["id"] for row in self.overlays.overlay_layers(value, "16:9")], expected)

    def test_unresolved_source_pool_fails_but_its_permanent_members_do_not_count_as_candidates(self):
        with self.assertRaisesRegex(ValueError, "случайн|randomGroup"):
            self.overlays.overlay_layers(source_preset(), "16:9")
        value = source_preset()
        value["layouts"]["16:9"] = [row for row in value["layouts"]["16:9"]
                                            if row["id"] not in ("picture0", "subscribe1")]
        # Two permanent members plus one pool member in the same random source.
        self.assertEqual(len(self.overlays.overlay_layers(value, "16:9")), 5)

    def test_source_validation_rejects_missing_reference_duplicate_id_kind_and_invalid_controls(self):
        for mutate in (
            lambda value: value["layouts"]["16:9"][0].update(librarySourceId="missing"),
            lambda value: value["librarySources"].append(copy.deepcopy(value["librarySources"][0])),
            lambda value: value["librarySources"][0].update(enabled="false"),
            lambda value: value["librarySources"][0].update(mode="cycle"),
            lambda value: value["librarySources"][0].update(kind="audio"),
            lambda value: value["librarySources"][0].update(root="https://example.com"),
            lambda value: value["librarySources"][0].update(id=""),
        ):
            value = source_preset()
            mutate(value)
            with self.assertRaises(ValueError):
                self.overlays.normalize_overlay_template(value)

    def test_disabled_source_missing_assets_do_not_block_file_validation(self):
        value = source_preset()
        value["librarySources"] = [value["librarySources"][-1]]
        value["layouts"]["16:9"] = [value["layouts"]["16:9"][-1]]
        normalized = self.overlays.normalize_overlay_template(value, check_files=True)
        self.assertEqual(self.overlays.overlay_layers(normalized, "16:9", check_files=True), [])

    def test_source_snapshot_save_load_keeps_metadata_and_never_reselects(self):
        resolved = self.overlays.resolve_overlay_template(source_preset(), rng=random.Random(7))
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source-project.newsflow"
            timeline.TimelineProject("sources", overlay_template=resolved).save(path)
            with patch.object(self.overlays.random, "SystemRandom", side_effect=AssertionError("reroll")):
                loaded = timeline.TimelineProject.load(path)
                self.assertEqual(timeline.remotion_payload(loaded)["overlayTemplate"], resolved)
                self.assertEqual(self.overlays.overlay_layers(loaded.overlay_template, "16:9"), resolved["layouts"]["16:9"])

    def test_manual_group_names_are_independent_from_source_ids(self):
        value = source_preset()
        value["layouts"]["16:9"] += [candidate("manual0", "subscribe"), candidate("manual1", "subscribe")]
        resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
        selected = [row for row in resolved["layouts"]["16:9"] if row.get("randomGroup") == "subscribe"]
        self.assertEqual(len(selected), 1)
        self.assertNotIn("librarySourceId", selected[0])

    def test_identical_group_labels_in_different_roots_still_choose_from_each_source(self):
        value = source_preset()
        for row in value["layouts"]["16:9"]:
            if row.get("randomGroup"):
                row["randomGroup"] = "shared label"
        resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(7))
        chosen = [row for row in resolved["layouts"]["16:9"] if row.get("randomGroup")]
        self.assertEqual(sorted(row["librarySourceId"] for row in chosen), ["pictures", "subscribe"])

    def test_switching_source_kind_filters_without_losing_other_per_file_settings(self):
        value = source_preset()
        value["layouts"]["16:9"] = [row for row in value["layouts"]["16:9"]
                                         if row.get("librarySourceId") == "subscribe"]
        before = copy.deepcopy(value["layouts"])
        for kind, expected in (("video", {"permanent-video", "subscribe0"}),
                               ("image", {"permanent-image", "subscribe1"})):
            value["librarySources"][0]["kind"] = kind
            normalized = self.overlays.normalize_overlay_template(value)
            self.assertEqual(len(normalized["layouts"]["16:9"]), 4)
            resolved = self.overlays.resolve_overlay_template(value, rng=random.Random(3))
            self.assertEqual({r["id"] for r in resolved["layouts"]["16:9"]}, expected)
            self.assertEqual({r["id"] for r in self.overlays.overlay_layers(value, "16:9")}, expected)
        self.assertEqual(value["layouts"], before)

    def test_filtered_missing_asset_does_not_block_visible_matching_file(self):
        value = source_preset()
        value["librarySources"][0]["kind"] = "image"
        value["layouts"]["16:9"] = [value["layouts"]["16:9"][1]]
        normalized = self.overlays.normalize_overlay_template(value, check_files=True)
        self.assertEqual(self.overlays.overlay_layers(normalized, "16:9", check_files=True), [])


if __name__ == "__main__":
    unittest.main()
