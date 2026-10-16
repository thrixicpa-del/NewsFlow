"""Disposable visual admission and selector contract checks for PR403."""

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import ClipIndex, SearchHit
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineProject


class ColdFairnessSelectorTests(unittest.TestCase):
    def test_completion_probes_lazily_and_stops_after_the_first_funded_winner(self):
        class Admission:
            _visual_cold_windows = 0
            def visual_cold_credit_available(self, **_):
                return self._visual_cold_windows < 1
            @contextmanager
            def visual_cold_window_grant(self, *_, **__):
                self._visual_cold_windows += 1
                yield
        index, probes = Admission(), []
        items = [FootageItem(f'D:/synthetic/family-{n:04d}/clip.mp4', 'cargo port') for n in range(100)]
        for item in items:
            item._visual_assessor = lambda *_, **__: {'relation': 'direct'}
        def complete():
            if index._visual_cold_windows:
                return 'winner'
            raise bridge.MontageSelectionFailure({})
        result = bridge._recover_montage_visual_alternatives(
            index, 'cargo port', {'STRICT_MATCH': [SearchHit(item, .9, 30.) for item in items]},
            required_duration=6., assessment_duration=6.398,
            source_exists=lambda _: True, source_allowed=lambda _: True,
            source_duration=lambda item: probes.append(item.path) or 30., can_complete=complete)
        self.assertEqual('winner', result)
        self.assertEqual([items[0].path], probes)

    def test_work_order_round_robins_families_without_truncating_paths(self):
        first = [SearchHit(FootageItem(f'D:/synthetic/a/{n}.mp4', 'cargo port'), .99 - n * .01,
                           30., source_family='a') for n in range(20)]
        other = SearchHit(FootageItem('D:/synthetic/b/one.mp4', 'cargo port'), .5, 30., source_family='b')
        order = bridge._montage_visual_work_order('cargo port', {'STRICT_MATCH': [*first, other]}, 6.)
        self.assertEqual([first[0].item.path, other.item.path, first[1].item.path],
                         [hit.item.path for hit, _ in order[:3]])
        self.assertEqual({hit.item.path for hit in [*first, other]}, {hit.item.path for hit, _ in order})

    def test_existing_ci_voice_map_suite_collects_all_cold_regressions_once(self):
        def cases(suite):
            for value in suite:
                if isinstance(value, unittest.TestSuite):
                    yield from cases(value)
                else:
                    yield value.id()
        identities = list(cases(unittest.TestLoader().loadTestsFromName('tests.test_voice_map')))
        for name in ('tests.test_visual_cold_budget', 'tests.test_montage_cold_fairness'):
            expected = list(cases(unittest.TestLoader().loadTestsFromName(name)))
            self.assertTrue(expected)
            for identity in expected:
                self.assertEqual(1, identities.count(identity), identity)

    def test_selector_assesses_actual_interval_without_relabeling_minimum(self):
        item = FootageItem("D:/synthetic/port.mp4", "oil tanker port", tags=["oil-tanker-port"])
        asked = []

        def assess(_query, start, duration, **_kwargs):
            asked.append((start, duration))
            return {"relation": "direct" if duration == 6.398 else "unknown",
                    "source_start": start, "duration": duration}

        item._visual_assessor = assess
        selection = bridge._select_montage_candidate(
            "oil tanker port", strict_hits=[SearchHit(item, .9, 30.0)],
            fallback_hits=[], relaxed_hits=[], category_hits=[], safe_context_hits=[],
            required_duration=6.0, assessment_duration=6.398, match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(),
            project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _item: True, source_duration=lambda _item: 30.0,
        )
        self.assertEqual(item.path, selection.item.path)
        self.assertEqual({6.398}, {duration for _start, duration in asked})

    def test_fixed_fast_origin_cannot_be_replaced_by_a_better_other_window(self):
        item = FootageItem("D:/synthetic/port.mp4", "oil tanker port", tags=["oil-tanker-port"])

        def assess(_query, start, duration, **kwargs):
            if kwargs.get("allow_alternatives"):
                return {"relation": "direct", "source_start": 16.0, "duration": duration}
            return {"relation": "context" if start == 8.0 else "direct",
                    "source_start": start, "duration": duration}

        item._visual_assessor = assess
        origin = bridge._montage_clip_key(item.path)
        selection = bridge._select_montage_candidate(
            "oil tanker port", strict_hits=[SearchHit(item, .9, 30.0)],
            fallback_hits=[], relaxed_hits=[], category_hits=[], safe_context_hits=[],
            required_duration=6.0, assessment_duration=6.398, match_threshold=.22,
            used_paths=set(), used_families=set(), project_used_paths=set(),
            project_used_families=set(), reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _item: True, source_duration=lambda _item: 30.0,
            fixed_source_starts={origin: 8.0},
        )
        self.assertEqual(8.0, selection.source_start)

    def test_ordinary_funding_reaches_late_named_target_before_unknown_families(self):
        class FakeAdmission:
            def __init__(self):
                self.remaining = 2
                self.funded = []

            def visual_cold_credit_available(self, *, emergency=False):
                return self.remaining > 0 and not emergency

            @contextmanager
            def visual_cold_window_grant(self, path, start, duration, *, emergency=False):
                self.remaining -= 1
                self.funded.append((str(path), start, duration))
                yield

        query = "Vladimir Putin comments at a press conference"
        filler = [FootageItem(f"D:/synthetic/family-{n}/clip.mp4", "press conference")
                  for n in range(100)]
        target = FootageItem("D:/synthetic/putin/clip.mp4", "Vladimir Putin press conference")
        index = FakeAdmission()
        for item in [*filler, target]:
            item._visual_assessor = lambda _query, start, duration, **_kwargs: {
                "relation": "direct", "source_start": start, "duration": duration}
        hits = {"STRICT_MATCH": [*[SearchHit(item, .9, 30.0) for item in filler],
                                 SearchHit(target, .8, 30.0)],
                "RELAXED_SEMANTIC": [], "CATEGORY_MATCH": [], "SAFE_CONTEXT": []}
        bridge._prefetch_montage_visual_windows(
            index, query, hits, required_duration=6.0, assessment_duration=6.398,
            source_exists=lambda _item: True, source_allowed=lambda _item: True,
        )
        self.assertEqual(target.path, index.funded[0][0])
        self.assertEqual([6.398, 6.398], [entry[2] for entry in index.funded])

    def test_two_failed_primaries_can_recover_only_cold_alternative(self):
        class FakeAdmission:
            def __init__(self):
                self.charged = 0
                self.active = None
                self.funded = set()

            def visual_cold_credit_available(self, *, emergency=False):
                return self.charged < (5 if emergency else 2)

            @contextmanager
            def visual_cold_window_grant(self, path, start, duration, *, emergency=False):
                self.active = (str(path), start, duration)
                yield
                self.active = None

            def assess(self, path, start, duration, **kwargs):
                key = path, start, duration
                if key not in self.funded and self.active == key:
                    self.funded.add(key)
                    self.charged += 1
                relation = "direct" if key in self.funded and path.endswith("a.mp4") and start == 12.0 else "unknown"
                result = {"relation": relation, "source_start": start, "duration": duration,
                          "reason": "scene-cold-credit-deferred" if key not in self.funded else "incompatible"}
                if kwargs.get("allow_alternatives") and relation != "direct":
                    for alternative in (0.0, 12.0):
                        if alternative != start:
                            proposed = self.assess(path, alternative, duration)
                            if proposed["relation"] == "direct":
                                return proposed
                return result

        index = FakeAdmission()
        a = FootageItem("D:/synthetic/family-a/a.mp4", "oil tanker port", tags=["oil-tanker-port"])
        b = FootageItem("D:/synthetic/family-b/b.mp4", "oil tanker port", tags=["oil-tanker-port"])
        for item in (a, b):
            item._visual_assessor = (lambda _query, start, duration, path=item.path, **kwargs:
                                     index.assess(path, start, duration, **kwargs))
        hits = {"STRICT_MATCH": [SearchHit(a, .9, 30.0), SearchHit(b, .8, 30.0)],
                "RELAXED_SEMANTIC": [], "CATEGORY_MATCH": [], "SAFE_CONTEXT": []}
        bridge._prefetch_montage_visual_windows(
            index, "oil tanker port", hits, required_duration=6.0,
            assessment_duration=6.398, source_exists=lambda _item: True,
            source_allowed=lambda _item: True,
        )
        self.assertEqual(2, index.charged)
        self.assertNotIn((a.path, 12.0, 6.398), index.funded)
        recovered = bridge._recover_montage_visual_alternatives(
            index, "oil tanker port", hits, required_duration=6.0,
            assessment_duration=6.398, source_exists=lambda _item: True,
            source_allowed=lambda _item: True,
            source_duration=lambda _item: 30.398,
            can_complete=lambda: bridge._select_montage_candidate(
                "oil tanker port", strict_hits=hits["STRICT_MATCH"], fallback_hits=[],
                relaxed_hits=[], category_hits=[], safe_context_hits=[],
                required_duration=6.0, assessment_duration=6.398, match_threshold=.22,
                used_paths=set(), used_families=set(), project_used_paths=set(),
                project_used_families=set(), reserved_paths=set(), reserved_families=set(),
                source_exists=lambda _item: True, source_duration=lambda _item: 30.398,
            ),
        )
        self.assertEqual(a.path, recovered.item.path)
        self.assertEqual(3, index.charged)


