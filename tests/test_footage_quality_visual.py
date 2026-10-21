"""Visual-assessor contracts, not real model accuracy assertions."""
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject


class WindowVisualQualityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def item(self, name, tags, relation):
        path = self.root / name
        path.write_bytes(b'test-owned-contract-file')
        item = FootageItem(str(path), name, tags=tags)
        def assess(query, start, duration, **kwargs):
            value = relation(start) if callable(relation) else relation
            return {'relation': value, 'source': 'automatic-window-clip',
                    'source_start': start, 'duration': duration,
                    'event_confirmed': False, 'motion_verified': False}
        item._visual_assessor = assess
        return item

    def test_unchecked_explosion_metadata_cannot_replace_statement_or_meeting(self):
        for query, tag in (("official statement journalists cameras", "press-conference"),
                           ("delegations diplomatic meeting", "diplomatic-negotiations"),
                           ("military officers meeting at headquarters", "diplomatic-negotiations")):
            for title in ("explosion.mp4", "blast.mp4", "shelling.mp4", "frontline combat.mp4",
                          "артиллерийский обстрел.mp4", "взрыв.mp4", "explosion during official statement.mp4"):
                with self.subTest(query=query, title=title):
                    item = FootageItem(str(self.root / "unchecked.mp4"), title, tags=[tag])
                    self.assertFalse(bridge._semantic_clip_ok(query, item))

    def test_raw_continuity_rejects_unchecked_explosion_for_meeting(self):
        item = FootageItem(str(self.root / "unchecked.mp4"), "explosion blast shelling.mp4",
                           tags=["diplomatic-negotiations"])
        selected = bridge._select_visual_continuity_candidate(
            [item], scene_query="delegations diplomatic meeting", required_duration=6,
            project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6, source_allowed=lambda _: True,
            diversity_seed="unchecked-kinetic-contract")
        self.assertIsNone(selected)

    def test_external_prefilter_rejects_unchecked_explosion_for_statement(self):
        self.assertFalse(bridge._external_candidate_ok("official statement journalists cameras", {
            "url": "https://example.invalid/fixture.mp4", "title": "explosion blast shelling",
            "tags": ["press-conference"],
        }))

    def test_checked_meeting_window_in_mixed_kinetic_source_is_preserved(self):
        from scriptor.visual_evidence import classify_window
        item = self.item("explosion blast shelling.mp4", ["diplomatic-negotiations"], "direct")
        checked = classify_window("delegations diplomatic meeting", [{"meeting": .36, "combat": .20}] * 3)
        self.assertTrue(bridge._semantic_clip_ok("delegations diplomatic meeting", item, visual_assessment=checked))

    def test_unknown_or_contradictory_windows_reject_peaceful_roles(self):
        for query in ("official statement", "delegations diplomatic meeting", "peaceful civilian protest rally"):
            for relation in ("unknown", "contradiction"):
                with self.subTest(query=query, relation=relation):
                    item = self.item("anonymous.mp4", [], relation)
                    self.assertFalse(bridge._semantic_clip_ok(query, item))

    def test_earlier_comment_cannot_hide_a_later_kinetic_event(self):
        for title in (
            "Putin comments, then shelling begins.mp4",
            "Путин прокомментировал, затем произошёл взрыв.mp4",
            "Putin comments on shelling, then an explosion begins.mp4",
            "Putin comments then shelling begins.mp4",
            "Путин прокомментировал затем произошёл взрыв.mp4",
            "Putin comments on policy shelling starts.mp4",
        ):
            with self.subTest(title=title):
                item = FootageItem(str(self.root / "unchecked.mp4"), title, tags=["press-conference"])
                self.assertFalse(bridge._semantic_clip_ok("Vladimir Putin official statement", item))

    def test_unchecked_kinetic_guard_preserves_comments_meetings_and_neutral_context(self):
        for title, query, tag in (
            ("Путин прокомментировал обстрел города.mp4", "Vladimir Putin official statement", "press-conference"),
            ("Putin comments on shelling.mp4", "Vladimir Putin official statement", "press-conference"),
            ("official statement about shelling.mp4", "official statement", "press-conference"),
            ("military officers meeting about explosions.mp4", "delegations diplomatic meeting", "diplomatic-negotiations"),
            ("government building exterior.mp4", "official statement", "parliament-government"),
            ("no explosions.mp4", "official statement", "press-conference"),
            ("взрывов не было.mp4", "official statement", "press-conference"),
            ("frontline explosion.mp4", "frontline battlefield soldiers", "frontline-combat"),
        ):
            with self.subTest(title=title):
                item = FootageItem(str(self.root / "unchecked.mp4"), title, tags=[tag])
                self.assertTrue(bridge._semantic_clip_ok(query, item))

    def test_bar_cannot_be_official_context_from_a_model_tag(self):
        item = self.item('interview.mp4', ['diplomatic-negotiations'], 'contradiction')
        self.assertFalse(bridge._semantic_clip_ok('official statement government briefing', item))

    def test_explicit_patrol_boat_cannot_illustrate_commercial_port_loading(self):
        item = self.item('Американские патрульные катера ВМС Украины.mp4', ['port-logistics'], 'direct')
        self.assertFalse(bridge._semantic_clip_ok('seaport cargo cranes ships loading freight', item))
        self.assertTrue(bridge._semantic_clip_ok('navy patrol boat in port', item))

    def test_tokayev_catalog_context_is_not_russian_government_context(self):
        item = self.item('Токаев заседание Казахстан.mp4', [], 'context')
        item._visual_assessor = lambda *args, **kwargs: {'relation':'context','dominant_kind':'meeting'}
        self.assertFalse(bridge._semantic_clip_ok('Moscow Russia government building exterior illustrative context', item))
        self.assertTrue(bridge._semantic_clip_ok('Kazakhstan government building exterior illustrative context', item))

    def test_lukashenko_meeting_cannot_replace_a_named_zelensky_statement(self):
        item = self.item('Лукашенко заседание.mp4', [], 'context')
        item._visual_assessor = lambda *args, **kwargs: {'relation':'context','dominant_kind':'meeting'}
        self.assertFalse(bridge._semantic_clip_ok('Volodymyr Zelensky official statement', item))
        self.assertTrue(bridge._semantic_clip_ok('delegations diplomatic meeting', item))

    def test_foreign_government_does_not_become_ukrainian_from_a_reported_topic(self):
        item = self.item('Лукашенко о фотографиях украинского беспилотника.mp4', [], 'context')
        item._visual_assessor = lambda *args, **kwargs: {'relation': 'context', 'dominant_kind': 'meeting'}
        self.assertFalse(bridge._semantic_clip_ok('Kyiv Ukraine government city', item))
        self.assertTrue(bridge._semantic_clip_ok('Belarus government meeting', item))
        self.assertTrue(bridge._semantic_clip_ok('delegations diplomatic meeting', item))

    def test_curated_government_person_overrides_reported_topic_catalog_hint(self):
        item = self.item('Лукашенко о фотографиях украинского беспилотника.mp4', [], 'context')
        item._visual_assessor = lambda *args, **kwargs: {'relation': 'context', 'dominant_kind': 'meeting'}
        stat = Path(item.path).stat()
        item.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'observations': [{'person_id': 'zelensky', 'source': 'curated', 'start': 0, 'end': 6}]}
        self.assertTrue(bridge._semantic_clip_ok('Kyiv Ukraine government city', item))

    def test_protest_against_lukashenko_is_not_a_wrong_portrait(self):
        item = self.item('Протест против Лукашенко.mp4', ['protest-crowd'], 'direct')
        self.assertTrue(bridge._semantic_clip_ok('peaceful civilian protest rally placards', item))

    def test_joint_russian_kazakh_meeting_remains_valid_context(self):
        item = self.item('Putin Tokayev Russia Kazakhstan delegations.mp4', [], 'context')
        item._visual_assessor = lambda *args, **kwargs: {'relation':'context','dominant_kind':'meeting'}
        self.assertTrue(bridge._semantic_clip_ok('Moscow Russia government building exterior illustrative context', item))

    def test_stored_navy_query_cannot_change_commercial_shipping_role(self):
        from tests.test_footage_quality_voice import segment, status_for
        scenes, _ = bridge._voice_map_scenes(status_for([
            segment('В порту продолжается погрузка зерна на суда.', duration=6, query='ship navy cargo vessel'),
        ], 6))
        self.assertFalse(bridge._montage_has_naval_hint(scenes[0]['visual_query_en']))
        self.assertIn('port', scenes[0]['visual_query_en'])

    def test_stored_fire_query_cannot_turn_storage_into_an_emergency(self):
        from tests.test_footage_quality_voice import segment, status_for
        scenes, _ = bridge._voice_map_scenes(status_for([
            segment('На складе хранят зерно.', duration=6, query='warehouse fire emergency workers'),
        ], 6))
        self.assertNotIn('fire', scenes[0]['visual_query_en'])
        self.assertNotIn('emergency', scenes[0]['visual_query_en'])
        self.assertIn('warehouse', scenes[0]['visual_query_en'])

    def test_real_port_window_can_correct_conflicting_weak_combat_tag(self):
        item = self.item('port.mp4', ['port-logistics', 'frontline-combat'], 'direct')
        self.assertTrue(bridge._semantic_clip_ok('seaport cargo cranes ships', item))

    def test_person_in_protest_hint_is_not_a_visible_portrait(self):
        item = self.item('protest against Putin.mp4', ['protest-crowd'], 'direct')
        self.assertTrue(bridge._semantic_clip_ok('peaceful civilian protest rally placards', item))

    def test_rotation_must_validate_the_actual_source_window(self):
        item = self.item('mixed.mp4', ['port-logistics'], lambda start: 'direct' if start == 0 else 'contradiction')
        query = 'seaport cargo cranes ships'
        self.assertTrue(bridge._semantic_clip_ok(query, item, source_start=0))
        self.assertFalse(bridge._semantic_clip_ok(query, item, source_start=6))

    def test_direct_port_in_later_retrieval_beats_early_context(self):
        context = self.item('warehouse.mp4', ['port-logistics'], 'context')
        direct = self.item('ship.mp4', ['port-logistics'], 'direct')
        selection = bridge._select_montage_candidate('seaport cargo cranes ships',
            strict_hits=[SearchHit(context, .5, 7)], fallback_hits=[],
            relaxed_hits=[SearchHit(direct, .4, 7)], required_duration=6,
            match_threshold=.22, used_paths=set(), used_families=set(),
            project_used_paths=set(), project_used_families=set(),
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 7)
        self.assertEqual(direct.path, selection.item.path)
        self.assertEqual('direct', selection.diagnostics['visual']['relation'])

    def test_rejected_window_is_deep_checked_once_across_relaxation_stages(self):
        item = self.item('ship.mp4', ['port-logistics'], 'direct')
        calls = []
        def blocked(value):
            calls.append(value.path)
            return False
        with self.assertRaises(bridge.MontageSelectionFailure) as failure:
            bridge._select_montage_candidate('seaport cargo cranes ships',
                strict_hits=[SearchHit(item, .5, 7)], fallback_hits=[],
                required_duration=6, match_threshold=.22,
                used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
                reserved_paths=set(), reserved_families=set(), source_exists=lambda _: True,
                source_duration=lambda _: 7, source_allowed=blocked)
        self.assertEqual(1, len(calls))
        self.assertEqual(1, failure.exception.diagnostics['unique_rejected_safety'])
        self.assertGreater(failure.exception.diagnostics['rejection_events'], 1)

    def test_family_reuse_prefers_unseen_sibling_before_repeating_a_path(self):
        repeated = self.item('used-ship.mp4', ['port-logistics'], 'direct')
        sibling = self.item('unseen-ship.mp4', ['port-logistics'], 'direct')
        repeated_key = bridge._montage_clip_key(repeated.path)
        selection = bridge._select_montage_candidate('seaport cargo cranes ships',
            strict_hits=[SearchHit(repeated, .8, 7, source_family='cargo-family'),
                         SearchHit(sibling, .4, 7, source_family='cargo-family')],
            fallback_hits=[], required_duration=6, match_threshold=.22,
            used_paths={repeated_key}, used_families={'cargo-family'},
            project_used_paths={repeated_key}, project_used_families={'cargo-family'},
            reserved_paths=set(), reserved_families=set(),
            batch_family_buckets={'cargo-family': ['EARLY', 'MIDDLE']},
            source_exists=lambda _: True, source_duration=lambda _: 7)
        self.assertEqual(sibling.path, selection.item.path)
        self.assertEqual('cargo-family', selection.source_family)
        self.assertEqual('SAFE_REUSE', selection.fallback_level)
        self.assertTrue(selection.reused)

    def test_unseen_sibling_context_rotates_without_bypassing_floor_or_contradiction(self):
        for relation, score in (('direct', .01), ('context', .4), ('contradiction', .9)):
            with self.subTest(relation=relation, score=score):
                repeated = self.item('used-ship.mp4', ['port-logistics'], 'direct')
                sibling = self.item('unseen-ship.mp4', ['port-logistics'], relation)
                repeated_key = bridge._montage_clip_key(repeated.path)
                selection = bridge._select_montage_candidate('seaport cargo cranes ships',
                    strict_hits=[SearchHit(repeated, .8, 7, source_family='cargo-family'),
                                 SearchHit(sibling, score, 7, source_family='cargo-family')],
                    fallback_hits=[], required_duration=6, match_threshold=.22,
                    used_paths={repeated_key}, used_families={'cargo-family'},
                    project_used_paths={repeated_key}, project_used_families={'cargo-family'},
                    reserved_paths=set(), reserved_families=set(),
                    source_exists=lambda _: True, source_duration=lambda _: 7)
                self.assertEqual(sibling.path if relation == 'context' else repeated.path, selection.item.path)

    def test_unseen_sibling_cannot_displace_confirmed_person_in_reused_family(self):
        query = 'Nikol Pashinyan official statement government briefing'
        repeated = self.item('used-statement.mp4', ['press-conference'], 'direct')
        sibling = self.item('unseen-delegation.mp4', ['diplomatic-negotiations'], 'direct')
        sibling._visual_assessor = lambda query, start, duration, **kwargs: {
            'relation': 'direct', 'dominant_kind': 'meeting', 'source_start': start}
        stat = Path(repeated.path).stat()
        repeated.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'observations': [{'person_id': 'pashinyan', 'source': 'curated', 'start': 0, 'end': 7}]}
        repeated_key = bridge._montage_clip_key(repeated.path)
        selection = bridge._select_montage_candidate(query,
            strict_hits=[SearchHit(repeated, .4, 7, source_family='statement-family'),
                         SearchHit(sibling, .9, 7, source_family='statement-family')],
            fallback_hits=[], required_duration=6, match_threshold=.22,
            used_paths={repeated_key}, used_families={'statement-family'},
            project_used_paths={repeated_key}, project_used_families={'statement-family'},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 7)
        self.assertEqual(repeated.path, selection.item.path)
        self.assertEqual('confirmed', selection.diagnostics['person']['status'])

    def select_with_reused_candidate(self, query, repeated, fresh, *, score=.4, source_allowed=None,
                                    allow_safe_reuse=True):
        key = bridge._montage_clip_key(repeated.path)
        return bridge._select_montage_candidate(query,
            strict_hits=[SearchHit(repeated, score, 7, source_family='used-family'),
                         SearchHit(fresh, .5, 7, source_family='fresh-family')],
            fallback_hits=[], required_duration=6, match_threshold=.22,
            used_paths={key}, used_families={'used-family'},
            project_used_paths={key}, project_used_families={'used-family'},
            reserved_paths=set(), reserved_families=set(),
            source_exists=lambda _: True, source_duration=lambda _: 7,
            source_allowed=source_allowed, allow_safe_reuse=allow_safe_reuse)

    def test_explicitly_disabled_reuse_retains_unique_context_contract(self):
        direct = self.item('used-ship.mp4', ['port-logistics'], 'direct')
        context = self.item('unseen-warehouse.mp4', ['port-logistics'], 'context')
        selection = self.select_with_reused_candidate('seaport cargo cranes ships', direct, context,
                                                      allow_safe_reuse=False)
        self.assertEqual(context.path, selection.item.path)
        self.assertFalse(selection.reused)

    def test_fresh_checked_context_precedes_reused_direct_port(self):
        direct = self.item('used-ship.mp4', ['port-logistics'], 'direct')
        context = self.item('unseen-warehouse.mp4', ['port-logistics'], 'context')
        selection = self.select_with_reused_candidate('seaport cargo cranes ships', direct, context)
        self.assertEqual(context.path, selection.item.path)
        self.assertEqual('context', selection.diagnostics['visual']['relation'])
        self.assertFalse(selection.reused)

    def test_reused_confirmed_person_beats_fresh_institution_context(self):
        query = 'Nikol Pashinyan official statement government briefing'
        direct = self.item('used-statement.mp4', ['press-conference'], 'direct')
        context = self.item('unseen-delegation.mp4', ['diplomatic-negotiations'], 'context')
        context._visual_assessor = lambda query, start, duration, **kwargs: {
            'relation': 'context', 'dominant_kind': 'meeting', 'source_start': start}
        stat = Path(direct.path).stat()
        direct.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'observations': [{'person_id': 'pashinyan', 'source': 'curated', 'start': 0, 'end': 7}]}
        selection = self.select_with_reused_candidate(query, direct, context)
        self.assertEqual(direct.path, selection.item.path)
        self.assertEqual('confirmed', selection.diagnostics['person']['status'])

    def test_inadmissible_reused_direct_still_allows_fresh_context(self):
        for defect in ('below-floor', 'contradiction', 'source-disallowed'):
            with self.subTest(defect=defect):
                direct = self.item('used-ship.mp4', ['port-logistics'],
                                   'contradiction' if defect == 'contradiction' else 'direct')
                context = self.item('unseen-warehouse.mp4', ['port-logistics'], 'context')
                selection = self.select_with_reused_candidate('seaport cargo cranes ships', direct, context,
                    score=.01 if defect == 'below-floor' else .4,
                    source_allowed=lambda item, defect=defect, direct=direct: defect != 'source-disallowed' or item.path != direct.path)
                self.assertEqual(context.path, selection.item.path)
                self.assertEqual('SAFE_CONTEXT', selection.fallback_level)

    def prepare_two_scene_project(self, *, named_person=False, fast_confirmed_escape=False):
        from scriptor.config import Settings
        from scriptor.core import ScenarioRequest
        from scriptor.runner import Job, RunState
        from tests.media_fixtures import write_readable_video
        from tests.test_footage_quality_voice import segment, status_for

        text = ('Пашинян выступил с заявлением.' if named_person else 'В порту грузят контейнеры на суда.')
        query = ('Nikol Pashinyan official statement government briefing' if named_person
                 else 'seaport cargo cranes ships')
        direct_name = ('Nikol Pashinyan hint.mp4' if fast_confirmed_escape else 'statement.mp4')
        direct = self.item(direct_name if named_person else 'ship.mp4',
                           ['press-conference'] if named_person else ['port-logistics'], 'direct')
        context = self.item('verified-statement.mp4' if fast_confirmed_escape else
                            ('delegations.mp4' if named_person else 'warehouse.mp4'),
                            ['diplomatic-negotiations'] if named_person else ['port-logistics'],
                            'direct' if fast_confirmed_escape else 'context')
        for item in (direct, context):
            write_readable_video(Path(item.path), duration=7)
        if named_person:
            context._visual_assessor = lambda query, start, duration, **kwargs: {
                'relation': 'direct' if fast_confirmed_escape else 'context',
                'dominant_kind': 'official' if fast_confirmed_escape else 'meeting', 'source_start': start}
            direct._visual_assessor = lambda query, start, duration, **kwargs: {
                'relation': 'direct', 'dominant_kind': 'official', 'source_start': start}
            confirmed = context if fast_confirmed_escape else direct
            stat = Path(confirmed.path).stat()
            confirmed.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                'observations': [{'person_id': 'pashinyan', 'source': 'curated', 'start': 0, 'end': 7}]}
        voice = self.root / 'voice.wav'
        voice.write_bytes(b'test-owned-voice')
        settings = Settings(footage_folders=[str(self.root)], montage_auto_web=False,
            montage_fast_reuse_enabled=fast_confirmed_escape, montage_unique_footage_percent=50,
            montage_export_davinci_xml=False,
            montage_project_folder=str(self.root / 'projects'),
            montage_output_folder=str(self.root / 'output'), voice_scenario_outputs={'1': str(voice)})
        job = Job(ScenarioRequest(0, text, '', 'test-quality-voice'), RunState.DONE, f'{text} {text}', '')
        scene_count = 3 if fast_confirmed_escape else 2
        status = status_for([segment(text, duration=6, query=query, identity=i + 1, start=i * 6)
                             for i in range(scene_count)], scene_count * 6)
        levels = {level: [SearchHit(direct, .4, 7, source_family='direct-family'),
                          SearchHit(context, .5, 7, source_family='context-family')]
                  for level in bridge._MONTAGE_FALLBACK_LEVELS}
        scene_levels = [levels, levels]
        if fast_confirmed_escape:
            cached_only = {level: hits[:1] for level, hits in levels.items()}
            scene_levels = [cached_only, cached_only, levels]
        with patch.object(bridge, 'load_settings', return_value=settings), \
             patch.object(bridge, 'load_session', return_value=([text], [job])), \
             patch.object(bridge, 'save_settings'), \
             patch.object(bridge, 'snapshot', return_value={}), \
             patch.object(bridge, 'app_data_root', return_value=self.root), \
             patch.object(bridge, '_ensure_voice_map_for_scenario', return_value=status), \
             patch.object(bridge.ClipIndex, 'count', return_value=2), \
             patch.object(bridge, '_montage_search_ladders', return_value=scene_levels), \
             patch.object(bridge, '_montage_screen_text_safe', return_value=True), \
             patch.object(bridge, 'probe_media_duration', return_value=scene_count * 6), \
             patch.object(bridge, 'probe_video_duration', return_value=7):
            result = bridge.prepare_montage({'scenarioIndex': 0})
        return TimelineProject.load(Path(result['preparedProject']['path'])), context if fast_confirmed_escape else direct

    def test_prepare_rotates_direct_port_to_fresh_checked_warehouse_context(self):
        project, direct = self.prepare_two_scene_project()
        self.assertEqual(direct.path, project.clips[0].path)
        self.assertNotEqual(direct.path, project.clips[1].path)
        self.assertEqual('SAFE_CONTEXT', project.clips[1].fallback_level)

    def test_prepare_reservation_race_keeps_first_action_then_rotates_to_fresh_context(self):
        usage = {'lock': threading.RLock(), 'claims': {}, 'placements': {}, 'windows': {}}
        prepare, claim = bridge.prepare_montage, bridge._claim_batch_family
        collided = []

        def racing_claim(current_usage, family, bucket, *args, **kwargs):
            if family == 'direct-family' and not collided:
                collided.append(family)
                current_usage['claims'][(bucket, family)] = 99
                return False
            return claim(current_usage, family, bucket, *args, **kwargs)

        with (patch.object(bridge, 'prepare_montage', side_effect=lambda payload: prepare(
                    {**payload, '_batchFootageUsage': usage})),
              patch.object(bridge, '_claim_batch_family', side_effect=racing_claim),
              patch('tests.media_fixtures.write_readable_video', side_effect=lambda path, **_: Path(path).write_bytes(b'disposable-source')),
              patch.object(bridge, '_cached_or_probed_montage_duration', return_value=7)):
            project, direct = self.prepare_two_scene_project()
        self.assertEqual(['direct-family'], collided)
        self.assertEqual(direct.path, project.clips[0].path)
        self.assertNotEqual(direct.path, project.clips[1].path)
        self.assertEqual('SAFE_REUSE', project.clips[0].fallback_level)
        self.assertEqual('direct', project.clips[0].selection_diagnostics['visual']['relation'])

    def test_prepare_reuses_confirmed_speaker_before_fresh_institution_context(self):
        project, direct = self.prepare_two_scene_project(named_person=True)
        self.assertEqual([direct.path, direct.path], [clip.path for clip in project.clips])
        self.assertEqual('confirmed', project.clips[1].selection_diagnostics['person']['status'])

    def test_prepare_fast_pool_probable_speaker_yields_to_fresh_confirmed_speaker(self):
        project, confirmed = self.prepare_two_scene_project(named_person=True, fast_confirmed_escape=True)
        self.assertEqual('probable', project.clips[0].selection_diagnostics['person']['status'])
        self.assertNotEqual(confirmed.path, project.clips[1].path)
        self.assertEqual(confirmed.path, project.clips[2].path)
        self.assertEqual('confirmed', project.clips[2].selection_diagnostics['person']['status'])

    def test_inadmissible_confirmed_speaker_cannot_evict_valid_fast_cached_speaker(self):
        query = 'Nikol Pashinyan official statement government briefing'
        for defect in ('below-floor', 'source-disallowed', 'short-source', 'wrong-person'):
            with self.subTest(defect=defect):
                cached = self.item('Nikol Pashinyan hint.mp4', ['press-conference'], 'direct')
                confirmed = self.item('verified-statement.mp4', ['press-conference'], 'direct')
                for item in (cached, confirmed):
                    item._visual_assessor = lambda query, start, duration, **kwargs: {
                        'relation': 'direct', 'dominant_kind': 'official', 'source_start': start}
                stat = Path(confirmed.path).stat()
                confirmed.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
                    'observations': [{'person_id': 'putin' if defect == 'wrong-person' else 'pashinyan',
                                      'source': 'curated', 'start': 0, 'end': 7}]}
                levels = {level: [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
                levels['STRICT_MATCH'] = [SearchHit(cached, .5, 7),
                    SearchHit(confirmed, .01 if defect == 'below-floor' else .4, 7)]
                origin = TimelineClip(cached.path, '', query, duration=6)
                result = bridge._fast_reuse_pool_hits(levels,
                    {bridge._montage_clip_key(cached.path): origin}, 6,
                    lambda item, defect=defect, confirmed=confirmed: 3 if defect == 'short-source' and item.path == confirmed.path else 7,
                    scene_query=query, match_threshold=.22,
                    source_allowed=lambda item, defect=defect, confirmed=confirmed: defect != 'source-disallowed' or item.path != confirmed.path)
                self.assertEqual([cached.path], [hit.item.path for hit in result['STRICT_MATCH']])

    def test_fast_context_escapes_to_available_direct_port(self):
        context = self.item('warehouse.mp4', ['port-logistics'], 'context')
        direct = self.item('ship.mp4', ['port-logistics'], 'direct')
        levels = {level: [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
        levels['STRICT_MATCH'] = [SearchHit(context, .5, 7), SearchHit(direct, .4, 7)]
        cached = TimelineClip(path=context.path, narration='', visual_query_en='seaport cargo cranes ships', duration=6)
        result = bridge._fast_reuse_pool_hits(levels,
            {bridge._montage_clip_key(context.path): cached}, 6, lambda _: 7,
            scene_query='seaport cargo cranes ships')
        self.assertFalse(any(result.values()))

    def test_short_or_missing_sources_do_not_consume_visual_refinement(self):
        for invalid in ('short', 'missing'):
            with self.subTest(invalid=invalid):
                bad = self.item(f'{invalid}.mp4', ['port-logistics'], 'direct')
                good = self.item(f'good-{invalid}.mp4', ['port-logistics'], 'direct')
                calls = []
                assessor = bad._visual_assessor
                def count(*args, calls=calls, assessor=assessor, **kwargs):
                    calls.append(1)
                    return assessor(*args, **kwargs)
                bad._visual_assessor = count
                result = bridge._select_montage_candidate('seaport cargo cranes ships',
                    strict_hits=[SearchHit(bad, .5, 2 if invalid == 'short' else 7), SearchHit(good, .4, 7)],
                    fallback_hits=[], required_duration=6, match_threshold=.22,
                    used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
                    reserved_paths=set(), reserved_families=set(),
                    source_exists=lambda item, invalid=invalid, bad=bad: not (invalid == 'missing' and item.path == bad.path),
                    source_duration=lambda _: 7)
                self.assertEqual(good.path, result.item.path)
                self.assertEqual([], calls)

    def test_fast_context_does_not_hide_direct_material_in_a_later_window(self):
        context = self.item('warehouse.mp4', ['port-logistics'], 'context')
        direct = self.item('ship.mp4', ['port-logistics'], 'contradiction')
        def assess(query, start, duration, *, allow_alternatives=False):
            usable = start == 12 or allow_alternatives
            return {'relation': 'direct' if usable else 'contradiction',
                    'source': 'automatic-window-clip', 'source_start': 12 if usable else start}
        direct._visual_assessor = assess
        levels = {level: [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
        levels['STRICT_MATCH'] = [SearchHit(context, .5, 7), SearchHit(direct, .4, 30)]
        cached = TimelineClip(path=context.path, narration='', visual_query_en='seaport cargo cranes ships', duration=6)
        result = bridge._fast_reuse_pool_hits(levels,
            {bridge._montage_clip_key(context.path): cached}, 6, lambda _: 30,
            scene_query='seaport cargo cranes ships')
        self.assertFalse(any(result.values()))

    def test_unverified_budget_failure_is_not_reported_as_material_scarcity(self):
        item = self.item('unchecked.mp4', ['port-logistics'], 'unknown')
        item._visual_assessor = lambda *args, **kwargs: {
            'relation': 'unknown', 'reason': 'cold-window-budget-exhausted'}
        with self.assertRaises(bridge.MontageSelectionFailure) as failure:
            bridge._select_montage_candidate('seaport cargo cranes ships',
                strict_hits=[SearchHit(item, .5, 7)], fallback_hits=[],
                required_duration=6, match_threshold=.22,
                used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
                reserved_paths=set(), reserved_families=set(), source_exists=lambda _: True,
                source_duration=lambda _: 7)
        self.assertEqual({'cold-window-budget-exhausted': 1},
                         failure.exception.diagnostics.get('visual_rejection_reasons'))

    def test_continental_europe_is_not_an_exact_eu_institution(self):
        self.assertFalse(bridge._montage_entity_conflict(
            'European grain freight railway', 'Ukraine Odesa rail freight'))
        self.assertTrue(bridge._montage_entity_conflict(
            'European Union Brussels parliament', 'Ukraine Odesa government'))
        self.assertTrue(bridge._montage_entity_conflict(
            'European Parliament institutions', 'Moscow Russia government'))
        self.assertTrue(bridge._montage_entity_conflict(
            'порты в Европейском союзе', 'Украина Одесса порт'))

    def test_forbidden_direct_person_does_not_evict_safe_cached_context(self):
        query = 'Nikol Pashinyan official statement government briefing'
        context = self.item('delegations.mp4', ['diplomatic-negotiations'], 'context')
        context._visual_assessor = lambda *args, **kwargs: {
            'relation': 'context', 'dominant_kind': 'meeting', 'source_start': 0}
        wrong = self.item('Vladimir Putin.mp4', ['press-conference'], 'direct')
        levels = {level: [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
        levels['STRICT_MATCH'] = [SearchHit(context, .5, 7), SearchHit(wrong, .4, 7)]
        cached = TimelineClip(path=context.path, narration='', visual_query_en=query, duration=6)
        result = bridge._fast_reuse_pool_hits(levels,
            {bridge._montage_clip_key(context.path): cached}, 6, lambda _: 7, scene_query=query)
        self.assertEqual([context.path], [hit.item.path for hit in result['STRICT_MATCH']])

    def test_stored_institution_query_cannot_invent_a_parliament_for_port_capacity(self):
        from tests.test_footage_quality_voice import segment, status_for
        text = 'Порты используют дополнительные мощности в странах Европейского союза.'
        raw = 'Europe European Parliament Brussels institutions, seaport cargo cranes ships'
        scenes, _ = bridge._voice_map_scenes(status_for([segment(text, duration=6, query=raw)], 6))
        self.assertIn('port', scenes[0]['visual_query_en'])
        self.assertIn('European Union', scenes[0]['visual_query_en'])
        self.assertNotIn('Parliament', scenes[0]['visual_query_en'])
        self.assertNotIn('Brussels', scenes[0]['visual_query_en'])

    def test_fast_context_yields_to_confirmed_person_in_later_curated_window(self):
        query = 'Nikol Pashinyan official statement government briefing'
        context = self.item('delegations.mp4', ['diplomatic-negotiations'], 'context')
        context._visual_assessor = lambda *args, **kwargs: {
            'relation': 'context', 'dominant_kind': 'meeting', 'source_start': 0}
        official = self.item('statement.mp4', ['press-conference'], 'direct')
        official._visual_assessor = lambda query, start, duration, **kwargs: {
            'relation': 'direct', 'dominant_kind': 'official', 'source_start': start}
        stat = Path(official.path).stat()
        official.person_evidence = {'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'observations': [{'person_id': 'pashinyan', 'source': 'curated', 'start': 6, 'end': 12}]}
        levels = {level: [] for level in bridge._MONTAGE_FALLBACK_LEVELS}
        levels['STRICT_MATCH'] = [SearchHit(context, .5, 13), SearchHit(official, .4, 13)]
        cached = TimelineClip(path=context.path, narration='', visual_query_en=query, duration=6)
        result = bridge._fast_reuse_pool_hits(levels,
            {bridge._montage_clip_key(context.path): cached}, 6, lambda _: 13, scene_query=query)
        self.assertFalse(any(result.values()))

    def test_place_only_stored_query_keeps_current_action_and_authored_place(self):
        from tests.test_footage_quality_voice import segment, status_for
        for text, raw, action in (
            ('В порту грузят контейнеры на суда.', 'Ukraine Ukrainian flag Kyiv', 'port'),
            ('Делегации провели переговоры.', 'Geneva Switzerland', 'diplomatic'),
        ):
            with self.subTest(raw=raw):
                scenes, _ = bridge._voice_map_scenes(status_for([segment(text, duration=6, query=raw)], 6))
                self.assertIn(action, scenes[0]['visual_query_en'])
                self.assertIn(raw, scenes[0]['visual_query_en'])

    def test_iran_source_context_is_not_imported_into_a_story_without_iran(self):
        source = self.item('Iran Tehran missile launch.mp4', ['frontline-combat'], 'direct')
        self.assertFalse(bridge._montage_story_candidate_allowed(
            'На фронте в Украине продолжаются бои.', source))
        self.assertFalse(bridge._montage_story_candidate_allowed(
            'В порту возобновилась погрузка контейнеров.', source))
        self.assertTrue(bridge._montage_story_candidate_allowed(
            'Иран сообщил о ситуации в Тегеране.', source))
        neutral = self.item('cargo.mp4', ['iran-government-tehran'], 'direct')
        self.assertTrue(bridge._montage_story_candidate_allowed(
            'В порту возобновилась погрузка контейнеров.', neutral))
        for name in ('iran_tanker_01.mp4', 'cargo_iran.mp4', 'Iranian tanker.mp4', 'Tehran_cargo.mp4'):
            with self.subTest(name=name):
                item = self.item(name, ['port-logistics'], 'direct')
                self.assertFalse(bridge._montage_story_candidate_allowed('В порту грузят суда.', item))
                self.assertTrue(bridge._montage_story_candidate_allowed('Iranian exports from Tehran.', item))

    def test_automatic_country_tag_is_not_confirmed_geography(self):
        warehouse = self.item('warehouse.mp4', ['russia-government-moscow', 'port-logistics'], 'context')
        self.assertTrue(bridge._semantic_clip_ok('European Union cargo port storage logistics', warehouse))
        named = self.item('Moscow Russia warehouse.mp4', ['port-logistics'], 'context')
        self.assertFalse(bridge._semantic_clip_ok('European Union cargo port storage logistics', named))

    def test_render_recovery_detects_healthy_but_forbidden_iran_source(self):
        item = self.item('Iran_tanker.mp4', ['port-logistics'], 'direct')
        project = TimelineProject('Логистика Украины', clips=[
            TimelineClip(item.path, 'В порту грузят суда.', 'seaport cargo ships', duration=6)])
        with patch.object(bridge, '_cached_or_probed_montage_duration', return_value=6):
            self.assertEqual([item.path], bridge._montage_project_missing_clips(project))

    def test_stored_protest_query_does_not_invent_a_protest_for_transport_costs(self):
        from tests.test_footage_quality_voice import segment, status_for
        segments = [segment('Порты продолжают погрузку.', duration=6),
                    segment('Трейдер закладывает больше времени и денег.', duration=6,
                            query='farmers tractors protest', identity=2, start=6)]
        scenes, _ = bridge._voice_map_scenes(status_for(segments, 12))
        self.assertNotIn('protest', scenes[1]['visual_query_en'])
        self.assertIn('port', scenes[1]['visual_query_en'])


if __name__ == '__main__':
    unittest.main()
