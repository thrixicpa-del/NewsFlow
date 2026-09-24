"""Deterministic cross-process regressions for Montage owner publication."""
from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from queue import Empty
from unittest.mock import patch

from scriptor import bridge

_DEAD_PID = 2147483647
_WAIT_SECONDS = 15


def _claim_contender(root, role, mode, owner_pid, paused, contender_ready, publish, claimed, finish, results):
    """Keep a real child owner alive until both acquisition results are known."""
    real_dump = bridge.json.dump
    real_running = bridge._montage_process_is_running
    real_guard = bridge._exclusive_settings_write
    if role == "owner":
        owner_pid.value = os.getpid()

    def wait_for(event, message):
        if not event.wait(_WAIT_SECONDS):
            raise TimeoutError(message)

    @contextmanager
    def observed_guard(*args, **kwargs):
        if role == "contender":
            # In the fixed implementation the contender reaches the mutex
            # BEFORE it can inspect the partially published/stale record.
            contender_ready.set()
        with real_guard(*args, **kwargs):
            yield

    def delayed_dump(value, stream, *args, **kwargs):
        if role == "owner" and mode == "partial":
            # open("x") has already made an empty owner record visible.
            paused.set()
            wait_for(publish, "owner publication was not released")
        return real_dump(value, stream, *args, **kwargs)

    def observed_running(pid):
        if role == "owner" and mode == "stale" and pid == _DEAD_PID:
            paused.set()
            wait_for(publish, "stale-owner replacement was not released")
        if role == "contender" and (pid is None or pid == _DEAD_PID):
            # Old code has read an empty/dead record. Let the first caller
            # publish and CLOSE the live record before this stale reader
            # tries unlink(). This also reproduces on Windows, where an open
            # writer's handle would otherwise prevent deletion.
            contender_ready.set()
            wait_for(claimed, "first owner did not finish its claim")
        if pid == _DEAD_PID:
            return False
        if pid == owner_pid.value:
            # Windows intentionally recognises NewsFlowCore.exe, not this
            # fixture's python.exe. Model ONLY the known-live owner child as
            # packaged Core; keep the file operations and OS mutex real.
            return True
        return real_running(pid)

    lock_path = None
    with patch.object(bridge, "app_data_root", return_value=Path(root)), \
         patch.object(bridge, "_exclusive_settings_write", side_effect=observed_guard), \
         patch.object(bridge, "_montage_process_is_running", side_effect=observed_running), \
         patch.object(bridge.json, "dump", side_effect=delayed_dump):
        try:
            try:
                lock_path = bridge._claim_montage_queue_lock()
                results.put((role, lock_path is not None, ""))
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                results.put((role, False, f"{type(exc).__name__}: {exc}"))
            finally:
                if role == "owner":
                    claimed.set()
            if lock_path is not None:
                wait_for(finish, "parent did not release the acquired owner")
        finally:
            if lock_path is not None:
                bridge._release_montage_queue_lock(lock_path)


class MontageQueueLockTests(unittest.TestCase):
    def _check_contending_claims(self, mode):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(prefix="newsflow-montage-lock-") as temporary:
            root = Path(temporary)
            lock_path = root / "montage-queue.lock"
            if mode == "stale":
                lock_path.write_text(json.dumps({"pid": _DEAD_PID}), encoding="utf-8")
            owner_pid = context.Value("q", 0)
            paused, ready, publish, claimed, finish = [context.Event() for _ in range(5)]
            results = context.Queue()
            processes = [context.Process(
                target=_claim_contender,
                args=(str(root), role, mode, owner_pid, paused, ready, publish, claimed, finish, results),
                name=f"montage-lock-{role}",
            ) for role in ("owner", "contender")]
            started = []
            observed = []
            try:
                processes[0].start()
                started.append(processes[0])
                self.assertTrue(paused.wait(_WAIT_SECONDS), "owner never reached publication boundary")
                processes[1].start()
                started.append(processes[1])
                self.assertTrue(ready.wait(_WAIT_SECONDS), "contender never reached acquisition boundary")
                publish.set()
                for _ in processes:
                    try:
                        observed.append(results.get(timeout=_WAIT_SECONDS))
                    except Empty:
                        self.fail("a claimant did not return a result")
            finally:
                publish.set()
                finish.set()
                for process in started:
                    process.join(_WAIT_SECONDS)
                for process in started:
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
                "overlapping processes must not both acquire the Montage queue",
            )
            self.assertFalse(lock_path.exists(), "owner record was not released")

    def test_partial_owner_publication_cannot_be_reclaimed(self):
        self._check_contending_claims("partial")

    def test_two_stale_readers_cannot_replace_the_new_live_owner(self):
        self._check_contending_claims("stale")

    def test_failed_publication_releases_the_mutex_for_recovery(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-montage-lock-") as temporary:
            root = Path(temporary)
            with patch.object(bridge, "app_data_root", return_value=root):
                with patch.object(bridge.json, "dump", side_effect=OSError("publication failed")), \
                     self.assertRaisesRegex(OSError, "publication failed"):
                    bridge._claim_montage_queue_lock()
                owner = bridge._claim_montage_queue_lock()
                self.assertIsNotNone(owner)
                try:
                    self.assertIsNone(bridge._claim_montage_queue_lock())
                    self.assertEqual(json.loads(owner.read_text(encoding="utf-8"))["pid"], os.getpid())
                finally:
                    bridge._release_montage_queue_lock(owner)
                self.assertFalse((root / "montage-queue.lock").exists())


if __name__ == "__main__":
    unittest.main()
