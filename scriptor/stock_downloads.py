"""Queue-owned, bounded stock prefetch with durable, secret-free telemetry."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from concurrent.futures import CancelledError, ThreadPoolExecutor, TimeoutError
from hashlib import sha256
from pathlib import Path


def _process_token(pid: int):
    """Creation identity works for both source Python and Frozen, without PID reuse."""
    if pid <= 0:
        return None
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            try:
                exit_code = wintypes.DWORD()
                if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
                    return None
                times = [wintypes.FILETIME() for _ in range(4)]
                if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                    return None
                return f'{times[0].dwHighDateTime}:{times[0].dwLowDateTime}'
            finally:
                kernel.CloseHandle(handle)
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        if fields[0] in ('Z', 'X'):
            return None
        return fields[19]  # Linux stat field 22: process start time.
    except (OSError, ValueError, IndexError):
        return None


def read_download_status(path: Path) -> dict:
    """Read the last run even after exit; never present a dead owner as live."""
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(state, dict):
            return {}
        token = _process_token(int(state.get('pid', 0)))
        if state.get('running') and (not token or token != state.get('ownerToken')):
            state['running'] = False
            state['interrupted'] = True
        with path.with_suffix('.jsonl').open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 32768))
            lines = stream.read().splitlines()
        history = []
        for line in lines:
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    history.append(event)
            except (ValueError, AttributeError):
                continue
        state['history'] = history[-12:]
        return state
    except (OSError, ValueError, TypeError):
        return {}


class StockDownloadQueue:
    def __init__(self, workers: int, status_path: Path, *, paused=None, checkpoint=None):
        self.limit = max(1, int(workers))
        self.path = Path(status_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(self.limit * 2)
        self._pool = ThreadPoolExecutor(self.limit, thread_name_prefix='newsflow-stock')
        self._inflight = {}
        self._paused = paused or (lambda: False)
        self._checkpoint = checkpoint or (lambda: None)
        self._control_lock = threading.Lock()
        self._last_control = 0.0
        self._pause_state = False
        self._started = time.perf_counter()
        self._last_progress = 0.0
        self._state = {'runId': uuid.uuid4().hex, 'pid': os.getpid(), 'running': True,
                       'ownerToken': _process_token(os.getpid()),
                       'startedAt': time.time(), 'updatedAt': time.time(), 'limit': self.limit,
                       'active': 0, 'queued': 0, 'completed': 0, 'failed': 0, 'cancelled': 0,
                       'bytesDownloaded': 0, 'bytesPerSecond': 0, 'elapsedSeconds': 0,
                       'phaseSeconds': {'search': 0.0, 'validation': 0.0}}
        with self._lock:
            self._publish('started')

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def snapshot(self):
        with self._lock:
            return {**self._state, 'phaseSeconds': dict(self._state['phaseSeconds'])}

    def _publish(self, event):
        self._state['updatedAt'] = time.time()
        elapsed = max(.001, time.perf_counter() - self._started)
        self._state['elapsedSeconds'] = round(elapsed, 3)
        self._state['bytesPerSecond'] = round(self._state['bytesDownloaded'] / elapsed)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._state), encoding='utf-8')
        os.replace(temporary, self.path)
        with self.path.with_suffix('.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({**self._state, 'event': event}) + '\n')

    def checkpoint(self):
        while True:
            if self._stop.is_set():
                raise InterruptedError('Stock download queue stopped')
            # All transfers share one control poll: do not parse the large
            # production settings once per 256 KiB per download worker.
            with self._control_lock:
                now = time.perf_counter()
                if now - self._last_control >= .25:
                    self._checkpoint()
                    self._pause_state = bool(self._paused())
                    self._last_control = now
                paused = self._pause_state
            if not paused:
                return
            self._stop.wait(.2)

    @staticmethod
    def _key(service, candidate):
        # URLs, titles, credentials and raw provider identifiers are not logged.
        provider = 'wikimedia' if candidate.provider == 'commons' else candidate.provider
        return sha256(f'{Path(service.root).resolve()}:{provider}:{candidate.kind}:{candidate.asset_id}'.encode()).hexdigest()

    def submit(self, service, candidate, *, block=True):
        key = self._key(service, candidate)
        while True:
            with self._lock:
                if self._stop.is_set():
                    raise InterruptedError('Stock download queue stopped')
                if key in self._inflight:
                    return self._inflight[key]
                if self._slots.acquire(blocking=False):
                    self._state['queued'] += 1
                    try:
                        self._publish('queued')
                        future = self._pool.submit(self._run, service, candidate)
                    except BaseException:
                        self._state['queued'] -= 1
                        self._slots.release()
                        raise
                    self._inflight[key] = future
                    future.add_done_callback(lambda done: self._finished(key, done))
                    return future
            if not block:
                return None
            self.checkpoint()
            self._stop.wait(.05)

    def _run(self, service, candidate):
        transferred = 0
        def progress(total):
            nonlocal transferred
            with self._lock:
                self._state['bytesDownloaded'] += max(0, total - transferred)
                transferred = total
                if time.perf_counter() - self._last_progress >= 1:
                    self._last_progress = time.perf_counter()
                    self._publish('progress')
        with self._lock:
            self._state['queued'] -= 1
            self._state['active'] += 1
            self._publish('downloading')
        event = 'completed'
        try:
            return service.fetch(candidate, checkpoint=self.checkpoint, progress=progress)
        except (InterruptedError, CancelledError):
            event = 'cancelled'
            raise
        except BaseException:
            event = 'failed'
            raise
        finally:
            with self._lock:
                self._state['active'] -= 1
                self._state[event] += 1
                self._publish(event)

    def _finished(self, key, future):
        with self._lock:
            self._inflight.pop(key, None)
            self._slots.release()
            if future.cancelled():
                self._state['queued'] -= 1
                self._state['cancelled'] += 1
                self._publish('cancelled')

    def result(self, future, checkpoint=None):
        while True:
            (checkpoint or self.checkpoint)()
            try:
                return future.result(timeout=.2)
            except TimeoutError:
                if future.done():
                    return future.result()  # Propagate a transfer's own TimeoutError.

    def call(self, phase, function, *args, **kwargs):
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            with self._lock:
                self._state['phaseSeconds'][phase] += time.perf_counter() - started
                self._publish(phase)

    def close(self):
        self._stop.set()
        self._pool.shutdown(wait=True, cancel_futures=True)
        with self._lock:
            self._state['running'] = False
            self._publish('stopped')
