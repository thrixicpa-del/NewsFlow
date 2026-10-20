"""Stock preferences and credentials never use production data or network."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scriptor import bridge, config


class StockSettingsTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        config.save_settings(config.Settings(montage_renderer="ffmpeg"))

    def test_modes_sources_and_trim_roundtrip_with_legacy_compatibility(self):
        for mode in ("local", "hybrid", "stock"):
            result = bridge.save_montage_settings({"sourceMode": mode, "stockSources": ["pexels", "nasa"], "stockTrim": False})
            self.assertEqual(result["montageSettings"]["sourceMode"], mode)
            self.assertEqual(result["montageSettings"]["stockSources"], ["pexels", "nasa"])
            self.assertFalse(config.load_settings().montage_stock_trim)
        before = (self.root / "NewsFlow/settings.json").read_bytes()
        for payload in ({"sourceMode": "random"}, {"stockSources": ["youtube"]}):
            with self.assertRaises(ValueError):
                bridge.save_montage_settings(payload)
            self.assertEqual((self.root / "NewsFlow/settings.json").read_bytes(), before)

    def test_hd_defaults_and_retired_continuity_setting_for_new_and_legacy_settings(self):
        path = self.root / "NewsFlow/settings.json"
        legacy = json.loads(path.read_text(encoding="utf-8"))
        legacy["montage_auto_fill_gaps"] = False
        legacy.pop("montage_stock_hd_only", None)
        path.write_text(json.dumps(legacy), encoding="utf-8")
        for settings in (config.Settings(), config.load_settings()):
            self.assertFalse(hasattr(settings, "montage_auto_fill_gaps"))
            self.assertTrue(settings.montage_stock_hd_only)

    def test_hd_preference_roundtrip_without_retired_continuity_setting(self):
        for hd in (False, True):
            settings = config.load_settings()
            settings.montage_stock_hd_only = hd
            config.save_settings(settings)
            restarted = config.load_settings()
            self.assertEqual(restarted.montage_stock_hd_only, hd)
            self.assertNotIn("montage_auto_fill_gaps", json.loads((self.root / "NewsFlow/settings.json").read_text(encoding="utf-8")))

    def test_stale_worker_preserves_hd_operator_changes(self):
        stale = config.load_settings()
        edited = config.load_settings()
        edited.montage_stock_hd_only = False
        config.save_settings(edited)
        stale.montage_task_statuses["1"] = {"status": "Рендер"}
        config.save_settings(stale)
        restarted = config.load_settings()
        self.assertFalse(restarted.montage_stock_hd_only)

    def test_library_checkbox_roundtrip_path_and_validation(self):
        result = bridge.save_montage_settings({"stockUseLibrary": False})
        self.assertFalse(result["montageSettings"]["stockUseLibrary"])
        self.assertFalse(config.load_settings().montage_stock_use_library)
        expected = str(Path(config.load_settings().footage_download_folder) / "Стоки")
        self.assertEqual(result["montageSettings"]["stockLibraryFolder"], expected)
        stale = config.load_settings()
        bridge.save_montage_settings({"stockUseLibrary": True})
        config.save_settings(stale)
        self.assertTrue(config.load_settings().montage_stock_use_library)
        with self.assertRaises(ValueError):
            bridge.save_montage_settings({"stockUseLibrary": "false"})

    def test_many_keys_are_protected_deduplicated_and_never_in_snapshot(self):
        secrets = [f"test-pexels-secret-{i:03d}" for i in range(130)]
        result = bridge.save_montage_stock_keys({"provider": "pexels", "keys": secrets + secrets[:1]})
        self.assertEqual(len(result["montageSettings"]["stockKeys"]), 130)
        settings = config.load_settings()
        self.assertEqual([key.secret for key in settings.stock_api_keys], secrets)
        visible = json.dumps(result)
        stored = (self.root / "NewsFlow/settings.json").read_text(encoding="utf-8")
        for secret in secrets:
            self.assertNotIn(secret, visible)
            self.assertNotIn(secret, stored)
        bridge.save_montage_stock_keys({"provider": "pixabay", "keys": [secrets[0]]})
        self.assertEqual(len(config.load_settings().stock_api_keys), 131)

    def test_stale_worker_cannot_restore_removed_key_or_overwrite_source_edits(self):
        bridge.save_montage_stock_keys({"provider": "coverr", "keys": ["test-key-one", "test-key-two"]})
        stale = config.load_settings()
        keys = bridge.snapshot()["montageSettings"]["stockKeys"]
        bridge.save_montage_stock_keys({"id": keys[0]["id"], "remove": True})
        bridge.save_montage_stock_keys({"id": keys[1]["id"], "active": False})
        bridge.save_montage_settings({"sourceMode": "stock", "stockSources": [], "stockTrim": False})
        stale.montage_task_statuses["1"] = {"status": "Подбор футажей"}
        config.save_settings(stale)
        current = config.load_settings()
        self.assertEqual(len(current.stock_api_keys), 1)
        self.assertFalse(current.stock_api_keys[0].active)
        self.assertEqual(current.montage_source_mode, "stock")
        self.assertEqual(current.montage_stock_sources, [])
        self.assertFalse(current.montage_stock_trim)

    def test_invalid_provider_and_secret_shape_never_change_storage(self):
        for payload in ({"provider": "openai", "keys": ["x"]}, {"provider": "pexels", "keys": "x"}, {"provider": "pexels", "keys": ["x\ny"]}):
            with self.assertRaises(ValueError):
                bridge.save_montage_stock_keys(payload)
        self.assertEqual(getattr(config.load_settings(), "stock_api_keys", []), [])
