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

    def test_library_checks_all_synonyms_before_network_and_can_be_disabled(self):
        for enabled in (True, False):
            with self.subTest(library=enabled):
                selector = self.selector("stock", candidates=[])
                selector.use_library = enabled
                selector.service.cached = lambda query, **_kwargs: [self.candidate] if query == "freight railway" else []
                self.calls.clear()
                with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_a, **_k: source):
                    choice = selector.select(self.scene, {}, ["cargo train", "freight railway"], used_families=set())
                if enabled:
                    self.assertIsNotNone(choice)
                    self.assertEqual(self.calls, [], "A matching library synonym must avoid new provider requests")
                else:
                    self.assertIsNone(choice)
                    self.assertTrue(self.calls)

    def test_library_without_query_words_is_scored_before_provider_discovery(self):
        import hashlib
        import json

        from scriptor.stock_sources import StockCandidate, StockService

        query = 'operations control room operators'
        for score in (.8, .1):
            with self.subTest(score=score):
                service = StockService(self.root / f'library-{score}', keys={}, enabled=['pexels'])
                candidate = StockCandidate('pexels', '42', 'File:AirTraffic-8.jpg', '',
                    'https://www.pexels.com/video/42/', 'Pexels License',
                    'https://www.pexels.com/license/', 'Creator', kind='image')
                contents = f'isolated image fixture {score}'.encode()
                digest = hashlib.sha256(contents).hexdigest()
                filename = digest + '.jpg'
                (service.originals / filename).write_bytes(contents)
                with service._db() as db:
                    db.execute('INSERT INTO assets VALUES (?,?,?,?)',
                        (service._identity(candidate), digest, filename, json.dumps(candidate.to_dict())))
                self.assertEqual(service.cached(query, kind='image'), [])
                selector = self.selector('hybrid', score=score, candidates=[])
                selector.service = service
                scored_queries = []
                selector.index.score_file = (
                    lambda _path, value, score=score, recorded=scored_queries: recorded.append(value) or score
                )
                with (patch.object(service, 'search', return_value=[]) as search,
                      patch.object(service, '_open', side_effect=AssertionError('Offline regression')) as network,
                      patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source)):
                    choice = selector.select({**self.scene, 'visual_query_en': query}, {}, [query], used_families=set())
                if score >= selector.threshold:
                    self.assertIsNotNone(choice, 'An eligible downloaded image must not require matching filename words')
                    search.assert_not_called()
                else:
                    self.assertIsNone(choice, 'Library fallback must retain the original CLIP threshold')
                self.assertTrue(scored_queries, 'The unmatched library asset must reach visual validation')
                self.assertEqual(set(scored_queries), {query}, 'Discovery must never replace the original visual gate')
                self.assertTrue(all(call.args[0] for call in search.call_args_list), 'Empty queries are library-only')
                network.assert_not_called()

    def test_query_matched_library_wins_before_unmatched_library_scan(self):
        selector = self.selector('stock', candidates=[])
        visited = []
        def cached(query, *, kind='video'):
            visited.append(query)
            return [self.candidate] if query == 'cargo train' and kind == 'video' else []
        selector.service.cached = cached
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        self.assertIsNotNone(choice)
        self.assertNotIn('', visited)
        self.assertEqual(self.calls, [])

    def test_recent_but_suitable_library_material_avoids_provider_search(self):
        selector = self.selector("stock", candidates=[])
        selector.service.cached = lambda *_a, **_k: [self.candidate]
        import hashlib
        family = 'stock-sha256::' + hashlib.sha256(self.original.read_bytes()).hexdigest()
        with patch("scriptor.stock_selection.prepare_stock_media", side_effect=lambda source, *_a, **_k: source):
            choice = selector.select(self.scene, {}, ["cargo train"], used_families=set(), history_families={family})
        self.assertIsNotNone(choice)
        self.assertEqual(self.calls, [], "Library reuse must not require fresh network discovery")

    def test_bad_window_does_not_hide_other_valid_windows_of_the_same_original(self):
        def prepare(source, *_a, **kwargs):
            if kwargs.get('source_start', 0) == 3.5:
                raise ValueError('One unreadable test interval')
            return source
        selector = self.selector('stock')
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=prepare):
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        self.assertIsNotNone(choice)
        # First window is valid but rejected by CLIP; the middle is broken;
        # the final valid window must still be considered.
        selector = self.selector('stock')
        scores = iter([.1, .8])
        selector._score = lambda *_a: next(scores)
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=prepare):
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        self.assertIsNotNone(choice)
        self.assertEqual(choice.provenance['originalStart'], 7.)

    def test_rejected_batch_claim_cannot_enter_safe_reuse_pool(self):
        selector = self.selector('stock')
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
            first = selector.select(self.scene, {}, ['cargo train'], used_families=set())
            self.assertIsNotNone(first)
            selector.reject_unclaimed(first.family)
            self.assertFalse(selector.pool)
            choice = selector.select(self.scene, {}, ['cargo train'], used_families={first.family}, allow_reuse=True)
        self.assertIsNone(choice, 'A different project owns this family; it is not our reusable accepted footage')

    def test_safe_reuse_rotates_the_whole_accepted_pool_within_one_long_project(self):
        from collections import Counter
        candidates = []
        for number in range(3):
            path = self.root / f'stock-{number}.mp4'
            path.write_bytes(f'unique-{number}'.encode())
            candidates.append(SimpleNamespace(**{**vars(self.candidate), 'asset_id': str(number), 'local_path': path}))
        selector = self.selector('stock', candidates=candidates)
        own, counts = set(), Counter()
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
            for number in range(15):
                choice = selector.select(self.scene, {}, ['cargo train'], used_families=own, allow_reuse=number >= 3)
                self.assertIsNotNone(choice)
                own.add(choice.family)
                counts[choice.family] += 1
        self.assertEqual(sorted(counts.values()), [5, 5, 5])

    def test_hybrid_can_use_a_relevant_stock_image_after_video_exhaustion(self):
        selector = self.selector('hybrid', candidates=[])
        image = SimpleNamespace(**{**vars(self.candidate), 'kind': 'image'})
        selector.service.search = lambda _query, *, kind='video', **_k: [image] if kind == 'image' else []
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        self.assertIsNotNone(choice)
        self.assertEqual(choice.provenance['kind'], 'image')

    def test_hybrid_cached_image_does_not_require_new_video_discovery(self):
        selector = self.selector('hybrid', candidates=[])
        image = SimpleNamespace(**{**vars(self.candidate), 'kind': 'image'})
        selector.service.cached = lambda _query, *, kind='video': [image] if kind == 'image' else []
        with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        self.assertIsNotNone(choice)
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
