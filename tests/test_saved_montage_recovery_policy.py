"""Independent integration regressions for saved block/stock recovery policies."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, montage_continuity
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject
from tests.media_fixtures import write_readable_video


class SavedMontageRecoveryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.environ.get("NEWSFLOW_TEST_MODE"), "1")
        temporary = tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"])
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.block = self.root / "curated"
        self.block.mkdir()
        self.short = self.block / "short.mp4"
        self.healthy = self.block / "cargo-port.mp4"
        write_readable_video(self.short, duration=1)
        write_readable_video(self.healthy, duration=3)

    def project(self, clip, mode="stock"):
        return TimelineProject("Новости порта", clips=[clip], source_policy={
            "mode": mode, "footageBlock": {"root": str(self.block), "blockId": "manual"}})

    def clip(self, path, *, duration=2, start=0):
        return TimelineClip(str(path), "Погрузка грузов", "cargo port", duration=duration,
                            source_start=start, minimum_source_duration=duration,
                            voice_segment_id=17, voice_segment_ids=[17])

    def test_readable_short_source_is_reported_before_queue_render(self):
        for mode in ("stock", "hybrid", "local", "block"):
            with self.subTest(mode=mode):
                project = self.project(self.clip(self.short), mode)
                self.assertEqual(bridge._montage_project_missing_clips(project), [str(self.short)])

    def test_remaining_source_window_not_total_file_duration_is_checked(self):
        project = self.project(self.clip(self.healthy, start=2))
        self.assertEqual(bridge._montage_project_missing_clips(project), [str(self.healthy)])

    def test_short_source_is_replaced_without_replanning_the_voice_beat(self):
        project = self.project(self.clip(self.short))
        item = FootageItem(str(self.healthy), "Cargo port")
        self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [item]), 1)
        self.assertEqual(project.clips[0].path, str(self.healthy))
        self.assertEqual((project.clips[0].duration, project.clips[0].voice_segment_ids), (2, [17]))

    def test_continuity_fills_short_interval_after_replacement_is_exhausted(self):
        project = self.project(self.clip(self.short))
        prepared = self.root / "held.mp4"
        with patch.object(montage_continuity, "prepare_continuity_media", return_value=prepared):
            self.assertEqual(montage_continuity.resolve_project_continuity(
                project, self.root / "cache", duration_probe=lambda _path: 1), 1)
        self.assertEqual(project.clips[0].path, str(prepared))
        self.assertEqual(project.clips[0].duration, 2)

    def test_manual_block_keeps_owner_selected_file_despite_story_metadata(self):
        chosen = self.block / "Iran_port.mp4"
        self.healthy.rename(chosen)
        project = self.project(self.clip(chosen), "block")
        self.assertEqual(bridge._montage_project_missing_clips(project), [])
        # The automatic library route retains its established country guard.
        project.source_policy["mode"] = "stock"
        self.assertEqual(bridge._montage_project_missing_clips(project), [str(chosen)])

    def test_block_recovery_uses_curated_root_without_semantic_reranking(self):
        chosen = self.block / "Iran_port.mp4"
        self.healthy.rename(chosen)
        project = self.project(self.clip(self.block / "deleted.mp4"), "block")
        item = FootageItem(str(chosen), "Iran port")
        with patch.object(bridge, "_semantic_clip_ok", side_effect=AssertionError("block is manually curated")):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [item]), 1)
        self.assertEqual(project.clips[0].path, str(chosen))

    def test_block_recovery_cannot_substitute_an_outside_file(self):
        outside = self.root / "outside.mp4"
        self.healthy.rename(outside)
        project = self.project(self.clip(self.block / "deleted.mp4"), "block")
        self.assertEqual(bridge._repair_missing_project_clips(project,
            lambda *_: [FootageItem(str(outside), "Cargo port")]), 0)


if __name__ == "__main__":
    unittest.main()
