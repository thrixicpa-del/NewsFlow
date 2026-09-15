from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from . import config
from .cover_library import CoverLibrary
from .config import (Settings, SettingsFileCorruptError, app_data_root, load_settings,
                     migrate_newsflow_storage, protect, save_settings)
from .core import ScenarioRequest
from .runner import Job, RunState
from .session import load_session, save_session


class TestStorageIsolationTests(unittest.TestCase):
    def test_test_runtime_refuses_production_storage_without_explicit_test_root(self):
        """A test process must fail before it can create/write canonical NewsFlow data."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NEWSFLOW_TEST_MODE", None)
            os.environ.pop("NEWSFLOW_TEST_ROOT", None)
            with self.assertRaisesRegex(RuntimeError, "NEWSFLOW_TEST_ROOT"):
                app_data_root()

    def test_explicit_test_root_rejects_declared_production_localappdata(self):
        """A test must fail, not redirect silently, when pointed at production."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            production_parent = root / "production-local-appdata"
            isolated_root = root / "isolated-test-storage"
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(isolated_root),
                "LOCALAPPDATA": str(production_parent),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(production_parent),
            }, clear=False):
                with self.assertRaisesRegex(RuntimeError, "production"):
                    app_data_root()

            self.assertFalse((isolated_root / "NewsFlow" / "settings.json").exists())
            self.assertFalse((production_parent / "NewsFlow" / "settings.json").exists())

    def test_test_root_is_used_when_localappdata_is_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated_root = Path(directory) / "isolated-test-storage"
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(isolated_root),
                "LOCALAPPDATA": str(isolated_root),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(Path(directory) / "production-local-appdata"),
            }, clear=False):
                test_path = app_data_root()
                save_settings(Settings(idea_results=["Тестовая тема"]))

            self.assertEqual(test_path, isolated_root / "NewsFlow")
            self.assertTrue((test_path / "settings.json").is_file())


class StorageMigrationTests(unittest.TestCase):
    def test_snapshot_temp_output_is_replaced_with_persistent_newsflow_folder(self):
        """A portable snapshot directory must never become the render destination."""
        persistent_root = Path(r"D:\NewsFlow Studio")
        snapshot_output = Path(
            r"C:\Users\borov\AppData\Local\Temp\newsflow-snapshot-xinegnir\output"
        )
        with patch("scriptor.config.storyflow_documents_root", return_value=persistent_root):
            result = migrate_newsflow_storage(str(snapshot_output), "Готовые ролики")

        self.assertEqual(result, str(persistent_root / "Готовые ролики"))


class AuthRecoveryTests(unittest.TestCase):
    def test_recovery_fills_only_missing_auth_and_channels_from_complete_library(self):
        """A blank upgraded profile must recover auth without touching production data."""
        from .config import recover_missing_auth_and_channels

        current = {
            "analytics_channels": [],
            "chrome_sessions": [{"label": "Текущая", "profile_id": "current"}],
            "youtube_oauth_tokens_protected": protect(json.dumps({})),
            "youtube_oauth_pending_handoffs_protected": protect(json.dumps({})),
            "youtube_api_key_protected": protect(""),
            "google_oauth_client_file": "",
            "youtube_oauth_service_url": "",
            "idea_topics": [{"title": "Не менять"}],
            "cover_queue": [{"title": "Не менять"}],
        }
        legacy = {
            "analytics_channels": [{"profile_id": "channel-1", "name": "Канал"}],
            "chrome_sessions": [{"label": "Старая", "profile_id": "old"}],
            "youtube_oauth_tokens_protected": protect(json.dumps({"channel-1": "token"})),
            "youtube_oauth_pending_handoffs_protected": protect(json.dumps({"channel-1": {"state": "ready"}})),
            "youtube_api_key_protected": protect("api-key"),
            "google_oauth_client_file": r"C:\\oauth-client.json",
            "youtube_oauth_service_url": "https://oauth.example",
        }

        recovered, changed = recover_missing_auth_and_channels(current, [legacy])

        self.assertTrue(changed)
        self.assertEqual(recovered["analytics_channels"], legacy["analytics_channels"])
        self.assertEqual(recovered["chrome_sessions"], current["chrome_sessions"])
        self.assertEqual(recovered["idea_topics"], current["idea_topics"])
        self.assertEqual(recovered["cover_queue"], current["cover_queue"])
        self.assertEqual(recovered["google_oauth_client_file"], legacy["google_oauth_client_file"])
        self.assertEqual(recovered["youtube_oauth_tokens_protected"], legacy["youtube_oauth_tokens_protected"])

    def test_recovery_never_replaces_a_valid_current_channel_or_token(self):
        """A current logged-in profile always wins over an older backup."""
        from .config import recover_missing_auth_and_channels

        current = {
            "analytics_channels": [{"profile_id": "current-channel"}],
            "youtube_oauth_tokens_protected": protect(json.dumps({"current-channel": "current-token"})),
        }
        legacy = {
            "analytics_channels": [{"profile_id": "legacy-channel"}],
            "youtube_oauth_tokens_protected": protect(json.dumps({"legacy-channel": "legacy-token"})),
        }

        recovered, changed = recover_missing_auth_and_channels(current, [legacy])

        self.assertFalse(changed)
        self.assertEqual(recovered, current)


