"""Isolated regressions for snapshot revision binding versus local publication."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scriptor.session as session


class SessionRevisionSerializationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        settings = SimpleNamespace(
            deleted_scenario_titles=[], deleted_scenario_production_ids=[],
            idea_results=[], cover_queue=[],
        )
        root_patch = patch.object(session, "app_data_root", return_value=self.root)
        settings_patch = patch.object(session, "load_settings", return_value=settings)
        root_patch.start()
        settings_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(settings_patch.stop)

    def test_snapshot_binding_keeps_local_publication_locked(self):
        """A reader must not publish R1's revision after a local R2 writer."""
        session.save_session(["R1"], [])
        snapshot_parsed = threading.Event()
        release_reader = threading.Event()
        failures = []
        observed = []
        original = session._apply_scenario_tombstones

        def delayed_filter(titles, jobs, settings=None):
            snapshot_parsed.set()
            if not release_reader.wait(5):
                raise AssertionError("reader release was not signalled")
            return original(titles, jobs, settings=settings)

        def read():
            try:
                observed.append(session.load_session())
            except BaseException as error:
                failures.append(error)

        with patch.object(session, "_apply_scenario_tombstones", side_effect=delayed_filter):
            worker = threading.Thread(target=read, daemon=True)
            worker.start()
            try:
                self.assertTrue(snapshot_parsed.wait(5))
                key = str(session.session_path().resolve()).casefold()
                lock = session._SESSION_WRITE_LOCKS[key]
                acquired = lock.acquire(blocking=False)
                if acquired:
                    lock.release()
                self.assertFalse(acquired, "publication became possible before snapshot revision binding")
            finally:
                release_reader.set()
                worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(observed, [(["R1"], [])])
        session.save_session(["R2"], [])
        session.save_session(["R3"], [])
        self.assertEqual(session.load_session()[0], ["R3"])

    def test_external_revision_change_still_rejects_stale_writer(self):
        """Do not 'fix' the race by binding old state to the newest disk hash."""
        session.save_session(["R1"], [])
        original = session._remember_session_revision
        changed = False

        def external_commit(path, revision):
            nonlocal changed
            if not changed:
                changed = True
                session._write_session_file(path, session._session_data(["R2"], []))
            return original(path, revision)

        with patch.object(session, "_remember_session_revision", side_effect=external_commit):
            self.assertEqual(session.load_session()[0], ["R1"])
        with self.assertRaises(session.SessionWriteConflictError):
            session.save_session(["stale"], [])
        data = json.loads(session.session_path().read_text(encoding="utf-8"))
        self.assertEqual(data["titles"], ["R2"])

    def test_malformed_primary_recovery_remains_reentrant(self):
        session._write_session_file(
            session.backup_session_path(), session._session_data(["backup"], []),
        )
        session.session_path().write_text('{"titles":', encoding="utf-8")
        results = []
        failures = []

        def recover():
            try:
                results.append(session.load_session())
            except BaseException as error:
                failures.append(error)

        worker = threading.Thread(target=recover, daemon=True)
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive(), "recovery deadlocked inside the local snapshot lock")
        self.assertEqual(failures, [])
        self.assertEqual(results, [(["backup"], [])])
        session.save_session(["continued"], [])
        self.assertEqual(session.load_session()[0], ["continued"])

    def test_repeated_reader_and_writer_keep_complete_snapshots(self):
        session.save_session(["old"], [])
        stop = threading.Event()
        failures = []
        observed = []

        def read():
            while not stop.is_set():
                try:
                    observed.append(session.load_session()[0][0])
                except BaseException as error:
                    failures.append(error)
                    return

        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        try:
            for index in range(50):
                session.save_session([f"new-{index}"], [])
        finally:
            stop.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertTrue(set(observed).issubset({"old"} | {f"new-{i}" for i in range(50)}))
        self.assertEqual(session.load_session()[0], ["new-49"])


if __name__ == "__main__":
    unittest.main()
