"""Settings access races must not be treated as corrupt user data."""
import errno
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch

from scriptor import config


class SettingsReadRaceTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory(prefix="newsflow-settings-race-"))
        self.enterContext(patch.dict(os.environ, {
            "NEWSFLOW_TEST_MODE": "1", "NEWSFLOW_TEST_ROOT": root,
            "LOCALAPPDATA": root,
            "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(root) / "untouched-production"),
        }))
        self.enterContext(patch.object(config, "gpu_timeline_available", return_value=False))
        self.path = config.config_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.raw = json.dumps({
            "schema_version": 4, "idea_results": ["Preserved topic"],
            "cover_queue": [{"production_item_id": "pi-preserved", "title": "Preserved topic",
                             "image_prompt": "Literal manual prompt", "headline_source": "MANUAL"}],
            "unknown_operator_setting": "preserve on save",
        })
        self.path.write_text(self.raw, encoding="utf-8")

    def intermittent_reader(self, failures):
        read = Path.read_text
        pending = list(failures)

        def access(path, *args, **kwargs):
            if path == self.path and pending:
                raise pending.pop(0)
            return read(path, *args, **kwargs)

        return patch.object(Path, "read_text", access)

    def test_load_retries_permission_race_without_losing_manual_state(self):
        with self.intermittent_reader([PermissionError(errno.EACCES, "sharing race")]):
            settings = config.load_settings()
        self.assertEqual(settings.idea_results, ["Preserved topic"])
        self.assertEqual(settings.cover_queue[0]["production_item_id"], "pi-preserved")
        self.assertEqual(settings.cover_queue[0]["image_prompt"], "Literal manual prompt")
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.raw)

    def test_load_retries_file_disappearing_between_stat_and_open(self):
        with self.intermittent_reader([FileNotFoundError(errno.ENOENT, "replace race")]):
            settings = config.load_settings()
        self.assertEqual(settings.idea_results, ["Preserved topic"])

    def test_save_retries_current_disk_read_before_merging(self):
        settings = config.load_settings()
        settings.cover_variant_count = 3
        with self.intermittent_reader([PermissionError(errno.EACCES, "sharing race")]):
            config.save_settings(settings)
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(result["cover_variant_count"], 3)
        self.assertEqual(result["cover_queue"][0]["production_item_id"], "pi-preserved")

    def test_save_transient_missing_file_preserves_concurrent_manual_rows(self):
        stale = config.load_settings()
        latest = config.load_settings()
        latest.cover_queue.append({"production_item_id": "pi-concurrent", "title": "Concurrent topic",
                                   "image_prompt": "Concurrent manual scene", "prompt_provider": "manual"})
        config.save_settings(latest)
        with self.intermittent_reader([FileNotFoundError(errno.ENOENT, "replace race")]):
            config.save_settings(stale)
        rows = config.load_settings().cover_queue
        self.assertEqual({row["production_item_id"] for row in rows}, {"pi-preserved", "pi-concurrent"})
        self.assertEqual(rows[1]["image_prompt"], "Concurrent manual scene")

    def test_runtime_seal_retries_transient_read_and_keeps_bytes_if_already_current(self):
        with self.intermittent_reader([PermissionError(errno.EACCES, "sharing race")]):
            self.assertFalse(config.seal_current_runtime_storage())
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.raw)

    def test_voice_reconciliation_retries_the_same_settings_read_contract(self):
        with self.intermittent_reader([PermissionError(errno.EACCES, "sharing race")]):
            result = config.reconcile_voice_outputs([{"production_item_id": "absent"}])
        self.assertEqual(result["applied_indices"], [])

    def test_persistent_access_failure_is_bounded_and_not_labelled_corruption(self):
        attempts = []
        read = Path.read_text

        def denied(path, *args, **kwargs):
            if path == self.path:
                attempts.append(1)
                raise PermissionError(errno.EACCES, "persistent access denial")
            return read(path, *args, **kwargs)

        with patch.object(Path, "read_text", denied), patch.object(config.time, "sleep"), \
                self.assertRaises(RuntimeError) as caught:
            config.load_settings()
        self.assertNotIsInstance(caught.exception, config.SettingsFileCorruptError)
        self.assertGreater(len(attempts), 1)
        self.assertLessEqual(len(attempts), 25)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.raw)

    def test_bad_json_is_not_retried_or_overwritten(self):
        self.path.write_text('{"broken":', encoding="utf-8")
        with patch.object(config.time, "sleep") as delay:
            with self.assertRaises(config.SettingsFileCorruptError):
                config.load_settings()
            with self.assertRaises(config.SettingsFileCorruptError):
                config.save_settings(config.Settings())
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"broken":')
        delay.assert_not_called()

    def test_nonretryable_io_error_does_not_become_json_corruption(self):
        with self.intermittent_reader([OSError(errno.EIO, "disk failure")]), \
                patch.object(config.time, "sleep") as delay, self.assertRaises(RuntimeError) as caught:
            config.load_settings()
        self.assertNotIsInstance(caught.exception, config.SettingsFileCorruptError)
        delay.assert_not_called()
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.raw)

    def test_load_does_not_return_defaults_while_writer_lock_hides_existing_file(self):
        self.path.with_suffix(".lock").touch()
        exists = Path.exists

        def missing_during_replace(path):
            return False if path == self.path else exists(path)

        with patch.object(Path, "exists", missing_during_replace):
            self.assertEqual(config.load_settings().idea_results, ["Preserved topic"])

    def test_save_persistent_denial_never_replaces_existing_state(self):
        settings = config.load_settings()
        settings.cover_variant_count = 10
        failures = [PermissionError(errno.EACCES, "persistent access denial") for _ in range(20)]
        with self.intermittent_reader(failures), patch.object(config.time, "sleep"), \
                self.assertRaises(config.SettingsFileReadError):
            config.save_settings(settings)
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.raw)

    def test_native_concurrent_atomic_replacements_keep_reads_valid(self):
        payload = {**json.loads(self.raw), "synthetic_padding": "x" * 200_000}
        raw = json.dumps(payload)
        self.path.write_text(raw, encoding="utf-8")
        deadline = monotonic() + 1

        def writer():
            successes = 0
            temporary = self.path.with_suffix(".synthetic.tmp")
            while monotonic() < deadline:
                temporary.write_text(raw, encoding="utf-8")
                try:
                    os.replace(temporary, self.path)
                    successes += 1
                except PermissionError:
                    pass  # A locked destination is not a committed replacement.
                sleep(0.005)
            return successes

        def reader():
            successes = 0
            while monotonic() < deadline:
                self.assertEqual(json.loads(config._read_settings_text(self.path)), payload)
                successes += 1
                sleep(0.005)
            return successes

        with ThreadPoolExecutor(max_workers=11) as pool:
            writes = pool.submit(writer)
            reads = [pool.submit(reader) for _ in range(10)]
            self.assertGreater(writes.result(), 0)
            self.assertTrue(all(result.result() > 0 for result in reads))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), payload)

    def test_retained_initial_lock_does_not_block_a_new_profile(self):
        self.path.unlink()
        result = config.reconcile_voice_outputs([{"production_item_id": "missing"}])
        self.assertEqual(result["skip_reasons"], {"SETTINGS_MISSING": 1})
        self.assertTrue(self.path.with_suffix(".lock").exists())
        settings = config.load_settings()
        settings.idea_results = ["First topic"]
        config.save_settings(settings)
        self.assertEqual(config.load_settings().idea_results, ["First topic"])

    def test_stale_cover_save_cannot_share_completed_paths_between_same_title_ids(self):
        first = {"production_item_id": "first", "title": "Same topic", "status": "Готово",
                 "progress": 100, "paths": ["first-owned.png"]}
        second = {"production_item_id": "second", "title": "Same topic", "status": "Готово",
                  "progress": 100, "paths": ["second-owned.png"]}
        merged = config._merge_cover_queue([first, second], [
            {**first, "status": "Ожидает", "progress": 0, "paths": []},
            {**second, "status": "Ожидает", "progress": 0, "paths": []},
        ])
        self.assertEqual({row["production_item_id"]: row["paths"] for row in merged},
                         {"first": ["first-owned.png"], "second": ["second-owned.png"]})

    def test_reused_legacy_title_is_not_ownership_evidence_for_new_production_id(self):
        legacy = {"title": "Reused topic", "paths": ["old-cover.png"], "status": "Готово"}
        current = {"production_item_id": "new-item", "title": "Reused topic",
                   "paths": [], "status": "Ожидает"}
        merged = config._merge_cover_queue([legacy], [current])
        owned = next(row for row in merged if row.get("production_item_id") == "new-item")
        self.assertEqual(owned["paths"], [])
        self.assertEqual(owned["status"], "Ожидает")
