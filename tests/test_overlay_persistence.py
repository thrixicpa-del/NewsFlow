import copy
import json
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scriptor import bridge, config
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.timeline import TimelineClip, TimelineProject
from tests.media_fixtures import write_readable_video


def template(name="logo", *, enabled=False, path=""):
    return {"version": 1, "layouts": {"16:9": [{
        "id": name, "name": name, "enabled": enabled, "path": path,
        "kind": "image", "x": 10, "y": 20, "width": 200, "height": 100,
        "keepAspect": True, "opacity": 1, "start": 0, "duration": 5,
        "mode": "once", "repeatEvery": 10, "endOffset": 5,
        "chromaEnabled": False, "chromaColor": "#00FF00",
        "chromaSimilarity": .1, "chromaBlend": .1, "audioEnabled": False,
    }], "9:16": []}}


class OverlayPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path_patch = patch.object(config, "config_path", return_value=self.root / "settings.json")
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.real_snapshot = bridge.snapshot
        self.snapshot_patch = patch.object(bridge, "snapshot", return_value={})
        self.snapshot_patch.start()
        self.addCleanup(self.snapshot_patch.stop)

    def save_rows(self, rows):
        settings = config.load_settings()
        settings.montage_task_statuses = rows
        config.save_settings(settings)
        return settings

    def test_default_round_trip_and_stale_worker_does_not_revert(self):
        old_worker = config.load_settings()
        bridge.save_montage_overlays({"scope": "new", "template": template()})
        config.save_settings(old_worker)
        saved = config.load_settings()
        self.assertEqual(saved.montage_overlay_template, template())
        self.assertEqual(json.loads((self.root / "settings.json").read_text("utf-8"))["montage_overlay_template"], template())

    def test_default_changes_only_future_queue_snapshots(self):
        settings = config.load_settings()
        settings.montage_overlay_template = template("old")
        voice = self.root / "voice.mp3"
        voice.write_bytes(b"voice")
        bridge._sync_montage_handoff(settings, 0, "one", str(voice), transferred=True)
        config.save_settings(settings)
        bridge.save_montage_overlays({"scope": "new", "template": template("new")})
        settings = config.load_settings()
        self.assertEqual(settings.montage_task_statuses["0"]["overlayTemplate"], template("old"))
        bridge._sync_montage_handoff(settings, 1, "two", str(voice), transferred=True)
        self.assertEqual(settings.montage_task_statuses["1"]["overlayTemplate"], template("new"))
        settings.montage_overlay_template["layouts"]["16:9"][0]["name"] = "edited"
        self.assertEqual(settings.montage_task_statuses["1"]["overlayTemplate"]["layouts"]["16:9"][0]["name"], "new")

    def test_selected_skips_active_and_updates_pending_without_changing_default(self):
        self.save_rows({"0": {"status": "Готов к монтажу"}, "1": {"status": "Рендер"}})
        result = bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template()})
        settings = config.load_settings()
        self.assertEqual(settings.montage_task_statuses["0"]["overlayTemplate"], template())
        self.assertTrue(settings.montage_task_statuses["0"]["overlayTemplateIndividualized"])
        self.assertNotIn("overlayTemplate", settings.montage_task_statuses["1"])
        self.assertEqual(settings.montage_overlay_template["layouts"], {"16:9": [], "9:16": []})
        self.assertEqual(result["operationResult"]["skippedIndices"], [1])

    def test_overwrite_conflict_is_atomic_across_selection(self):
        self.save_rows({"0": {"status": "Готов к монтажу"}, "1": {
            "status": "Ошибка", "overlayTemplate": template("individual"), "overlayTemplateIndividualized": True,
        }})
        before = (self.root / "settings.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite|перезапис|подтверж"):
            bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template()})
        self.assertEqual((self.root / "settings.json").read_bytes(), before)
        bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template(), "overwrite": True})
        self.assertEqual(config.load_settings().montage_task_statuses["1"]["overlayTemplate"], template())

    def test_saved_project_updated_without_footage_selection(self):
        project_path = self.root / "saved.newsflow"
        TimelineProject(title="saved", clips=[TimelineClip(path="unchanged.mp4", duration=5, narration="voice", visual_query_en="scene")]).save(project_path)
        original = json.loads(project_path.read_text("utf-8"))
        self.save_rows({"0": {"status": "Ошибка", "projectPath": str(project_path)}})
        with patch.object(bridge, "prepare_montage", side_effect=AssertionError("must not select footage")):
            bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template()})
        saved = json.loads(project_path.read_text("utf-8"))
        self.assertEqual(saved["overlay_template"], template())
        self.assertEqual(saved["clips"], original["clips"])
        self.assertEqual(TimelineProject.load(project_path).overlay_template, template())

    def test_project_override_requires_confirmation_even_for_legacy_queue_row(self):
        project_path = self.root / "saved.newsflow"
        TimelineProject(title="saved").save(project_path)
        raw = json.loads(project_path.read_text("utf-8"))
        raw["overlay_template"] = template("individual")
        project_path.write_text(json.dumps(raw), "utf-8")
        self.save_rows({"0": {"status": "Ошибка", "projectPath": str(project_path)}})
        before = project_path.read_bytes()
        with self.assertRaises(ValueError):
            bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template()})
        self.assertEqual(project_path.read_bytes(), before)

    def test_selected_change_invalidates_baked_master_without_deleting_output(self):
        project_path = self.root / "saved.newsflow"
        prior_mp4 = self.root / "prior.mp4"
        prior_xml = self.root / "prior.fcpxml"
        prior_mp4.write_bytes(b"prior render")
        prior_xml.write_text("prior xml", "utf-8")
        TimelineProject(title="saved", output_path=str(prior_mp4), davinci_xml_path=str(prior_xml)).save(project_path)
        self.save_rows({"0": {"status": "Готово", "projectPath": str(project_path), "outputPath": str(prior_mp4)}})
        bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template()})
        project = TimelineProject.load(project_path)
        self.assertEqual(project.output_path, "")
        self.assertEqual(project.davinci_xml_path, "")
        self.assertTrue(project.overlay_needs_render)
        self.assertTrue(config.load_settings().montage_task_statuses["0"]["overlayNeedsRender"])
        self.assertEqual(prior_mp4.read_bytes(), b"prior render")
        self.assertEqual(prior_xml.read_text("utf-8"), "prior xml")

    def test_missing_enabled_media_rejects_without_mutation(self):
        config.save_settings(config.load_settings())
        before = (self.root / "settings.json").read_bytes()
        with self.assertRaises((ValueError, FileNotFoundError)):
            bridge.save_montage_overlays({"scope": "new", "template": template(enabled=True, path=str(self.root / "missing.png"))})
        self.assertEqual((self.root / "settings.json").read_bytes(), before)

    def test_stale_progress_merge_preserves_newer_overlay_revision(self):
        old = {"status": "Готов к монтажу", "updatedAt": "2026-10-18 10:00:00", "overlayTemplate": template("old")}
        fresh = {**old, "overlayTemplate": template("new"), "overlayTemplateIndividualized": True, "overlayTemplateRevision": 100}
        progress = {**old, "status": "Планирование", "updatedAt": "2026-10-18 10:00:01"}
        result = config._merge_montage_task_statuses({"0": fresh}, {"0": progress})["0"]
        self.assertEqual(result["status"], "Планирование")
        self.assertEqual(result["overlayTemplate"], template("new"))
        self.assertTrue(result["overlayTemplateIndividualized"])

    def test_prepare_snapshot_prefers_explicit_empty_queue_template(self):
        settings = config.load_settings()
        settings.montage_overlay_template = template("global")
        empty = {"version": 1, "layouts": {"16:9": [], "9:16": []}}
        settings.montage_task_statuses["0"] = {"overlayTemplate": copy.deepcopy(empty)}
        config.save_settings(settings)
        self.assertEqual(bridge._montage_overlay_template_for_task(settings, 0), empty)
        self.assertEqual(bridge._montage_overlay_template_for_task(settings, 1), template("global"))

    def test_missing_project_rejects_entire_selection_before_writing(self):
        self.save_rows({"0": {"status": "Готов к монтажу"}, "1": {
            "status": "Ошибка", "projectPath": str(self.root / "missing.newsflow"),
        }})
        before = (self.root / "settings.json").read_bytes()
        with self.assertRaises(ValueError):
            bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template()})
        self.assertEqual((self.root / "settings.json").read_bytes(), before)

    def test_render_exports_xml_with_staged_master_and_final_reference(self):
        project_path = self.root / "saved.newsflow"
        TimelineProject(title="saved").save(project_path)
        settings = config.load_settings()
        settings.montage_export_davinci_xml = True
        config.save_settings(settings)
        expected_output = Path(config.load_settings().montage_output_folder) / "saved.mp4"

        def render(_project, output, **_kwargs):
            output.write_bytes(b"rendered")
            _project.output_path = str(output)
            return output

        def export(_project, path, **_kwargs):
            path.write_text("xml", "utf-8")

        with patch.object(bridge, "render_project", side_effect=render), \
                patch.object(bridge, "export_fcpxml", side_effect=export) as xml:
            bridge.render_montage({"projectPath": str(project_path)})
        self.assertEqual(xml.call_args.kwargs["baked_reference"], expected_output)
        self.assertIn(".newsflow-staging", str(xml.call_args.kwargs["baked_source"]))
        self.assertEqual(TimelineProject.load(project_path).output_path, str(expected_output))

    def test_prepare_persists_queued_override_and_defers_xml_with_explicit_warning(self):
        footage = self.root / "footage"
        footage.mkdir()
        write_readable_video(footage / "Iran oil tanker Hormuz shipping.mp4")
        voice = self.root / "voice.mp3"
        voice.write_bytes(b"voice")
        overlay = self.root / "overlay.png"
        overlay.write_bytes(b"image is decoded at render, not during scene selection")
        queued_template = template("queued", enabled=True, path=str(overlay))
        settings = config.Settings(
            footage_folders=[str(footage)], montage_project_folder=str(self.root / "projects"),
            montage_use_script_text=False, montage_auto_web=False, montage_export_davinci_xml=True,
            montage_overlay_template=template("future"),
            montage_task_statuses={"0": {"overlayTemplate": queued_template}},
            voice_scenario_outputs={"1": str(voice)},
        )
        job = Job(ScenarioRequest(0, "Iran oil tanker Hormuz", ""), RunState.DONE, "", "")
        with patch.object(bridge, "load_settings", return_value=settings), \
                patch.object(bridge, "load_session", return_value=(["Iran oil tanker Hormuz"], [job])), \
                patch.object(bridge, "save_settings"), \
                patch.object(bridge, "_montage_screen_text_safe", return_value=True), \
                patch.object(bridge.ClipIndex, "count", return_value=0), \
                patch.object(bridge, "probe_media_duration", return_value=6.0), \
                patch.object(bridge, "probe_video_duration", return_value=8.0), \
                patch.object(bridge, "export_fcpxml", side_effect=AssertionError("must defer XML until rendered")):
            result = bridge.prepare_montage({"scenarioIndex": 0})
        prepared = result["preparedProject"]
        self.assertIn("XML", prepared["warning"])
        self.assertEqual(TimelineProject.load(Path(prepared["path"])).overlay_template, queued_template)

    def test_all_started_queue_phases_are_skipped(self):
        phases = sorted(bridge.MONTAGE_ACTIVE_STATUSES)
        self.save_rows({str(index): {"status": phase} for index, phase in enumerate(phases)})
        result = bridge.save_montage_overlays({"scope": "selected", "indices": list(range(len(phases))), "template": template()})
        self.assertEqual(result["operationResult"]["skippedIndices"], list(range(len(phases))))
        self.assertEqual(result["operationResult"]["count"], 0)

    def test_worker_refreshes_selected_template_before_starting(self):
        worker = self.save_rows({"0": {"status": "Готов к монтажу", "overlayTemplate": template("old")}})
        bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template("selected")})
        bridge._montage_task_update(worker, 0, status="Планирование", progress=8)
        self.assertEqual(worker.montage_task_statuses["0"]["overlayTemplate"], template("selected"))
        self.assertEqual(config.load_settings().montage_task_statuses["0"]["overlayTemplate"], template("selected"))

    def test_same_second_restart_persists_active_state_before_selected_edit(self):
        worker = self.save_rows({"0": {"status": "Готово", "progress": 100, "updatedAt": "2099-01-01 00:00:00"}})
        with patch.object(bridge.time, "strftime", return_value="2099-01-01 00:00:00"):
            bridge._montage_task_update(worker, 0, status="В очереди", progress=0)
        self.assertEqual(config.load_settings().montage_task_statuses["0"]["status"], "В очереди")
        result = bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template()})
        self.assertEqual(result["operationResult"]["skippedIndices"], [0])

    def test_selected_reload_waits_for_queue_start_lock_and_skips_started_row(self):
        worker = self.save_rows({"0": {"status": "Готов к монтажу"}})
        started = threading.Event()
        outcome = []
        errors = []

        def edit():
            started.set()
            try:
                outcome.append(bridge.save_montage_overlays({"scope": "selected", "indices": [0], "template": template()}))
            except (OSError, ValueError, RuntimeError) as error:
                errors.append(error)

        with bridge._montage_overlay_edit_lock():
            thread = threading.Thread(target=edit)
            thread.start()
            self.assertTrue(started.wait(5))
            # Persist the worker's acquired ownership before releasing the
            # check/write boundary. The editor must read after that release.
            worker.montage_task_statuses["0"]["status"] = "Планирование"
            worker.montage_task_statuses["0"]["updatedAt"] = "2026-10-18 10:00:00"
            config.save_settings(worker)
        thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(outcome[0]["operationResult"]["skippedIndices"], [0])
        self.assertNotIn("overlayTemplate", config.load_settings().montage_task_statuses["0"])

    def test_mixed_selection_snapshots_scenario_without_task_and_preserves_on_handoff(self):
        self.save_rows({"0": {"status": "Готов к монтажу"}})
        job = Job(ScenarioRequest(1, "two", "", production_item_id="pi-two"), RunState.DONE, "script", "")
        with patch.object(bridge, "load_session", return_value=(["one", "two"], [job])):
            result = bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template("batch")})
        settings = config.load_settings()
        self.assertEqual(result["operationResult"]["count"], 2)
        self.assertEqual(settings.montage_task_statuses["1"]["production_item_id"], "pi-two")
        self.assertEqual(settings.montage_task_statuses["1"]["title"], "two")
        voice = self.root / "voice.mp3"
        voice.write_bytes(b"voice")
        settings.montage_overlay_template = template("future")
        bridge._sync_montage_handoff(settings, 1, "two", str(voice), transferred=True, production_item_id="pi-two")
        self.assertEqual(settings.montage_task_statuses["1"]["overlayTemplate"], template("batch"))

    def test_missing_task_outside_current_session_rejects_whole_selection(self):
        self.save_rows({"0": {"status": "Готов к монтажу"}})
        before = (self.root / "settings.json").read_bytes()
        with patch.object(bridge, "load_session", return_value=(["one"], [])), self.assertRaises(ValueError):
            bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": template()})
        self.assertEqual((self.root / "settings.json").read_bytes(), before)

    def render_only_fixture(self, *, missing=False, wrong_identity=False):
        voice = self.root / "voice.mp3"
        voice.write_bytes(b"voice")
        clip = self.root / "clip.mp4"
        clip.write_bytes(b"clip")
        project_path = self.root / "saved.newsflow"
        project = TimelineProject(title="saved", voiceover_path=str(voice), clips=[
            TimelineClip(path=str(clip), narration="script", visual_query_en="saved", duration=6),
        ])
        project.save(project_path)
        prior_output = self.root / "output" / "saved.mp4"
        prior_output.parent.mkdir()
        prior_output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
        settings = config.Settings(
            montage_project_folder=str(self.root), montage_output_folder=str(self.root / "output"),
            montage_export_davinci_xml=False, voice_scenario_outputs={"1": str(voice)},
            montage_task_statuses={"0": {"status": "Готово", "title": "saved", "projectPath": str(project_path),
                                          "outputPath": str(prior_output),
                                          "production_item_id": "stale" if wrong_identity else "pi-current"}},
        )
        job = Job(ScenarioRequest(0, "saved", "", production_item_id="pi-current"), RunState.DONE, "script", "")

        def render(saved, output, **_kwargs):
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
            saved.output_path = str(output)
            return output

        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, kwargs in {
            "load_settings": {"return_value": settings}, "load_session": {"return_value": (["saved"], [job])},
            "save_settings": {}, "prepare_montage": {"side_effect": AssertionError("selection forbidden")},
            "_repair_missing_project_clips": {"side_effect": AssertionError("repair forbidden")},
            "_complete_project_visual_tail": {"side_effect": AssertionError("tail selection forbidden")},
            "_montage_project_missing_clips": {"return_value": [str(clip)] if missing else []},
            "_validated_montage_clip_duration": {"return_value": 8},
            "probe_media_duration": {"return_value": 6}, "validate_rendered_montage": {},
            "render_project": {"side_effect": render},
        }.items():
            stack.enter_context(patch.object(bridge, name, **kwargs))
        return settings, project_path

    def test_render_only_uses_saved_plan_without_selection_repair_or_tail_changes(self):
        settings, project_path = self.render_only_fixture()
        clips = json.loads(project_path.read_text("utf-8"))["clips"]
        result = bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(json.loads(project_path.read_text("utf-8"))["clips"], clips)
        self.assertEqual(settings.montage_task_statuses["0"]["status"], "Готово")

    def test_render_only_reports_missing_clip_without_reselection(self):
        settings, project_path = self.render_only_fixture(missing=True)
        original = project_path.read_bytes()
        result = bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        self.assertEqual(result["operationResult"]["count"], 0)
        self.assertEqual(settings.montage_task_statuses["0"]["status"], "Ошибка")
        self.assertEqual(project_path.read_bytes(), original)

    def test_render_only_rejects_stale_production_identity(self):
        settings, _ = self.render_only_fixture(wrong_identity=True)
        with self.assertRaises(ValueError):
            bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        self.assertEqual(settings.montage_task_statuses["0"]["status"], "Ошибка")
        self.assertTrue(settings.montage_task_statuses["0"].get("error"))
        self.assertTrue(settings.montage_task_statuses["0"].get("updatedAt"))

    def test_render_only_missing_project_persists_selected_error_before_exit(self):
        settings, path = self.render_only_fixture()
        path.unlink()
        settings.montage_task_statuses["0"]["updatedAt"] = "2026-10-18 00:00:00"
        untouched = {"title": "unselected", "status": "Готово", "updatedAt": "2026-10-18 00:00:00"}
        settings.montage_task_statuses["1"] = copy.deepcopy(untouched)
        config.save_settings(settings)
        with patch.object(bridge, "save_settings", side_effect=config.save_settings), self.assertRaises(ValueError):
            bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        saved = config.load_settings().montage_task_statuses
        self.assertEqual(saved["0"]["status"], "Ошибка")
        self.assertTrue(saved["0"]["error"])
        self.assertGreater(saved["0"]["updatedAt"], "2026-10-18 00:00:00")
        self.assertEqual(saved["1"], untouched)

    def test_render_only_active_queue_rejection_does_not_mark_selected_error(self):
        settings, _ = self.render_only_fixture()
        settings.montage_task_statuses["0"].update(status="Рендер", error="", updatedAt="2026-10-18 00:00:00")
        original = copy.deepcopy(settings.montage_task_statuses)
        with patch.object(bridge, "_recover_interrupted_montage_tasks", return_value=False), \
                patch.object(bridge, "_reconcile_montage_outputs", return_value=False), self.assertRaises(ValueError):
            bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        self.assertEqual(settings.montage_task_statuses, original)

    def test_render_only_batch_preflight_abort_ends_every_selected_idle_row(self):
        settings, project_path = self.render_only_fixture()
        prior_output = Path(settings.montage_task_statuses["0"]["outputPath"])
        original_video = prior_output.read_bytes()
        original_project = project_path.read_bytes()
        settings.montage_task_statuses["0"]["updatedAt"] = "2026-10-18 00:00:00"
        settings.montage_task_statuses["1"] = {
            "status": "Готово", "title": "second", "production_item_id": "pi-second",
            "projectPath": str(self.root / "missing.newsflow"), "updatedAt": "2026-10-18 00:00:00",
        }
        untouched = {"status": "Готово", "title": "unselected", "updatedAt": "2026-10-18 00:00:00"}
        settings.montage_task_statuses["2"] = copy.deepcopy(untouched)
        settings.voice_scenario_outputs["2"] = settings.voice_scenario_outputs["1"]
        jobs = [
            Job(ScenarioRequest(0, "saved", "", production_item_id="pi-current"), RunState.DONE, "script", ""),
            Job(ScenarioRequest(1, "second", "", production_item_id="pi-second"), RunState.DONE, "script", ""),
        ]
        config.save_settings(settings)
        with patch.object(bridge, "load_session", return_value=(["saved", "second", "unselected"], jobs)), \
                patch.object(bridge, "save_settings", side_effect=config.save_settings), self.assertRaises(ValueError):
            bridge._run_montage_queue_unlocked({"indices": [0, 1], "renderOnly": True})
        saved = config.load_settings().montage_task_statuses
        self.assertEqual(saved["0"]["status"], "Ошибка")
        self.assertIn("ошибка проверки строки 2", saved["0"]["error"])
        self.assertEqual(saved["1"]["status"], "Ошибка")
        self.assertIn("подготовьте", saved["1"]["error"])
        self.assertGreater(saved["0"]["updatedAt"], "2026-10-18 00:00:00")
        self.assertGreater(saved["1"]["updatedAt"], "2026-10-18 00:00:00")
        self.assertEqual(saved["2"], untouched)
        self.assertEqual(prior_output.read_bytes(), original_video)
        self.assertEqual(project_path.read_bytes(), original_project)

    def test_pending_project_snapshot_exposes_template_and_hides_stale_output_xml(self):
        projects = self.root / "projects"
        projects.mkdir()
        outputs = self.root / "outputs"
        outputs.mkdir()
        (outputs / "saved.mp4").write_bytes(b"old render")
        (projects / "saved.fcpxml").write_text("old xml", "utf-8")
        TimelineProject(title="saved", overlay_template=template(), overlay_needs_render=True).save(projects / "saved.newsflow")
        settings = config.Settings(montage_project_folder=str(projects), montage_output_folder=str(outputs))
        with patch.object(bridge, "load_settings", return_value=settings), \
                patch.object(bridge, "load_session", return_value=([], [])), \
                patch.object(bridge, "_hydrate_cover_library", return_value=False):
            result = self.real_snapshot()
        project = result["montageProjects"][0]
        self.assertEqual(project["overlayTemplate"], template())
        self.assertTrue(project["overlayNeedsRender"])
        self.assertEqual(project["outputPath"], "")
        self.assertEqual(project["fcpxmlPath"], "")
        task = bridge._montage_task_snapshot_projection("0", {
            "overlayNeedsRender": True, "overlayTemplate": template(), "outputPath": "previous.mp4",
        })
        self.assertEqual(task["overlayTemplate"], template())
        self.assertEqual(task["outputPath"], "")
        self.assertEqual(task["previousOutputPath"], "previous.mp4")

    def random_pool(self):
        first = self.root / "a.png"
        second = self.root / "b.png"
        first.write_bytes(b"asset")
        second.write_bytes(b"asset")
        pool = template("first", enabled=True, path=str(first))
        pool["libraryRoot"] = str(self.root)
        pool["layouts"]["16:9"][0]["randomGroup"] = "logo"
        other = copy.deepcopy(pool["layouts"]["16:9"][0])
        other.update(id="second", name="second", path=str(second))
        pool["layouts"]["16:9"].append(other)
        chosen = []
        for layer in pool["layouts"]["16:9"]:
            choice = copy.deepcopy(pool)
            choice["layouts"]["16:9"] = [copy.deepcopy(layer)]
            chosen.append(choice)
        return pool, chosen

    def test_random_pool_materializes_once_per_new_queue_entry_and_preserves_default(self):
        pool, choices = self.random_pool()
        settings = config.load_settings()
        settings.montage_overlay_template = copy.deepcopy(pool)
        voice = self.root / "voice.mp3"
        voice.write_bytes(b"voice")
        with patch("scriptor.overlays.resolve_overlay_template", side_effect=choices, create=True) as resolve:
            bridge._sync_montage_handoff(settings, 0, "one", str(voice), transferred=True)
            bridge._sync_montage_handoff(settings, 1, "two", str(voice), transferred=True)
            bridge._sync_montage_handoff(settings, 0, "one", str(voice), transferred=True)
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(settings.montage_task_statuses["0"]["overlayTemplate"], choices[0])
        self.assertEqual(settings.montage_task_statuses["1"]["overlayTemplate"], choices[1])
        self.assertEqual(settings.montage_overlay_template, pool)

    def test_selected_pool_materializes_separately_for_each_video_and_saved_project(self):
        pool, choices = self.random_pool()
        project = self.root / "saved.newsflow"
        TimelineProject(title="one").save(project)
        self.save_rows({"0": {"status": "Ошибка", "projectPath": str(project)}, "1": {"status": "Ожидает MP3"}})
        with patch("scriptor.overlays.resolve_overlay_template", side_effect=choices, create=True) as resolve:
            bridge.save_montage_overlays({"scope": "selected", "indices": [0, 1], "template": pool})
        self.assertEqual(resolve.call_count, 2)
        saved = config.load_settings()
        self.assertEqual(saved.montage_task_statuses["0"]["overlayTemplate"], choices[0])
        self.assertEqual(saved.montage_task_statuses["1"]["overlayTemplate"], choices[1])
        self.assertEqual(TimelineProject.load(project).overlay_template, choices[0])
        self.assertEqual(saved.montage_overlay_template["layouts"], {"16:9": [], "9:16": []})

    def test_default_pool_keeps_candidates_without_resolving(self):
        pool, _ = self.random_pool()
        with patch("scriptor.overlays.resolve_overlay_template", side_effect=AssertionError("defaults keep pool"), create=True):
            bridge.save_montage_overlays({"scope": "new", "template": pool})
        self.assertEqual(config.load_settings().montage_overlay_template, pool)

    def test_legacy_unsnapshotted_prepare_materializes_and_persists_before_planning(self):
        pool, choices = self.random_pool()
        settings = config.load_settings()
        settings.montage_overlay_template = pool
        config.save_settings(settings)
        with patch("scriptor.overlays.resolve_overlay_template", return_value=choices[0], create=True) as resolve:
            first = bridge._montage_overlay_template_for_task(settings, 0)
            second = bridge._montage_overlay_template_for_task(settings, 0)
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(first, choices[0])
        self.assertEqual(second, choices[0])
        self.assertEqual(config.load_settings().montage_task_statuses["0"]["overlayTemplate"], choices[0])

    def test_saved_plan_render_never_rerolls_chosen_random_asset(self):
        pool, choices = self.random_pool()
        settings, project_path = self.render_only_fixture()
        settings.montage_overlay_template = pool
        project = TimelineProject.load(project_path)
        project.overlay_template = choices[0]
        project.save(project_path)
        with patch("scriptor.overlays.resolve_overlay_template", side_effect=AssertionError("render cannot reroll"), create=True):
            result = bridge._run_montage_queue_unlocked({"indices": [0], "renderOnly": True})
        self.assertEqual(result["operationResult"]["count"], 1)
        self.assertEqual(TimelineProject.load(project_path).overlay_template, choices[0])
        self.assertEqual(settings.montage_task_statuses["0"]["overlayTemplate"], choices[0])

    def test_scan_command_delegates_to_library_service_and_returns_assets(self):
        scanned = {"folder": str(self.root), "assets": [{"path": str(self.root / "a.png"), "kind": "image", "name": "a.png"}], "skippedSymlinks": 2}
        scan = Mock(return_value=scanned)
        with patch.dict(sys.modules, {"scriptor.overlay_library": SimpleNamespace(scan_overlay_library=scan)}):
            result = bridge.scan_montage_overlays({"folder": str(self.root)})
        scan.assert_called_once_with(str(self.root))
        self.assertEqual(result["operationResult"], {"kind": "overlay-library", **scanned})


if __name__ == "__main__":
    unittest.main()
