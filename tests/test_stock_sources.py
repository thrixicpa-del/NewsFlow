"""Offline stock-provider contracts; every filesystem write is disposable."""
from __future__ import annotations

import io
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from scriptor.stock_sources import (
    StockCandidate,
    StockService,
    StockSourceError,
    _SafeRedirect,
)


class Response(io.BytesIO):
    def __init__(self, value, headers=None):
        super().__init__(value if isinstance(value, bytes) else json.dumps(value).encode())
        self.headers = headers or {}


def candidate(provider='pexels', asset_id='1', url='https://videos.pexels.com/a.mp4'):
    return StockCandidate(provider, asset_id, 'Moon flight', url,
                          'https://www.pexels.com/video/1/?token=secret',
                          'Pexels License', 'https://www.pexels.com/license/',
                          'Jane Artist', 'video', ('moon', 'flight'), 12, 1920, 1080)


def process_worker(root, mode, index, result):
    """Spawned Windows worker: fake transport, real cache/OS locks/SQLite."""
    try:
        with patch('scriptor.stock_sources.socket.getaddrinfo', return_value=[
                (2, 1, 6, '', ('93.184.216.34', 443))]):
            service = StockService(Path(root), keys={'pexels': ['key-' + str(i) for i in range(12)]},
                                   enabled=['pexels'])
            seen = []
            def transport(req, **kwargs):
                if mode == 'keys':
                    seen.append(req.get_header('Authorization'))
                    return Response({'videos': []})
                with (Path(root) / 'downloads.txt').open('a') as marker:
                    marker.write('download\n')
                return Response(b'concurrent original')
            service._open = transport
            if mode == 'keys':
                for i in range(12):
                    service.search(f'worker {index} query {i}')
                result.put(seen)
            else:
                result.put(str(service.fetch(candidate())))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        result.put('ERROR:' + type(exc).__name__)


class StockSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dns = patch('scriptor.stock_sources.socket.getaddrinfo', return_value=[
            (2, 1, 6, '', ('93.184.216.34', 443))])
        self.dns.start()
        self.addCleanup(self.dns.stop)

    def service(self, enabled=('pexels',), keys=None):
        return StockService(self.root, keys=keys or {'pexels': ['one']}, enabled=list(enabled))

    def test_all_keys_rotate_without_cap_and_persist_without_secrets(self):
        keys = ['unique-secret-' + str(i) for i in range(40)]
        service = self.service(keys={'pexels': keys + [keys[0]]})
        seen = []
        def transport(request, **kwargs):
            seen.append(request.get_header('Authorization'))
            return Response({'videos': []})
        with patch.object(service, '_open', side_effect=transport):
            for i in range(41):
                service.search('query ' + str(i))
        self.assertEqual(seen, keys + [keys[0]])
        resumed = self.service(keys={'pexels': keys})
        with patch.object(resumed, '_open', side_effect=transport):
            resumed.search('resumed')
        self.assertEqual(seen[-1], keys[1])
        self.assertNotIn(b'unique-secret', (self.root / 'stock-cache.sqlite3').read_bytes())

    def test_429_stops_provider_all_keys_and_honours_retry_after(self):
        service = self.service(keys={'pexels': ['one', 'two']})
        with patch.object(service, '_open', side_effect=HTTPError(
                'https://api.pexels.com', 429, 'rate', {'Retry-After': '600'}, None)) as net:
            self.assertEqual(service.search('one'), [])
            self.assertEqual(service.search('two'), [])
        self.assertEqual(net.call_count, 1)
        resumed = self.service(keys={'pexels': ['one', 'two']})
        with patch.object(resumed, '_open') as net:
            self.assertEqual(resumed.search('three'), [])
        net.assert_not_called()

    def test_401_marks_key_bad_and_next_request_uses_other_key(self):
        service = self.service(keys={'pexels': ['one', 'two']})
        with patch.object(service, '_open', side_effect=HTTPError(
                'https://api.pexels.com', 401, 'bad', {}, None)):
            service.search('first')
        seen = []
        with patch.object(service, '_open', side_effect=lambda req, **kw:
                          (seen.append(req.get_header('Authorization')) or Response({'videos': []}))):
            service.search('second')
            service.search('third')
        self.assertEqual(seen, ['two', 'two'])

    def test_pixabay_search_cache_survives_restart_for_24_hours(self):
        service = self.service(('pixabay',), {'pixabay': ['secret']})
        response = {'hits': [{'id': 7, 'pageURL': 'https://pixabay.com/videos/id-7/',
                              'user': 'Artist', 'tags': 'moon, space', 'duration': 7,
                              'videos': {'large': {'url': 'https://cdn.pixabay.com/video/a.mp4',
                                                   'width': 1920, 'height': 1080}}}]}
        with patch.object(service, '_open', return_value=Response(response)):
            results = service.search('moon')
        self.assertEqual(results[0].asset_id, '7')
        resumed = self.service(('pixabay',), {'pixabay': ['secret']})
        with patch.object(resumed, '_open') as net:
            self.assertEqual(resumed.search('moon')[0].asset_id, '7')
        net.assert_not_called()
        with closing(sqlite3.connect(self.root / 'stock-cache.sqlite3')) as db:
            db.execute('UPDATE searches SET created=created-86401')
            db.commit()
        with patch.object(resumed, '_open', return_value=Response({'hits': []})) as net:
            self.assertEqual(resumed.search('moon'), [])
        self.assertEqual(net.call_count, 1)

    def test_pexels_images_and_coverr_signed_urls_never_persist(self):
        service = self.service(('pexels', 'coverr'), {'pexels': ['one'], 'coverr': ['two']})
        def transport(req, **kwargs):
            if 'pexels' in req.full_url:
                return Response({'photos': [{'id': 2, 'alt': 'Moon', 'url': 'https://www.pexels.com/photo/2/',
                    'photographer': 'Artist', 'src': {'original': 'https://images.pexels.com/photos/2/a.jpeg'},
                    'width': 1800, 'height': 1200}]})
            return Response({'hits': [{'id': 'flight', 'title': 'Moon', 'duration': 10,
                'urls': {'mp4_download': 'https://storage.coverr.co/v/flight?token=signed-secret'},
                'creator': {'name': 'Artist'}, 'tags': ['space']}]})
        with patch.object(service, '_open', side_effect=transport):
            images = service.search('moon', kind='image')
            videos = service.search('moon')
        self.assertEqual([x.provider for x in images], ['pexels'])
        coverr = next(x for x in videos if x.provider == 'coverr')
        self.assertNotIn('signed-secret', repr(coverr))
        self.assertNotIn('download_url', coverr.to_dict())
        self.assertNotIn(b'signed-secret', (self.root / 'stock-cache.sqlite3').read_bytes())

    def test_commons_rejects_unknown_sa_nc_nd_and_preserves_cc_by_author(self):
        service = self.service(('commons',), {})
        def item(index, license):
            return {'pageid': index, 'title': 'File:Moon.webm', 'imageinfo': [{
                'url': 'https://upload.wikimedia.org/wikipedia/commons/a/moon.webm',
                'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Moon.webm',
                'mime': 'video/webm', 'width': 1920, 'height': 1080,
                'extmetadata': {'LicenseShortName': {'value': license},
                                'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by/4.0/'},
                                'Artist': {'value': '<a href="url">Lunar Artist</a>'}}}]}
        with patch.object(service, '_open', return_value=Response({'query': {'pages': [
                item(i, value) for i, value in enumerate(['CC BY-SA 4.0', 'CC BY-NC 4.0',
                    'CC BY-ND 4.0', 'Unknown', 'CC BY 4.0'])]}})):
            found = service.search('moon')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].author, 'Lunar Artist')
        self.assertEqual(found[0].license, 'CC BY 4.0')
        self.assertEqual(found[0].provider, 'wikimedia')

    def test_wikimedia_setting_enables_canonical_provider_and_commons_alias(self):
        service = self.service(('wikimedia', 'commons'), {})
        response = {'query': {'pages': [{'pageid': 5, 'title': 'File:Moon.png', 'imageinfo': [{
            'url': 'https://upload.wikimedia.org/wikipedia/commons/a/moon.png',
            'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Moon.png', 'mime': 'image/png',
            'extmetadata': {'LicenseShortName': {'value': 'CC0'}, 'Artist': {'value': 'Artist'}}}]}]}}
        with patch.object(service, '_open', side_effect=lambda *args, **kw: Response(response)) as net:
            found = service.search('moon', kind='image')
        self.assertEqual([x.provider for x in found], ['wikimedia'])
        self.assertEqual(net.call_count, 1)

    def test_nasa_requires_explicit_pd_and_excludes_third_party_rights(self):
        service = self.service(('nasa',), {})
        descriptions = ['NASA moon landing', 'Public domain. Copyright ESA.',
                        'Public domain. No third-party rights apply.']
        response = {'collection': {'items': [{'data': [{'nasa_id': str(i), 'title': 'Moon',
            'description': text, 'media_type': 'image', 'photographer': 'NASA'}],
            'links': [{'href': 'https://images-assets.nasa.gov/image/moon/a.jpg'}]}
            for i, text in enumerate(descriptions)]}}
        with patch.object(service, '_open', return_value=Response(response)):
            found = service.search('moon', kind='image')
        self.assertEqual([x.asset_id for x in found], ['2'])

    def test_failure_isolated_and_no_disabled_provider_fallback(self):
        service = self.service(('pexels', 'pixabay'), {'pexels': ['one'], 'pixabay': ['two']})
        def transport(req, **kwargs):
            if 'pexels' in req.full_url:
                raise OSError('private url containing credential')
            return Response({'hits': [{'id': 7, 'pageURL': 'https://pixabay.com/videos/id-7/',
                 'user': 'Artist', 'videos': {'small': {'url': 'https://cdn.pixabay.com/a.mp4'}}}]})
        with patch.object(service, '_open', side_effect=transport):
            self.assertEqual([x.provider for x in service.search('moon')], ['pixabay'])
        self.assertEqual(self.service((), {}).search('moon'), [])

    def test_download_deduplicates_bytes_and_cached_original_works_offline(self):
        service = self.service()
        first = candidate()
        second = candidate(asset_id='2')
        with patch.object(service, '_open', side_effect=lambda *args, **kw: Response(b'original-media')) as net:
            path = service.fetch(first)
            self.assertEqual(service.fetch(first), path)
            self.assertEqual(service.fetch(second), path)
        self.assertEqual(net.call_count, 2)
        self.assertEqual(path.read_bytes(), b'original-media')
        self.assertFalse(path.stat().st_mode & 0o222)
        resumed = self.service()
        cached = resumed.cached('moon')
        self.assertEqual(len(cached), 2)
        self.assertEqual(cached[0].local_path, path)
        with patch.object(resumed, '_open') as net:
            self.assertEqual(resumed.fetch(cached[0]), path)
        net.assert_not_called()
        with closing(sqlite3.connect(self.root / 'stock-cache.sqlite3')) as db:
            records = [json.loads(row[0]) for row in db.execute('SELECT metadata FROM assets')]
        self.assertEqual(records[0]['author'], 'Jane Artist')
        self.assertEqual(records[0]['source_url'], 'https://www.pexels.com/video/1/')
        self.assertIn('downloaded_at', records[0])

    def test_concurrent_same_asset_downloads_once(self):
        service = self.service()
        with (patch.object(service, '_open', side_effect=lambda req, **kw: Response(b'media')) as net,
              ThreadPoolExecutor(max_workers=6) as pool):
            paths = list(pool.map(lambda _: service.fetch(candidate()), range(6)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(net.call_count, 1)

    def test_http_private_credentials_and_unknown_host_are_rejected(self):
        service = self.service()
        for url in ['http://videos.pexels.com/a.mp4', 'https://127.0.0.1/a',
                    'https://videos.pexels.com.evil.org/a', 'https://user:pass@videos.pexels.com/a',
                    'https://videos.pexels.com:444/a']:
            with self.subTest(url=url), patch.object(service, '_open') as net:
                with self.assertRaises(StockSourceError):
                    service.fetch(candidate(url=url))
                net.assert_not_called()
        with patch('scriptor.stock_sources.socket.getaddrinfo', return_value=[
                (2, 1, 6, '', ('127.0.0.1', 443))]), patch.object(service, '_open') as net:
            with self.assertRaises(StockSourceError):
                service.fetch(candidate())
            net.assert_not_called()

    def test_oversized_download_is_atomic_and_never_cached(self):
        service = self.service()
        with (patch('scriptor.stock_sources.MAX_DOWNLOAD_BYTES', 5), patch.object(
                service, '_open', return_value=Response(b'too-large')), self.assertRaises(StockSourceError)):
            service.fetch(candidate())
        self.assertEqual(service.cached('moon'), [])
        self.assertEqual(list((self.root / 'originals').iterdir()), [])

    def test_pause_checkpoint_propagates_and_media_never_gets_authorization(self):
        calls = []
        service = StockService(self.root, keys={'pexels': ['one']}, enabled=['pexels'],
                               checkpoint=lambda: calls.append('checkpoint'))
        requests = []
        with patch.object(service, '_open', side_effect=lambda req, **kw:
                          (requests.append(req) or Response(b'media'))):
            service.fetch(candidate())
        self.assertGreaterEqual(len(calls), 2)
        self.assertIsNone(requests[0].get_header('Authorization'))
        def cancel():
            raise InterruptedError('cancelled')
        service.checkpoint = cancel
        with patch.object(service, '_open') as net, self.assertRaises(InterruptedError):
            service.search('moon')
        net.assert_not_called()

    def test_crossprocess_rotation_and_same_asset_lock(self):
        context = multiprocessing.get_context('spawn')
        for mode in ('keys', 'download'):
            with self.subTest(mode=mode):
                result = context.Queue()
                workers = [context.Process(target=process_worker,
                    args=(str(self.root), mode, index, result)) for index in range(4)]
                for worker in workers:
                    worker.start()
                try:
                    values = [result.get(timeout=25) for _ in workers]
                finally:
                    for worker in workers:
                        worker.join(timeout=5)
                        if worker.is_alive():
                            worker.terminate()
                            worker.join(timeout=5)
                    result.close()
                    result.join_thread()
                self.assertTrue(all(worker.exitcode == 0 for worker in workers))
                if mode == 'keys':
                    seen = [key for group in values for key in group]
                    self.assertEqual({key: seen.count(key) for key in set(seen)},
                                     {'key-' + str(i): 4 for i in range(12)})
                else:
                    self.assertEqual(len(set(values)), 1)
                    self.assertTrue(Path(values[0]).is_file())
                    self.assertEqual((self.root / 'downloads.txt').read_text().splitlines(), ['download'])

    def test_untrusted_candidate_local_path_cannot_bypass_cache(self):
        service = self.service()
        arbitrary = self.root / 'outside.mp4'
        arbitrary.write_bytes(b'private file')
        item = replace(candidate(), local_path=arbitrary)
        with patch.object(service, '_open', side_effect=lambda *args, **kw: Response(b'public original')):
            path = service.fetch(item)
        self.assertNotEqual(path, arbitrary)
        self.assertEqual(path.read_bytes(), b'public original')

    def test_media_429_cools_down_api_keys_even_before_first_search(self):
        service = self.service(keys={'pexels': ['one', 'two']})
        with (patch.object(service, '_open', side_effect=HTTPError(
                'https://videos.pexels.com/a', 429, 'rate', {'Retry-After': '600'}, None)),
              self.assertRaises(StockSourceError)):
            service.fetch(candidate())
        with patch.object(service, '_open') as net:
            self.assertEqual(service.search('moon'), [])
        net.assert_not_called()

    def test_search_restart_refreshes_signed_download_using_asset_detail(self):
        service = self.service(('coverr',), {'coverr': ['key']})
        entry = {'id': 'flight', 'title': 'Moon', 'duration': 10, 'creator': {'name': 'Artist'},
                 'urls': {'mp4_download': 'https://storage.coverr.co/v/flight?token=first-secret'}}
        with patch.object(service, '_open', return_value=Response({'hits': [entry]})):
            service.search('moon')
        resumed = self.service(('coverr',), {'coverr': ['key']})
        refreshed = dict(entry, urls={'mp4_download': 'https://storage.coverr.co/v/flight?token=second-secret'})
        seen = []
        def transport(req, **kwargs):
            seen.append(req.full_url)
            return Response(refreshed if 'api.coverr.co' in req.full_url else b'original')
        with patch.object(resumed, '_open', side_effect=transport):
            item = resumed.search('moon')[0]
            self.assertEqual(item.download_url, '')
            path = resumed.fetch(item)
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[0].startswith('https://api.coverr.co/videos/flight?'))
        self.assertEqual(seen[1], 'https://storage.coverr.co/v/flight?token=second-secret')
        self.assertNotIn(b'secret', (self.root / 'stock-cache.sqlite3').read_bytes())

    def test_redirect_rejects_private_and_authenticated_destinations(self):
        service = self.service()
        request = Request('https://videos.pexels.com/a.mp4')
        handler = _SafeRedirect(lambda url: service._validate_url('pexels', url), False)
        for destination in ('http://videos.pexels.com/a', 'https://127.0.0.1/a', 'https://evil.org/a'):
            with self.assertRaises(StockSourceError):
                handler.redirect_request(request, None, 302, '', {}, destination)
        authenticated = _SafeRedirect(lambda url: None, True)
        with self.assertRaises(StockSourceError):
            authenticated.redirect_request(Request('https://api.pexels.com', headers={'Authorization': 'secret'}),
                                           None, 302, '', {}, 'https://videos.pexels.com/a')

    def test_digest_deduplication_across_providers_keeps_both_attributions(self):
        service = self.service(('pexels', 'pixabay'))
        alternate = StockCandidate('pixabay', '7', 'Moon', 'https://cdn.pixabay.com/a.webm',
            'https://pixabay.com/videos/id-7/', 'Pixabay Content License',
            'https://pixabay.com/service/license-summary/', 'Different Artist', tags=('moon',))
        with patch.object(service, '_open', side_effect=lambda *args, **kw: Response(b'same original')):
            first, second = service.fetch(candidate()), service.fetch(alternate)
        self.assertEqual(first, second)
        self.assertEqual({item.author for item in service.cached('moon')}, {'Jane Artist', 'Different Artist'})

    def test_download_url_cannot_be_mistaken_for_public_attribution_page(self):
        service = self.service(('coverr',), {'coverr': ['key']})
        signed = 'https://storage.coverr.co/v/sensitive-jwt-in-path'
        entry = {'id': 'flight', 'title': 'Moon', 'url': signed, 'urls': {'mp4_download': signed}}
        with patch.object(service, '_open', return_value=Response({'hits': [entry]})):
            item = service.search('moon')[0]
        self.assertEqual(item.source_url, 'https://coverr.co/videos/flight')
        self.assertNotIn(b'sensitive-jwt', (self.root / 'stock-cache.sqlite3').read_bytes())
        forged = replace(candidate(), source_url='https://videos.pexels.com/private-token/a.mp4')
        with patch.object(service, '_open') as net, self.assertRaises(StockSourceError):
            service.fetch(forged)
        net.assert_not_called()

    def test_media_cooldown_blocks_direct_and_remembered_urls_but_allows_valid_cache(self):
        service = self.service()
        with patch.object(service, '_open', return_value=Response(b'original')):
            original = service.fetch(candidate())
        with (patch.object(service, '_open', side_effect=HTTPError(
                'https://videos.pexels.com/rate', 429, 'rate', {'Retry-After': '600'}, None)),
              self.assertRaises(StockSourceError)):
            service.fetch(candidate(asset_id='rate'))
        resumed = self.service()
        remembered = replace(candidate(asset_id='3'), download_url='')
        resumed._urls[('pexels', '3', 'video')] = 'https://videos.pexels.com/remembered.mp4'
        with patch.object(resumed, '_open', side_effect=lambda *args, **kw: Response(b'forbidden')) as net:
            self.assertEqual(resumed.fetch(candidate()), original)
            for item in (candidate(asset_id='2'), remembered):
                with self.subTest(asset=item.asset_id), self.assertRaises(StockSourceError):
                    resumed.fetch(item)
        net.assert_not_called()

    def test_corrupt_original_is_excluded_from_cache_and_rejected_without_network(self):
        for index, modified in enumerate((b'x', b'modified-media')):
            with self.subTest(modified=modified):
                service = StockService(self.root / str(index), keys={}, enabled=['pexels'])
                with patch.object(service, '_open', return_value=Response(b'original-media')):
                    path = service.fetch(candidate())
                path.chmod(0o600)
                path.write_bytes(modified)
                path.chmod(0o400)
                resumed = StockService(self.root / str(index), keys={}, enabled=['pexels'])
                self.assertEqual(resumed.cached('moon'), [])
                with patch.object(resumed, '_open') as net, self.assertRaises(StockSourceError):
                    resumed.fetch(candidate())
                net.assert_not_called()
                self.assertEqual(path.read_bytes(), modified)

    def test_corrupt_dedup_target_and_orphan_original_are_not_relabelled_or_overwritten(self):
        for retain_record in (True, False):
            with self.subTest(retain_record=retain_record):
                service = StockService(self.root / str(retain_record), keys={}, enabled=['pexels'])
                with patch.object(service, '_open', return_value=Response(b'original-media')):
                    path = service.fetch(candidate())
                path.chmod(0o600)
                path.write_bytes(b'modified-media')
                path.chmod(0o400)
                if not retain_record:
                    with closing(sqlite3.connect(service.db_path)) as db:
                        db.execute('DELETE FROM assets')
                        db.commit()
                with (patch.object(service, '_open', return_value=Response(b'original-media')),
                      self.assertRaises(StockSourceError)):
                    service.fetch(candidate(asset_id='2'))
                self.assertEqual(path.read_bytes(), b'modified-media')
                with closing(sqlite3.connect(service.db_path)) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0], int(retain_record))
                self.assertEqual(list(service.originals.glob('*.part')), [])

    def test_fetch_rejects_disabled_provider_even_with_existing_original(self):
        service = self.service()
        with patch.object(service, '_open', return_value=Response(b'original')):
            service.fetch(candidate())
        disabled = self.service((), {})
        with patch.object(disabled, '_open') as net:
            for item in (candidate(), candidate(asset_id='2')):
                with self.subTest(asset=item.asset_id), self.assertRaises(StockSourceError):
                    disabled.fetch(item)
        net.assert_not_called()


if __name__ == '__main__':
    unittest.main()