class ColdFairnessPreparationTests(unittest.TestCase):
    """Actual prepare/save route with fake classifications and no real decoding."""

    def prepare(self, *, context_primary=False, fast=False, fail=False, mixed=False, warm_context=False,
                continuity_only=False, continuity_after_negatives=False, cold_used_continuity=False):
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState
        from tests.test_footage_quality_voice import segment, status_for

        temporary = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        index = ClipIndex(root / 'index.sqlite3')
        index._visual_memory_clear()
        index._loaded_model_revision = index._local_model_revision()
        voice = root / 'voice.wav'
        voice.write_bytes(b'disposable contract voice')
        text, query, actual = 'В порту разгружают суда.', 'seaport cargo cranes ships', 6.398
        if mixed:
            text, query = 'Путин выступил с заявлением.', 'Vladimir Putin official statement government briefing'
        count = 50  # First scene releases two of the existing 96 cold charges.
        cached = {}
        attempts = []

        def assessment(path, start, duration, **kwargs):
            key = path, start, duration
            relation = 'unknown'
            if key not in cached:
                _, reason = index._visual_window_features(Path(path), float(start), float(duration))
                if reason == 'window-assessment-unavailable:ValueError':
                    attempts.append(key)
                    relation = ('context' if context_primary and path.endswith('c.mp4') and start == 0
                                else 'context' if mixed and path.endswith('a.mp4') and start == 12
                                else 'direct' if not context_primary and path.endswith('a.mp4') and start == 12
                                else 'contradiction')
                    cached[key] = relation
            relation = cached.get(key, relation)
            result = {'relation': relation, 'source_start': start, 'duration': duration,
                      'dominant_kind': 'meeting' if mixed else 'port',
                      'source': 'fake-contract-classifier', 'reason': 'fake' if key in cached else reason}
            if kwargs.get('allow_alternatives') and relation != 'direct':
                for alternative in (0., 12., 24.):
                    if alternative != start:
                        proposed = assessment(path, alternative, duration)
                        if proposed['relation'] == 'direct' or (proposed['relation'] == 'context'
                                                                and result['relation'] != 'context'):
                            result = proposed
            return result

        items = []
        for name in ('c',) if continuity_only else (('a', 'b', 'c') if context_primary or continuity_after_negatives else ('a', 'b')):
            path = root / (name + '.mp4')
            path.write_bytes(b'disposable contract footage')
            item = FootageItem(str(path), 'port ships ' + name, tags=['port-logistics'])
            if mixed:
                stat = path.stat()
                item.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                    'observations': [{'person_id': 'pashinyan', 'source': 'curated',
                                      'start': 0., 'end': actual, 'complete': True}]}
            item._visual_assessor = lambda _q, start, duration, path=str(path), **kwargs: assessment(path, start, duration, **kwargs)
            items.append(item)
        if warm_context:
            cached[str(root / 'c.mp4'), 0., actual] = 'context'
        hits = [SearchHit(item, .9 - n * .1, 30.398, source_family='family-' + str(n))
                for n, item in enumerate(items)]
        levels = {level: hits for level in bridge._MONTAGE_FALLBACK_LEVELS}
        if continuity_only or continuity_after_negatives:
            context_primary = True
            levels = {level: hits[:2] if continuity_after_negatives else [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
        settings = Settings(footage_folders=[str(root)], montage_auto_web=False,
                            montage_fast_reuse_enabled=fast, montage_unique_footage_percent=2,
                            montage_export_davinci_xml=False,
                            montage_project_folder=str(root / 'projects'),
                            montage_output_folder=str(root / 'output'), voice_scenario_outputs={'1': str(voice)})
        job = Job(ScenarioRequest(0, text, '', 'cold-admission-contract'), RunState.DONE, text, '')
        status = status_for([segment(text, duration=actual, query=query, identity=i + 1, start=i * actual)
                             for i in range(count)], count * actual)
        # Freeze the planner boundary here: the planner's real 6.398/6.0
        # contract has separate VoiceMap tests. This test exercises admission
        # through the real prepare/save path with 50 identical exact keys.
        scenes = [{'narration': text, 'visual_query_en': query, 'duration': actual,
                   'minimum_footage_duration': 6., 'voice_segment_id': i + 1,
                   'narration_start': i * actual, 'narration_end': (i + 1) * actual}
                  for i in range(count)]
        voice_duration = count * actual
        if cold_used_continuity:
            scenes[-1]['duration'] = actual + .001
            scenes[-1]['narration_end'] += .001
            voice_duration += .001
        with (patch.object(bridge, 'load_settings', return_value=settings),
              patch.object(bridge, 'load_session', return_value=([text], [job])),
              patch.object(bridge, 'save_settings'), patch.object(bridge, 'snapshot', return_value={}),
              patch.object(bridge, 'app_data_root', return_value=root),
              patch.object(bridge, 'ClipIndex', return_value=index),
              patch.object(bridge, '_ensure_voice_map_for_scenario', return_value=status),
              patch.object(bridge, '_voice_map_scenes', return_value=(scenes, {'alignmentMode': 'approximate'})),
              patch.object(index, 'count', return_value=len(items)),
              patch.object(index, 'search_many', return_value=[]),
              patch.object(index, 'continuity_items', return_value=items[-1:] if continuity_only or continuity_after_negatives else []),
              patch.object(index, 'current_continuity_item', side_effect=lambda item, **_: item),
              patch.object(index, '_models', return_value=(object(), object())),
              patch.object(index, '_sample_visual_window', side_effect=ValueError('fake decoder')),
              patch.object(bridge, '_montage_search_ladders', return_value=[levels] * count),
              patch.object(bridge, '_montage_screen_text_safe', return_value=True),
              patch.object(bridge, 'probe_media_duration', return_value=voice_duration),
              patch.object(bridge, 'probe_video_duration', return_value=30.398),
              patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30.398)):
            if fail:
                with (patch.object(bridge, '_prefetch_montage_visual_windows', side_effect=RuntimeError('injected stop')),
                      self.assertRaisesRegex(RuntimeError, 'injected stop')):
                    bridge.prepare_montage({'scenarioIndex': 0})
                self.assertIsNone(index._visual_scene_admission)
                self.assertEqual({}, index._visual_cold_grants)
                return
            try:
                result = bridge.prepare_montage({'scenarioIndex': 0})
            except RuntimeError as error:
                error.add_note(repr([(Path(path).name, start, duration) for path, start, duration in attempts]))
                raise
        project = TimelineProject.load(Path(result['preparedProject']['path']))
        self.assertEqual(count, len(project.clips))
        self.assertIsNone(index._visual_scene_admission)
        self.assertEqual({}, index._visual_cold_grants)
        self.assertLessEqual(index._visual_cold_windows, 96)
        expected_durations = (actual, actual + .001) if cold_used_continuity else (actual,)
        self.assertTrue(all(any(abs(duration - expected) < 1e-9 for expected in expected_durations)
                            for _, _, duration in attempts))
        self.assertEqual(6., project.clips[0].minimum_source_duration)
        return project, attempts

    def test_prepare_recovers_cold_alternative_and_saves_exact_actual_window(self):
        project, _ = self.prepare()
        self.assertEqual(3, project.clips[0].selection_diagnostics['cold_budget']['charged'])
        self.assertEqual(1, project.clips[0].selection_diagnostics['cold_budget']['emergency'])
        self.assertEqual(12., project.clips[0].source_start)
        self.assertTrue(all(clip.path.endswith('a.mp4') and clip.source_start == 12. for clip in project.clips))

    def test_prepare_can_complete_from_unfunded_primary_context(self):
        project, _ = self.prepare(context_primary=True)
        self.assertTrue(all(clip.path.endswith('c.mp4') and clip.source_start == 0. for clip in project.clips))
        self.assertEqual('context', project.clips[0].selection_diagnostics['visual']['relation'])
        self.assertEqual(3, project.clips[0].selection_diagnostics['cold_budget']['charged'])

    def test_cached_context_completes_without_emergency_borrowing(self):
        project, _ = self.prepare(context_primary=True, warm_context=True)
        self.assertTrue(all(clip.path.endswith('c.mp4') for clip in project.clips))
        self.assertEqual(0, project.clips[0].selection_diagnostics['cold_budget']['emergency'])

    def test_contradictory_primary_does_not_erase_later_institution_context(self):
        project, attempts = self.prepare(mixed=True)
        self.assertTrue(all(clip.path.endswith('a.mp4') and clip.source_start == 12. for clip in project.clips))
        self.assertEqual('unknown', project.clips[0].selection_diagnostics['person']['status'])
        self.assertEqual('context', project.clips[0].selection_diagnostics['visual']['relation'])
        self.assertFalse(any(start == 0. for _, start, _ in attempts))

    def test_prepare_fast_reuse_keeps_funded_exact_origin(self):
        project, _ = self.prepare(fast=True)
        self.assertTrue(all(clip.source_start == 12. for clip in project.clips))
        self.assertTrue(all(clip.selection_diagnostics['cold_budget']['charged'] == 0 for clip in project.clips[1:]))

    def test_prepare_exception_closes_admission(self):
        self.prepare(fail=True)

    def test_full_continuity_pool_can_fund_ordinary_work_and_reuse_safe_context(self):
        project, _ = self.prepare(continuity_only=True)
        self.assertTrue(all(clip.fallback_level == 'VISUAL_CONTINUITY_FALLBACK' and clip.source_start == 0.
                            and clip.path.endswith('c.mp4') for clip in project.clips))
        self.assertEqual(1, project.clips[0].selection_diagnostics['cold_budget']['charged'])
        self.assertEqual(0, project.clips[0].selection_diagnostics['cold_budget']['emergency'])

    def test_full_continuity_primary_precedes_failed_retrieval_alternatives(self):
        project, _ = self.prepare(continuity_after_negatives=True)
        self.assertEqual('VISUAL_CONTINUITY_FALLBACK', project.clips[0].fallback_level)
        self.assertEqual(3, project.clips[0].selection_diagnostics['cold_budget']['charged'])
        self.assertEqual(1, project.clips[0].selection_diagnostics['cold_budget']['emergency'])

    def test_used_continuity_can_fund_its_new_exact_actual_duration(self):
        project, attempts = self.prepare(continuity_only=True, cold_used_continuity=True)
        self.assertEqual('VISUAL_CONTINUITY_FALLBACK', project.clips[-1].fallback_level)
        self.assertTrue(project.clips[-1].reused)
        self.assertEqual(1, project.clips[-1].selection_diagnostics['cold_budget']['charged'])
        self.assertEqual([6.398, 6.399], [round(duration, 3) for _, _, duration in attempts])


if __name__ == "__main__":
    unittest.main()