class CurrentRuntimePriorityTests(unittest.TestCase):
    def test_current_settings_do_not_implicitly_read_legacy_state(self):
        """An old Scriptor profile cannot alter current topics, covers or sessions on load."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_root = root / "current-test-storage"
            legacy_local_appdata = current_root
            current_settings = current_root / "NewsFlow" / "settings.json"
            current_settings.parent.mkdir(parents=True)
            current_settings.write_text(json.dumps({
                "idea_results": ["Текущая тема"],
                "cover_queue": [{"title": "Текущая обложка"}],
                "chrome_sessions": [],
            }, ensure_ascii=False), encoding="utf-8")
            legacy_settings = legacy_local_appdata / "Scriptor" / "settings.json"
            legacy_settings.parent.mkdir(parents=True)
            legacy_settings.write_text(json.dumps({
                "idea_results": ["Старая тема"],
                "cover_queue": [{"title": "Старая обложка"}],
                "chrome_sessions": [{"label": "Старая сессия", "profile_id": "legacy"}],
            }, ensure_ascii=False), encoding="utf-8")

            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(current_root),
                "LOCALAPPDATA": str(legacy_local_appdata),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production-local-appdata"),
            }, clear=False):
                settings = load_settings()

            self.assertEqual(settings.idea_results, ["Текущая тема"])
            self.assertEqual(settings.cover_queue, [{"title": "Текущая обложка"}])
            self.assertEqual(settings.chrome_sessions, [])


class SchemaVersionSafetyTests(unittest.TestCase):
    def test_runtime_seal_preserves_payload_and_rejects_a_prior_writer(self):
        """A schema-3 bridge must fail before it can write a schema-4 current state."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root),
                "LOCALAPPDATA": str(root),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production-local-appdata"),
            }, clear=False):
                path = app_data_root() / "settings.json"
                original = {
                    "schema_version": 3,
                    "idea_results": ["Текущая тема"],
                    "cover_queue": [{"production_item_id": "current:1", "title": "Текущая обложка"}],
                    "unknown_user_value": {"preserve": True},
                }
                path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")

                config.seal_current_runtime_storage()
                sealed = json.loads(path.read_text(encoding="utf-8"))

                self.assertEqual(sealed, {**original, "schema_version": 4})
                with patch.object(config, "SETTINGS_SCHEMA_VERSION", 3):
                    with self.assertRaises(config.SettingsSchemaVersionError):
                        load_settings()

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {**original, "schema_version": 4})

    def test_newer_settings_schema_refuses_downgrade_without_rewriting_data(self):
        """An old build must stop before it can replace data written by a newer runtime."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "isolated-test-storage"
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(current),
                "LOCALAPPDATA": str(current),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production-local-appdata"),
            }, clear=False):
                path = app_data_root() / "settings.json"
                raw = json.dumps({"schema_version": 999, "idea_results": ["Новая тема"]}, ensure_ascii=False)
                path.write_text(raw, encoding="utf-8")

                with self.assertRaisesRegex(RuntimeError, "новее"):
                    load_settings()

            self.assertEqual(path.read_text(encoding="utf-8"), raw)

    def test_restart_preserves_current_settings_scripts_and_covers_in_test_storage(self):
        """The current runtime must restart from its own state, not a legacy fallback."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {
                "NEWSFLOW_TEST_MODE": "1",
                "NEWSFLOW_TEST_ROOT": str(root),
                "LOCALAPPDATA": str(root),
                "NEWSFLOW_PRODUCTION_LOCALAPPDATA": str(root / "production-local-appdata"),
            }, clear=False):
                settings = Settings(
                    idea_results=["Текущая тема"],
                    cover_queue=[{"production_item_id": "pi-1", "title": "Текущая обложка"}],
                )
                save_settings(settings)
                save_session(["Текущая тема"], [
                    Job(ScenarioRequest(0, "Текущая тема", "P", "pi-1"), RunState.DONE, "Текущий сценарий", ""),
                ])
                library = CoverLibrary(app_data_root() / "covers-library.json")
                library.persist(settings.cover_queue, {"image": [], "video": []}, {})

                restarted = load_settings()
                titles, jobs = load_session()
                restored_covers, _capabilities, _usage = library.hydrate([], {"image": [], "video": []}, {})

            self.assertEqual(restarted.idea_results, ["Текущая тема"])
            self.assertEqual(titles, ["Текущая тема"])
            self.assertEqual(jobs[0].result, "Текущий сценарий")
            self.assertEqual(restored_covers[0]["title"], "Текущая обложка")


