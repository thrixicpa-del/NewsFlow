"""Cross-process cover ownership without provider calls or production data."""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scriptor import bridge

_DEAD_PID = 2147483647
_WAIT_SECONDS = 15


def _claim_cover_contender(root, role, mode, owner_pid, paused, ready, publish, claimed, finish, results):
    real_dump = bridge.json.dump
    real_running = bridge._cover_generation_process_is_running
    real_guard = bridge._exclusive_settings_write
    if role == "owner":
        owner_pid.value = os.getpid()

    def wait_for(event, message):
        if not event.wait(_WAIT_SECONDS):
            raise TimeoutError(message)

    @contextmanager
    def observed_guard(*args, **kwargs):
        if role == "contender":
            ready.set()
        with real_guard(*args, **kwargs):
            yield

    def delayed_dump(value, stream, *args, **kwargs):
        if role == "owner" and mode == "partial":
            # The empty path is visible after open("x"), before JSON exists.
            paused.set()
            wait_for(publish, "parent did not release owner publication")
        return real_dump(value, stream, *args, **kwargs)

    def observed_running(pid):
        if role == "owner" and mode == "stale" and pid == _DEAD_PID:
            paused.set()
            wait_for(publish, "parent did not release stale-owner replacement")
        if role == "contender" and (pid is None or pid == _DEAD_PID):
            # Let the old implementation retain its stale observation, then
            # close the first writer before it unlinks the newly live record.
            # This ordering also reproduces with Windows file sharing rules.
            ready.set()
            wait_for(claimed, "first cover owner never completed publication")
        if pid == _DEAD_PID:
            return False
        if pid == owner_pid.value:
            return True  # Known-live child; liveness itself is tested below.
        return real_running(pid)

    lock_path = None
    with patch.object(bridge, "app_data_root", return_value=Path(root)), \
         patch.object(bridge, "_exclusive_settings_write", side_effect=observed_guard), \
         patch.object(bridge, "_cover_generation_process_is_running", side_effect=observed_running), \
         patch.object(bridge.json, "dump", side_effect=delayed_dump):
        try:
            try:
                lock_path = bridge._claim_cover_generation_lock()
                results.put((role, lock_path is not None, ""))
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                results.put((role, False, f"{type(exc).__name__}: {exc}"))
            finally:
                if role == "owner":
                    claimed.set()
            if lock_path is not None:
                wait_for(finish, "parent did not release cover owner")
        finally:
            if lock_path is not None:
                bridge._release_cover_generation_lock(lock_path)


class CoverGenerationOwnerTests(unittest.TestCase):
    def _check_contenders(self, mode):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as temporary:
            root = Path(temporary)
            lock_path = root / "cover-generation.lock"
            if mode == "stale":
                lock_path.write_text(json.dumps({"pid": _DEAD_PID}), encoding="utf-8")
            owner_pid = context.Value("q", 0)
            paused, ready, publish, claimed, finish = [context.Event() for _ in range(5)]
            results = context.Queue()
            processes = [context.Process(
                target=_claim_cover_contender,
                args=(str(root), role, mode, owner_pid, paused, ready, publish, claimed, finish, results),
                name=f"cover-owner-{role}",
            ) for role in ("owner", "contender")]
            started = []
            observed = []
            try:
                processes[0].start()
                started.append(processes[0])
                self.assertTrue(paused.wait(_WAIT_SECONDS), "owner missed publication boundary")
                processes[1].start()
                started.append(processes[1])
                self.assertTrue(ready.wait(_WAIT_SECONDS), "contender missed acquisition boundary")
                publish.set()
                observed = [results.get(timeout=_WAIT_SECONDS) for _ in processes]
            finally:
                publish.set()
                finish.set()
                for process in started:
                    process.join(_WAIT_SECONDS)
                    if process.is_alive():
                        process.terminate()
                        process.join(_WAIT_SECONDS)
                results.close()
                results.join_thread()
            self.assertEqual([process.exitcode for process in started], [0, 0])
            self.assertEqual([error for _, _, error in observed if error], [])
            self.assertEqual(
                {role: acquired for role, acquired, _ in observed},
                {"owner": True, "contender": False},
                "two cover processes must never both own one generation batch",
            )
            self.assertFalse(lock_path.exists())

    def test_partial_cover_owner_cannot_be_stolen(self):
        self._check_contenders("partial")

    def test_stale_cover_reader_cannot_replace_new_live_owner(self):
        self._check_contenders("stale")

    def test_windows_owner_identity_accepts_source_and_frozen_runtime(self):
        for executable, image, expected in (
            ("python.exe", "python.exe", True),
            ("NewsFlowCore.exe", "NewsFlowCore.exe", True),
            ("python.exe", "notepad.exe", False),
        ):
            with self.subTest(executable=executable, image=image):
                def query(_handle, _flags, buffer, _length, *, image=image):
                    buffer.value = f"C:/Runtime/{image}"
                    return True

                kernel = SimpleNamespace(
                    OpenProcess=Mock(return_value=1), QueryFullProcessImageNameW=query,
                    CloseHandle=Mock(),
                )
                windows_os = SimpleNamespace(name="nt", getpid=os.getpid)
                with patch.object(bridge, "os", windows_os), \
                     patch.object(bridge.sys, "executable", f"C:/Runtime/{executable}"), \
                     patch.object(ctypes, "windll", SimpleNamespace(kernel32=kernel), create=True):
                    self.assertEqual(bridge._cover_generation_process_is_running(_DEAD_PID), expected)
                kernel.CloseHandle.assert_called_once_with(1)

    def test_failed_publication_is_recoverable_and_foreign_owner_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"]) as temporary, \
             patch.object(bridge, "app_data_root", return_value=Path(temporary)):
            with patch.object(bridge.json, "dump", side_effect=OSError("publication failed")), \
                 self.assertRaisesRegex(OSError, "publication failed"):
                bridge._claim_cover_generation_lock()
            lock = bridge._claim_cover_generation_lock()
            self.assertIsNotNone(lock)
            try:
                self.assertIsNone(bridge._claim_cover_generation_lock())
                original = lock.read_bytes()
                with patch.object(bridge.os, "getpid", return_value=_DEAD_PID):
                    bridge._release_cover_generation_lock(lock)
                self.assertEqual(lock.read_bytes(), original)
            finally:
                bridge._release_cover_generation_lock(lock)
            self.assertFalse(lock.exists())
