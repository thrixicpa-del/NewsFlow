"""Opt-in thematic stock remains licensed, unique and grounded in the scene."""
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor.footage import FootageItem
from scriptor.stock_selection import StockSceneSelector


class StockContextSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="newsflow-context-selector-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "original.mp4"
        self.source.write_bytes(b"original low resolution source")
        self.window = self.root / "prepared-1080.mp4"
        self.window.write_bytes(b"prepared scaled video")
        self.local = self.root / "local.mp4"
        self.local.write_bytes(b"local source")
        self.original_query = "empty airport terminal"
        self.context_query = "airport building exterior"
        self.scene = {"visual_query_en": self.original_query, "duration": 3.0,
                      "narration": "Пустой терминал", "narration_start": 6.0, "narration_end": 9.0}
        self.candidate = SimpleNamespace(provider="pexels", asset_id="42", title="Airport exterior",
            kind="video", source_url="https://example.test/42", license="licensed", tags=(),
            to_dict=lambda: {"provider": "pexels", "asset_id": "42", "license": "licensed"})
        self.events = []
        self.scores = []
        self.local_hits = {"CATEGORY_MATCH": [SimpleNamespace(
            item=FootageItem(str(self.local), "Airport building", "local"), score=.05)]}
        owner = self

        class Service:
            enabled = ("pexels",)

            def cached(self, query, *, kind):
                owner.events.append(("cache", query, kind))
                return [owner.candidate] if query == owner.context_query and kind == owner.candidate.kind else []

            def search(self, query, *, kind, limit):
                owner.events.append(("search", query, kind))
                return []

            def fetch(self, _candidate):
                owner.events.append(("fetch",))
                return owner.source

        self.service = Service()
        prepare = patch("scriptor.stock_selection.prepare_stock_media", return_value=self.window)
        self.prepare = prepare.start()
        self.addCleanup(prepare.stop)

    def selector(self, mode="stock", *, score=.7, hd_only=None, semantic_ok=None, source_allowed=None):
        def score_file(path, query):
            self.scores.append((Path(path), query))
            return score if query == self.context_query else .1
        options = {} if hd_only is None else {"hd_only": hd_only}
        return StockSceneSelector(mode=mode, service=self.service,
            index=SimpleNamespace(score_file=score_file), cache_root=self.root / "cache",
            threshold=.22, trim=False, aspect_ratio="16:9", checkpoint=lambda: None,
            semantic_ok=semantic_ok or (lambda *_args: True),
            source_allowed=source_allowed or (lambda *_args: True), duration_probe=lambda _path: 3.0, **options)

    def context(self, selector, *, used=(), hits=None, queries=None):
        return selector.select_context(self.scene, self.local_hits if hits is None else hits,
            [self.context_query] if queries is None else queries, used_families=set(used), position_bucket="middle")

    def test_context_is_explicit_and_does_not_relax_exact_selection(self):
        selector = self.selector()
        self.assertIsNone(selector.select(self.scene, {}, [self.original_query], used_families=set()))
        choice = self.context(selector)
        self.assertEqual(choice.level, "THEMATIC_CONTEXT")
        self.assertEqual(choice.provenance["contextQuery"], self.context_query)
        self.assertEqual(choice.provenance["contextScore"], .7)
        self.assertNotIn("clipScore", choice.provenance)
        self.assertEqual(choice.position_bucket, "middle")
        self.assertEqual(self.scene["visual_query_en"], self.original_query)

    def test_original_scene_contradiction_remains_a_hard_guard(self):
        checked = []
        selector = self.selector(semantic_ok=lambda query, _item: checked.append(query) or query != self.original_query)
        self.assertIsNone(self.context(selector))
        self.assertTrue(checked)
        self.assertEqual(set(checked), {self.original_query})
        self.assertFalse(any(event[0] == "fetch" for event in self.events))

    def test_below_threshold_context_is_rejected(self):
        self.assertIsNone(self.context(self.selector(score=.21)))
        self.assertTrue(self.scores)
        self.assertEqual({query for _, query in self.scores}, {self.context_query})

    def test_stock_mode_ignores_local_hits_and_cached_image_precedes_search(self):
        self.candidate.kind = "image"
        choice = self.context(self.selector())
        self.assertEqual(choice.item.path, str(self.window))
        self.assertFalse(any(event[0] == "search" for event in self.events))
        self.assertNotIn(self.local, [path for path, _ in self.scores])

    def test_local_mode_never_fetches_stock_and_hybrid_prefers_context_local(self):
        for mode in ("local", "hybrid"):
            with self.subTest(mode=mode):
                selector = self.selector(mode)
                choice = self.context(selector)
                self.assertEqual(choice.item.path, str(self.local))
                self.assertEqual(choice.level, "THEMATIC_CONTEXT")
                self.assertFalse(choice.provenance, "Local context is not a downloaded stock source")
        self.assertEqual(self.events, [])
        self.assertIsNone(self.context(self.selector("local"), hits={}))
        self.assertEqual(self.events, [])

    def test_used_stock_family_cannot_reappear_as_context(self):
        family = "stock-sha256::" + hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertIsNone(self.context(self.selector(), used={family}))

    def test_used_local_family_cannot_reappear_as_context(self):
        from scriptor.stock_selection import local_family
        family = local_family(self.local_hits["CATEGORY_MATCH"][0].item)
        self.assertIsNone(self.context(self.selector("local"), used={family}))

    def test_interrupted_local_context_score_aborts_without_fallback(self):
        selector = self.selector("hybrid")
        with patch.object(selector, '_score', side_effect=InterruptedError('cancelled by user')), \
             self.assertRaisesRegex(InterruptedError, 'cancelled by user'):
            self.context(selector)
        self.assertEqual(self.events, [])
        self.assertEqual(selector.pool, [])

    def test_source_permissions_are_retained(self):
        self.assertIsNone(self.context(self.selector(source_allowed=lambda _item: False)))

    def test_no_queries_means_no_random_or_generic_stock_discovery(self):
        self.assertIsNone(self.context(self.selector(), queries=["", "  "]))
        self.assertEqual(self.events, [])

    def test_hd_only_checks_original_before_preparation_even_with_trim_off(self):
        selector = self.selector(hd_only=True)
        with patch("scriptor.stock_selection.source_is_hd", return_value=False) as hd:
            self.assertIsNone(self.context(selector))
        hd.assert_called_once_with(self.source, "video")
        self.prepare.assert_not_called()

    def test_hd_off_preserves_legacy_stock_and_skips_original_probe(self):
        selector = self.selector(hd_only=False)
        with patch("scriptor.stock_selection.source_is_hd", return_value=False) as hd:
            self.assertIsNotNone(self.context(selector))
        hd.assert_not_called()

    def test_hd_gate_also_applies_to_normal_exact_selection(self):
        selector = self.selector(hd_only=True)
        scene = {**self.scene, "visual_query_en": self.context_query}
        with patch("scriptor.stock_selection.source_is_hd", return_value=False) as hd:
            self.assertIsNone(selector.select(scene, {}, [self.context_query], used_families=set()))
        hd.assert_called_once_with(self.source, "video")
        self.prepare.assert_not_called()

    def test_hd_original_verdict_is_memoized_by_contents_not_prepared_path(self):
        selector = self.selector(hd_only=True)
        with patch("scriptor.stock_selection.source_is_hd", return_value=True) as hd:
            self.assertIsNotNone(self.context(selector))
            self.assertIsNotNone(self.context(selector))
            self.assertEqual(hd.call_count, 1)
            self.source.write_bytes(b"different original content")
            self.assertIsNotNone(self.context(selector))
            self.assertEqual(hd.call_count, 2)

    def test_hd_rejects_real_360_image_despite_high_metadata_and_prepared_resolution(self):
        from PIL import Image
        self.source = self.root / "original-360.jpg"
        Image.new("RGB", (640, 360), "blue").save(self.source)
        self.candidate.kind = "image"
        self.candidate.width, self.candidate.height = 1920, 1080
        self.assertIsNone(self.context(self.selector(hd_only=True)))
        self.prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
