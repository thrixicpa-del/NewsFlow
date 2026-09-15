import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor.ai_index import ClipIndex
from scriptor.footage import (FootageItem, download_best_youtube_segment, rank_items,
                              scan_folders)


class FootageLibraryTests(unittest.TestCase):
    def test_incremental_index_reuses_unchanged_clips_reindexes_changes_and_removes_missing(self):
        """The footage maintenance path must not reopen unchanged video files."""
        import numpy as np

        class ImageEmbedder:
            def embed(self, images, batch_size=32):
                return [np.array([1.0, 0.0], dtype=np.float32) for _ in images]

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / "first.mp4"
            second = root / "second.mp4"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            index = ClipIndex(
                root / "footage.sqlite3",
                embedder_factory=lambda: (ImageEmbedder(), object()),
            )
            index._sample_frames = lambda _path: ([object()], 6.5, 1920, 1080)

            initial = index.index_folders([str(root)])
            unchanged = index.index_folders([str(root)])
            second.write_bytes(b"second changed")
            changed = index.index_folders([str(root)])
            first.unlink()
            removed = index.remove_missing()

        self.assertEqual((initial.indexed, initial.skipped), (2, 0))
        self.assertEqual((unchanged.indexed, unchanged.skipped), (0, 2))
        self.assertEqual((changed.indexed, changed.skipped), (1, 1))
        self.assertEqual(removed, 1)
    def test_scans_video_extensions_recursively(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Iran").mkdir()
            (root / "Iran" / "tanker_strait.mp4").touch()
            (root / "notes.txt").touch()
            items = scan_folders([folder])
            self.assertEqual([item.name for item in items], ["tanker_strait.mp4"])

    def test_ranks_semantically_named_local_clip_first(self):
        items = [
            FootageItem("a.mp4", "meeting.mp4", tags=["meeting"]),
            FootageItem("b.mp4", "tanker.mp4", tags=["иран", "танкер", "море"]),
        ]
        self.assertEqual(rank_items("Иран танкер", items)[0].path, "b.mp4")

    @patch("scriptor.footage.download_youtube_segment")
    def test_youtube_sampler_keeps_best_visual_timestamp(self, download):
        download.side_effect = lambda result, folder, start, duration: FootageItem(
            str(Path(folder) / f"preview-{start:.0f}.mp4"), "preview.mp4", "youtube")
        result = {"title": "test", "source_url": "https://example.test/video", "duration": 106}
        chosen = download_best_youtube_segment(
            result, Path("downloads"), "oil tanker",
            lambda path, query: 1.0 if "75" in str(path) else 0.0, probes=5)
        self.assertIn("75", chosen.path)
        self.assertEqual(download.call_args.args[2], 75.0)


if __name__ == "__main__":
    unittest.main()
