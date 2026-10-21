"""Isolated stock adapters and immutable originals cache (standard library only).

Provider schemas follow their official documentation:
https://www.pexels.com/api/documentation/
https://pixabay.com/api/docs/ (mandatory 24-hour search cache)
https://api.coverr.co/docs/videos/ (mp4_download records the download event)
https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf
https://www.mediawiki.org/wiki/API:Imageinfo

MoneyPrinterTurbo's MIT material.py was reviewed for provider orientation; no
implementation code was copied. NASA's catalog is NOT blanket public domain.
Only explicit public-domain entries with explicit absence of third-party rights
are accepted. Commons share-alike/NC/ND/unknown licenses are unsupported.

Assets/trust boundaries: API keys stay in memory; remote JSON/URLs are untrusted;
SQLite contains safe attribution, search records and hashed key rotation state.
Neither signed media URLs nor authorization headers are persisted or logged.
"""
from __future__ import annotations

import html
import ipaddress
import json
import math
import os
import re
import socket
import sqlite3
import stat
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_RESULTS = 40
_TTL = 24 * 60 * 60
_API_SLOTS = {provider: threading.BoundedSemaphore(3)
              for provider in ('pexels', 'pixabay', 'coverr', 'wikimedia', 'nasa')}
_HOSTS = {
    'pexels': {'api.pexels.com', 'www.pexels.com', 'pexels.com',
               'videos.pexels.com', 'images.pexels.com', 'static.pexels.com',
               'static-videos.pexels.com', 'player.vimeo.com'},
    'pixabay': {'pixabay.com', 'www.pixabay.com', 'cdn.pixabay.com',
                'videos.pixabay.com', 'vimeo.com', 'player.vimeo.com'},
    'coverr': {'api.coverr.co', 'coverr.co', 'www.coverr.co', 'storage.coverr.co'},
    'wikimedia': {'commons.wikimedia.org', 'upload.wikimedia.org'},
    'nasa': {'images-api.nasa.gov', 'images.nasa.gov', 'images-assets.nasa.gov',
             'www.nasa.gov', 'nasa.gov'},
}
_LICENSES = {
    'pexels': ('Pexels License', 'https://www.pexels.com/license/'),
    'pixabay': ('Pixabay Content License', 'https://pixabay.com/service/license-summary/'),
    'coverr': ('Coverr License', 'https://coverr.co/license'),
    'nasa': ('Public domain', 'https://www.nasa.gov/nasa-brand-center/images-and-media/'),
}
_PAGE_HOSTS = {
    'pexels': {'www.pexels.com', 'pexels.com'},
    'pixabay': {'www.pixabay.com', 'pixabay.com'},
    'coverr': {'www.coverr.co', 'coverr.co'},
    'wikimedia': {'commons.wikimedia.org'},
    'nasa': {'images.nasa.gov'},
}


class StockSourceError(RuntimeError):
    """Safe error without remote URLs, response bodies or credentials."""


def _text(value: object, maximum: int = 1000) -> str:
    return html.unescape(re.sub(r'<[^>]*>', '', str(value or '')))[:maximum].strip()


