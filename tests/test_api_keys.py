"""Credential editing uses synthetic keys in isolated storage, never providers."""
import asyncio
import hashlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import config_path, load_settings, save_settings
from scriptor.observability import action_trace_path
from scriptor.openai_client import HybridTextPool


class ApiKeyEditingTests(unittest.TestCase):
    def setUp(self):
        root = os.environ.get("NEWSFLOW_TEST_ROOT")
        if not root or not config_path().resolve().is_relative_to(Path(root).resolve()):
            raise RuntimeError("Credential tests require isolated storage via tests/run_isolated.py")
        config_path().unlink(missing_ok=True)
        self.snapshot = patch.object(bridge, "snapshot", return_value={"keyStatus": {}})
        self.snapshot.start()
        self.addCleanup(self.snapshot.stop)

    def seed(self, kind="openai"):
        bridge.add_api_key({"kind": kind, "label": "Original", "secret": "synthetic-old"})
        bridge.set_key_active({"kind": kind, "index": 0, "active": False})
        bridge.save_api_key_note({"kind": kind, "index": 0, "note": "keep note"})
        label = "YouTube Data API" if kind == "youtube" else "Original"
        return {"kind": kind, "index": 0, "fingerprint": bridge._api_key_fingerprint("synthetic-old"),
                "revision": hashlib.sha256(f"synthetic-old\0{label}".encode()).hexdigest()}

    def test_reveal_is_explicit_read_only_and_returns_only_selected_credential(self):
        payload = self.seed()
        before = config_path().read_bytes()
        result = bridge.reveal_api_key(payload)
        self.assertEqual(result, {"secret": "synthetic-old", "label": "Original", "revision": payload["revision"]})
        self.assertEqual(config_path().read_bytes(), before)

    def test_edit_all_services_replaces_one_key_preserves_metadata_and_encrypts(self):
        fields = {"fastgen": "cover_api_keys", "openai": "openai_api_keys",
                  "voicer": "secret_voicer_keys", "lumean": "lumean_api_keys",
                  "voicegen": "voicegen_api_keys", "wproject": "wproject_api_keys"}
        for kind in [*fields, "youtube"]:
            with self.subTest(kind=kind):
                payload = self.seed(kind)
                bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
                restored = load_settings()
                if kind == "youtube":
                    self.assertEqual(restored.youtube_api_key, "synthetic-new")
                    self.assertFalse(restored.youtube_api_enabled)
                else:
                    rows = getattr(restored, fields[kind])
                    self.assertEqual(len(rows), 1)
                    self.assertEqual((rows[0].label, rows[0].secret, rows[0].active),
                                     ("Updated", "synthetic-new", False))
                self.assertEqual(restored.api_key_notes[f"{kind}:0"], "keep note")
                self.assertNotIn("synthetic-new", config_path().read_text(encoding="utf-8"))

    def test_stale_form_rejected_without_mutation(self):
        payload = self.seed()
        bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
        before = config_path().read_bytes()
        for operation in (bridge.update_api_key, bridge.reveal_api_key):
            with self.assertRaisesRegex(ValueError, "изменён"):
                operation({**payload, "secret": "synthetic-other"})
        self.assertEqual(config_path().read_bytes(), before)

    def test_stale_background_save_cannot_resurrect_old_key(self):
        for kind, field in (("openai", "openai_api_keys"), ("fastgen", "cover_api_keys"),
                            ("youtube", "youtube_api_key")):
            with self.subTest(kind=kind):
                payload = self.seed(kind)
                stale = load_settings()
                bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
                stale.idea_custom_text = "background progress"
                save_settings(stale)
                restored = load_settings()
                if kind == "youtube":
                    self.assertEqual(restored.youtube_api_key, "synthetic-new")
                else:
                    self.assertEqual([key.secret for key in getattr(restored, field)], ["synthetic-new"])
                self.assertEqual(restored.idea_custom_text, "background progress")

    def test_new_request_uses_new_authorization_not_old_key(self):
        payload = self.seed()
        bridge.set_key_active({"kind": "openai", "index": 0, "active": True})
        bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"output_text":"OK"}')) as transport:
            pool = HybridTextPool([], load_settings().openai_api_keys, "")
            self.assertEqual(asyncio.run(pool.generate("synthetic test")), "OK")
        self.assertEqual(transport.call_args.args[0].get_header("Authorization"), "Bearer synthetic-new")

    def test_invalid_empty_or_missing_identity_never_changes_disk(self):
        payload = self.seed()
        before = config_path().read_bytes()
        for changes in ({"secret": " "}, {"index": -1}, {"kind": "unknown"}, {"fingerprint": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bridge.update_api_key({**payload, "secret": "synthetic-new", **changes})
        self.assertEqual(config_path().read_bytes(), before)

    def test_replace_race_is_checked_under_settings_lock(self):
        payload = self.seed()
        original_save = bridge.save_settings

        def competing_save(settings):
            with patch.object(bridge, "save_settings", original_save):
                bridge.update_api_key({**payload, "secret": "synthetic-winner", "label": "Winner"})
            original_save(settings)

        with patch.object(bridge, "save_settings", side_effect=competing_save), \
                self.assertRaisesRegex(ValueError, "изменён"):
            bridge.update_api_key({**payload, "secret": "synthetic-loser", "label": "Loser"})
        self.assertEqual(load_settings().openai_api_keys[0].secret, "synthetic-winner")

    def test_bridge_trace_does_not_persist_revealed_or_updated_secret(self):
        payload = self.seed()
        for name, values in (("reveal-api-key", payload),
                             ("update-api-key", {**payload, "secret": "synthetic-new", "label": "Updated"})):
            with patch("sys.argv", ["bridge", name]), patch.object(bridge, "_bridge_payload_from_cli", return_value=values), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                bridge.main()
                self.assertNotIn("error", json.loads(output.getvalue()))
        trace = action_trace_path().read_text(encoding="utf-8")
        self.assertNotIn("synthetic-old", trace)
        self.assertNotIn("synthetic-new", trace)

    def test_normal_snapshot_never_contains_secret(self):
        self.seed()
        self.snapshot.stop()
        result = bridge.snapshot()
        self.assertNotIn("synthetic-old", json.dumps(result))
        self.assertEqual(result["keyStatus"]["openai"][0]["fingerprint"],
                         hashlib.sha256(b"synthetic-old").hexdigest()[:10])

    def test_edit_preserves_other_credentials_and_provider_configuration(self):
        payload = self.seed("wproject")
        bridge.add_api_key({"kind": "wproject", "label": "Other", "secret": "synthetic-other"})
        settings = load_settings()
        settings.wproject_api_keys[0].streams = 3
        settings.openai_model = "unchanged-model"
        settings.output_folder = "unchanged-path"
        save_settings(settings)
        bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
        restored = load_settings()
        self.assertEqual([item.secret for item in restored.wproject_api_keys],
                         ["synthetic-new", "synthetic-other"])
        self.assertEqual(restored.wproject_api_keys[0].streams, 3)
        self.assertEqual(restored.openai_model, "unchanged-model")
        self.assertEqual(restored.output_folder, "unchanged-path")

    def test_failed_publication_preserves_old_key_and_recovery_copy(self):
        payload = self.seed()
        before = config_path().read_bytes()
        with patch("scriptor.config.os.replace", side_effect=OSError("synthetic disk failure")), \
                self.assertRaises(OSError):
            bridge.update_api_key({**payload, "secret": "synthetic-new"})
        self.assertEqual(config_path().read_bytes(), before)
        self.assertEqual(load_settings().openai_api_keys[0].secret, "synthetic-old")
        self.assertFalse(list(config_path().parent.glob(".*.tmp")))

    def test_stale_worker_preserves_key_order_and_index_notes_after_rotation(self):
        payload = self.seed()
        bridge.add_api_key({"kind": "openai", "label": "Second", "secret": "synthetic-second"})
        bridge.save_api_key_note({"kind": "openai", "index": 1, "note": "second note"})
        stale = load_settings()
        bridge.update_api_key({**payload, "label": "Updated", "secret": "synthetic-new"})
        for _ in range(2):
            save_settings(stale)
            restored = load_settings()
            self.assertEqual([key.secret for key in restored.openai_api_keys],
                             ["synthetic-new", "synthetic-second"])
            self.assertEqual(restored.api_key_notes["openai:0"], "keep note")
            self.assertEqual(restored.api_key_notes["openai:1"], "second note")

    def test_stale_worker_cannot_revert_label_only_edit(self):
        payload = self.seed()
        stale = load_settings()
        bridge.update_api_key({**payload, "label": "Renamed", "secret": "synthetic-old"})
        save_settings(stale)
        self.assertEqual(load_settings().openai_api_keys[0].label, "Renamed")
        with self.assertRaisesRegex(ValueError, "изменён"):
            bridge.update_api_key({**payload, "label": "Stale name", "secret": "synthetic-old"})

    def test_rotation_of_duplicate_secret_keeps_two_exact_rows(self):
        payload = self.seed()
        bridge.add_api_key({"kind": "openai", "label": "Duplicate", "secret": "synthetic-old"})
        stale = load_settings()
        bridge.update_api_key({**payload, "label": "Renamed", "secret": "synthetic-new"})
        save_settings(stale)
        self.assertEqual([(key.label, key.secret) for key in load_settings().openai_api_keys],
                         [("Renamed", "synthetic-new"), ("Duplicate", "synthetic-old")])

    def test_fastgen_rename_keeps_explicit_key_selection_after_stale_save(self):
        payload = self.seed("fastgen")
        settings = load_settings()
        settings.cover_api_keys[0].active = True
        settings.cover_selected_key_labels = ["Original"]
        save_settings(settings)
        stale = load_settings()
        bridge.update_api_key({**payload, "label": "Renamed", "secret": "synthetic-new"})
        self.assertEqual([key.secret for key in bridge._selected_fastgen_keys(load_settings())], ["synthetic-new"])
        save_settings(stale)
        self.assertEqual([key.secret for key in bridge._selected_fastgen_keys(load_settings())], ["synthetic-new"])

    def test_unrelated_key_edit_cannot_overwrite_concurrent_settings_or_fastgen_selection(self):
        openai = self.seed()
        fastgen = self.seed("fastgen")
        settings = load_settings()
        settings.cover_api_keys[0].active = True
        settings.cover_selected_key_labels = ["Original"]
        save_settings(settings)
        original_save = bridge.save_settings

        def competing_save(settings):
            with patch.object(bridge, "save_settings", original_save):
                bridge.update_api_key({**fastgen, "label": "Renamed", "secret": "synthetic-fastgen-new"})
                concurrent = load_settings()
                concurrent.output_folder = "concurrent-path"
                original_save(concurrent)
            original_save(settings)

        with patch.object(bridge, "save_settings", side_effect=competing_save):
            bridge.update_api_key({**openai, "label": "Updated", "secret": "synthetic-openai-new"})
        restored = load_settings()
        self.assertEqual([key.secret for key in bridge._selected_fastgen_keys(restored)], ["synthetic-fastgen-new"])
        self.assertEqual(restored.output_folder, "concurrent-path")
        self.assertEqual(restored.openai_api_keys[0].secret, "synthetic-openai-new")
