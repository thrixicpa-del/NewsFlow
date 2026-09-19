from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import IndexProgress


class MontageIndexBridgeIntegrityTests(unittest.TestCase):
    def test_dead_active_owner_becomes_truthful_interrupted_resume_state(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-index-status-") as temporary:
            root = Path(temporary)
            status = root / "footage-index-status.json"
            status.write_text(
                '{"stage":"embedding","active":true,"ownerPid":987654321,'
                '"total":8,"processed":3,"indexed":2,"failed":1,"updatedAt":"old"}',
                encoding="utf-8",
            )
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_index_process_is_running", return_value=False):
                recovered = bridge._read_footage_index_status()

            self.assertEqual(recovered["stage"], "paused")
            self.assertFalse(recovered["active"])
            self.assertEqual((recovered["total"], recovered["processed"], recovered["indexed"]), (8, 3, 2))
            self.assertIn("прерван", recovered["message"].casefold())
            self.assertTrue(recovered["updatedAt"])

    def test_index_lock_allows_only_one_owner_inside_the_same_process(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-index-lock-") as temporary:
            root = Path(temporary)
            barrier = threading.Barrier(2)
            leases = []
            errors = []

            def claim():
                barrier.wait(timeout=2)
                try:
                    leases.append(bridge._claim_footage_index_lock())
                except RuntimeError as exc:
                    errors.append(str(exc))

            with patch.object(bridge, "app_data_root", return_value=root):
                workers = [threading.Thread(target=claim) for _ in range(2)]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join(timeout=3)
                for lease in leases:
                    lease.release()

            self.assertEqual(len(leases), 1)
            self.assertEqual(len(errors), 1)
            self.assertIn("уже выполняется", errors[0])

    def test_dead_process_lock_is_reclaimed(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-index-dead-lock-") as temporary:
            root = Path(temporary)
            lock_path = root / "footage-index-run.lock"
            lock_path.write_text('{"pid":987654321}', encoding="utf-8")
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_index_process_is_running", return_value=False):
                lease = bridge._claim_footage_index_lock()
                lease.release()

            self.assertFalse(lock_path.exists())

    def test_bridge_reports_media_scan_counts_instead_of_semantic_pass_counts(self):
        class FakeIndex:
            db_path = Path("isolated-index.sqlite3")

            def __init__(self, _path):
                pass

            def remove_missing(self):
                return 1

            def index_folders(self, _folders, progress=None):
                result = IndexProgress(total=4, processed=4, indexed=2, skipped=1, failed=1,
                                       stage="complete", removed=1)
                if progress:
                    progress(result)
                return result

            def enrich_semantic_tags(self, progress=None):
                raise AssertionError("base indexing must not run deep semantic enrichment")

        with tempfile.TemporaryDirectory(prefix="newsflow-index-command-") as temporary:
            root = Path(temporary)
            clips = root / "clips"
            clips.mkdir()
            settings = SimpleNamespace(footage_folders=[str(clips)])
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "ClipIndex", FakeIndex), \
                 patch.object(bridge, "snapshot", return_value={}):
                result = bridge.index_footage({})

            self.assertEqual(result["indexResult"], {
                "total": 4,
                "processed": 4,
                "indexed": 2,
                "skipped": 1,
                "failed": 1,
                "removed": 1,
            })


if __name__ == "__main__":
    unittest.main()
