import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scriptor.config import Settings, load_settings, save_settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.session import (
    backup_session_path,
    legacy_session_path,
    load_session,
    migrate_legacy_session,
    remove_scenarios,
    rename_scenario,
    save_session,
    session_path,
)


class SessionTests(unittest.TestCase):
    def test_rename_scenario_updates_saved_job_title(self):
        job = Job(ScenarioRequest(0, "Старая", "P"), RunState.PAUSED, "Ответ", "Причина")
        titles, jobs = rename_scenario(["Старая"], [job], 0, "  Новая тема  ")
        self.assertEqual(titles, ["Новая тема"])
        self.assertEqual(jobs[0].request.title, "Новая тема")
        self.assertEqual(jobs[0].result, "Ответ")
    def test_remove_selected_scenarios_reindexes_remaining_jobs(self):
        titles = ["A", "B", "C", "D"]
        jobs = [
            Job(ScenarioRequest(i, title, f"P{i}"), RunState.DONE, f"R{i}", "")
            for i, title in enumerate(titles)
        ]
        remaining_titles, remaining_jobs = remove_scenarios(titles, jobs, {1, 3})
        self.assertEqual(remaining_titles, ["A", "C"])
        self.assertEqual([job.request.index for job in remaining_jobs], [0, 1])
        self.assertEqual([job.request.title for job in remaining_jobs], ["A", "C"])
        self.assertEqual(remaining_jobs[1].result, "R2")

    def test_completed_and_failed_jobs_survive_restart(self):
        jobs = [
            Job(ScenarioRequest(0, "Первый", "P1"), RunState.DONE, "Текст", ""),
            Job(ScenarioRequest(1, "Второй", "P2"), RunState.ERROR, "", "Ошибка сети"),
        ]
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            save_session(["Первый", "Второй"], jobs)
            titles, restored = load_session()
            self.assertEqual(titles, ["Первый", "Второй"])
            self.assertEqual(restored[0].result, "Текст")
            self.assertEqual(restored[0].state, RunState.DONE)
            self.assertEqual(restored[1].error, "Ошибка сети")

    def test_story_plan_and_accepted_prefix_survive_restart_and_rename(self):
        plan = {
            "thesis": "Одна история",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие"}],
            "content_atoms": [{"id": "C001", "summary": "Факт", "owner_part_id": "P1"}],
            "parts": [{"id": "P1", "role": "COMPLETE", "purpose": "История", "macro_id": "M1",
                       "content_ids": ["C001"], "target_chars": 5000, "opens": [], "closes": [],
                       "transition_direction": "финал"}],
        }
        job = Job(
            ScenarioRequest(0, "Первая", "P", target_chars=5000), RunState.PAUSED,
            "Принятая часть", "", story_plan=plan,
            accepted_story_parts=[{"part_id": "P1", "text": "Принятая часть", "content_ids": ["C001"], "target_chars": 5000}],
            story_planner_status="READY",
        )
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            save_session(["Первая"], [job])
            titles, restored = load_session()
            titles, renamed = rename_scenario(titles, restored, 0, "Переименованная")
            self.assertEqual(titles, ["Переименованная"])
            self.assertEqual(renamed[0].story_plan, plan)
            self.assertEqual(renamed[0].accepted_story_parts, job.accepted_story_parts)
            self.assertEqual(renamed[0].story_planner_status, "READY")

    def test_invalid_session_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            path = os.path.join(folder, "NewsFlow")
            os.makedirs(path)
            with open(os.path.join(path, "session.json"), "w", encoding="utf-8") as stream:
                stream.write("not json")
            self.assertEqual(load_session(), ([], []))

    def test_session_uses_newsflow_data_folder_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            first = [Job(ScenarioRequest(0, "Первый", "P"), RunState.DONE, "Первый текст", "")]
            second = [Job(ScenarioRequest(0, "Первый", "P"), RunState.DONE, "Новый текст", "")]
            save_session(["Первый"], first)
            save_session(["Первый"], second)
            self.assertIn("NewsFlow", str(session_path()))
            self.assertTrue(backup_session_path().is_file())
            session_path().write_text("broken", encoding="utf-8")
            titles, restored = load_session()
            self.assertEqual(titles, ["Первый"])
            self.assertEqual(restored[0].result, "Первый текст")

    def test_legacy_session_is_ignored_until_explicit_migration(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            legacy_session_path().parent.mkdir(parents=True)
            legacy_session_path().write_text(
                '{"titles":["Старый"],"jobs":[{"index":0,"title":"Старый","prompt":"","state":"Готово","result":"Текст","error":""}]}',
                encoding="utf-8",
            )
            titles, restored = load_session()
            self.assertEqual((titles, restored), ([], []))
            self.assertFalse(session_path().exists())

    def test_explicit_legacy_session_migration_preserves_current_session_priority(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            legacy_session_path().parent.mkdir(parents=True)
            legacy_session_path().write_text(
                '{"titles":["Старый"],"jobs":[{"index":0,"title":"Старый","prompt":"","state":"Готово","result":"Текст","error":""}]}',
                encoding="utf-8",
            )
            titles, restored = migrate_legacy_session()

            self.assertEqual(titles, ["Старый"])
            self.assertEqual(restored[0].result, "Текст")
            self.assertTrue(session_path().is_file())

    def test_current_session_does_not_recover_legacy_texts_automatically(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            legacy_session_path().parent.mkdir(parents=True)
            legacy_session_path().write_text(
                '{"titles":["Первый","Второй"],"jobs":['
                '{"index":0,"title":"Первый","prompt":"P1","state":"Готово","result":"Текст 1","error":""},'
                '{"index":1,"title":"Второй","prompt":"P2","state":"Готово","result":"Текст 2","error":""}]}',
                encoding="utf-8",
            )
            session_path().parent.mkdir(parents=True, exist_ok=True)
            session_path().write_text('{"version":1,"titles":["Второй","Первый"],"jobs":[]}', encoding="utf-8")
            titles, restored = load_session()
            self.assertEqual(titles, ["Второй", "Первый"])
            self.assertEqual(restored, [])

    def test_recovers_empty_primary_session_from_matching_backup(self):
        """A stale empty primary file must not hide an active production batch."""
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            titles = ["Первый", "Второй"]
            jobs = [
                Job(ScenarioRequest(0, "Первый", "P1"), RunState.DONE, "Текст 1", ""),
                Job(ScenarioRequest(1, "Второй", "P2"), RunState.DONE, "Текст 2", ""),
            ]
            session_path().parent.mkdir(parents=True, exist_ok=True)
            (session_path().parent / "settings.json").write_text(
                json.dumps({"idea_results": titles}, ensure_ascii=False), encoding="utf-8",
            )
            save_session(titles, jobs)
            save_session([], [])

            restored_titles, restored_jobs = load_session()

            self.assertEqual(restored_titles, titles)
            self.assertEqual([job.result for job in restored_jobs], ["Текст 1", "Текст 2"])

    def test_does_not_restore_backup_after_an_intentional_empty_queue(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            save_session(["Первый"], [Job(ScenarioRequest(0, "Первый", "P"), RunState.DONE, "Текст", "")])
            save_session([], [])

            self.assertEqual(load_session(), ([], []))

    def test_recovers_empty_primary_from_cover_queue_when_idea_list_is_stale(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            titles = ["Актуальная тема", "Ещё одна тема"]
            jobs = [
                Job(ScenarioRequest(0, titles[0], "P1"), RunState.DONE, "Текст 1", ""),
                Job(ScenarioRequest(1, titles[1], "P2"), RunState.DONE, "Текст 2", ""),
            ]
            session_path().parent.mkdir(parents=True, exist_ok=True)
            (session_path().parent / "settings.json").write_text(json.dumps({
                "idea_results": ["Устаревшая тема"],
                "cover_queue": [{"title": title} for title in titles],
            }, ensure_ascii=False), encoding="utf-8")
            save_session(titles, jobs)
            save_session([], [])

            restored_titles, restored_jobs = load_session()

            self.assertEqual(restored_titles, titles)
            self.assertEqual([job.result for job in restored_jobs], ["Текст 1", "Текст 2"])

    def test_empty_primary_never_restores_a_backup_containing_a_deleted_scenario(self):
        """A stale cover title is not authority to undo an explicit deletion."""
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            titles = ["Оставить", "Удалено"]
            jobs = [
                Job(ScenarioRequest(0, titles[0], "P1", "keep"), RunState.DONE, "Текст 1", ""),
                Job(ScenarioRequest(1, titles[1], "P2", "deleted"), RunState.DONE, "Текст 2", ""),
            ]
            save_settings(Settings(
                idea_results=titles,
                cover_queue=[{"title": title} for title in titles],
                deleted_scenario_production_ids=["deleted"],
            ))
            save_session(titles, jobs)
            save_session([], [])

            self.assertEqual(load_session(), ([], []))


    def test_primary_session_projects_durable_tombstones_after_stale_worker_write(self):
        """A stale full primary written after delete/reset must stay deleted on restart."""
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            settings = Settings(
                deleted_scenario_titles=["legacy deleted"],
                deleted_scenario_production_ids=["deleted-id"],
            )
            save_settings(settings)
            titles = ["Оставить", "Удалено по ID", "Legacy Deleted"]
            jobs = [
                Job(ScenarioRequest(0, titles[0], "P0", "keep-id"), RunState.DONE, "Keep", ""),
                Job(ScenarioRequest(1, titles[1], "P1", "deleted-id"), RunState.DONE, "Gone", ""),
                Job(ScenarioRequest(2, titles[2], "P2", ""), RunState.DONE, "Legacy gone", ""),
            ]
            # Simulates a detached worker which persisted its stale pre-delete
            # in-memory session after the user action had already completed.
            save_session(titles, jobs)

            restored_titles, restored_jobs = load_session()

            self.assertEqual(restored_titles, ["Оставить"])
            self.assertEqual([job.request.production_item_id for job in restored_jobs], ["keep-id"])

    def test_new_production_id_may_reuse_a_legacy_deleted_title(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            save_settings(Settings(deleted_scenario_titles=["повторяемая тема"]))
            save_session(
                ["Повторяемая тема"],
                [Job(ScenarioRequest(0, "Повторяемая тема", "P", "new-production-id"),
                     RunState.DONE, "New work", "")],
            )

            titles, jobs = load_session()

            self.assertEqual(titles, ["Повторяемая тема"])
            self.assertEqual(jobs[0].request.production_item_id, "new-production-id")

    def test_stale_settings_save_cannot_erase_scenario_tombstones(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"LOCALAPPDATA": folder}):
            save_settings(Settings(
                deleted_scenario_titles=["Удалённая тема"],
                deleted_scenario_production_ids=["deleted-id"],
            ))
            # Detached workers created before the delete carry no tombstones.
            save_settings(Settings())
            restored = load_settings()

            self.assertIn("удалённая тема", restored.deleted_scenario_titles)
            self.assertIn("deleted-id", restored.deleted_scenario_production_ids)

if __name__ == "__main__":
    unittest.main()