class CorruptSettingsSafetyTests(unittest.TestCase):
    def test_load_does_not_convert_corrupt_settings_into_default_state(self):
        """Replacing this error path with `data = {}` would destroy user state on a later save."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            path = Path(directory) / "NewsFlow" / "settings.json"
            path.parent.mkdir(parents=True)
            corrupt = '{"idea_topics": [broken-json'
            path.write_text(corrupt, encoding="utf-8")

            with self.assertRaises(SettingsFileCorruptError):
                load_settings()

            self.assertEqual(path.read_text(encoding="utf-8"), corrupt)

    def test_save_refuses_to_overwrite_corrupt_settings(self):
        """A stale worker must not atomically replace a recoverable corrupt file with defaults."""
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            path = Path(directory) / "NewsFlow" / "settings.json"
            path.parent.mkdir(parents=True)
            corrupt = '{"youtube_oauth_tokens_protected": invalid'
            path.write_text(corrupt, encoding="utf-8")

            with self.assertRaises(SettingsFileCorruptError):
                save_settings(Settings())

            self.assertEqual(path.read_text(encoding="utf-8"), corrupt)


class SnapshotReadSafetyTests(unittest.TestCase):
    def test_snapshot_does_not_create_or_persist_settings_without_an_explicit_command(self):
        """Turning a read refresh into an implicit migration write would recreate settings here."""
        from . import bridge

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"), \
                patch("scriptor.bridge.load_session", return_value=([], [])):
            bridge.snapshot()

            self.assertFalse((Path(directory) / "NewsFlow" / "settings.json").exists())

    def test_explicit_reconciliation_persists_legacy_production_item_recovery(self):
        """Legacy projection remains available, but only an explicit reconcile may commit it."""
        from . import bridge

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                patch("scriptor.config.storyflow_documents_root", return_value=Path(directory) / "media"), \
                patch("scriptor.bridge.load_session", return_value=([], [])):
            save_settings(Settings(idea_results=["Конкретная новость для старого проекта"]))

            bridge.reconcile_runtime_state()

            restored = load_settings()
            self.assertEqual(len(restored.idea_production_items), 1)
            self.assertEqual(restored.idea_production_items[0]["title"], "Конкретная новость для старого проекта")

    def test_reconcile_runtime_state_is_available_only_as_a_named_bridge_command(self):
        """A generic snapshot command must not be the only way to commit a migration."""
        from . import bridge

        response = {"operationResult": {"kind": "runtime-reconcile"}}
        output = StringIO()
        with patch.object(sys, "argv", ["bridge.py", "reconcile-runtime-state", "{}"]), \
                patch.object(bridge, "reconcile_runtime_state", return_value=response), \
                redirect_stdout(output):
            bridge.main()

        self.assertEqual(json.loads(output.getvalue()), response)
