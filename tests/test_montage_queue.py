import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge, config
from scriptor.config import OpenAIKey, Settings
from scriptor.footage import FootageItem
from scriptor.runner import RunState
from scriptor.ai_index import SearchHit


class MontageQueueStateTests(unittest.TestCase):
    def test_unmarked_legacy_remotion_default_migrates_to_fast_news_ffmpeg(self):
        """An old implicit renderer default must not keep a new queue on the slow route."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text('{"montage_renderer":"remotion"}', encoding="utf-8")
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()

        self.assertEqual(restored.montage_renderer, "ffmpeg")
        self.assertFalse(restored.montage_renderer_explicit)

    def test_explicit_remotion_selection_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings_path.write_text(
                '{"montage_renderer":"remotion","montage_renderer_explicit":true}', encoding="utf-8",
            )
            with patch.object(config, "config_path", return_value=settings_path):
                restored = config.load_settings()

        self.assertEqual(restored.montage_renderer, "remotion")
        self.assertTrue(restored.montage_renderer_explicit)

    def test_normalized_montage_query_deduplicates_and_removes_generic_phrases(self):
        normalized = bridge._normalized_montage_visual_query(
            "international news, documentary footage, oil tanker refinery oil terminal, "
            "oil tanker refinery oil terminal, seaport cargo cranes ships"
        )
        self.assertEqual(
            normalized,
            "oil tanker refinery oil terminal, seaport cargo cranes ships",
        )

    def test_prepare_montage_uses_local_scan_when_ai_index_is_empty(self):
        """A new footage folder must work before its optional AI index is built."""
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            footage = root / "footage"
            footage.mkdir()
            (footage / "Iran oil tanker Hormuz shipping.mp4").write_bytes(b"source")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(
                footage_folders=[str(footage)], voicer_output_folder=str(root),
                montage_project_folder=str(root / "projects"), montage_output_folder=str(root / "output"),
                montage_use_script_text=False, montage_auto_web=False,
            )
            job = Job(ScenarioRequest(0, "Iran oil tanker Hormuz", ""), RunState.DONE, "", "")
            settings.voice_scenario_outputs = {"1": str(voice)}
            with patch.object(bridge, "load_settings", return_value=settings), \
                 patch.object(bridge, "load_session", return_value=(["Iran oil tanker Hormuz"], [job])), \
                 patch.object(bridge, "save_settings"), \
                 patch.object(bridge, "snapshot", return_value={}), \
                 patch.object(bridge.ClipIndex, "count", return_value=0), \
                 patch.object(bridge, "probe_media_duration", return_value=6.0), \
                 patch.object(bridge, "probe_video_duration", return_value=8.0):
                result = bridge.prepare_montage({"scenarioIndex": 0})

        self.assertEqual(result["preparedProject"]["clips"], 1)

    def test_selection_uses_reserved_candidate_only_after_new_candidates_are_exhausted(self):
        available = FootageItem("D:/new-family/clip_new_001.mp4", "new.mp4", tags=["oil-tanker-port"])
        reserved = FootageItem("D:/reserved-family/clip_reserved_001.mp4", "reserved.mp4", tags=["oil-tanker-port"])
        query = "oil tanker refinery oil terminal"
        result = bridge._select_montage_candidate(
            query,
            strict_hits=[SearchHit(available, .30, duration=6.0), SearchHit(reserved, .95, duration=6.0)],
            fallback_hits=[],
            required_duration=6.0,
            match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
            reserved_paths={bridge._montage_clip_key(reserved.path)},
            reserved_families={bridge._montage_clip_family_key(reserved.path)},
            source_exists=lambda item: True,
            source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, available.path)
        self.assertEqual(result.fallback_level, "STRICT_MATCH")
        self.assertFalse(result.reused_reserved_candidate)

    def test_selection_uses_safe_reserved_reuse_when_reservation_exhausts_candidates(self):
        reserved = FootageItem("D:/reserved-family/clip_reserved_001.mp4", "reserved.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(reserved, .30, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
            reserved_paths={bridge._montage_clip_key(reserved.path)},
            reserved_families={bridge._montage_clip_family_key(reserved.path)},
            source_exists=lambda item: True, source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, reserved.path)
        self.assertEqual(result.fallback_level, "RESERVED_REUSE")
        self.assertTrue(result.reused_reserved_candidate)

    def test_reservation_race_converts_valid_selection_to_safe_reuse(self):
        item = FootageItem("D:/reserved/clip_001.mp4", "shot.mp4")
        selection = bridge.MontageCandidateSelection(item, 6.0, .30, "STRICT_MATCH", False, {})
        reused = bridge._safe_reuse_after_reservation_race(selection, claim=lambda _: False)
        self.assertEqual(reused.fallback_level, "SAFE_REUSE")
        self.assertTrue(reused.reused_reserved_candidate)

    def test_selection_uses_the_only_safe_clip_as_last_resort(self):
        """Quality exhaustion must not turn one valid local clip into NO_FOOTAGE."""
        same = FootageItem("D:/one-family/clip_001.mp4", "same.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(same, .30, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(same.path)},
            used_families={bridge._montage_clip_family_key(same.path)},
            project_used_paths={bridge._montage_clip_key(same.path)},
            project_used_families={bridge._montage_clip_family_key(same.path)},
            recent_project_paths={bridge._montage_clip_key(same.path)},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda item: True, source_duration=lambda item: 6.0,
        )
        self.assertEqual(result.item.path, same.path)
        self.assertEqual(result.fallback_level, "LAST_RESORT")

    def test_safe_reuse_avoids_the_immediately_previous_clip_when_an_older_valid_clip_exists(self):
        """A B A is acceptable after quality exhaustion; A A is not."""
        older = FootageItem("D:/pool/older.mp4", "older.mp4", tags=["oil-tanker-port"])
        previous = FootageItem("D:/pool/previous.mp4", "previous.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(previous, .95, duration=6.0), SearchHit(older, .30, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(older.path), bridge._montage_clip_key(previous.path)},
            used_families={bridge._montage_clip_family_key(older.path), bridge._montage_clip_family_key(previous.path)},
            project_used_paths={bridge._montage_clip_key(older.path), bridge._montage_clip_key(previous.path)},
            project_used_families={bridge._montage_clip_family_key(older.path), bridge._montage_clip_family_key(previous.path)},
            recent_project_paths={bridge._montage_clip_key(previous.path)},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, older.path)
        self.assertEqual(result.fallback_level, "SAFE_REUSE")

    def test_diagnostics_separate_unique_diversity_rejections_from_pass_events(self):
        """One candidate may be examined repeatedly but remains one unique rejection."""
        used = FootageItem("D:/used/used.mp4", "used.mp4", tags=["oil-tanker-port"])
        fresh = FootageItem("D:/fresh/fresh.mp4", "fresh.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(used, .40, duration=6.0), SearchHit(fresh, .30, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(used.path)},
            used_families={bridge._montage_clip_family_key(used.path)},
            project_used_paths=set(), project_used_families=set(),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, fresh.path)
        self.assertEqual(result.diagnostics["unique_rejected_diversity"], 1)
        self.assertGreaterEqual(result.diagnostics["rejection_events"], 1)

    def test_last_resort_still_avoids_previous_clip_when_any_other_valid_clip_exists(self):
        previous = FootageItem("D:/pool/previous.mp4", "previous.mp4", tags=["oil-tanker-port"])
        alternative = FootageItem("D:/pool/alternative.mp4", "alternative.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery oil terminal",
            strict_hits=[SearchHit(previous, .95, duration=6.0), SearchHit(alternative, .20, duration=6.0)],
            fallback_hits=[], required_duration=6.0, match_threshold=.22,
            used_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            used_families={bridge._montage_clip_family_key(previous.path), bridge._montage_clip_family_key(alternative.path)},
            project_used_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            project_used_families={bridge._montage_clip_family_key(previous.path), bridge._montage_clip_family_key(alternative.path)},
            recent_project_paths={bridge._montage_clip_key(previous.path), bridge._montage_clip_key(alternative.path)},
            immediately_previous_path=bridge._montage_clip_key(previous.path),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, alternative.path)
        self.assertEqual(result.fallback_level, "LAST_RESORT")

    def test_failed_planner_releases_only_its_own_batch_reservations(self):
        usage = {
            "lock": __import__("threading").RLock(),
            "paths": {"path-82": 81, "path-83": 82},
            "families": {"family-82": 81, "family-83": 82},
        }
        bridge._release_batch_footage_reservations(usage, 81)
        self.assertNotIn("path-82", usage["paths"])
        self.assertNotIn("family-82", usage["families"])
        self.assertEqual(usage["paths"]["path-83"], 82)
        self.assertEqual(usage["families"]["family-83"], 82)

    def test_selection_uses_relaxed_match_below_ideal_threshold(self):
        item = FootageItem("D:/oil/clip_001.mp4", "oil.mp4", tags=["oil-tanker-port"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery", strict_hits=[SearchHit(item, .18, duration=6.0)], fallback_hits=[],
            required_duration=6.0, match_threshold=.22, used_paths=set(), used_families=set(),
            project_used_paths=set(), project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.fallback_level, "RELAXED_MATCH")
        self.assertEqual(result.diagnostics["rejected_threshold"], 1)

    def test_selection_skips_missing_strict_candidate_for_valid_category_candidate(self):
        missing = FootageItem("D:/oil/missing.mp4", "missing.mp4", tags=["oil-tanker-port"])
        category = FootageItem("D:/port/clip_002.mp4", "port.mp4", tags=["port-logistics"])
        result = bridge._select_montage_candidate(
            "oil tanker refinery", strict_hits=[SearchHit(missing, .50, duration=6.0)],
            fallback_hits=[SearchHit(category, .20, duration=6.0)], required_duration=6.0,
            match_threshold=.22, used_paths=set(), used_families=set(), project_used_paths=set(),
            project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda item: item.path != missing.path, source_duration=lambda _: 6.0,
        )
        self.assertEqual(result.item.path, category.path)
        self.assertEqual(result.fallback_level, "CATEGORY_CONTEXT_FALLBACK")
        self.assertGreaterEqual(result.diagnostics["rejected_missing"], 2)

    def test_snapshot_sync_never_replaces_a_render_error_with_new_mp3(self):
        """A finished MP3 scan must not hide a resumable footage/render error."""
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / "voice.mp3"
            voice.write_bytes(b"mp3")
            settings = Settings(voice_scenario_outputs={"13": str(voice)})
            settings.montage_task_statuses = {
                "12": {
                    "title": "Тема", "scenarioIndex": 12, "status": "Ошибка",
                    "phase": "Ошибка рендера", "progress": 100,
                    "error": "Футаж не найден: D:/missing.mp4",
                    "projectPath": "D:/projects/topic.newsflow",
                    "voicePath": str(voice),
                }
            }
            changed = bridge._sync_finished_scenarios_to_montage(settings, [{
                "index": 12, "title": "Тема", "state": RunState.DONE.value, "result": "Сценарий",
            }])
            self.assertFalse(changed)
            self.assertEqual(settings.montage_task_statuses["12"]["status"], "Ошибка")
            self.assertEqual(settings.montage_task_statuses["12"]["projectPath"], "D:/projects/topic.newsflow")

    def test_snapshot_sync_restores_an_error_hidden_by_old_mp3_handoff(self):
        with tempfile.TemporaryDirectory() as folder:
            voice = Path(folder) / "voice.mp3"
            voice.write_bytes(b"mp3")
            settings = Settings(voice_scenario_outputs={"14": str(voice)})
            settings.montage_task_statuses = {
                "13": {
                    "title": "Тема", "scenarioIndex": 13, "status": "Новый MP3",
                    "phase": "Новая озвучка", "progress": 0, "voicePath": str(voice),
                    "projectPath": "D:/projects/topic.newsflow", "error": "",
                    "timeline": [{"label": "Ошибка рендера", "progress": 100,
                                  "detail": "Футаж не найден: D:/missing.mp4"}],
                }
            }
            changed = bridge._sync_finished_scenarios_to_montage(settings, [{
                "index": 13, "title": "Тема", "state": RunState.DONE.value, "result": "Сценарий",
            }])
            self.assertTrue(changed)
            row = settings.montage_task_statuses["13"]
            self.assertEqual(row["status"], "Ошибка")
            self.assertEqual(row["phase"], "Ошибка рендера")
            self.assertIn("Футаж не найден", row["error"])

    def test_render_preflight_reports_only_missing_timeline_clips(self):
        """A saved project is replanned before FFmpeg when a source vanished."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            present = root / "present.mp4"
            missing = root / "missing.mp4"
            present.write_bytes(b"clip")
            project = TimelineProject(
                title="Тема",
                clips=[
                    TimelineClip(path=str(present), narration="a", visual_query_en="a", duration=6),
                    TimelineClip(path=str(missing), narration="b", visual_query_en="b", duration=6),
                ],
            )
            with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: 6.0 if path == present else 0.0):
                self.assertEqual(bridge._montage_project_missing_clips(project), [str(missing)])

    def test_missing_clip_recovery_replaces_only_the_invalid_slot(self):
        """Recovery preserves all healthy edits, narration and source MP3."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, missing, last, replacement = (root / name for name in ("first.mp4", "gone.mp4", "last.mp4", "replacement.mp4"))
            first.write_bytes(b"first")
            last.write_bytes(b"last")
            replacement.write_bytes(b"replacement")
            project = TimelineProject(
                title="Тема", voiceover_path="D:/audio/13.mp3",
                clips=[
                    TimelineClip(str(first), "first narration", "first query", duration=6.0),
                    TimelineClip(str(missing), "missing narration", "missing query", duration=4.0),
                    TimelineClip(str(last), "last narration", "last query", duration=6.0),
                ],
            )
            durations = {str(first): 6.0, str(missing): 0.0, str(last): 6.0, str(replacement): 6.0}
            with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: durations[str(path)]):
                repaired = bridge._repair_missing_project_clips(
                    project,
                    lambda clip, _excluded: [FootageItem(str(replacement), replacement.name, "local")],
                )
            self.assertEqual(repaired, 1)
            self.assertEqual([clip.path for clip in project.clips], [str(first), str(replacement), str(last)])
            self.assertEqual(project.clips[1].narration, "missing narration")
            self.assertEqual(project.clips[1].visual_query_en, "missing query")
            self.assertEqual(project.voiceover_path, "D:/audio/13.mp3")

    def test_missing_clip_recovery_never_uses_an_invalid_or_too_short_replacement(self):
        from scriptor.timeline import TimelineClip, TimelineProject

        project = TimelineProject(title="Тема", clips=[TimelineClip("gone.mp4", "n", "q", duration=5.0)])
        durations = {"gone.mp4": 0.0, "tiny.mp4": 2.0, "healthy.mp4": 6.0}
        with patch("scriptor.bridge._validated_montage_clip_duration", side_effect=lambda path: durations[str(path)]):
            repaired = bridge._repair_missing_project_clips(
                project,
                lambda _clip, _excluded: [
                    FootageItem("tiny.mp4", "tiny.mp4"),
                    FootageItem("healthy.mp4", "healthy.mp4"),
                ],
            )
        self.assertEqual(repaired, 1)
        self.assertEqual(project.clips[0].path, "healthy.mp4")

    def test_ormuz_scene_rejects_explicit_ukraine_clip(self):
        scene = "Strait of Hormuz oil tanker Iran Persian Gulf"
        wrong = FootageItem("D:/clips/Pokrovsk_Ukraine_42.mp4", "Pokrovsk Ukraine battle.mp4", tags=["ukraine", "pokrovsk"])
        right = FootageItem("D:/clips/oil_tanker_hormuz_12.mp4", "oil tanker Hormuz.mp4", tags=["iran", "tanker"])
        self.assertFalse(bridge._semantic_clip_ok(scene, wrong))
        self.assertTrue(bridge._semantic_clip_ok(scene, right))

    def test_ormuz_scene_rejects_explicitly_wrong_external_result_before_download(self):
        scene = "Strait of Hormuz oil tanker Iran Persian Gulf"
        wrong = {"title": "Pokrovsk battle footage Ukraine", "url": "https://example.test/pokrovsk.mp4"}
        right = {"title": "Oil tanker at the Strait of Hormuz", "url": "https://example.test/tanker.mp4"}
        self.assertFalse(bridge._external_candidate_ok(scene, wrong))
        self.assertTrue(bridge._external_candidate_ok(scene, right))

    def test_frontline_scene_prefers_enriched_military_footage(self):
        scene = "frontline battlefield soldiers advancing infantry armored vehicles"
        frontline = FootageItem("D:/clips/a.mp4", "clip.mp4", tags=["frontline-combat", "offensive-advance"])
        neutral = FootageItem("D:/clips/b.mp4", "clip.mp4", tags=["international-news"])
        self.assertGreater(bridge._montage_semantic_bonus(scene, frontline),
                           bridge._montage_semantic_bonus(scene, neutral))

    def test_war_scene_rejects_explicit_agriculture_footage(self):
        scene = "missile drone artillery strike frontline battlefield"
        farm = FootageItem("D:/clips/potato_harvest_tractor.mp4", "potato harvest.mp4",
                           tags=["agriculture-farming", "картошка"])
        drone = FootageItem("D:/clips/military_uav.mp4", "military drone.mp4",
                            tags=["military-drone"])
        self.assertFalse(bridge._semantic_clip_ok(scene, farm))
        self.assertTrue(bridge._semantic_clip_ok(scene, drone))

    def test_agriculture_scene_keeps_agriculture_footage_available(self):
        scene = "potato harvest farming tractor agricultural field"
        farm = FootageItem("D:/clips/potato_harvest_tractor.mp4", "potato harvest.mp4",
                           tags=["agriculture-farming"])
        self.assertTrue(bridge._semantic_clip_ok(scene, farm))

    def test_protest_and_migrant_scenes_prefer_their_own_clusters(self):
        protest = FootageItem("D:/clips/protest.mp4", "clip.mp4", tags=["protest-crowd"])
        border = FootageItem("D:/clips/border.mp4", "clip.mp4", tags=["migrant-border"])
        neutral = FootageItem("D:/clips/office.mp4", "clip.mp4", tags=["political-office"])
        self.assertGreater(bridge._montage_semantic_bonus("protest crowd street rally", protest),
                           bridge._montage_semantic_bonus("protest crowd street rally", neutral))
        self.assertGreater(bridge._montage_semantic_bonus("migrants border crossing", border),
                           bridge._montage_semantic_bonus("migrants border crossing", neutral))

    def test_short_indexed_source_is_not_used_for_a_long_scene(self):
        # The selection filter rejects an undersized SearchHit before FFmpeg
        # can turn its missing tail into a frozen final frame.
        from scriptor.ai_index import SearchHit
        item = FootageItem("D:/clips/two-seconds.mp4", "two-seconds.mp4", tags=["frontline-combat"])
        self.assertLess(SearchHit(item, .9, duration=2.0).duration, 5.8)

    def test_terminal_153_second_tail_uses_a_real_last_resort_clip(self):
        """A tiny audio remainder must not fail just because only a reused real clip remains."""
        from scriptor.timeline import TimelineClip, TimelineProject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            voice = root / "voice.mp3"
            footage = root / "news-footage.mp4"
            voice.write_bytes(b"voice")
            footage.write_bytes(b"footage")
            project = TimelineProject(
                title="Тема", voiceover_path=str(voice),
                clips=[TimelineClip(str(footage), "narration", "news footage", duration=6.0)],
            )
            # target = 7.53 seconds: one six-second clip leaves exactly 1.53.
            with patch.object(bridge, "probe_media_duration", return_value=7.4466666667), \
                 patch.object(bridge, "_cached_or_probed_montage_duration", return_value=6.0), \
                 patch.object(bridge, "_replacement_candidates_for_clip", return_value=[
                     FootageItem(str(footage), footage.name, "local"),
                 ]):
                appended = bridge._complete_project_visual_tail(project, object(), Settings(montage_auto_web=False))

        self.assertEqual(appended, 1)
        self.assertEqual(len(project.clips), 2)
        self.assertAlmostEqual(sum(clip.duration for clip in project.clips), 7.53, places=2)
        self.assertAlmostEqual(project.clips[-1].duration, 1.53, places=2)
        self.assertEqual(project.clips[-1].path, str(footage))

    def test_clip_identity_is_case_insensitive_and_absolute(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Shot.MP4"
            path.write_bytes(b"x")
            self.assertEqual(bridge._montage_clip_key(str(path)), bridge._montage_clip_key(str(path).lower()))

    def test_candidate_identity_does_not_resolve_each_library_path(self):
        """Ranking thousands of candidates must not call Windows path resolution."""
        with patch("scriptor.bridge.Path.resolve", side_effect=AssertionError("filesystem resolve")):
            key = bridge._montage_clip_key("D:/library/one/clip_001.mp4")
            family = bridge._montage_clip_family_key("D:/library/one/clip_001.mp4")
        self.assertEqual(key, "d:\\library\\one\\clip_001.mp4")
        self.assertEqual(family, "d:\\library\\one")

    def test_candidate_family_identity_does_not_construct_path_objects(self):
        with patch("scriptor.bridge.Path", side_effect=AssertionError("Path must not be used in ranking")):
            family = bridge._montage_clip_family_key("D:/library/one/clip_001.mp4")
        self.assertEqual(family, "d:\\library\\one")

    def test_generated_cuts_from_one_original_are_one_source_family(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Зеленский" / "Исходный ролик"
            source.mkdir(parents=True)
            first = source / "clip_a9hd_001.mp4"
            second = source / "clip_z22p_945.mp4"
            other = Path(folder) / "Зеленский" / "Другой исходник" / "clip_z22p_945.mp4"
            other.parent.mkdir(parents=True)
            for path in (first, second, other):
                path.write_bytes(b"x")
            self.assertEqual(bridge._montage_clip_family_key(str(first)), bridge._montage_clip_family_key(str(second)))
            self.assertNotEqual(bridge._montage_clip_family_key(str(first)), bridge._montage_clip_family_key(str(other)))

    def test_same_source_family_is_excluded_even_when_clip_paths_differ(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "one-source"
            source.mkdir()
            used = source / "clip_a_001.mp4"
            alternate_cut = source / "clip_b_002.mp4"
            for path in (used, alternate_cut):
                path.write_bytes(b"x")
            item = FootageItem(str(alternate_cut), alternate_cut.name)
            self.assertTrue(bridge._montage_item_is_excluded(
                item, {bridge._montage_clip_key(str(used))},
                {bridge._montage_clip_family_key(str(used))},
            ))
    def test_paused_montage_is_still_an_active_batch(self):
        self.assertTrue(bridge.montage_queue_is_active({"3": {"status": "Пауза"}}))
        self.assertTrue(bridge.montage_queue_is_active({"3": {"status": "Рендер"}}))
        self.assertFalse(bridge.montage_queue_is_active({"3": {"status": "Готово"}}))

    def test_user_selected_planning_workers_are_not_hiddenly_limited_by_library_size(self):
        self.assertEqual(bridge._montage_planning_worker_limit(12, 8, 28_975), 8)
        self.assertEqual(bridge._montage_planning_worker_limit(4, 8, 28_975), 4)
        self.assertEqual(bridge._montage_planning_worker_limit(12, 8, 12_000), 8)
        self.assertEqual(bridge._montage_planning_worker_limit(6, 3, 100), 3)

    def test_montage_parallelism_values_are_saved_without_hidden_upper_limits(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge.save_settings"), \
                patch("scriptor.bridge.snapshot", return_value={}):
            bridge.save_montage_settings({
                "planningWorkers": 48,
                "downloadWorkers": 36,
                "renderWorkers": 24,
                "remotionFrameConcurrency": 20,
            })
        self.assertEqual(settings.montage_planning_workers, 48)
        self.assertEqual(settings.montage_download_workers, 36)
        self.assertEqual(settings.montage_render_workers, 24)
        self.assertEqual(settings.montage_remotion_frame_concurrency, 20)

    def test_fast_reuse_can_be_scoped_to_separate_one_based_topic_ranges(self):
        settings = Settings(montage_fast_reuse_enabled=True, montage_unique_footage_percent=35,
                            montage_fast_reuse_ranges=[
                                {"start": 1, "end": 3, "percent": 13},
                                {"start": 7, "end": 8, "percent": 20},
                            ])
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 0), 13)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 2), 13)
        self.assertIsNone(bridge._fast_reuse_percent_for_scenario(settings, 3))
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 6), 20)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 7), 20)

    def test_fast_reuse_without_ranges_applies_default_to_every_topic(self):
        settings = Settings(montage_fast_reuse_enabled=True, montage_unique_footage_percent=25)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 0), 25)
        self.assertEqual(bridge._fast_reuse_percent_for_scenario(settings, 100), 25)

    def test_interrupted_queue_is_recovered_without_deleting_its_source_data(self):
        settings = Settings()
        settings.montage_task_statuses = {
            "2": {"title": "Тест", "status": "Рендер", "progress": 72,
                  "timeline": [{"at": "10:00:00", "label": "Рендер", "progress": 72}]}
        }
        self.assertTrue(bridge._recover_interrupted_montage_tasks(settings))
        task = settings.montage_task_statuses["2"]
        self.assertEqual(task["status"], "Ошибка")
        self.assertEqual(task["phase"], "Предыдущий запуск остановлен")
        self.assertIn("остановлена", task["error"])
        self.assertEqual(task["title"], "Тест")

    def test_default_queue_skips_a_valid_ready_video(self):
        """Ordinary resume must never rebuild a completed, valid MP4."""
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"valid-video")
            settings = Settings()
            settings.montage_task_statuses = {
                "0": {"title": "Тест", "status": "Готово", "outputPath": str(output)},
                "1": {"title": "Ещё тема", "status": "Ошибка", "outputPath": ""},
            }
            with patch("scriptor.bridge._is_valid_montage_output", side_effect=lambda path: path == output):
                self.assertFalse(bridge._montage_task_needs_render(settings, 0))
                self.assertTrue(bridge._montage_task_needs_render(settings, 1))

    def test_ready_output_check_uses_mp4_header_without_starting_ffprobe(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
            with patch("scriptor.bridge.probe_media_duration", side_effect=AssertionError("ffprobe must not start")):
                self.assertTrue(bridge._is_valid_montage_output(output))

    def test_reconcile_stale_render_with_valid_output_as_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "Готово.mp4"
            output.write_bytes(b"valid-video")
            settings = Settings()
            settings.montage_task_statuses = {
                "5": {"title": "Тест", "status": "Рендер", "outputPath": str(output)},
            }
            with patch("scriptor.bridge._is_valid_montage_output", side_effect=lambda path: path == output):
                self.assertTrue(bridge._reconcile_montage_outputs(settings, force_interrupted=True))
            task = settings.montage_task_statuses["5"]
            self.assertEqual(task["status"], "Готово")
            self.assertEqual(task["phase"], "MP4 восстановлен")

    def test_reconcile_reattaches_registered_valid_mp4_when_task_path_is_stale(self):
        """A durable registered output is authoritative over an old task path."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stale = root / "old" / "Тема.mp4"
            recovered = root / "moved" / "Тема.mp4"
            recovered.parent.mkdir()
            recovered.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"x" * 2048)
            settings = Settings()
            settings.montage_task_statuses = {
                "5": {"title": "Тема", "status": "Ошибка", "phase": "MP4 не найден",
                      "outputPath": str(stale), "voicePath": str(root / "voice.mp3")},
            }
            settings.pipeline_montage_outputs = [str(stale), str(recovered)]

            self.assertTrue(bridge._reconcile_montage_outputs(settings))

            task = settings.montage_task_statuses["5"]
            self.assertEqual(task["status"], "Готово")
            self.assertEqual(task["outputPath"], str(recovered))
            self.assertEqual(settings.pipeline_montage_outputs, [str(stale), str(recovered)])

    def test_reconcile_keeps_missing_registered_output_for_publication_recovery(self):
        """A missing MP4 is a recoverable reference, never a reason to erase the production record."""
        settings = Settings()
        missing = "D:/missing/episode.mp4"
        settings.pipeline_montage_outputs = [missing]

        bridge._reconcile_montage_outputs(settings)

        self.assertEqual(settings.pipeline_montage_outputs, [str(Path(missing))])

    def test_task_update_persists_a_visible_timeline_and_keeps_external_pause(self):
        worker_settings = Settings()
        latest_settings = Settings(montage_queue_paused=True)
        with patch("scriptor.bridge.load_settings", return_value=latest_settings), \
                patch("scriptor.bridge.save_settings") as save:
            bridge._montage_task_update(
                worker_settings, 4, status="Подбор футажей", phase="Подбор футажей",
                progress=42, detail="Сцена 2/8: tanker.mp4", title="Тестовая тема",
            )
        task = worker_settings.montage_task_statuses["4"]
        self.assertTrue(worker_settings.montage_queue_paused)
        self.assertEqual(task["status"], "Подбор футажей")
        self.assertEqual(task["progress"], 42)
        self.assertEqual(task["timeline"][-1]["detail"], "Сцена 2/8: tanker.mp4")
        save.assert_called_once_with(worker_settings)

    def test_render_update_records_heartbeat_and_render_start(self):
        settings = Settings()
        with patch("scriptor.bridge.load_settings", return_value=settings), \
                patch("scriptor.bridge.save_settings"):
            bridge._montage_task_update(
                settings, 4, status="Рендер", phase="Подготовка рендера", progress=60,
                detail="FFmpeg запускается", ffmpegPid=12345,
            )
        task = settings.montage_task_statuses["4"]
        self.assertEqual(task["ffmpegPid"], 12345)
        self.assertTrue(task["renderStartedAt"])
        self.assertTrue(task["lastHeartbeatAt"])
        self.assertTrue(task["lastProgressAt"])

    def test_only_transient_render_failures_are_retried(self):
        self.assertTrue(bridge._is_retryable_montage_error("WinError 32: file is busy"))
        self.assertTrue(bridge._is_retryable_montage_error("FFmpeg timed out while saving"))
        self.assertTrue(bridge._is_retryable_montage_error("Таймлайн футажей короче озвучки на 3.0 сек"))
        self.assertTrue(bridge._is_retryable_montage_error("Футаж не найден: D:\\missing.mp4"))

    def test_stale_cover_save_cannot_revert_newer_montage_render_status(self):
        """A parallel non-montage worker must not roll a rendered row back to footage.

        The long cover worker keeps its own Settings instance.  Before the
        regression fix, its next whole-file save replaced the newer montage
        progress written by the montage worker.
        """
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale_cover_settings = Settings()
            stale_cover_settings.montage_task_statuses = {
                "0": {"status": "Подбор футажей", "phase": "Подбор футажей",
                      "progress": 45, "updatedAt": "2026-09-09 10:19:48"}
            }
            montage_settings = Settings()
            montage_settings.montage_task_statuses = {
                "0": {"status": "Рендер", "phase": "Склейка",
                      "progress": 97, "updatedAt": "2026-09-09 10:26:45"}
            }
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(montage_settings)
                config.save_settings(stale_cover_settings)
                persisted = config.load_settings().montage_task_statuses["0"]
            self.assertEqual(persisted["status"], "Рендер")
            self.assertEqual(persisted["phase"], "Склейка")
            self.assertEqual(persisted["progress"], 97)

    def test_montage_save_cannot_revert_a_newer_cover_status(self):
        """A background renderer must not hide a cover that just finished."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale_montage_settings = Settings(cover_queue=[{
                "scenario_index": 1, "title": "Тема", "status": "Подготовка запросов",
                "progress": 10, "updatedAt": "2026-09-09T10:00:00.000000",
            }])
            completed_cover_settings = Settings(cover_queue=[{
                "scenario_index": 1, "title": "Тема", "status": "Готово",
                "progress": 100, "path": "D:/cover.png",
                "updatedAt": "2026-09-09T10:00:01.000000",
            }])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(stale_montage_settings)
                config.save_settings(completed_cover_settings)
                config.save_settings(stale_montage_settings)
                persisted = config.load_settings().cover_queue[0]
            self.assertEqual(persisted["status"], "Готово")
            self.assertEqual(persisted["path"], "D:/cover.png")

    def test_stale_worker_cannot_drop_newly_added_openai_keys(self):
        """Saving old queue state must preserve API keys added in the UI."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            stale = Settings(openai_api_keys=[OpenAIKey("Первый", "key-one", True)])
            updated = Settings(openai_api_keys=[
                OpenAIKey("Первый", "key-one", True),
                OpenAIKey("Второй", "key-two", True),
            ])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(stale)
                config.save_settings(updated)
                config.save_settings(stale)
                persisted = config.load_settings()
            self.assertEqual([key.secret for key in persisted.openai_api_keys], ["key-one", "key-two"])

    def test_stale_worker_cannot_erase_persisted_production_state(self):
        """An old detached worker must never replace a completed release with blanks."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            completed = Settings(
                idea_results=[{"title": "Готовый сценарий", "script": "Текст"}],
                idea_production_items=[{"id": "production:1", "title": "Готовый сценарий"}],
                voice_scenario_outputs={"0": "D:/voices/0001.mp3"},
                pipeline_montage_outputs=["D:/videos/0001.mp4"],
                seo_queue=[{"scenario_index": 0, "title": "Готовый сценарий"}],
            )
            stale_worker = Settings()
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(completed)
                config.save_settings(stale_worker)
                persisted = config.load_settings()

            self.assertEqual(persisted.idea_results, completed.idea_results)
            self.assertEqual(persisted.idea_production_items, completed.idea_production_items)
            self.assertEqual(persisted.voice_scenario_outputs, completed.voice_scenario_outputs)
            self.assertEqual(persisted.pipeline_montage_outputs, completed.pipeline_montage_outputs)
            self.assertEqual(persisted.seo_queue, completed.seo_queue)

    def test_production_clear_requires_a_typed_confirmation_phrase(self):
        """A stale UI action with only a boolean must never erase work folders."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = Settings(
                output_folder=str(root / "output"),
                voicer_output_folder=str(root / "voices"),
                cover_output_folder=str(root / "covers"),
                seo_output_folder=str(root / "seo"),
                media_output_folder=str(root / "media"),
                cutter_output_folder=str(root / "cuts"),
                footage_download_folder=str(root / "downloads"),
                mixer_output_folder=str(root / "mix"),
                montage_output_folder=str(root / "mp4"),
                montage_project_folder=str(root / "projects"),
            )
            protected_video = root / "mp4" / "keep.mp4"
            protected_video.parent.mkdir()
            protected_video.write_bytes(b"keep")
            with patch("scriptor.bridge.load_settings", return_value=settings):
                with self.assertRaisesRegex(ValueError, "контрольную фразу"):
                    bridge.clear_production_queue({"confirmed": True})
            self.assertTrue(protected_video.exists())

    def test_settings_save_creates_an_independent_recovery_snapshot(self):
        """A future faulty write must leave a readable pre-write state behind."""
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            settings = Settings(idea_results=[{"title": "Сценарий"}])
            with patch.object(config, "config_path", return_value=settings_path):
                config.save_settings(settings)
                changed = Settings(idea_results=[{"title": "Новый сценарий"}])
                config.save_settings(changed)

            archives = sorted((Path(folder) / "state-backups").glob("settings-*.json"))
            self.assertTrue(archives)
            archived = __import__("json").loads(archives[-1].read_text(encoding="utf-8"))
            self.assertEqual(archived["idea_results"], settings.idea_results)

    def test_temp_cover_output_is_migrated_to_the_permanent_library(self):
        """A disposable test/snapshot directory must never become a production cover path."""
        temporary = str(Path(tempfile.gettempdir()) / "tmp-newsflow-cover-test" / "covers")
        with patch.object(config, "storyflow_documents_root", return_value=Path("D:/NewsFlow Studio")):
            migrated = config.migrate_standard_folder(temporary, "Обложки", "Обложки")
        self.assertEqual(migrated, "D:\\NewsFlow Studio\\Обложки")

    def test_remove_result_never_touches_source_audio_or_outside_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "MP4"
            output.mkdir()
            generated = output / "Тема.mp4"
            generated.write_bytes(b"generated")
            source = root / "voice.mp3"
            source.write_bytes(b"voice")
            outside = root / "outside.mp4"
            outside.write_bytes(b"keep")
            settings = Settings(montage_output_folder=str(output))
            settings.pipeline_montage_outputs = [str(generated), str(outside)]
            settings.montage_task_statuses = {
                "1": {"title": "Тема", "outputPath": str(generated), "voicePath": str(source)}
            }
            bridge._remove_montage_output(settings, 1)
            self.assertFalse(generated.exists())
            self.assertTrue(source.exists())
            self.assertTrue(outside.exists())
            self.assertNotIn(str(generated), settings.pipeline_montage_outputs)
            self.assertIn(str(outside), settings.pipeline_montage_outputs)

    def test_remove_all_montage_results_deletes_only_generated_mp4_and_cannot_resurrect_them(self):
        """The bulk MP4 action clears current render rows, never the audio or source footage."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "MP4"
            output.mkdir()
            first = output / "Первый.mp4"
            second = output / "Второй.mp4"
            first.write_bytes(b"first-render")
            second.write_bytes(b"second-render")
            voice = root / "voice.mp3"
            footage = root / "source.mp4"
            outside = root / "outside.mp4"
            voice.write_bytes(b"voice")
            footage.write_bytes(b"footage")
            outside.write_bytes(b"outside")
            settings = Settings(montage_output_folder=str(output))
            settings.pipeline_montage_outputs = [str(first), str(second), str(outside)]
            settings.montage_task_statuses = {
                "1": {"title": "Первый", "status": "Готово", "outputPath": str(first), "voicePath": str(voice), "sourcePath": str(footage)},
                "2": {"title": "Второй", "status": "Готово", "outputPath": str(second), "voicePath": str(voice), "sourcePath": str(footage)},
            }

            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge.save_settings"), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.remove_montage_results({"all": True})

            self.assertEqual(result["operationResult"]["count"], 2)
            self.assertFalse(first.exists())
            self.assertFalse(second.exists())
            self.assertTrue(voice.exists())
            self.assertTrue(footage.exists())
            self.assertTrue(outside.exists())
            self.assertEqual(settings.pipeline_montage_outputs, [str(outside)])
            self.assertTrue(all(item["status"] == "Удалено" and not item["outputPath"]
                                for item in settings.montage_task_statuses.values()))

            bridge._reconcile_montage_outputs(settings)
            self.assertTrue(all(item["status"] == "Удалено"
                                for item in settings.montage_task_statuses.values()))

    def test_remove_project_keeps_rendered_mp4_and_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            projects = root / "projects"
            output = root / "MP4"
            projects.mkdir(); output.mkdir()
            project = projects / "Тема.newsflow"
            project.write_text("{}", encoding="utf-8")
            remotion = output / "Тема.remotion.json"
            remotion.write_text("{}", encoding="utf-8")
            video = output / "Тема.mp4"
            video.write_bytes(b"video")
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")
            settings = Settings(montage_project_folder=str(projects), montage_output_folder=str(output))
            with patch("scriptor.bridge.load_settings", return_value=settings), \
                    patch("scriptor.bridge.snapshot", return_value={}):
                result = bridge.remove_montage_projects({"paths": [str(project)]})
            self.assertEqual(result["operationResult"]["count"], 1)
            self.assertFalse(project.exists())
            self.assertFalse(remotion.exists())
            self.assertTrue(video.exists())
            self.assertTrue(voice.exists())


if __name__ == "__main__":
    unittest.main()
