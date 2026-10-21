"""Bounded stock transfer concurrency and persisted diagnostics; no providers."""
import json
import os
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch


class StockDownloadQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def queue(self, workers=3, **kwargs):
        from scriptor.stock_downloads import StockDownloadQueue
        return StockDownloadQueue(workers, self.root / 'downloads.json', **kwargs)

    def service(self, fetch):
        return SimpleNamespace(root=self.root, fetch=fetch)

    def candidate(self, asset_id):
        return SimpleNamespace(provider='nasa', kind='video', asset_id=str(asset_id))

    def test_one_planner_fills_configured_pool_and_pending_is_bounded(self):
        release = threading.Event()
        started = threading.Barrier(4)
        def fetch(candidate, **kwargs):
            started.wait(timeout=3)
            self.assertTrue(release.wait(3))
            return self.root / candidate.asset_id
        with self.queue() as pool:
            service = self.service(fetch)
            futures = [pool.submit(service, self.candidate(i), block=False) for i in range(6)]
            try:
                started.wait(timeout=3)
                state = pool.snapshot()
                self.assertEqual((state['active'], state['queued'], state['limit']), (3, 3, 3))
                self.assertIsNone(pool.submit(service, self.candidate(7), block=False))
                # Remaining jobs must not wait on the first-wave barrier.
                service.fetch = lambda candidate, **kwargs: self.root / candidate.asset_id
            finally:
                release.set()
            for future in futures:
                pool.result(future)
        state = json.loads((self.root / 'downloads.json').read_text())
        self.assertFalse(state['running'])
        self.assertEqual((state['completed'], state['active'], state['queued']), (6, 0, 0))

    def test_duplicate_inflight_asset_uses_one_transfer_and_errors_are_observed(self):
        release, started = threading.Event(), threading.Event()
        calls = []
        def fetch(candidate, **kwargs):
            calls.append(candidate.asset_id)
            started.set()
            self.assertTrue(release.wait(3))
            raise OSError('provider unavailable; private URL must not enter diagnostics')
        with self.queue(2) as pool:
            service, candidate = self.service(fetch), self.candidate(1)
            first = pool.submit(service, candidate)
            self.assertTrue(started.wait(3))
            second = pool.submit(service, candidate)
            self.assertIs(first, second)
            release.set()
            with self.assertRaises(OSError):
                pool.result(first)
        self.assertEqual(calls, ['1'])
        text = (self.root / 'downloads.jsonl').read_text()
        self.assertNotIn('private URL', text)
        self.assertEqual(json.loads((self.root / 'downloads.json').read_text())['failed'], 1)

    def test_pause_then_close_cancels_pending_without_stuck_threads(self):
        paused = threading.Event()
        paused.set()
        entered = threading.Event()
        def fetch(candidate, *, checkpoint, **kwargs):
            entered.set()
            checkpoint()
            self.fail('paused download must not pass checkpoint')
        pool = self.queue(1, paused=paused.is_set)
        pool.submit(self.service(fetch), self.candidate(1))
        self.assertTrue(entered.wait(3))
        pool.submit(self.service(fetch), self.candidate(2))
        with ThreadPoolExecutor(1) as closer:
            closer.submit(pool.close).result(timeout=3)
        state = pool.snapshot()
        self.assertEqual((state['active'], state['queued'], state['cancelled']), (0, 0, 2))

    def test_progress_and_phase_history_survive_a_new_reader(self):
        def fetch(candidate, *, progress, **kwargs):
            progress(1024)
            progress(2048)
            return self.root / 'original.mp4'
        with self.queue(1) as pool:
            self.assertEqual(pool.call('search', lambda: 42), 42)
            pool.result(pool.submit(self.service(fetch), self.candidate(1)))
        from scriptor.stock_downloads import read_download_status
        state = read_download_status(self.root / 'downloads.json')
        self.assertEqual(state['bytesDownloaded'], 2048)
        self.assertGreater(state['phaseSeconds']['search'], 0)
        self.assertGreater(state['bytesPerSecond'], 0)
        self.assertTrue(any(event['event'] == 'completed' for event in state['history']))

    def test_source_owner_is_live_for_a_separate_reader_and_pid_reuse_is_rejected(self):
        from scriptor.stock_downloads import read_download_status
        with self.queue(1):
            code = "import json,sys; from pathlib import Path; from scriptor.stock_downloads import read_download_status; print(json.dumps(read_download_status(Path(sys.argv[1]))))"
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.root / 'downloads.json')],
                                    capture_output=True, text=True, timeout=5, check=True)
            self.assertTrue(json.loads(result.stdout)['running'])
            with patch('scriptor.stock_downloads._process_token', return_value='another-creation-time'):
                state = read_download_status(self.root / 'downloads.json')
                self.assertFalse(state['running'])
                self.assertTrue(state['interrupted'])

    def test_control_poll_is_shared_by_chunks_instead_of_loading_settings_per_chunk(self):
        polls = []
        with self.queue(1, checkpoint=lambda: polls.append(1)) as pool:
            for _ in range(1000):
                pool.checkpoint()
        self.assertEqual(len(polls), 1)

    def test_exited_owner_is_not_live_even_while_its_process_handle_is_retained(self):
        from scriptor.stock_downloads import _process_token
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(60)'], creationflags=flags)
        try:
            self.assertIsNotNone(_process_token(child.pid))
            child.terminate()
            child.wait(timeout=5)
            self.assertIsNone(_process_token(child.pid))
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)

    def test_selector_keeps_later_waves_parallel_and_never_downloads_rejected_metadata(self):
        from scriptor.stock_selection import StockSceneSelector
        release, later_started = threading.Event(), threading.Event()
        initial_release, first_wait = threading.Event(), threading.Event()
        lock = threading.Lock()
        candidates, calls = [], []
        active_later = 0
        for i in range(10):
            path = self.root / f'{i}.mp4'
            path.write_bytes(str(i).encode())
            candidates.append(SimpleNamespace(provider='nasa', kind='video', asset_id=str(i),
                title='wrong object' if i == 9 else 'Cargo train', source_url='', license='', tags=(),
                local_path=path, to_dict=dict))
        def fetch(candidate, **kwargs):
            nonlocal active_later
            calls.append(candidate.asset_id)
            if int(candidate.asset_id) < 4:
                self.assertTrue(initial_release.wait(3))
            if 4 <= int(candidate.asset_id) < 9:
                with lock:
                    active_later += 1
                    if active_later >= 2:
                        later_started.set()
                try:
                    self.assertTrue(release.wait(3), 'later waves became serial')
                finally:
                    with lock:
                        active_later -= 1
            return candidate.local_path
        with self.queue(2) as pool, ThreadPoolExecutor(1) as planner:
            wait_for_result = pool.result
            def observe_wait(*args, **kwargs):
                first_wait.set()
                return wait_for_result(*args, **kwargs)
            pool.result = observe_wait
            service = self.service(fetch)
            service.enabled = ['nasa']
            service.search = lambda *args, **kwargs: candidates
            selector = StockSceneSelector(mode='stock', service=service,
                index=SimpleNamespace(score_file=lambda *_: .8), cache_root=self.root / 'prepared',
                threshold=.2, trim=True, aspect_ratio='16:9', use_library=False,
                semantic_ok=lambda _, item: 'wrong' not in item.name, source_allowed=lambda _: True,
                duration_probe=lambda _: 10, checkpoint=lambda: None, download_queue=pool)
            scene = {'visual_query_en': 'cargo train', 'duration': 3, 'narration': 'Cargo train'}
            with patch('scriptor.stock_selection.prepare_stock_media', side_effect=lambda source, *_a, **_k: source):
                result = planner.submit(selector.select, scene, {}, ['cargo train'], used_families=set())
                try:
                    self.assertTrue(first_wait.wait(3))
                    initial_release.set()
                    self.assertTrue(later_started.wait(3), 'pool must refill beyond its first 2*workers candidates')
                finally:
                    initial_release.set()
                    release.set()
                choice = result.result(timeout=5)
            self.assertEqual(choice.item.path, str(candidates[0].local_path))
            self.assertNotIn('9', calls)

    def test_real_cache_fetch_reports_bytes_and_keeps_planner_checkpoint_isolated(self):
        from scriptor.stock_sources import StockService
        from tests.test_stock_sources import Response, candidate
        def planner_checkpoint():
            self.fail('download worker called the planner checkpoint')
        service = StockService(self.root / 'cache', keys={}, enabled=['pexels'], checkpoint=planner_checkpoint)
        content = b'original' * 100000
        with patch.object(service, '_validate_url'), \
                patch.object(service, '_open', return_value=Response(content)), self.queue(2) as pool:
            output = pool.result(pool.submit(service, candidate()))
            self.assertEqual(output.read_bytes(), content)
            self.assertEqual(pool.snapshot()['bytesDownloaded'], len(content))
        self.assertIs(service.checkpoint, planner_checkpoint)
        self.assertEqual(list(service.originals.glob('*.part')), [])


if __name__ == '__main__':
    unittest.main()
