import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scriptor.timeline import TimelineClip, TimelineProject


class StockCreditsTests(unittest.TestCase):
    def test_local_rerender_replaces_old_stock_credits_with_empty_current_manifest(self):
        from scriptor.stock_credits import stage_stock_credits

        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output.mp4'
            output.with_suffix('.stocks.json').write_text('old stock credits', encoding='utf-8')
            pairs = stage_stock_credits(TimelineProject('Local', source_policy={'mode': 'local'}), root / 'staged/output.mp4', output)
            self.assertEqual(len(pairs), 2)
            self.assertEqual(json.loads(pairs[0][0].read_text(encoding='utf-8'))['materials'], [])

    def test_credits_follow_actual_used_assets_without_internal_paths_or_urls(self):
        from scriptor.stock_credits import stage_stock_credits

        metadata = {"provider": "wikimedia", "asset_id": "7", "author": "Alice",
            "title": "Freight", "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "source_url": "https://commons.wikimedia.org/wiki/File:Freight.webm", "originalSha256": "abc",
            "originalPath": "C:/private/original.webm", "download_url": "https://cdn.invalid/?token=secret"}
        project = TimelineProject("T", clips=[TimelineClip("a.mp4", "N", "Q", stock_provenance=metadata)] * 2)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = stage_stock_credits(project, root / "staging/result.mp4", root / "output/result.mp4")
            text = pairs[0][0].read_text(encoding="utf-8")
            data = json.loads(text)
            self.assertEqual(len(data["materials"]), 1)
            self.assertEqual(data["materials"][0]["scenes"], [1, 2])
            self.assertIn("Alice", text)
            self.assertNotIn("private", text)
            self.assertNotIn("token", text)
            self.assertIn("CC BY 4.0", pairs[1][0].read_text(encoding="utf-8"))
