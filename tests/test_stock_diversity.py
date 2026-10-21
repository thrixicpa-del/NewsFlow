"""Bounded synonym and ten-project diversity regressions; offline, isolated."""
import io
import json
import os
import sqlite3
import tempfile
import unittest
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from scriptor.bridge import _montage_query_ladder
from scriptor.stock_selection import StockSceneSelector, stock_query_variants
from scriptor.stock_sources import StockService
from scriptor.timeline import TimelineClip
from tests import test_stock_pipeline as pipeline_fixture


class StockDiversityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scene = {'visual_query_en': 'cargo train', 'narration': 'Грузовой поезд', 'duration': 2.0}
        self.transfers, self.searches = Counter(), 0
        self.rows = []
        self.dns = patch('scriptor.stock_sources.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('93.184.216.34', 443))])
        self.dns.start()
        self.addCleanup(self.dns.stop)
        self.transport_patch = patch.object(StockService, '_open', self.transport)
        self.transport_patch.start()
        self.addCleanup(self.transport_patch.stop)
        self.prepare_patch = patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_args, **_kwargs: source)
        self.prepare_patch.start()
        self.addCleanup(self.prepare_patch.stop)

    def transport(self, request, **_kwargs):
        parsed = urlsplit(request.full_url)
        if parsed.hostname == 'videos.pexels.com':
            asset = parsed.path.split('/')[-1].split('.')[0]
            self.transfers[asset] += 1
            response = io.BytesIO(('unique stock bytes ' + asset).encode())
            response.headers = {}
            return response
        if parsed.path.endswith('/search'):
            self.searches += 1
            value = {'videos': self.rows}
        else:
            asset = parsed.path.rsplit('/', 1)[-1]
            value = next(row for row in self.rows if str(row['id']) == asset)
        response = io.BytesIO(json.dumps(value).encode())
        response.headers = {}
        return response

    def selector(self, count, *, use_library=True):
        self.rows = [{'id': index, 'url': f'https://www.pexels.com/video/{index}/', 'title': 'Cargo train',
            'user': {'name': 'Synthetic artist'}, 'duration': 10,
            'video_files': [{'width': 320, 'height': 180, 'file_type': 'video/mp4',
                             'link': f'https://videos.pexels.com/{index}.mp4'}]} for index in range(count)]
        service = StockService(self.root / 'original-cache', keys={'pexels': ['synthetic-key']}, enabled=['pexels'])
        return StockSceneSelector(mode='stock', service=service, index=SimpleNamespace(score_file=lambda *_args: .8),
            cache_root=self.root / 'prepared', threshold=.22, trim=False, aspect_ratio='16:9',
            semantic_ok=lambda *_args: True, source_allowed=lambda *_args: True,
            duration_probe=lambda *_args: 10.0, checkpoint=lambda: None, use_library=use_library)

    def record(self, selector, choices, number):
        clips = [TimelineClip(choice.item.path, '', 'cargo train', 2., source=choice.item.source,
            source_family=choice.family, stock_provenance=choice.provenance or {},
            position_bucket=getattr(choice, "position_bucket", "")) for choice in choices]
        record = getattr(selector, 'record_project_usage', None)
        if record is not None:
            record(f'project-{number}', clips)

    def test_long_production_ladder_keeps_all_clauses_and_synonyms_without_count_cap(self):
        query = ('Armenia parliament meeting, government building, diplomatic summit, journalists cameras, '
                 'city exterior, negotiation venue, public square, national assembly')
        variants = stock_query_variants({'visual_query_en': query}, _montage_query_ladder(query), 'Armenia')
        self.assertEqual(variants[0], query)
        self.assertGreater(len(variants), 10)
        for clause in query.split(", "):
            self.assertTrue(any(clause in value for value in variants), clause)
        self.assertTrue(any('conference' in value for value in variants))
        self.assertTrue(any('negotiations' in value for value in variants))

    def test_ten_related_projects_expand_to_thirty_distinct_sources_when_library_preference_is_off(self):
        history, all_families = set(), []
        for project in range(10):
            selector = self.selector(30, use_library=False)  # Prefer fresh discovery instead of library reuse.
            own, choices = set(), []
            for _scene in range(3):
                choice = selector.select(self.scene, {}, ['cargo train'], used_families=own, history_families=history)
                self.assertIsNotNone(choice, 'Search must expand beyond the first ten provider candidates')
                own.add(choice.family)
                choices.append(choice)
            self.assertEqual(len(own), 3)
            self.record(selector, choices, project)
            history.update(own)
            all_families.extend(own)
        self.assertEqual(len(set(all_families)), 30)
        self.assertEqual(sum(self.transfers.values()), 30)
        self.assertTrue(all(count == 1 for count in self.transfers.values()))
        self.assertEqual(self.searches, 1, 'Search results must survive restart with their existing TTL')

    def test_ten_projects_rotate_thirty_library_sources_without_any_network_after_restart(self):
        initial = self.selector(30)
        for candidate in initial.service.search('cargo train', kind='video', limit=40):
            initial.service.fetch(candidate)
        self.assertEqual(sum(self.transfers.values()), 30)
        self.transfers.clear()
        self.searches = 0
        history, selected = set(), set()
        for number in range(10):
            selector = self.selector(30)
            own, choices = set(), []
            for _scene in range(3):
                choice = selector.select(self.scene, {}, ['cargo train'], used_families=own, history_families=history)
                self.assertIsNotNone(choice)
                own.add(choice.family)
                choices.append(choice)
            self.record(selector, choices, number)
            history.update(own)
            selected.update(own)
        self.assertEqual(len(selected), 30)
        self.assertEqual(self.searches, 0)
        self.assertEqual(sum(self.transfers.values()), 0)

    def test_library_exhausts_later_pages_before_any_provider_search(self):
        selector = self.selector(41)
        candidates = [selector.service._parse_item('pexels', row, 'video') for row in self.rows]
        paths = [selector.service.fetch(candidate) for candidate in candidates]
        import hashlib
        used = {'stock-sha256::' + hashlib.sha256(path.read_bytes()).hexdigest() for path in paths[1:]}
        self.searches = 0
        choice = selector.select(self.scene, {}, ['cargo train'], used_families=used)
        self.assertIsNotNone(choice)
        self.assertEqual(choice.item.path, str(paths[0]))
        self.assertEqual(self.searches, 0, 'Asset 41 is already downloaded; no provider discovery is needed')
        self.assertEqual(sum(self.transfers.values()), 41)

    def test_scarce_three_sources_rotate_evenly_across_ten_projects_and_their_windows(self):
        counts, windows, history = Counter(), set(), set()
        for project in range(10):
            selector = self.selector(3)
            choice = selector.select(self.scene, {}, ['cargo train'], used_families=set(), history_families=history)
            self.assertIsNotNone(choice)
            counts[choice.family] += 1
            windows.add((choice.family, choice.provenance['originalStart']))
            self.record(selector, [choice], project)
            history.add(choice.family)
        self.assertEqual(sorted(counts.values()), [3, 3, 4])
        self.assertGreaterEqual(len(windows), 9)
        self.assertEqual(sum(self.transfers.values()), 3)

    def test_scarce_library_sources_move_between_start_middle_and_end_across_projects(self):
        placements, orders = {}, set()
        for number in range(10):
            selector = self.selector(3)
            own, choices = set(), []
            for bucket in ('EARLY', 'MIDDLE', 'LATE'):
                selector.position_bucket = bucket
                choice = selector.select(self.scene, {}, ['cargo train'], used_families=own)
                self.assertIsNotNone(choice)
                placements.setdefault(choice.family, set()).add(bucket)
                choices.append(choice)
                own.add(choice.family)
            self.record(selector, choices, number)
            orders.add(tuple(choice.family for choice in choices))
        self.assertGreaterEqual(len(orders), 3, 'Scarce sources should not keep the same order in every video')
        self.assertTrue(all(len(buckets) == 3 for buckets in placements.values()))
        self.assertEqual(sum(self.transfers.values()), 3)

    def test_history_retry_is_idempotent_and_does_not_change_original(self):
        selector = self.selector(3)
        choice = selector.select(self.scene, {}, ['cargo train'], used_families=set())
        original = Path(choice.item.path).read_bytes()
        self.record(selector, [choice], 1)
        self.record(selector, [choice], 1)
        self.assertTrue((self.root / 'prepared' / 'selection-usage.sqlite3').exists())
        with closing(sqlite3.connect(self.root / 'prepared' / 'selection-usage.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT uses FROM families WHERE family=?', (choice.family,)).fetchone()[0], 1)
        self.assertEqual(Path(choice.item.path).read_bytes(), original)


class StockHistoryStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_parallel_accepted_projects_keep_all_counts_after_restart(self):
        from scriptor.stock_history import StockUsageHistory
        history = StockUsageHistory(self.root)
        clip = TimelineClip('test.mp4', '', '', 2., source_family='family', source_start=1.)
        with ThreadPoolExecutor(max_workers=4) as workers:
            list(workers.map(lambda number: history.record(f'project-{number}', [clip]), range(12)))
        counts, windows = StockUsageHistory(self.root).snapshot(['family'])
        self.assertEqual(counts['family'][0], 12)
        self.assertEqual(windows[('family', 1000, 3000)][0], 12)
        history.record('project-0', [clip])
        self.assertEqual(history.snapshot(['family'])[0]['family'][0], 12)

    def test_unknown_schema_and_corrupt_history_are_not_silently_reset(self):
        from scriptor.stock_history import StockUsageHistory
        history = StockUsageHistory(self.root)
        with closing(sqlite3.connect(history.path)) as db:
            db.execute('PRAGMA user_version=2')
        before = history.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'версия'):
            StockUsageHistory(self.root)
        self.assertEqual(history.path.read_bytes(), before)
        history.path.write_bytes(b'damaged disposable history')
        with self.assertRaises(sqlite3.DatabaseError):
            StockUsageHistory(self.root)
        self.assertEqual(history.path.read_bytes(), b'damaged disposable history')


class StockHistoryPipelineTests(unittest.TestCase):
    def setUp(self):
        pipeline_fixture.StockPipelineTests.setUp(self)

    def test_accepted_preparation_records_history_but_failed_publication_does_not(self):
        pipeline_fixture.StockPipelineTests.prepare(self, 'stock')
        from scriptor.config import load_settings
        ledger = Path(load_settings().footage_download_folder) / 'Стоки' / 'prepared' / 'selection-usage.sqlite3'
        self.assertTrue(ledger.exists(), str(list(self.root.rglob("selection-usage.sqlite3"))))
        with closing(sqlite3.connect(ledger)) as db:
            before = db.execute('SELECT SUM(uses) FROM families').fetchone()[0]
        self.assertEqual(before, 1)
        with patch('scriptor.bridge._publish_staged_paths', return_value=[]), self.assertRaises(RuntimeError):
            pipeline_fixture.StockPipelineTests.prepare(self, 'stock')
        with closing(sqlite3.connect(ledger)) as db:
            self.assertEqual(db.execute('SELECT SUM(uses) FROM families').fetchone()[0], before)
