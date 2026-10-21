"""Independent provider admission regressions; disposable storage, no network."""
from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

from scriptor.stock_sources import StockService, StockSourceError
from tests.test_stock_sources import Response


class StockProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.service = StockService(
            Path(temporary.name), keys={'pexels': ['first-test-key', 'second-test-key']},
            enabled=['pexels'])

    def queued_request(self, while_waiting):
        slot = threading.BoundedSemaphore(1)
        slot.acquire()
        waiting = threading.Event()

        def acquire(**kwargs):
            waiting.set()
            return slot.acquire(**kwargs)

        gate = SimpleNamespace(acquire=acquire, release=slot.release)
        with patch.dict('scriptor.stock_sources._API_SLOTS', {'pexels': gate}), \
                patch.object(self.service, '_validate_url'), ThreadPoolExecutor(1) as executor:
            future = executor.submit(self.service._json, 'pexels', 'https://api.pexels.com/v1/search')
            try:
                self.assertTrue(waiting.wait(3), 'request must reach the saturated API gate')
                while_waiting()
            finally:
                slot.release()
            return future.result(timeout=3)

    def test_waiting_request_observes_new_provider_cooldown_before_transport(self):
        def rate_limited_neighbor():
            self.service._status('pexels', None, HTTPError(
                'https://api.pexels.com/v1/search', 429, 'Too many requests', {'Retry-After': '60'}, None))

        with patch.object(self.service, '_open', return_value=Response({})) as transport:
            with self.assertRaisesRegex(StockSourceError, 'cooling down'):
                self.queued_request(rate_limited_neighbor)
            transport.assert_not_called()

    def test_waiting_request_does_not_send_a_key_rejected_while_queued(self):
        def rejected_neighbor_key():
            self.service._status('pexels', 'first-test-key', HTTPError(
                'https://api.pexels.com/v1/search', 401, 'Unauthorized', {}, None))

        with patch.object(self.service, '_open', return_value=Response({})) as transport:
            self.assertEqual(self.queued_request(rejected_neighbor_key), {})
            request = transport.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'), 'second-test-key')

    def test_rate_limit_is_recorded_before_the_provider_slot_is_released(self):
        release_observations = []

        def release():
            try:
                self.service._check_cooldown('pexels')
            except StockSourceError:
                release_observations.append('cooling down')
            else:
                release_observations.append('still accepts requests')

        gate = SimpleNamespace(acquire=lambda **_kwargs: True, release=release)
        error_body = Response(b'provider error')
        rejection = HTTPError('https://api.pexels.com/v1/search', 429,
                              'Too many requests', {'Retry-After': '60'}, error_body)
        with patch.dict('scriptor.stock_sources._API_SLOTS', {'pexels': gate}), \
                patch.object(self.service, '_validate_url'), \
                patch.object(self.service, '_open', side_effect=rejection), \
                self.assertRaisesRegex(StockSourceError, 'Provider rejected request'):
            self.service._json('pexels', 'https://api.pexels.com/v1/search')
        self.assertEqual(release_observations, ['cooling down'])
        self.assertTrue(error_body.closed)

    def test_no_available_credentials_releases_provider_capacity(self):
        gate = threading.BoundedSemaphore(1)
        self.service.keys['pexels'] = []
        with patch.dict('scriptor.stock_sources._API_SLOTS', {'pexels': gate}), \
                patch.object(self.service, '_open') as transport:
            with self.assertRaisesRegex(StockSourceError, 'No available provider credentials'):
                self.service._json('pexels', 'https://api.pexels.com/v1/search')
            transport.assert_not_called()
            self.assertTrue(gate.acquire(blocking=False), 'credentials failure must release the API slot')
            gate.release()

    def test_interrupted_wait_does_not_reach_transport(self):
        def interrupt():
            raise InterruptedError('operator stopped the queue')

        with patch.object(self.service, '_open') as transport:
            with self.assertRaisesRegex(InterruptedError, 'operator stopped the queue'):
                self.queued_request(lambda: setattr(self.service, 'checkpoint', interrupt))
            transport.assert_not_called()


if __name__ == '__main__':
    unittest.main()
