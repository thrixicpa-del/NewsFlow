import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import config
from scriptor import bridge
from scriptor.config import Settings
from scriptor.cover_library import CoverLibrary
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState


class CoverQueueTombstoneTests(unittest.TestCase):
    def test_stale_queued_cover_job_cannot_target_a_reindexed_current_row(self):
        """A queued legacy ID must be skipped even if its old index now points at a current cover."""
        active_titles = [f"Текущая тема {index}" for index in range(84)]
        active_rows = [
            {"production_item_id": f"current:{index}", "title": title, "headline_status": "Ожидает генерации"}
            for index, title in enumerate(active_titles)
        ]
        historical_rows = [
            {"production_item_id": f"legacy-cover:{index}", "title": f"Историческая тема {index}",
             "headline_status": "READY", "headline_generation_timestamp": "2026-09-14T16:38:00"}
            for index in range(97)
        ]
        settings = Settings(
            cover_queue=[*active_rows, *historical_rows],
            idea_scenario_context={title: {"id": f"current:{index}", "title": title}
                                   for index, title in enumerate(active_titles)},
        )
        before_historical = [dict(item) for item in historical_rows]

        with patch.object(bridge, "load_session", return_value=(active_titles, [])):
            selected = bridge._select_current_cover_generation_rows(
                settings,
                {"indices": [0], "productionItemIds": ["legacy-cover:0"]},
                lambda _item: True,
            )

        self.assertEqual(selected, [])
        self.assertEqual(historical_rows, before_historical)

    def test_headline_batch_rejects_a_stale_job_before_provider_or_status_write(self):
        """A stale queued ID must not turn a current row into GENERATING after reindexing."""
        current = {
            "production_item_id": "current:1",
            "title": "Текущая тема",
            "headline_status": "Ожидает генерации",
        }
        settings = Settings(
            cover_queue=[current],
            idea_scenario_context={"Текущая тема": {"id": "current:1", "title": "Текущая тема"}},
        )
        before = dict(current)
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "load_session", return_value=(["Текущая тема"], [])):
            with self.assertRaisesRegex(ValueError, "Выберите сценарии"):
                bridge.generate_cover_headlines({
                    "indices": [0], "productionItemIds": ["legacy-cover:0"], "provider": "agent",
                })

        self.assertEqual(current, before)

    def test_title_tombstone_blocks_a_stale_session_before_cover_generation(self):
        """A pre-ID deleted title must not become active through an old session snapshot."""
        current = {"production_item_id": "current:deleted", "title": "Удалённая тема"}
        settings = Settings(
            cover_queue=[current],
            idea_scenario_context={"Удалённая тема": {"id": "current:deleted", "title": "Удалённая тема"}},
            deleted_scenario_titles=["удалённая тема"],
        )
        with patch.object(bridge, "load_session", return_value=(["Удалённая тема"], [])):
            selected = bridge._select_current_cover_generation_rows(
                settings,
                {"indices": [0], "productionItemIds": ["current:deleted"]},
                lambda _item: True,
            )

        self.assertEqual(selected, [])

    def test_explicit_canonical_cover_can_run_without_a_session_but_legacy_cannot(self):
        """Manual direct work may use a durable ID; a legacy registry key never gains that privilege."""
        settings = Settings(cover_queue=[
            {"production_item_id": "production:manual", "title": "Ручная текущая тема"},
            {"production_item_id": "legacy-cover:history", "title": "Историческая тема"},
        ])
        with patch.object(bridge, "load_session", return_value=([], [])):
            selected = bridge._select_current_cover_generation_rows(
                settings,
                {"indices": [0], "productionItemIds": ["production:manual"]},
                lambda _item: True,
            )

        self.assertEqual([item[1]["production_item_id"] for item in selected], ["production:manual"])

    def test_manual_direct_cover_receives_a_current_id_before_provider_work(self):
        """A new manual row must become a current identity, never a title-derived legacy key."""
        settings = Settings(cover_queue=[{"title": "Ручная тема"}])
        with patch.object(bridge, "load_session", return_value=([], [])):
            selected = bridge._select_current_cover_generation_rows(
                settings, {"indices": [0]}, lambda _item: True,
            )

        self.assertEqual(len(selected), 1)
        self.assertTrue(settings.cover_queue[0]["production_item_id"].startswith("production:manual:"))

    def test_fastgen_batch_rejects_a_stale_job_before_provider_or_status_write(self):
        """A stale queued render must not target a compacted current queue slot."""
        current = {
            "production_item_id": "current:1",
            "title": "Текущая тема",
            "status": "Ожидает",
            "progress": 0,
        }
        settings = Settings(
            cover_queue=[current],
            idea_scenario_context={"Текущая тема": {"id": "current:1", "title": "Текущая тема"}},
        )
        before = dict(current)
        with patch.object(bridge, "load_settings", return_value=settings), \
             patch.object(bridge, "_hydrate_cover_library", return_value=False), \
             patch.object(bridge, "load_session", return_value=(["Текущая тема"], [])):
            result = bridge._generate_covers_unlocked({
                "indices": [0], "productionItemIds": ["legacy-cover:0"], "operation": "test",
            })

        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertEqual(current, before)

    def test_explicitly_removed_cover_does_not_return_from_stale_settings_save(self):
        """A stale worker must not resurrect a cover row the user removed."""
        kept = {"scenario_index": 1, "title": "Оставить", "updatedAt": "2026-09-10T10:00:00"}
        removed = {"scenario_index": 2, "title": "Удалить", "updatedAt": "2026-09-10T10:00:00"}
        removed_key = config._cover_queue_key(removed, 1)

        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale = Settings(cover_queue=[kept, removed])
            cleaned = Settings(cover_queue=[kept], cover_queue_tombstones=[removed_key])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(stale)
                config.save_settings(cleaned)
                config.save_settings(stale)
                persisted = config.load_settings()

        self.assertEqual([item["title"] for item in persisted.cover_queue], ["Оставить"])
        self.assertEqual(persisted.cover_queue_tombstones, [removed_key])

    def test_removed_library_item_does_not_return_from_stale_persist(self):
        """The durable cover library also rejects stale writes for deleted rows."""
        kept = {"production_item_id": "item:keep", "title": "Оставить", "updatedAt": "2026-09-10T10:00:00"}
        removed = {"production_item_id": "item:removed", "title": "Удалить", "updatedAt": "2026-09-10T10:00:00"}

        with tempfile.TemporaryDirectory() as folder:
            library = CoverLibrary(Path(folder) / "covers-library.json")
            library.persist([kept, removed], {"image": [], "video": []}, {})
            library.remove(["item:removed"])
            library.persist([kept, removed], {"image": [], "video": []}, {})
            queue, _capabilities, _usage = library.hydrate([kept], {"image": [], "video": []}, {})

        self.assertEqual([item["title"] for item in queue], ["Оставить"])

    def test_canonical_hydration_does_not_restore_an_unrelated_legacy_cover(self):
        """A prior release's gallery row is not an active topic in a new batch."""
        with tempfile.TemporaryDirectory() as folder:
            library = CoverLibrary(Path(folder) / "covers-library.json")
            library.persist(
                [{
                    "production_item_id": "legacy-cover:old-release",
                    "title": "Старая тема",
                    "updatedAt": "2026-09-10T10:00:00",
                }],
                {"image": [], "video": []},
                {},
            )
            queue, _capabilities, _usage = library.hydrate(
                [],
                {"image": [], "video": []},
                {},
                active_production_ids={"production:current-release"},
            )

        self.assertEqual(queue, [])

    def test_runtime_hydration_projects_only_the_current_scenario_identity(self):
        """The covers view must follow the active session, not a prior release registry."""
        with tempfile.TemporaryDirectory() as folder:
            library_path = Path(folder) / "covers-library.json"
            CoverLibrary(library_path).persist(
                [{
                    "production_item_id": "legacy-cover:old-release",
                    "title": "Старая тема",
                    "updatedAt": "2026-09-10T10:00:00",
                }],
                {"image": [], "video": []},
                {},
            )
            current = {"id": "production:current", "title": "Текущая тема"}
            settings = Settings(idea_scenario_context={"Текущая тема": current})
            job = Job(ScenarioRequest(0, "Текущая тема", ""), RunState.DONE, "Сценарий", "")
            with patch.object(bridge, "_cover_library_path", return_value=library_path), \
                 patch.object(bridge, "load_session", return_value=(["Текущая тема"], [job])):
                bridge._hydrate_cover_library(settings)

        self.assertEqual([row["production_item_id"] for row in settings.cover_queue], ["production:current"])
        self.assertEqual([row["title"] for row in settings.cover_queue], ["Текущая тема"])
        self.assertEqual(settings.cover_queue[0]["headline_status"], "Ожидает генерации")
        self.assertEqual(settings.cover_queue[0]["subheadline_status"], "Ожидает генерации")

    def test_reconcile_repairs_missing_manual_context_before_cover_bulk_action(self):
        """Older current manual scripts must regain their own ID, never a title-matched legacy row."""
        title = "Текущий ручной сценарий без старого context"
        settings = Settings(cover_queue=[{
            "title": title,
            "status": "Ожидает",
            "headline_status": "Ожидает генерации",
        }])
        job = Job(ScenarioRequest(0, title, ""), RunState.DONE, "Готовый сценарий", "")

        with patch.object(bridge, "load_session", return_value=([title], [job])):
            bridge.ensure_idea_production_items(settings, active_titles=[title])
            bridge._sync_current_scenario_covers(settings)
            selected = bridge._select_current_cover_generation_rows(settings, {}, lambda _item: True)

        self.assertEqual(len(selected), 1)
        production_item_id = settings.idea_scenario_context[title]["id"]
        self.assertTrue(production_item_id)
        self.assertEqual(settings.cover_queue[0]["production_item_id"], production_item_id)
        self.assertFalse(production_item_id.startswith("legacy-cover:"))

    def test_restart_and_bulk_selection_keep_84_current_covers_separate_from_97_history_rows(self):
        """Canonical restart/reconcile may project 84 current IDs, but must never touch 97 historical rows."""
        active_titles = [f"Текущая тема {index}" for index in range(84)]
        active_context = {
            title: {"id": f"production:{index}", "title": title}
            for index, title in enumerate(active_titles)
        }
        historical_rows = [
            {
                "production_item_id": f"legacy-cover:{index}",
                "title": f"Историческая тема {index}",
                "headline_status": "READY",
                "cover_headline": f"СТАРЫЙ ТЕКСТ {index}",
                "headline_generation_timestamp": "2026-09-14T16:38:00",
                "updatedAt": "2026-09-14T16:38:00",
            }
            for index in range(97)
        ]
        with tempfile.TemporaryDirectory() as folder:
            library_path = Path(folder) / "covers-library.json"
            CoverLibrary(library_path).persist(historical_rows, {"image": [], "video": []}, {})
            before_history = CoverLibrary(library_path)._read()["items"]
            settings = Settings(
                cover_queue=[dict(item) for item in historical_rows],
                idea_scenario_context=active_context,
            )
            with patch.object(bridge, "_cover_library_path", return_value=library_path), \
                 patch.object(bridge, "load_session", return_value=(active_titles, [])):
                bridge._hydrate_cover_library(settings)
                first_ids = [row["production_item_id"] for row in settings.cover_queue]
                bridge._hydrate_cover_library(settings)
                second_ids = [row["production_item_id"] for row in settings.cover_queue]
                batch = bridge._select_current_cover_generation_rows(settings, {}, lambda _item: True)

            after_history = CoverLibrary(library_path)._read()["items"]

        self.assertEqual(len(first_ids), 84)
        self.assertEqual(set(first_ids), {f"production:{index}" for index in range(84)})
        self.assertEqual(second_ids, first_ids)
        self.assertEqual(len(batch), 84)
        self.assertEqual(before_history, after_history)

    def test_runtime_hydration_never_promotes_legacy_row_by_matching_title(self):
        """A historical title is not a durable identity and must not resurrect into the active queue."""
        with tempfile.TemporaryDirectory() as folder:
            library_path = Path(folder) / "covers-library.json"
            legacy = {
                "production_item_id": "legacy-cover:previous-release",
                "title": "Текущая тема",
                "script": "Готовый сценарий",
                "cover_headline": "ГЛАВНЫЙ ТЕКСТ",
                "cover_subheadline": "УТОЧНЕНИЕ",
                "image_prompt": "Concrete current scene",
                "updatedAt": "2026-09-10T10:00:00",
            }
            CoverLibrary(library_path).persist([legacy], {"image": [], "video": []}, {})
            current = {"id": "production:current", "title": "Текущая тема"}
            settings = Settings(cover_queue=[legacy], idea_scenario_context={"Текущая тема": current})
            job = Job(ScenarioRequest(0, "Текущая тема", ""), RunState.DONE, "Готовый сценарий", "")
            with patch.object(bridge, "_cover_library_path", return_value=library_path), \
                 patch.object(bridge, "load_session", return_value=(["Текущая тема"], [job])):
                bridge._hydrate_cover_library(settings)

        self.assertEqual(len(settings.cover_queue), 1)
        self.assertEqual(settings.cover_queue[0]["production_item_id"], "production:current")
        self.assertEqual(settings.cover_queue[0].get("cover_headline", ""), "")
        self.assertEqual(settings.cover_queue[0].get("cover_subheadline", ""), "")
        self.assertEqual(settings.cover_queue[0]["headline_status"], "Ожидает генерации")
        self.assertEqual(settings.cover_queue[0]["subheadline_status"], "Ожидает генерации")

    def test_library_persist_keeps_last_known_good_snapshot_before_replacing_state(self):
        """A failed release migration must have a cover-library rollback point."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "covers-library.json"
            library = CoverLibrary(path)
            original = {"production_item_id": "item:one", "title": "Первая", "updatedAt": "2026-09-10T10:00:00"}
            replacement = {"production_item_id": "item:two", "title": "Вторая", "updatedAt": "2026-09-10T10:01:00"}
            library.persist([original], {"image": [], "video": []}, {})
            library.persist([replacement], {"image": [], "video": []}, {})

            backup = Path(folder) / "state-backups" / "covers-library-last-known-good.json"
            self.assertTrue(backup.is_file())
            archived = __import__("json").loads(backup.read_text(encoding="utf-8"))
            self.assertIn("item:one", archived["items"])
