from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import (
    SCREEN_TEXT_CLASSIFIER_VERSION,
    ClipIndex,
    IndexProgress,
    proxy_cache_excluded_paths,
)
from scriptor.footage import FootageItem


class MontageIndexBridgeIntegrityTests(unittest.TestCase):
    def test_proxy_exclusion_read_does_not_create_or_migrate_a_missing_index(self):
        """Proxy warm-up must not create the footage index as a side effect."""
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-readonly-index-") as temporary:
            database = Path(temporary) / "footage-index.sqlite3"
            self.assertFalse(database.exists())
            self.assertEqual(proxy_cache_excluded_paths(database), set())
            self.assertFalse(database.exists())

    def test_dead_proxy_worker_is_interrupted_not_a_fake_resumable_pause(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-dead-worker-") as temporary:
            root = Path(temporary)
            (root / "proxy-cache-status.json").write_text(
                '{"stage":"warming","active":true,"pauseRequested":true,"ownerPid":987654321}',
                encoding="utf-8",
            )
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "_index_process_is_running", return_value=False):
                status = bridge._read_proxy_cache_status()

            self.assertEqual(status["stage"], "interrupted")
            self.assertFalse(status["active"])
            self.assertFalse(status["pauseRequested"])
            self.assertIn("запустите", status["message"].casefold())

    def test_proxy_pause_control_survives_status_writes_until_safe_checkpoint(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-pause-control-") as temporary:
            root = Path(temporary)
            status = {"stage": "warming", "active": True, "pauseRequested": False}
            writes = []
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "snapshot", return_value={}):
                bridge._write_proxy_cache_status(status)
                bridge.set_proxy_cache_paused({"paused": True})
                self.assertTrue(bridge._read_proxy_cache_pause_requested())

                def release_after_first_sleep(_seconds):
                    writes.append(bridge._read_proxy_cache_status(check_owner=False))
                    bridge._write_proxy_cache_pause_requested(False)

                with patch.object(bridge.time, "sleep", side_effect=release_after_first_sleep):
                    bridge._proxy_cache_wait_if_paused(status)

            self.assertTrue(any(item.get("pauseRequested") for item in writes))
            self.assertFalse(status["pauseRequested"])

    def test_proxy_warmup_reports_unavailable_roots_as_terminal_error(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-missing-root-") as temporary:
            root = Path(temporary)
            settings = SimpleNamespace(footage_folders=[str(root / "missing-drive")])
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 self.assertRaisesRegex(ValueError, "доступную папку"):
                bridge.warm_proxy_cache({})
            with patch.object(bridge, "app_data_root", return_value=root):
                status = bridge._read_proxy_cache_status(check_owner=False)

            self.assertEqual(status["stage"], "error")
            self.assertFalse(status["active"])
            self.assertIn("доступную папку", status["error"])

    def test_proxy_warmup_uses_configured_roots_and_skips_currently_blocked_footage(self):
        """A prewarm respects the same persisted exclusion verdicts as Montage."""
        worker = getattr(bridge, "warm_proxy_cache", None)
        self.assertTrue(callable(worker), "proxy warm-up worker is not implemented")

        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-warmup-") as temporary:
            root = Path(temporary)
            library = root / "library"
            library.mkdir()
            allowed = library / "allowed.mp4"
            blocked = library / "blocked-title-card.mp4"
            allowed.touch()
            blocked.touch()
            cache = root / "RenderProxy" / "Sources" / "allowed.mp4"

            settings = SimpleNamespace(footage_folders=[str(library)])
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "proxy_cache_excluded_paths",
                              return_value={os.path.normcase(str(blocked.resolve()))}), \
                 patch.object(bridge, "scan_folders", return_value=[
                     FootageItem(str(allowed), allowed.name),
                     FootageItem(str(blocked), blocked.name),
                 ]), \
                 patch.object(bridge, "warm_source_proxy", return_value=(cache, False)) as warm, \
                 patch.object(bridge, "snapshot", return_value={}):
                result = worker({})
                status = bridge._read_proxy_cache_status()

            warm.assert_called_once_with(allowed.resolve(), 1920, 1080, heartbeat=None)
            self.assertEqual(result["proxyCacheResult"], {
                "total": 2,
                "processed": 2,
                "ready": 1,
                "skipped": 0,
                "excluded": 1,
                "failed": 0,
            })
            self.assertEqual(status["stage"], "complete")
            self.assertFalse(status["active"])

    def test_proxy_pause_rejects_a_completed_warmup(self):
        """A stale completed status must never become a fake paused worker."""
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-pause-") as temporary:
            root = Path(temporary)
            (root / "proxy-cache-status.json").write_text(
                '{"stage":"complete","active":false}', encoding="utf-8",
            )
            with patch.object(bridge, "app_data_root", return_value=root), \
                 self.assertRaisesRegex(ValueError, "сейчас не выполняется"):
                bridge.set_proxy_cache_paused({"paused": True})

    def test_proxy_exclusions_include_current_text_blocks_and_disabled_footage(self):
        with tempfile.TemporaryDirectory(prefix="newsflow-proxy-exclusions-") as temporary:
            root = Path(temporary)
            text_blocked = root / "title-card.mp4"
            manually_blocked = root / "background.mp4"
            allowed = root / "scene.mp4"
            for path in (text_blocked, manually_blocked, allowed):
                path.write_bytes(path.name.encode("utf-8"))
            index = ClipIndex(root / "footage-index.sqlite3")
            with index._connect() as connection:
                for path in (text_blocked, manually_blocked, allowed):
                    stat = path.stat()
                    connection.execute(
                        "INSERT INTO clips(path,name,size,mtime_ns) VALUES(?,?,?,?)",
                        (str(path.resolve()), path.name, stat.st_size, stat.st_mtime_ns),
                    )
                connection.execute(
                    "UPDATE clips SET english_text=1, english_text_version=? WHERE path=?",
                    (SCREEN_TEXT_CLASSIFIER_VERSION, str(text_blocked.resolve())),
                )
                connection.execute(
                    "UPDATE clips SET disabled=1 WHERE path=?",
                    (str(manually_blocked.resolve()),),
                )

            excluded = proxy_cache_excluded_paths(index.db_path)

            self.assertEqual(
                excluded,
                {os.path.normcase(str(text_blocked.resolve())),
                 os.path.normcase(str(manually_blocked.resolve()))},
            )

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

    def test_screen_text_maintenance_reprocesses_previous_classifier_version(self):
        """A changed classifier must not trust verdicts produced by the old algorithm."""
        with tempfile.TemporaryDirectory(prefix="newsflow-screen-text-version-") as temporary:
            root = Path(temporary)
            clip = root / "clip.mp4"
            clip.write_bytes(b"fixture")
            index = ClipIndex(root / "footage-index.sqlite3", embedder_factory=lambda: (object(), object()))
            previous_version = SCREEN_TEXT_CLASSIFIER_VERSION - 1
            with index._connect() as connection:
                stat = clip.stat()
                connection.execute(
                    "INSERT INTO clips(path,name,size,mtime_ns,english_text,english_text_version) "
                    "VALUES(?,?,?,?,?,?)",
                    (str(clip.resolve()), clip.name, stat.st_size, stat.st_mtime_ns,
                     -1, previous_version),
                )

            with patch.object(index, "_text_model_is_cached", return_value=True), \
                 patch.object(index, "_query_vectors", return_value=[]), \
                 patch.object(index, "_bounded_screen_text_state", return_value=-1) as classify:
                result = index.classify_english_screen_text()

            self.assertEqual(result["checked"], 1)
            classify.assert_called_once_with(
                clip,
                str(clip.resolve()),
                samples=11,
                finalize_uncertain_as_safe=True,
                raise_on_decode_error=True,
            )

    def test_screen_text_maintenance_reports_progress_before_a_full_batch_finishes(self):
        """A long V7 maintenance run must visibly advance before 384 files."""
        with tempfile.TemporaryDirectory(prefix="newsflow-screen-text-progress-") as temporary:
            root = Path(temporary)
            index = ClipIndex(root / "footage-index.sqlite3", embedder_factory=lambda: (object(), object()))
            for number in range(2):
                clip = root / f"clip-{number}.mp4"
                clip.write_bytes(b"fixture")
                stat = clip.stat()
                with index._connect() as connection:
                    connection.execute(
                        "INSERT INTO clips(path,name,size,mtime_ns,english_text,english_text_version) "
                        "VALUES(?,?,?,?,?,?)",
                        (str(clip.resolve()), clip.name, stat.st_size, stat.st_mtime_ns,
                         -1, SCREEN_TEXT_CLASSIFIER_VERSION - 1),
                    )

            progress: list[int] = []
            with patch.object(index, "_text_model_is_cached", return_value=True), \
                 patch.object(index, "_query_vectors", return_value=[]), \
                 patch.object(index, "_bounded_screen_text_state", return_value=-1):
                index.classify_english_screen_text(
                    progress=lambda state: progress.append(state.processed), batch_clips=384,
                )

            self.assertIn(1, progress)

    def test_screen_text_maintenance_reuses_existing_index_without_media_roots(self):
        """The desktop command must classify stored vectors, not rescan footage."""
        states = []

        class FakeIndex:
            db_path = Path("isolated-index.sqlite3")

            def __init__(self, _path):
                pass

            def classify_english_screen_text(self, progress=None):
                state = IndexProgress(
                    total=5, processed=5, indexed=5, skipped=0, failed=0,
                    stage="screen-text",
                )
                if progress:
                    progress(state)
                state.stage = "complete"
                if progress:
                    progress(state)
                return {"checked": 5, "blocked": 2, "safe": 3, "uncertain": 0}

            def screen_text_stats(self):
                return {"blocked": 2, "safe": 3, "unchecked": 0}

        with tempfile.TemporaryDirectory(prefix="newsflow-screen-text-command-") as temporary:
            root = Path(temporary)
            settings = SimpleNamespace(footage_folders=[])
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "ClipIndex", FakeIndex), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge, "_write_footage_index_status", side_effect=states.append):
                result = bridge.index_footage({"screenText": True})

        self.assertEqual(result["operationResult"]["kind"], "screen-text")
        self.assertEqual(result["indexResult"], {
            "total": 5,
            "processed": 5,
            "indexed": 5,
            "skipped": 0,
            "failed": 0,
            "removed": 0,
            "screenText": {
                "checked": 5, "blocked": 2, "safe": 3, "uncertain": 0, "modelReady": True,
            },
        })
        self.assertEqual(states[-1]["stage"], "complete")

    def test_screen_text_maintenance_reports_a_missing_local_text_model(self):
        class FakeIndex:
            db_path = Path("isolated-index.sqlite3")

            def __init__(self, _path):
                pass

            def classify_english_screen_text(self, progress=None):
                state = IndexProgress(
                    total=2, processed=0, indexed=0, skipped=0, failed=0,
                    stage="screen-text",
                )
                if progress:
                    progress(state)
                state.stage = "complete"
                if progress:
                    progress(state)
                return {"checked": 0, "blocked": 0, "safe": 0, "uncertain": 2}

        with tempfile.TemporaryDirectory(prefix="newsflow-screen-text-model-") as temporary:
            root = Path(temporary)
            settings = SimpleNamespace(footage_folders=[])
            with patch.object(bridge, "app_data_root", return_value=root), \
                 patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "ClipIndex", FakeIndex), \
                 patch.object(bridge, "snapshot", return_value={}):
                result = bridge.index_footage({"screenText": True})

        self.assertFalse(result["indexResult"]["screenText"]["modelReady"])


if __name__ == "__main__":
    unittest.main()
