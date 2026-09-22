from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings
from scriptor.core import ScenarioRequest
from scriptor.runner import Job, RunState
from scriptor.timeline import TimelineClip, TimelineProject
from scriptor.voice_map import (
    VOICE_MAP_SCHEMA_VERSION,
    AlignmentResult,
    FfmpegWhisperAlignmentEngine,
    TimedObservation,
    VoiceMapContext,
    ensure_voice_map,
    inspect_voice_map,
    remove_voice_map,
    voice_map_path,
)

SCRIPT = (
    "После удара спасатели прибыли на место. "
    "Несколько зданий получили повреждения. "
    "Позже власти провели экстренное совещание."
)


def word_observations(script: str, step: float = 0.62) -> list[TimedObservation]:
    words = script.split()
    return [
        TimedObservation(
            text=word,
            start=round(index * step, 3),
            end=round((index + 1) * step, 3),
            confidence=0.98,
            kind="word",
        )
        for index, word in enumerate(words)
    ]


class FakeAlignmentEngine:
    name = "deterministic-test-alignment-v1"

    def __init__(self, observations: list[TimedObservation], confidence: float = 0.96):
        self.observations = observations
        self.confidence = confidence
        self.calls = 0

    def availability(self) -> tuple[bool, str]:
        return True, ""

    def align(self, _context: VoiceMapContext) -> AlignmentResult:
        self.calls += 1
        return AlignmentResult(
            engine=self.name,
            observations=self.observations,
            confidence=self.confidence,
        )


class UnavailableEngine:
    name = "missing-local-model"

    def availability(self) -> tuple[bool, str]:
        return False, "Alignment model not configured"

    def align(self, _context: VoiceMapContext) -> AlignmentResult:
        raise AssertionError("unavailable engine must not run")


class VoiceMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.audio = self.root / "voice.mp3"
        self.audio.write_bytes(b"synthetic-audio-version-one")
        self.duration = len(SCRIPT.split()) * 0.62

    def tearDown(self):
        self.temp.cleanup()

    def context(self, **changes) -> VoiceMapContext:
        context = VoiceMapContext(
            production_item_id="production:alpha",
            scenario_index=0,
            title="Одна новость",
            script=SCRIPT,
            audio_path=self.audio,
            audio_duration=self.duration,
            storage_root=self.root / "voice-maps",
        )
        return replace(context, **changes)

    def test_known_canonical_scenario_and_word_timestamps_create_ordered_segments(self):
        status = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        self.assertEqual(status.state, "ready")
        self.assertEqual(status.data["timingMode"], "aligned")
        self.assertEqual(status.data["alignmentEngine"], "deterministic-test-alignment-v1")
        segments = status.data["segments"]
        self.assertGreaterEqual(len(segments), 2)
        self.assertEqual(" ".join(item["text"] for item in segments), SCRIPT)
        self.assertEqual([item["id"] for item in segments], list(range(1, len(segments) + 1)))

    def test_boundaries_follow_canonical_phrases_instead_of_blind_six_second_windows(self):
        status = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        ends = [item["end"] for item in status.data["segments"][:-1]]
        self.assertTrue(ends)
        self.assertNotIn(6.0, ends)
        self.assertTrue(status.data["segments"][0]["text"].endswith("место."))

    def test_segments_are_positive_monotonic_bounded_and_reach_audio_end(self):
        status = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        cursor = 0.0
        for segment in status.data["segments"]:
            self.assertGreater(segment["duration"], 0.0)
            self.assertGreaterEqual(segment["start"], cursor)
            self.assertGreater(segment["end"], segment["start"])
            self.assertLessEqual(segment["duration"], 6.8)
            cursor = segment["end"]
        self.assertAlmostEqual(cursor, self.duration, delta=0.05)

    def test_word_alignment_does_not_leave_an_avoidable_short_final_segment(self):
        script = (
            "Танкеры проходят через Ормузский пролив утром. "
            "Нефтяные терминалы готовят грузы для международных рынков. "
            "Портовые службы контролируют движение судов и безопасность."
        )
        duration = len(script.split()) * 0.75
        context = self.context(script=script, audio_duration=duration)

        status = ensure_voice_map(
            context,
            engine=FakeAlignmentEngine(word_observations(script, step=0.75)),
        )

        self.assertGreaterEqual(status.data["segments"][-1]["duration"], 2.8)
        self.assertTrue(status.data["segments"][-1]["text"].endswith("безопасность."))

    def test_aligned_map_keeps_optional_real_word_evidence(self):
        status = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        words = status.data["alignment"]["words"]
        self.assertEqual(len(words), len(SCRIPT.split()))
        self.assertEqual(words[0]["text"], "После")
        self.assertEqual(words[-1]["end"], self.duration)

    def test_same_hashes_and_schema_reuse_map_without_rerunning_engine(self):
        engine = FakeAlignmentEngine(word_observations(SCRIPT))
        first = ensure_voice_map(self.context(), engine=engine)
        second = ensure_voice_map(self.context(), engine=engine)

        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(engine.calls, 1)

    def test_script_hash_mismatch_is_stale(self):
        ensure_voice_map(self.context(), engine=FakeAlignmentEngine(word_observations(SCRIPT)))

        status = inspect_voice_map(self.context(script=SCRIPT + " Новая фраза."))

        self.assertEqual(status.state, "stale")
        self.assertIn("script", status.reason.casefold())

    def test_audio_hash_mismatch_is_stale(self):
        ensure_voice_map(self.context(), engine=FakeAlignmentEngine(word_observations(SCRIPT)))
        self.audio.write_bytes(b"synthetic-audio-version-two")

        status = inspect_voice_map(self.context())

        self.assertEqual(status.state, "stale")
        self.assertIn("audio", status.reason.casefold())

    def test_unsupported_schema_requires_rebuild(self):
        created = ensure_voice_map(self.context(), engine=FakeAlignmentEngine(word_observations(SCRIPT)))
        payload = dict(created.data)
        payload["schemaVersion"] = VOICE_MAP_SCHEMA_VERSION + 1
        Path(created.path).write_text(json.dumps(payload), encoding="utf-8")

        status = inspect_voice_map(self.context())

        self.assertEqual(status.state, "stale")
        self.assertIn("schema", status.reason.casefold())

    def test_new_production_item_with_same_title_uses_another_artifact(self):
        first = ensure_voice_map(self.context(), engine=FakeAlignmentEngine(word_observations(SCRIPT)))
        other_context = self.context(production_item_id="production:beta")
        second = ensure_voice_map(other_context, engine=FakeAlignmentEngine(word_observations(SCRIPT)))

        self.assertNotEqual(first.path, second.path)
        self.assertEqual(second.data["productionItemId"], "production:beta")

    def test_interrupted_atomic_write_never_leaves_valid_looking_final_json(self):
        context = self.context()
        target = voice_map_path(context)
        with (
            patch("scriptor.voice_map.os.replace", side_effect=OSError("simulated crash")),
            self.assertRaises(OSError),
        ):
            ensure_voice_map(context, engine=FakeAlignmentEngine(word_observations(SCRIPT)))

        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_corrupt_json_is_recoverable_and_does_not_crash(self):
        path = voice_map_path(self.context())
        path.parent.mkdir(parents=True)
        path.write_text('{"schemaVersion":', encoding="utf-8")

        status = inspect_voice_map(self.context())

        self.assertEqual(status.state, "error")
        self.assertIn("json", status.reason.casefold())

    def test_segment_gap_is_rejected_as_corrupt_timing(self):
        created = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )
        payload = created.data
        payload["segments"][1]["start"] += 0.2
        payload["segments"][1]["duration"] = round(
            payload["segments"][1]["end"] - payload["segments"][1]["start"],
            3,
        )
        Path(created.path).write_text(json.dumps(payload), encoding="utf-8")

        status = inspect_voice_map(self.context())

        self.assertEqual(status.state, "error")
        self.assertIn("contiguous", status.reason.casefold())

    def test_overlapping_word_evidence_is_rejected_as_corrupt_timing(self):
        created = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )
        payload = created.data
        payload["alignment"]["words"][1]["start"] = 0.1
        Path(created.path).write_text(json.dumps(payload), encoding="utf-8")

        status = inspect_voice_map(self.context())

        self.assertEqual(status.state, "error")
        self.assertIn("word evidence", status.reason.casefold())

    def test_missing_engine_creates_explicit_approximate_map(self):
        status = ensure_voice_map(self.context(), engine=UnavailableEngine())

        self.assertEqual(status.state, "approximate")
        self.assertEqual(status.data["timingMode"], "approximate")
        self.assertEqual(status.data["alignmentEngine"], "newsflow-fallback")
        self.assertIn("Alignment model not configured", status.data["alignmentUnavailableReason"])
        self.assertNotIn("alignment", status.data)

    def test_alignment_unavailable_does_not_modify_script_or_audio(self):
        before_audio = self.audio.read_bytes()
        before_script = SCRIPT

        ensure_voice_map(self.context(), engine=UnavailableEngine())

        self.assertEqual(self.audio.read_bytes(), before_audio)
        self.assertEqual(self.context().script, before_script)

    def test_remove_voice_map_deletes_only_matching_identity(self):
        first = ensure_voice_map(self.context(), engine=FakeAlignmentEngine(word_observations(SCRIPT)))
        other = ensure_voice_map(
            self.context(production_item_id="production:beta"),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        self.assertTrue(remove_voice_map(self.context()))

        self.assertFalse(Path(first.path).exists())
        self.assertTrue(Path(other.path).exists())

    def test_stale_worker_cannot_publish_after_identity_is_tombstoned(self):
        context = self.context()
        current = {"value": context}

        class TombstoningEngine(FakeAlignmentEngine):
            def align(self, incoming: VoiceMapContext) -> AlignmentResult:
                result = super().align(incoming)
                current["value"] = None
                return result

        with self.assertRaisesRegex(RuntimeError, "deleted|stale"):
            ensure_voice_map(
                context,
                engine=TombstoningEngine(word_observations(SCRIPT)),
                current_context=lambda: current["value"],
            )

        self.assertFalse(voice_map_path(context).exists())

    def test_low_canonical_reconciliation_coverage_falls_back_without_fake_alignment(self):
        unrelated = [
            TimedObservation(word, index * 0.8, (index + 1) * 0.8, 0.9, "word")
            for index, word in enumerate(["совершенно", "посторонний", "текст"])
        ]

        status = ensure_voice_map(self.context(), engine=FakeAlignmentEngine(unrelated))

        self.assertEqual(status.state, "approximate")
        self.assertEqual(status.data["timingMode"], "approximate")
        self.assertIn("canonical", status.data["alignmentUnavailableReason"].casefold())

    def test_segment_timing_can_align_canonical_phrases_without_fake_word_evidence(self):
        observations = [
            TimedObservation("После удара спасатели прибыли на место.", 0.2, 3.72, 0.93, "segment"),
            TimedObservation("Несколько зданий получили повреждения.", 3.9, 6.2, 0.91, "segment"),
            TimedObservation("Позже власти провели экстренное совещание.", 6.4, self.duration, 0.94, "segment"),
        ]

        status = ensure_voice_map(self.context(), engine=FakeAlignmentEngine(observations))

        self.assertEqual(status.state, "ready")
        self.assertEqual(status.data["timingMode"], "aligned")
        self.assertNotIn("alignment", status.data)
        self.assertEqual(" ".join(item["text"] for item in status.data["segments"]), SCRIPT)

    def test_ffmpeg_adapter_requires_explicit_existing_model_without_network_activity(self):
        engine = FfmpegWhisperAlignmentEngine(model_path=self.root / "missing.bin")

        with patch("scriptor.voice_map.subprocess.run") as run:
            available, reason = engine.availability()

        self.assertFalse(available)
        self.assertEqual(reason, "Alignment model not configured")
        run.assert_not_called()

    def test_ffmpeg_adapter_requires_confirmed_whisper_filter(self):
        model = self.root / "model.bin"
        model.write_bytes(b"local-model-placeholder")
        engine = FfmpegWhisperAlignmentEngine(model_path=model)

        with patch("scriptor.voice_map.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = " .. silencedetect A->A"
            available, reason = engine.availability()

        self.assertFalse(available)
        self.assertIn("filter", reason.casefold())

    def test_ffmpeg_adapter_uses_packaged_runtime_executable_by_default(self):
        model = self.root / "model.bin"
        model.write_bytes(b"local-model-placeholder")
        engine = FfmpegWhisperAlignmentEngine(model_path=model)

        with (
            patch(
                "scriptor.voice_map.ffmpeg_executable",
                return_value="C:\\NewsFlow\\assets\\ffmpeg.exe",
            ),
            patch("scriptor.voice_map.subprocess.run") as run,
        ):
            run.return_value.returncode = 0
            run.return_value.stdout = " ... whisper A->A"
            available, reason = engine.availability()

        self.assertTrue(available, reason)
        self.assertEqual(run.call_args.args[0][0], "C:\\NewsFlow\\assets\\ffmpeg.exe")

    def test_ffmpeg_json_offsets_are_real_milliseconds_and_keep_segment_kind(self):
        observations = FfmpegWhisperAlignmentEngine._extract_observations({
            "transcription": [{
                "offsets": {"from": 420, "to": 3720},
                "text": "После удара спасатели прибыли на место.",
                "confidence": 0.93,
            }],
        })

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].start, 0.42)
        self.assertEqual(observations[0].end, 3.72)
        self.assertEqual(observations[0].kind, "segment")

    def test_bridge_builds_map_for_finished_scenario_and_projects_operator_state(self):
        settings = Settings(
            voice_scenario_outputs={"1": str(self.audio)},
            voice_task_statuses={"1": {"durationSeconds": self.duration}},
        )
        job = Job(
            ScenarioRequest(0, "Одна новость", "", "production:alpha"),
            RunState.DONE,
            SCRIPT,
            "",
        )
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=(["Одна новость"], [job])),
            patch.object(bridge, "save_settings") as save,
            patch.object(bridge, "app_data_root", return_value=self.root),
        ):
            status = bridge._ensure_voice_map_for_scenario(
                0,
                settings=settings,
                engine=UnavailableEngine(),
            )

        self.assertEqual(status.state, "approximate")
        self.assertEqual(settings.voice_task_statuses["1"]["voiceMapState"], "approximate")
        self.assertEqual(settings.voice_task_statuses["1"]["voiceMapLabel"], "Приблизительный тайминг")
        save.assert_called()

    def test_rebuild_command_uses_current_identity_without_starting_montage(self):
        settings = Settings(voice_scenario_outputs={"1": str(self.audio)})
        job = Job(
            ScenarioRequest(0, "Одна новость", "", "production:alpha"),
            RunState.DONE,
            SCRIPT,
            "",
        )
        rebuilt = type("Status", (), {
            "state": "ready", "label": "Тайминг готов", "path": "map.json",
            "reason": "", "data": {}, "reused": False,
        })()
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=(["Одна новость"], [job])),
            patch.object(bridge, "_ensure_voice_map_for_scenario", return_value=rebuilt) as ensure,
            patch.object(bridge, "prepare_montage") as prepare,
            patch.object(bridge, "snapshot", return_value={"voiceItems": []}),
        ):
            result = bridge.rebuild_voice_map({
                "scenarioIndex": 0,
                "productionItemId": "production:alpha",
            })

        ensure.assert_called_once_with(0, settings=settings, force=True)
        prepare.assert_not_called()
        self.assertEqual(result["operationResult"]["kind"], "voice-map-rebuild")

    def test_scenario_delete_persists_tombstone_before_voice_map_cleanup(self):
        settings = Settings(voice_scenario_outputs={"1": str(self.audio)})
        job = Job(
            ScenarioRequest(0, "Одна новость", "", "production:alpha"),
            RunState.DONE,
            SCRIPT,
            "",
        )
        events: list[str] = []
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=(["Одна новость"], [job])),
            patch.object(bridge, "save_settings", side_effect=lambda _value: events.append("tombstone")),
            patch.object(bridge, "save_session"),
            patch.object(bridge, "snapshot", return_value={}),
            patch.object(bridge, "remove_voice_map", side_effect=lambda _context: events.append("cleanup")),
        ):
            bridge.remove_scenarios_command({"indices": [0]})

        self.assertEqual(events, ["tombstone", "cleanup"])
        self.assertIn("production:alpha", settings.deleted_scenario_production_ids)

    def test_voice_map_segments_and_provenance_survive_newsflow_round_trip(self):
        status = ensure_voice_map(
            self.context(),
            engine=FakeAlignmentEngine(word_observations(SCRIPT)),
        )

        scenes, provenance = bridge._voice_map_scenes(status)
        project = TimelineProject(
            title="Одна новость",
            voiceover_path=str(self.audio),
            clips=[
                TimelineClip(
                    path=f"clip-{index}.mp4",
                    narration=scene["narration"],
                    visual_query_en=scene["visual_query_en"],
                    duration=scene["duration"],
                    voice_segment_id=scene["voice_segment_id"],
                    voice_segment_ids=scene["voice_segment_ids"],
                    narration_start=scene["narration_start"],
                    narration_end=scene["narration_end"],
                    minimum_source_duration=scene["minimum_footage_duration"],
                    visual_beat_index=scene["visual_beat_index"],
                    visual_beat_count=scene["visual_beat_count"],
                )
                for index, scene in enumerate(scenes)
            ],
            voice_map_provenance=provenance,
        )
        path = self.root / "project.newsflow"
        project.save(path)
        restored = TimelineProject.load(path)

        self.assertEqual(
            [clip.voice_segment_id for clip in restored.clips],
            [scene["voice_segment_id"] for scene in scenes],
        )
        self.assertEqual(
            [clip.visual_beat_index for clip in restored.clips],
            list(range(1, len(scenes) + 1)),
        )
        self.assertEqual(
            [clip.voice_segment_ids for clip in restored.clips],
            [scene["voice_segment_ids"] for scene in scenes],
        )
        self.assertEqual(restored.voice_map_provenance["alignmentMode"], "aligned")
        self.assertEqual(restored.voice_map_provenance["voiceMapSchemaVersion"], VOICE_MAP_SCHEMA_VERSION)
        self.assertEqual(restored.voice_map_provenance["scriptSha256"], status.data["scriptSha256"])
        self.assertAlmostEqual(sum(clip.duration for clip in restored.clips), self.duration, places=6)

    def test_voice_map_visual_beats_follow_six_second_cutter_grid_and_trim_only_tail(self):
        payload = {
            "schemaVersion": VOICE_MAP_SCHEMA_VERSION,
            "productionItemId": "production:alpha",
            "scriptSha256": "script-hash",
            "audioSha256": "audio-hash",
            "audioDuration": 14.4,
            "timingMode": "approximate",
            "alignmentEngine": "newsflow-fallback",
            "alignmentConfidence": 0.0,
            "segments": [
                {
                    "id": 1, "start": 0.0, "end": 2.0, "duration": 2.0,
                    "text": "Вашингтон меняет правила.", "visualQuery": "Washington White House US government",
                },
                {
                    "id": 2, "start": 2.0, "end": 7.0, "duration": 5.0,
                    "text": "Киев обсуждает новые условия поддержки.", "visualQuery": "Kyiv Ukraine government",
                },
                {
                    "id": 3, "start": 7.0, "end": 14.4, "duration": 7.4,
                    "text": "Европа оценивает последствия санкций для экономики.",
                    "visualQuery": "Europe Brussels economic sanctions",
                },
            ],
        }
        status = type("Status", (), {
            "state": "approximate", "path": str(self.root / "map.json"),
            "reason": "Alignment model not configured", "data": payload,
        })()

        scenes, _provenance = bridge._voice_map_scenes(status)

        self.assertEqual([round(scene["duration"], 3) for scene in scenes], [6.0, 6.0, 2.4])
        self.assertEqual([scene["narration_start"] for scene in scenes], [0.0, 6.0, 12.0])
        self.assertEqual([round(scene["narration_end"], 3) for scene in scenes], [6.0, 12.0, 14.4])
        self.assertEqual(
            [round(scene["minimum_footage_duration"], 3) for scene in scenes],
            [6.0, 6.0, 2.4],
        )
        self.assertEqual([scene["visual_beat_index"] for scene in scenes], [1, 2, 3])
        self.assertEqual({scene["visual_beat_count"] for scene in scenes}, {3})
        # Beat 1 overlaps segment 1 for 2s and segment 2 for 4s, so the
        # visual search must stay focused on Kyiv instead of concatenating
        # multiple entity queries into a broad ambiguous request.
        self.assertIn("Kyiv", scenes[0]["visual_query_en"])
        self.assertNotIn("Washington", scenes[0]["visual_query_en"])
        self.assertEqual(scenes[0]["voice_segment_ids"], [1, 2])
        self.assertEqual(scenes[0]["voice_segment_id"], 2)
        self.assertIn("Europe", scenes[1]["visual_query_en"])
        self.assertEqual(scenes[1]["voice_segment_ids"], [2, 3])
        for previous, current in pairwise(scenes):
            self.assertAlmostEqual(previous["narration_end"], current["narration_start"], places=6)
        self.assertAlmostEqual(sum(scene["duration"] for scene in scenes), 14.4, places=6)

    def test_6398_audio_uses_full_cutter_then_trimmed_terminal_footage(self):
        payload = {
            "schemaVersion": VOICE_MAP_SCHEMA_VERSION,
            "productionItemId": "production:alpha",
            "scriptSha256": "script-hash",
            "audioSha256": "audio-hash",
            "audioDuration": 6.398,
            "timingMode": "approximate",
            "alignmentEngine": "newsflow-fallback",
            "alignmentConfidence": 0.0,
            "segments": [{
                "id": 29,
                "start": 0.0,
                "end": 6.398,
                "duration": 6.398,
                "text": "После удара спасатели прибыли на место и начали разбирать завалы.",
                "visualQuery": "rescue emergency aftermath",
            }],
        }
        status = type("Status", (), {
            "state": "approximate", "path": str(self.root / "map.json"),
            "reason": "Alignment model not configured", "data": payload,
        })()

        scenes, _provenance = bridge._voice_map_scenes(status)

        self.assertEqual(len(scenes), 2)
        self.assertAlmostEqual(scenes[0]["duration"], 6.0, places=6)
        self.assertAlmostEqual(scenes[1]["duration"], 0.398, places=6)
        self.assertAlmostEqual(scenes[0]["minimum_footage_duration"], 6.0, places=6)
        self.assertAlmostEqual(scenes[1]["minimum_footage_duration"], 0.398, places=6)
        self.assertEqual([scene["voice_segment_id"] for scene in scenes], [29, 29])
        self.assertEqual([scene["voice_segment_ids"] for scene in scenes], [[29], [29]])
        self.assertEqual(scenes[0]["narration_start"], 0.0)
        self.assertAlmostEqual(scenes[-1]["narration_end"], 6.398, places=6)
        self.assertNotEqual([round(scene["duration"], 3) for scene in scenes], [3.199, 3.199])

    def test_prepare_montage_uses_voice_map_timing_instead_of_proportional_fitter(self):
        footage = self.root / "footage"
        footage.mkdir()
        source = footage / "rescue emergency aftermath.mp4"
        source.write_bytes(b"video")
        projects = self.root / "projects"
        settings = Settings(
            footage_folders=[str(footage)],
            montage_project_folder=str(projects),
            montage_output_folder=str(self.root / "output"),
            montage_auto_web=False,
            montage_export_davinci_xml=False,
            voice_scenario_outputs={"1": str(self.audio)},
        )
        job = Job(
            ScenarioRequest(0, "Спасательная операция", "", "production:alpha"),
            RunState.DONE,
            "После удара спасатели прибыли на место.",
            "",
        )
        payload = {
            "schemaVersion": VOICE_MAP_SCHEMA_VERSION,
            "productionItemId": "production:alpha",
            "scenarioIndex": 0,
            "title": "Спасательная операция",
            "audioPath": str(self.audio),
            "audioDuration": 6.0,
            "scriptSha256": "script-hash",
            "audioSha256": "audio-hash",
            "timingMode": "aligned",
            "alignmentEngine": "deterministic-test-alignment-v1",
            "alignmentConfidence": 0.97,
            "segments": [{
                "id": 7,
                "start": 0.0,
                "end": 6.0,
                "duration": 6.0,
                "text": job.result,
                "visualQuery": "rescue emergency aftermath",
            }],
        }
        status = type("Status", (), {
            "state": "ready", "label": "Тайминг готов", "path": str(self.root / "map.json"),
            "reason": "", "data": payload, "reused": True,
        })()
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=([job.request.title], [job])),
            patch.object(bridge, "save_settings"),
            patch.object(bridge, "snapshot", return_value={}),
            patch.object(bridge, "app_data_root", return_value=self.root),
            patch.object(bridge, "_ensure_voice_map_for_scenario", return_value=status),
            patch.object(bridge, "fit_scene_plan_to_voice_duration", side_effect=AssertionError("legacy fitter must not run")),
            patch.object(bridge, "_montage_screen_text_safe", return_value=True),
            patch.object(bridge.ClipIndex, "count", return_value=0),
            patch.object(bridge, "probe_media_duration", return_value=6.0),
            patch.object(bridge, "probe_video_duration", return_value=8.0),
        ):
            result = bridge.prepare_montage({"scenarioIndex": 0})

        project = TimelineProject.load(Path(result["preparedProject"]["path"]))
        self.assertEqual(project.voice_map_provenance["alignmentMode"], "aligned")
        self.assertEqual(project.clips[0].voice_segment_id, 7)
        self.assertEqual(project.clips[0].narration_start, 0.0)
        self.assertEqual(project.clips[0].narration_end, 6.0)

    def test_prepare_montage_does_not_bypass_invalid_map_for_current_identity(self):
        settings = Settings(
            footage_folders=[str(self.root / "footage")],
            montage_auto_web=False,
            voice_scenario_outputs={"1": str(self.audio)},
        )
        job = Job(
            ScenarioRequest(0, "Спасательная операция", "", "production:alpha"),
            RunState.DONE,
            SCRIPT,
            "",
        )
        failed = type("Status", (), {
            "state": "error", "label": "Ошибка тайминга", "path": "map.json",
            "reason": "VoiceMap segments are not contiguous", "data": {}, "reused": False,
        })()
        with (
            patch.object(bridge, "load_settings", return_value=settings),
            patch.object(bridge, "load_session", return_value=([job.request.title], [job])),
            patch.object(bridge, "app_data_root", return_value=self.root),
            patch.object(bridge, "_ensure_voice_map_for_scenario", return_value=failed),
            patch.object(bridge, "fit_scene_plan_to_voice_duration") as legacy_fitter,
            patch.object(bridge.ClipIndex, "count", return_value=1),
            patch.object(bridge, "probe_media_duration", return_value=self.duration),
            self.assertRaisesRegex(ValueError, "not contiguous"),
        ):
            bridge.prepare_montage({"scenarioIndex": 0})

        legacy_fitter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