def _number(value: object) -> float:
    try:
        result = float(value)
        return max(0.0, result) if math.isfinite(result) else 0.0
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _public_url(value: object) -> str:
    """Public attribution pages only; query, fragments and userinfo never persist."""
    try:
        parsed = urlsplit(str(value or ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return ''
        if parsed.port not in (None, 443):
            return ''
        return urlunsplit(('https', parsed.hostname, parsed.path, '', ''))
    except ValueError:
        return ''


def _commons_license(name: str, url: str) -> bool:
    name = name.upper().strip()
    if any(flag in name for flag in ('-SA', '-NC', '-ND', 'SHARE', 'NONCOMMERCIAL', 'NO DERIV')):
        return False
    if name in {'CC0', 'CC0 1.0', 'PUBLIC DOMAIN', 'PUBLIC DOMAIN MARK', 'PDM', 'PDM 1.0'}:
        return True
    return bool(re.fullmatch(r'CC BY (?:1\.0|2\.0|2\.5|3\.0|4\.0)', name)
                and re.fullmatch(r'https://creativecommons\.org/licenses/by/[\d.]+/?', url))


def _source_url(provider: str, value: object) -> str:
    url = _public_url(value)
    return url if urlsplit(url).hostname in _PAGE_HOSTS.get(provider, set()) else ''


@dataclass(frozen=True)
class StockCandidate:
    provider: str
    asset_id: str
    title: str
    download_url: str = field(repr=False)
    source_url: str
    license: str
    license_url: str
    author: str
    kind: str = 'video'
    tags: tuple[str, ...] = ()
    duration: float = 0
    width: int = 0
    height: int = 0
    local_path: Path | None = None

    def to_dict(self) -> dict:
        """Manifest-safe metadata; deliberately excludes download_url/local paths."""
        return {
            'provider': self.provider, 'asset_id': _text(self.asset_id, 300),
            'title': _text(self.title), 'source_url': _source_url(self.provider, self.source_url),
            'license': _text(self.license, 100), 'license_url': _public_url(self.license_url),
            'author': _text(self.author), 'kind': self.kind,
            'tags': [_text(tag, 100) for tag in self.tags[:50]],
            'duration': _number(self.duration), 'width': int(_number(self.width)),
            'height': int(_number(self.height)),
            'attribution': f'{_text(self.title)} — {_text(self.author)} / {self.provider} ({_text(self.license, 100)})',
        }


def _candidate_from(data: dict, local: Path | None = None) -> StockCandidate:
    fields = {key: data[key] for key in (
        'provider', 'asset_id', 'title', 'source_url', 'license', 'license_url',
        'author', 'kind', 'duration', 'width', 'height')}
    return StockCandidate(**fields, download_url='', tags=tuple(data.get('tags', [])), local_path=local)


class _SafeRedirect(HTTPRedirectHandler):
    def __init__(self, validate: Callable[[str], None], authenticated: bool):
        self.validate = validate
        self.authenticated = authenticated

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if self.authenticated:
            raise StockSourceError('Authenticated API redirects are unsupported')
        self.validate(newurl)
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected


class StockService:
    def __init__(self, root: Path, *, keys: dict[str, list[str]], enabled: list[str],
                 checkpoint: Callable[[], None] | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.originals = self.root / 'originals'
        self.originals.mkdir(exist_ok=True)
        (self.root / 'locks').mkdir(exist_ok=True)
        self.keys = {provider: list(dict.fromkeys(
            key.strip() for key in values if isinstance(key, str) and key.strip()))
            for provider, values in keys.items() if isinstance(values, (list, tuple))}
        self.enabled = tuple(dict.fromkeys(
            canonical for name in enabled
            if (canonical := ('wikimedia' if name == 'commons' else name)) in _HOSTS))
        self.checkpoint = checkpoint or (lambda: None)
        self._transfer_context = threading.local()
        self._urls: dict[tuple[str, str, str], str] = {}
        self.db_path = self.root / 'stock-cache.sqlite3'
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS rotation(provider TEXT PRIMARY KEY, cursor INTEGER NOT NULL DEFAULT 0,
                    cooldown REAL NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS key_state(provider TEXT NOT NULL, hash TEXT NOT NULL,
                    bad INTEGER NOT NULL DEFAULT 0, cooldown REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(provider, hash));
                CREATE TABLE IF NOT EXISTS searches(provider TEXT NOT NULL, query TEXT NOT NULL,
                    kind TEXT NOT NULL, created REAL NOT NULL, metadata TEXT NOT NULL,
                    PRIMARY KEY(provider, query, kind));
                CREATE TABLE IF NOT EXISTS assets(identity TEXT PRIMARY KEY, digest TEXT NOT NULL,
                    filename TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS assets_digest ON assets(digest);
                PRAGMA user_version=1;
            ''')

    def _checkpoint(self):
        (getattr(self._transfer_context, 'checkpoint', None) or self.checkpoint)()

    @contextmanager
    def _api_slot(self, provider):
        while not _API_SLOTS[provider].acquire(timeout=.2):
            self._checkpoint()
        try:
            self._checkpoint()
            yield
        finally:
            _API_SLOTS[provider].release()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.db_path, timeout=20)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def _lock(self, identity: str):
        """OS file lock releases on process death; no stale-lock deletion races."""
        with (self.root / 'locks' / (identity + '.lock')).open('a+b') as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b'0')
                handle.flush()
            deadline = time.monotonic() + 120
            while True:
                self._checkpoint()
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (OSError, BlockingIOError):
                    if time.monotonic() > deadline:
                        raise StockSourceError('Stock cache is busy') from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _key(self, provider: str) -> str | None:
        keys = self.keys.get(provider, [])
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO rotation(provider) VALUES (?)', (provider,))
            cursor, cooldown = db.execute(
                'SELECT cursor,cooldown FROM rotation WHERE provider=?', (provider,)).fetchone()
            if cooldown > time.time():
                raise StockSourceError('Provider is cooling down')
            if provider in {'wikimedia', 'nasa'}:
                return None
            for offset in range(len(keys)):
                index = (cursor + offset) % len(keys)
                hashed = sha256(keys[index].encode()).hexdigest()
                row = db.execute('SELECT bad,cooldown FROM key_state WHERE provider=? AND hash=?',
                                 (provider, hashed)).fetchone()
                if row and (row[0] or row[1] > time.time()):
                    continue
                db.execute('UPDATE rotation SET cursor=? WHERE provider=?', (index + 1, provider))
                return keys[index]
        raise StockSourceError('No available provider credentials')

    def _status(self, provider: str, key: str | None, error: HTTPError):
        if error.code not in (401, 403, 429):
            return
        cooldown = 0.0
        if error.code == 429:
            raw = str(error.headers.get('Retry-After', '60')) if error.headers else '60'
            try:
                wait = float(raw)
            except ValueError:
                try:
                    wait = parsedate_to_datetime(raw).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError):
                    wait = 60
            cooldown = time.time() + max(60, wait if math.isfinite(wait) else 60)
        with self._db() as db:
            db.execute('INSERT OR IGNORE INTO rotation(provider) VALUES (?)', (provider,))
            if cooldown:
                db.execute('UPDATE rotation SET cooldown=MAX(cooldown,?) WHERE provider=?',
                           (cooldown, provider))
            if key:
                db.execute('''INSERT INTO key_state(provider,hash,bad,cooldown) VALUES (?,?,?,?)
                    ON CONFLICT(provider,hash) DO UPDATE SET bad=MAX(bad,excluded.bad),
                    cooldown=MAX(cooldown,excluded.cooldown)''',
                    (provider, sha256(key.encode()).hexdigest(), int(error.code in (401, 403)), cooldown))

    def _validate_url(self, provider: str, url: str):
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or parsed.username or parsed.password
                    or parsed.hostname not in _HOSTS.get(provider, set())
                    or parsed.port not in (None, 443) or '\\' in url
                    or any(ord(c) < 32 for c in url)):
                raise StockSourceError('Unsupported provider URL')
            addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
                raise StockSourceError('Provider URL resolves to a private address')
        except (ValueError, OSError):
            raise StockSourceError('Provider URL validation failed') from None

    def _open(self, request: Request, *, provider: str, authenticated: bool):
        opener = build_opener(_SafeRedirect(
            lambda url: self._validate_url(provider, url), authenticated))
        return opener.open(request, timeout=15)

    def _json(self, provider: str, endpoint: str, params: dict | None = None) -> dict:
        self._checkpoint()
        key = self._key(provider)
        params = dict(params or {})
        headers = {'User-Agent': 'NewsFlow/1.0 (stock media discovery)', 'Accept': 'application/json'}
        if provider == 'pixabay':
            params['key'] = key
        elif key:
            headers['Authorization'] = ('Bearer ' if provider == 'coverr' else '') + key
        url = endpoint + (('?' + urlencode(params)) if params else '')
        self._validate_url(provider, url)
        try:
            with self._api_slot(provider), self._open(Request(url, headers=headers), provider=provider, authenticated=bool(key)) as response:
                raw = response.read(_MAX_JSON_BYTES + 1)
                if len(raw) > _MAX_JSON_BYTES:
                    raise StockSourceError('Provider response is too large')
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise StockSourceError('Unsupported provider response')
                return result
        except HTTPError as error:
            self._status(provider, key, error)
            error.close()
            raise StockSourceError('Provider rejected request') from None
        except InterruptedError:
            raise
        except (OSError, ValueError):
            raise StockSourceError('Provider request failed') from None

    @staticmethod
    def _query(query: str, kind: str) -> str:
        if kind not in ('video', 'image'):
            raise ValueError('Stock kind must be video or image')
        return ' '.join(str(query).split())[:300].casefold()

    def search(self, query: str, *, kind: str = 'video', limit: int = 6) -> list[StockCandidate]:
        query = self._query(query, kind)
        self._checkpoint()
        if not query or not self.enabled or limit <= 0:
            return []
        limit = min(_MAX_RESULTS, int(limit))
        with ThreadPoolExecutor(max_workers=min(5, len(self.enabled))) as pool:
            futures = [pool.submit(self._search, provider, query, kind) for provider in self.enabled]
            groups = []
            for future in futures:
                try:
                    groups.append(future.result())
                except InterruptedError:
                    raise
                except (StockSourceError, OSError, ValueError, KeyError, TypeError):
                    groups.append([])
        # Interleave sources so a single source cannot consume the whole limit.
        result = []
        for index in range(_MAX_RESULTS):
            for group in groups:
                if index < len(group):
                    result.append(group[index])
                    if len(result) == limit:
                        return result
        return result

    def _search(self, provider: str, query: str, kind: str) -> list[StockCandidate]:
        if provider == 'coverr' and kind == 'image':
            return []
        identity = sha256(f'search:{provider}:{kind}:{query}'.encode()).hexdigest()
        with self._lock(identity):
            with self._db() as db:
                cached = db.execute('SELECT created,metadata FROM searches WHERE provider=? AND query=? AND kind=?',
                                    (provider, query, kind)).fetchone()
            if cached and cached[0] > time.time() - _TTL:
                return [self._attach_local(_candidate_from(item)) for item in json.loads(cached[1])]
            if provider == 'pexels':
                path = 'videos/search' if kind == 'video' else 'search'
                data = self._json(provider, f'https://api.pexels.com/v1/{path}',
                                  {'query': query, 'per_page': _MAX_RESULTS})
            elif provider == 'pixabay':
                data = self._json(provider, 'https://pixabay.com/api/' + ('videos/' if kind == 'video' else ''),
                                  {'q': query, 'per_page': _MAX_RESULTS, 'safesearch': 'true'})
            elif provider == 'coverr':
                data = self._json(provider, 'https://api.coverr.co/videos',
                                  {'query': query, 'page_size': _MAX_RESULTS, 'urls': 'true'})
            elif provider == 'wikimedia':
                data = self._json(provider, 'https://commons.wikimedia.org/w/api.php', {
                    'action': 'query', 'format': 'json', 'formatversion': 2,
                    'generator': 'search', 'gsrsearch': query + (' filetype:video' if kind == 'video' else ' filetype:bitmap'),
                    'gsrnamespace': 6, 'gsrlimit': _MAX_RESULTS, 'prop': 'imageinfo',
                    'iiprop': 'url|mime|size|extmetadata'})
            else:
                data = self._json(provider, 'https://images-api.nasa.gov/search',
                                  {'q': query, 'media_type': kind, 'page_size': _MAX_RESULTS})
            found = self._parse(provider, data, kind)
            for item in found:
                self._urls[(provider, item.asset_id, kind)] = item.download_url
            with self._db() as db:
                db.execute('INSERT OR REPLACE INTO searches VALUES (?,?,?,?,?)',
                           (provider, query, kind, time.time(), json.dumps([x.to_dict() for x in found])))
            return [self._attach_local(item) for item in found]

    def _parse(self, provider: str, data: dict, kind: str) -> list[StockCandidate]:
        if provider == 'wikimedia':
            rows = data.get('query', {}).get('pages', [])
            rows = list(rows.values()) if isinstance(rows, dict) else rows
        elif provider == 'nasa':
            rows = data.get('collection', {}).get('items', [])
        else:
            rows = data.get(('videos' if kind == 'video' else 'photos') if provider == 'pexels' else 'hits', [])
        result = []
        if not isinstance(rows, list):
            return result
        for row in rows[:_MAX_RESULTS]:
            try:
                item = self._parse_item(provider, row, kind)
                if item and item.asset_id and item.source_url and item.license and item.author:
                    result.append(item)
            except (TypeError, ValueError, KeyError, AttributeError, IndexError):
                continue
        return result

    def _parse_item(self, provider: str, row: dict, kind: str) -> StockCandidate | None:
        asset_id = str(row.get('id', ''))
        title = _text(row.get('title') or row.get('alt') or row.get('tags') or asset_id)
        tags = row.get('tags', [])
        tags = tags.split(',') if isinstance(tags, str) else tags
        tags = tuple(_text(tag, 100) for tag in tags) if isinstance(tags, (list, tuple)) else ()
        width, height, duration = row.get('width', 0), row.get('height', 0), row.get('duration', 0)
        license_name, license_url = _LICENSES.get(provider, ('', ''))
        if provider == 'pexels':
            source = row.get('url', '')
            author = row.get('photographer') if kind == 'image' else row.get('user', {}).get('name')
            if kind == 'image':
                url = row.get('src', {}).get('original', '')
            else:
                files = [entry for entry in row.get('video_files', []) if entry.get('file_type') in (None, 'video/mp4')]
                best = max(files, key=lambda entry: _number(entry.get('width')) * _number(entry.get('height')), default={})
                url, width, height = best.get('link', ''), best.get('width', width), best.get('height', height)
        elif provider == 'pixabay':
            source, author = row.get('pageURL', ''), row.get('user', '')
            if kind == 'image':
                url = row.get('largeImageURL') or row.get('webformatURL', '')
                width, height = row.get('imageWidth', width), row.get('imageHeight', height)
            else:
                best = max(row.get('videos', {}).values(),
                           key=lambda entry: _number(entry.get('width')) * _number(entry.get('height')), default={})
                url, width, height = best.get('url', ''), best.get('width', width), best.get('height', height)
        elif provider == 'coverr':
            url = row.get('urls', {}).get('mp4_download', '')
            source = (_source_url(provider, row.get('canonical_url')) or _source_url(provider, row.get('url'))
                      or f'https://coverr.co/videos/{quote(asset_id, safe="")}')
            creator = row.get('creator') or row.get('author') or {}
            author = (creator.get('name') or creator.get('username')) if isinstance(creator, dict) else creator
            author = author or 'Coverr'
            width, height = row.get('max_width', width), row.get('max_height', height)
        elif provider == 'wikimedia':
            info = row.get('imageinfo', [])[0]
            mime = info.get('mime', '')
            if not mime.startswith(kind + '/') or mime in ('image/svg+xml', 'image/gif'):
                return None
            meta = info.get('extmetadata', {})
            license_name = _text(meta.get('LicenseShortName', {}).get('value'))
            license_url = _public_url(meta.get('LicenseUrl', {}).get('value'))
            if not _commons_license(license_name, license_url):
                return None
            author = _text(meta.get('Artist', {}).get('value'))
            title, asset_id = _text(row.get('title')), str(row.get('pageid', ''))
            source, url = info.get('descriptionurl', ''), info.get('url', '')
            width, height = info.get('width', 0), info.get('height', 0)
        else:
            meta = row.get('data', [])[0]
            rights = ' '.join(str(meta.get(key, '')) for key in ('description', 'description_508', 'rights', 'license'))
            lowered = _text(rights, 20000).lower()
            explicit_no_third = bool(re.search(r'no third[- ]party (?:rights|copyright)', lowered))
            if ('public domain' not in lowered or not explicit_no_third
                    or meta.get('copyright') or meta.get('third_party')
                    or re.search(r'(?:©|copyright\s+(?!free|does not|not applicable)|all rights reserved)', lowered)):
                return None
            asset_id, title = str(meta.get('nasa_id', '')), _text(meta.get('title'))
            author = _text(meta.get('photographer') or meta.get('secondary_creator') or meta.get('center') or 'NASA')
            source = 'https://images.nasa.gov/details/' + quote(asset_id, safe='')
            # Search links are previews; fetch resolves the original via /asset/:id.
            url = ''
            tags = tuple(_text(tag, 100) for tag in meta.get('keywords', [])[:50])
        if provider != 'nasa' and not url:
            return None
        return StockCandidate(provider, asset_id, title, str(url), _source_url(provider, source), license_name,
                              license_url, _text(author), kind, tags, _number(duration),
                              int(_number(width)), int(_number(height)))

    @staticmethod
    def _identity(candidate: StockCandidate) -> str:
        return sha256(f'{candidate.provider}:{candidate.kind}:{candidate.asset_id}'.encode()).hexdigest()

    def _verify_original(self, path: Path, expected_digest: str):
        """Recheck persisted bytes, including same-size edits; never heal in place."""
        if path.is_symlink():
            raise StockSourceError('Cached original failed integrity validation')
        digest, size = sha256(), 0
        try:
            with path.open('rb') as source:
                while True:
                    self._checkpoint()
                    chunk = source.read(256 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise StockSourceError('Cached original exceeds size limit')
                    digest.update(chunk)
        except InterruptedError:
            raise
        except OSError:
            raise StockSourceError('Cached original cannot be verified') from None
        if not size or digest.hexdigest() != expected_digest:
            raise StockSourceError('Cached original failed integrity validation')

    def _local(self, filename: str, expected_digest: str) -> Path | None:
        path = self.originals / filename
        if not re.fullmatch(r'[a-f0-9]{64}\.(?:mp4|webm|mov|jpg|jpeg|png|webp)', filename):
            return None
        if filename.split('.', 1)[0] != expected_digest:
            raise StockSourceError('Cached original failed integrity validation')
        if path.is_symlink() or path.resolve().parent != self.originals.resolve() or not path.is_file():
            return None
        self._verify_original(path, expected_digest)
        return path

    def _attach_local(self, item: StockCandidate) -> StockCandidate:
        with self._db() as db:
            row = db.execute('SELECT filename,digest FROM assets WHERE identity=?', (self._identity(item),)).fetchone()
        return replace(item, local_path=self._local(row[0], row[1]) if row else None)

    def cached(self, query: str, kind: str = 'video') -> list[StockCandidate]:
        # Keep the small list contract for existing callers. Selection consumes
        # every lazy page, so ineligible recent entries cannot hide older files.
        return next(self.cached_batches(query, kind), [])

    def cached_batches(self, query: str, kind: str = 'video'):
        query = self._query(query, kind)
        tokens = set(re.findall(r'\w+', query))
        before = None
        while True:
            self._checkpoint()
            # Release the DB connection before yielding/decoding media. A
            # descending rowid cursor is stable when concurrent downloads add
            # newer assets, and does not accumulate the whole library in RAM.
            with self._db() as db:
                rows = db.execute(
                    'SELECT rowid,filename,digest,metadata FROM assets '
                    'WHERE (? IS NULL OR rowid < ?) ORDER BY rowid DESC LIMIT 500',
                    (before, before)).fetchall()
            if not rows:
                return
            before = rows[-1][0]
            ranked = []
            for _, filename, digest, raw in rows:
                data = json.loads(raw)
                if data.get('kind') != kind:
                    continue
                words = set(re.findall(r'\w+', (' '.join(data.get('tags', [])) + ' ' + data.get('title', '')).casefold()))
                score = len(tokens & words)
                if score or not tokens:
                    ranked.append((score, filename, digest, data))
            ranked.sort(key=lambda item: -item[0])
            result = []
            for _, filename, digest, data in ranked:
                self._checkpoint()
                try:
                    path = self._local(filename, digest)
                except StockSourceError:
                    continue
                if path:
                    result.append(_candidate_from(data, path))
                    if len(result) == _MAX_RESULTS:
                        yield result
                        result = []
            if result:
                yield result

    def _check_cooldown(self, provider: str):
        with self._db() as db:
            row = db.execute('SELECT cooldown FROM rotation WHERE provider=?', (provider,)).fetchone()
        if row and row[0] > time.time():
            raise StockSourceError('Provider is cooling down')

    def _resolve(self, item: StockCandidate) -> str:
        remembered = self._urls.get((item.provider, item.asset_id, item.kind))
        if item.download_url or remembered:
            return item.download_url or remembered
        provider, asset_id = item.provider, quote(item.asset_id, safe='')
        if provider == 'nasa':
            data = self._json(provider, 'https://images-api.nasa.gov/asset/' + asset_id)
            extensions = ('.mp4', '.webm', '.mov') if item.kind == 'video' else ('.jpg', '.jpeg', '.png')
            urls = [entry.get('href', '') for entry in data.get('collection', {}).get('items', [])]
            urls = [url for url in urls if urlsplit(url).path.lower().endswith(extensions)]
            return next((url for url in urls if '~orig' in url or '~large' in url), next(iter(urls), ''))
        if provider == 'pexels':
            suffix = 'videos/videos/' if item.kind == 'video' else 'photos/'
            data = self._json(provider, 'https://api.pexels.com/v1/' + suffix + asset_id)
            parsed = self._parse(provider, {'videos' if item.kind == 'video' else 'photos': [data]}, item.kind)
        elif provider == 'pixabay':
            data = self._json(provider, 'https://pixabay.com/api/' + ('videos/' if item.kind == 'video' else ''),
                              {'id': item.asset_id})
            parsed = self._parse(provider, data, item.kind)
        elif provider == 'coverr':
            data = self._json(provider, 'https://api.coverr.co/videos/' + asset_id, {'urls': 'true'})
            parsed = self._parse(provider, {'hits': [data]}, item.kind)
        else:
            data = self._json(provider, 'https://commons.wikimedia.org/w/api.php', {
                'action': 'query', 'format': 'json', 'formatversion': 2, 'pageids': item.asset_id,
                'prop': 'imageinfo', 'iiprop': 'url|mime|size|extmetadata'})
            parsed = self._parse(provider, data, item.kind)
        return next((entry.download_url for entry in parsed if entry.asset_id == item.asset_id), '')

    def fetch(self, candidate: StockCandidate, *, checkpoint=None, progress=None) -> Path:
        previous = getattr(self._transfer_context, 'checkpoint', None)
        self._transfer_context.checkpoint = checkpoint
        try:
            return self._fetch(candidate, progress)
        finally:
            self._transfer_context.checkpoint = previous

    def _fetch(self, candidate: StockCandidate, progress=None) -> Path:
        self._checkpoint()
        if candidate.provider == 'commons':
            candidate = replace(candidate, provider='wikimedia')
        provider = candidate.provider
        if provider not in _HOSTS or candidate.kind not in ('image', 'video'):
            raise StockSourceError('Unsupported stock source')
        if provider not in self.enabled:
            raise StockSourceError('Stock source is disabled')
        if provider == 'wikimedia':
            allowed = _commons_license(candidate.license, candidate.license_url)
        else:
            allowed = candidate.license == _LICENSES[provider][0]
        if not allowed or not candidate.author or not _source_url(provider, candidate.source_url):
            raise StockSourceError('Missing supported license or attribution')
        identity = self._identity(candidate)
        with self._lock(identity):
            attached = self._attach_local(candidate)
            if attached.local_path:
                return attached.local_path
            self._check_cooldown(provider)
            url = self._resolve(candidate)
            self._validate_url(provider, url)
            suffix = Path(urlsplit(url).path).suffix.lower()
            allowed_extensions = ('.mp4', '.webm', '.mov') if candidate.kind == 'video' else ('.jpg', '.jpeg', '.png', '.webp')
            if suffix not in allowed_extensions:
                suffix = '.mp4' if candidate.kind == 'video' else '.jpg'
            descriptor, name = tempfile.mkstemp(prefix='download-', suffix='.part', dir=self.originals)
            temporary = Path(name)
            try:
                digest, size = sha256(), 0
                deadline = time.monotonic() + 120
                with os.fdopen(descriptor, 'wb') as output:
                    with self._open(Request(url, headers={'User-Agent': 'NewsFlow/1.0'}),
                                    provider=provider, authenticated=False) as response:
                        if int(response.headers.get('Content-Length', '0')) > MAX_DOWNLOAD_BYTES:
                            raise StockSourceError('Stock download exceeds size limit')
                        if any(mime in response.headers.get('Content-Type', '').lower() for mime in ('text/html', 'application/json')):
                            raise StockSourceError('Stock response is not media')
                        while True:
                            self._checkpoint()
                            if time.monotonic() > deadline:
                                raise StockSourceError('Stock download timed out')
                            chunk = response.read(256 * 1024)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > MAX_DOWNLOAD_BYTES:
                                raise StockSourceError('Stock download exceeds size limit')
                            output.write(chunk)
                            digest.update(chunk)
                            if progress:
                                progress(size)
                    output.flush()
                    os.fsync(output.fileno())
                if not size:
                    raise StockSourceError('Stock download is empty')
                hashed = digest.hexdigest()
                with self._lock(hashed):
                    with self._db() as db:
                        existing = db.execute('SELECT filename FROM assets WHERE digest=? LIMIT 1', (hashed,)).fetchone()
                    target = self._local(existing[0], hashed) if existing else None
                    if target is None:
                        target = self.originals / (hashed + suffix)
                        if target.exists():
                            self._verify_original(target, hashed)
                        else:
                            os.replace(temporary, target)
                            target.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
                    metadata = candidate.to_dict()
                    metadata.update({'sha256': hashed, 'bytes': size,
                                     'downloaded_at': datetime.now(timezone.utc).isoformat()})
                    with self._db() as db:
                        db.execute('INSERT OR REPLACE INTO assets VALUES (?,?,?,?)',
                                   (identity, hashed, target.name, json.dumps(metadata)))
                    return target
            except HTTPError as error:
                self._status(provider, None, error)
                error.close()
                raise StockSourceError('Provider rejected media download') from None
            except InterruptedError:
                raise
            except StockSourceError:
                raise
            except (OSError, ValueError):
                raise StockSourceError('Stock download failed') from None
            finally:
                temporary.unlink(missing_ok=True)
