"""Independent persistence regressions for the stock download timeline."""
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scriptor.stock_downloads import StockDownloadQueue, read_download_status


class StockTimelinePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "downloads.json"
        self.candidate = SimpleNamespace(provider="nasa", kind="video", asset_id="fixture")

    def test_transient_reader_lock_does_not_fail_a_transfer_or_leave_stale_counts(self):
        real_replace = os.replace
        for blocked_state in ("queued", "active", "completed"):
            with self.subTest(blocked_state=blocked_state):
                calls, blocked = [], []

                def fetch(candidate, calls=calls, **kwargs):
                    calls.append(candidate.asset_id)
                    return self.root / "fixture.mp4"

                def replace_with_one_reader_lock(source, target, blocked_state=blocked_state, blocked=blocked):
                    state = json.loads(Path(source).read_text(encoding="utf-8"))
                    if state[blocked_state] == 1 and not blocked:
                        blocked.append(True)
                        raise PermissionError(13, "Windows reader temporarily holds status.json")
                    return real_replace(source, target)

                with StockDownloadQueue(1, self.path) as queue:
                    service = SimpleNamespace(root=self.root, fetch=fetch)
                    with patch("scriptor.stock_downloads.os.replace", side_effect=replace_with_one_reader_lock):
                        result = queue.result(queue.submit(service, self.candidate))
                    self.assertEqual(result, self.root / "fixture.mp4")
                self.assertTrue(blocked)
                self.assertEqual(calls, ["fixture"])
                state = read_download_status(self.path)
                self.assertEqual(
                    (state["queued"], state["active"], state["completed"], state["failed"]),
                    (0, 0, 1, 0),
                )
                self.assertFalse(state["running"])

    def test_overlapping_queue_writers_do_not_share_a_temporary_status_file(self):
        first = StockDownloadQueue(1, self.path)
        second = StockDownloadQueue(1, self.path)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        barrier = threading.Barrier(2)
        write_text = Path.write_text

        def synchronized_write(path, *args, **kwargs):
            result = write_text(path, *args, **kwargs)
            if path.suffix == ".tmp":
                barrier.wait(timeout=3)
            return result

        with patch.object(Path, "write_text", synchronized_write), ThreadPoolExecutor(2) as writers:
            futures = [writers.submit(queue.call, "search", lambda: 42) for queue in (first, second)]
            self.assertEqual([future.result(timeout=5) for future in futures], [42, 42])
        self.assertIn(read_download_status(self.path)["runId"],
                      {first.snapshot()["runId"], second.snapshot()["runId"]})

    @unittest.skipUnless(os.name == "nt", "Native Windows reader sharing semantics")
    def test_native_windows_reader_can_overlap_status_publication(self):
        reader = None
        reader_blocked = threading.Event()
        sharing_errors = []
        real_replace = os.replace

        def observed_replace(source, target):
            try:
                return real_replace(source, target)
            except PermissionError:
                sharing_errors.append(True)
                reader_blocked.set()
                raise

        with StockDownloadQueue(1, self.path) as queue:
            reader = self.path.open("rb")
            try:
                def release_reader():
                    self.assertTrue(reader_blocked.wait(timeout=3))
                    reader.close()

                service = SimpleNamespace(root=self.root, fetch=lambda *_a, **_k: self.root / "fixture.mp4")
                with ThreadPoolExecutor(1) as readers, patch("scriptor.stock_downloads.os.replace", observed_replace):
                    release = readers.submit(release_reader)
                    result = queue.result(queue.submit(service, self.candidate))
                    release.result(timeout=3)
                self.assertEqual(result, self.root / "fixture.mp4")
                self.assertTrue(sharing_errors, "The fixture must exercise native Windows sharing restrictions")
                self.assertEqual(queue.snapshot()["completed"], 1)
            finally:
                reader.close()
