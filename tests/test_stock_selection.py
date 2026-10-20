"""Deterministic scene routing; no live network or model downloads."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor.footage import FootageItem


class StockSelectionTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.local = self.root / "local.mp4"
        self.local.write_bytes(b"local")
        self.original = self.root / "stock.mp4"
        self.original.write_bytes(b"stock")
        self.calls = []
        self.candidate = SimpleNamespace(provider="pexels", asset_id="42", title="Cargo freight railway",
            kind="video", source_url="https://www.pexels.com/video/42/", license="Pexels License",
            license_url="https://www.pexels.com/license/", author="Creator", tags=("cargo", "train"),
            local_path=self.original, to_dict=lambda: {"provider": "pexels", "asset_id": "42", "license": "Pexels License"})
        self.hits = {"STRICT_MATCH": [SimpleNamespace(item=FootageItem(str(self.local), "Cargo train"), score=.8)],
                     "RELAXED_SEMANTIC": [], "CATEGORY_MATCH": [], "SAFE_CONTEXT": []}
        self.scene = {"visual_query_en": "cargo train", "narration": "Грузовой поезд", "duration": 3.0}

    def selector(self, mode, score=.7, candidates=None):
        from scriptor.stock_selection import StockSceneSelector

        parent = self
        class Service:
            enabled = ("pexels",)
            def cached(self, query, kind="video"):
                return []
            def search(self, query, *, kind="video", limit=6):
                parent.calls.append((query, kind))
                return [parent.candidate] if candidates is None else candidates
            def fetch(self, candidate):
                return candidate.local_path

        return StockSceneSelector(mode=mode, service=Service(), index=SimpleNamespace(score_file=lambda *_args: score),
            cache_root=self.root / "cache", threshold=.22, trim=False, aspect_ratio="16:9",
            semantic_ok=lambda _query, item: "wrong" not in item.name,
            source_allowed=lambda _item: True, duration_probe=lambda _path: 10.0,
            checkpoint=lambda: None)

    def test_local_never_requests_stock_and_hybrid_prioritizes_exact_local(self):
        for mode in ("local", "hybrid"):
            with self.subTest(mode=mode):
                choice = self.selector(mode).select(self.scene, self.hits, ["cargo train"], used_families=set())
                self.assertEqual(choice.item.path, str(self.local))
        self.assertEqual(self.calls, [])

    def test_stock_excludes_local_and_checks_actual_window_with_clip(self):
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source):
            choice = self.selector("stock").select(self.scene, self.hits, ["cargo train"], used_families=set())
        self.assertEqual(choice.item.path, str(self.original))
        self.assertEqual(choice.item.source, "pexels")
        self.assertGreater(choice.score, .22)
        self.assertEqual(choice.provenance["asset_id"], "42")

    def test_bad_clip_or_contradictory_metadata_cannot_fill_a_scene(self):
        for score, title in ((.01, "Cargo train"), (.9, "wrong country train")):
            self.candidate.title = title
            with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source):
                choice = self.selector("stock", score=score).select(self.scene, self.hits, ["cargo train"], used_families=set())
            self.assertIsNone(choice)

    def test_hybrid_uses_related_local_after_stock_exhaustion(self):
        self.hits["RELAXED_SEMANTIC"] = self.hits.pop("STRICT_MATCH")
        choice = self.selector("hybrid", candidates=[]).select(self.scene, self.hits, ["cargo train", "freight railway"], used_families=set())
        self.assertEqual(choice.item.path, str(self.local))
        self.assertIn(("freight railway", "video"), self.calls)

    def test_reuse_is_forbidden_until_existing_uniqueness_policy_allows_it(self):
        selector = self.selector("stock")
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source):
            first = selector.select(self.scene, {}, ["cargo train"], used_families=set())
            blocked = selector.select(self.scene, {}, ["cargo train"], used_families={first.family})
            allowed = selector.select(self.scene, {}, ["cargo train"], used_families={first.family}, allow_reuse=True)
        self.assertIsNone(blocked)
        self.assertEqual(allowed.family, first.family)
        self.assertTrue(allowed.reused)

    def test_only_stock_can_use_licensed_animated_image_after_videos_fail(self):
        selector = self.selector("stock")
        image = SimpleNamespace(**vars(self.candidate))
        image.kind = "image"
        selector.service.search = lambda _q, *, kind="video", limit=6: [image] if kind == "image" else []
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source) as prepare:
            choice = selector.select(self.scene, {}, ["cargo train"], used_families=set())
        self.assertEqual(choice.provenance["kind"], "image")
        self.assertTrue(any(call.kwargs.get("kind") == "image" for call in prepare.call_args_list))

    def test_expansion_preserves_original_query_and_adds_real_synonyms(self):
        from scriptor.stock_selection import stock_query_variants
        queries = stock_query_variants(self.scene, {"STRICT_MATCH": ["cargo train"], "RELAXED_SEMANTIC": ["cargo train"]}, "Logistics")
        self.assertEqual(queries[0], "cargo train")
        self.assertTrue(any("freight" in query or "railway" in query for query in queries[1:]))

    def test_untrimmed_reuse_verifies_exact_requested_window(self):
        selector = self.selector("stock")
        short = self.root / "short.mp4"
        long = self.root / "long.mp4"
        short.write_bytes(b"good short window")
        long.write_bytes(b"bad additional tail")
        selector.index.score_file = lambda path, _query: .01 if path == long else .9
        def prepare(_source, *_args, **kwargs):
            return long if kwargs["duration"] >= 8 else short
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=prepare) as windows:
            first = selector.select(self.scene, {}, ["cargo train"], used_families=set())
            result = selector.select({**self.scene, "duration": 8.0}, {}, ["cargo train"],
                used_families={first.family}, allow_reuse=True)
        self.assertIsNone(result, "An unrelated extra tail cannot be accepted by a whole-file score")
        self.assertTrue(any(call.kwargs["duration"] == 8.0 for call in windows.call_args_list))

    def test_visual_cache_is_invalidated_when_actual_clip_models_change(self):
        selector = self.selector("stock")
        selector.index.score_file = lambda *_args: .8
        self.assertEqual(selector._score(self.original, "cargo train"), .8)
        selector.index.score_file = lambda *_args: .1
        with patch("scriptor.ai_index.IMAGE_MODEL", "new-image-model"):
            self.assertEqual(selector._score(self.original, "cargo train"), .1)

    def test_stock_fetch_honors_existing_download_semaphore(self):
        selector = self.selector("stock")
        class Gate:
            held = False
            def __enter__(self):
                self.held = True
            def __exit__(self, *_args):
                self.held = False
        gate = Gate()
        selector.download_semaphore = gate
        def fetch(_candidate):
            self.assertTrue(gate.held, "Existing queue download bound must cover stock transfers")
            return self.original
        selector.service.fetch = fetch
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_args, **_kwargs: source):
            self.assertIsNotNone(selector.select(self.scene, {}, ["cargo train"], used_families=set()))
