"""Disposable recovery contracts; synthetic labels do not prove real visuals."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.ai_index import ClipIndex, SearchHit
from scriptor.config import Settings
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject


class RecoveryVisualQualityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ['NEWSFLOW_TEST_ROOT'])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.voice = self.root / 'voice.wav'
        self.voice.touch()
        self.settings = Settings(footage_folders=[str(self.root)], montage_auto_web=False)

    def item(self, name, *, valid_start=0, valid_duration=30, source_url=''):
        path = self.root / name
        path.write_bytes(b'test-owned-contract-source')
        item = FootageItem(str(path), name, tags=['port-logistics'], source_url=source_url)
        def assess(_query, start, duration, **kwargs):
            if kwargs.get('allow_alternatives') and not valid_start <= start < valid_start + valid_duration:
                start = valid_start
            return {'relation': 'direct' if valid_start <= start and start + duration <= valid_start + valid_duration else 'contradiction',
                    'source_start': start, 'duration': duration, 'source': 'curated-interval'}
        item._visual_assessor = assess
        return item

    def clip(self, item, duration=6, narration='В порту идёт погрузка', **kwargs):
        return TimelineClip(item.path, narration, 'seaport cargo cranes ships', duration, **kwargs)

    def project(self, clips, title='Новости порта'):
        return TimelineProject(title, clips=clips, voiceover_path=str(self.voice))

    def index(self, hits=(), story='В порту идёт погрузка'):
        return SimpleNamespace(
            montage_story_context=story,
            candidate_filter=lambda item: bridge._montage_story_candidate_allowed(story, item),
            search_many=lambda *_args, **_kwargs: [[SearchHit(item, .9, 30) for item in hits]],
        )

    def test_missing_slot_rejects_iran_source_without_story_mention(self):
        bad, good = self.item('Iran_port.mp4'), self.item('ordinary_port.mp4')
        project = self.project([TimelineClip(str(self.root / 'missing.mp4'), 'Погрузка', 'seaport cargo cranes ships', 6)])
        with patch.object(bridge, '_validated_montage_clip_duration', side_effect=lambda path: 30 if path.is_file() else 0):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [bad, good]), 1)
        self.assertEqual(project.clips[0].path, good.path)

    def test_saved_neutral_path_keeps_indexed_iran_url_restriction(self):
        item = self.item('neutral-port.mp4', source_url='https://example.test/Iran-tanker')
        index = ClipIndex(self.root / 'saved-index.sqlite3')
        index.add_item(item)
        index.montage_story_context = 'В порту идёт погрузка'
        index.candidate_filter = lambda candidate: bridge._montage_story_candidate_allowed(index.montage_story_context, candidate)
        project = self.project([self.clip(item)])
        with patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30):
            self.assertEqual(bridge._montage_project_missing_clips(project, index), [item.path])

    def test_saved_neutral_path_with_iran_catalog_tag_cannot_skip_tail_guard(self):
        item = self.item('neutral-port.mp4')
        item.tags.append('Iran tanker source')
        index = ClipIndex(self.root / 'saved-index.sqlite3')
        index.add_item(item)
        index.montage_story_context = 'В порту идёт погрузка'
        index.candidate_filter = lambda candidate: bridge._montage_story_candidate_allowed(index.montage_story_context, candidate)
        project = self.project([self.clip(item)])
        with patch.object(bridge, 'probe_media_duration', return_value=6), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             self.assertRaisesRegex(ValueError, 'запрещённый контекстом'):
            bridge._complete_project_visual_tail(project, index, self.settings)

    def test_saved_catalog_iran_source_is_repaired_and_permitted_when_mentioned(self):
        iran = self.item('neutral-port.mp4', source_url='https://example.test/Iran-tanker')
        good = self.item('replacement.mp4')
        index = ClipIndex(self.root / 'saved-index.sqlite3')
        index.add_item(iran)
        index.montage_story_context = 'В порту идёт погрузка'
        index.candidate_filter = lambda candidate: bridge._montage_story_candidate_allowed(index.montage_story_context, candidate)
        project = self.project([self.clip(iran)])
        with patch.object(bridge, '_validated_montage_clip_duration', return_value=30):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [good], index=index), 1)
        self.assertEqual(project.clips[0].path, good.path)
        index.montage_story_context = 'В порту Ирана идёт погрузка'
        with patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30):
            self.assertEqual(bridge._montage_project_missing_clips(self.project([self.clip(iran)]), index), [])

    def test_healthy_forbidden_slot_is_repaired_without_changing_other_healthy_edits(self):
        iran, old, good = self.item('Iran_port.mp4'), self.item('unchanged.mp4'), self.item('replacement.mp4')
        kept = self.clip(old, source_start=4)
        project = self.project([self.clip(iran), kept])
        with patch.object(bridge, '_validated_montage_clip_duration', return_value=30):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [good]), 1)
        self.assertEqual(project.clips[0].path, good.path)
        self.assertIs(project.clips[1], kept)

    def test_iran_mention_in_another_story_row_permits_repair_source(self):
        iran, old = self.item('Iran_port.mp4'), self.item('old.mp4')
        project = self.project([TimelineClip(str(self.root / 'missing.mp4'), 'Погрузка', 'seaport cargo cranes ships', 6),
                                self.clip(old, narration='Позже обсудили Иран')])
        with patch.object(bridge, '_validated_montage_clip_duration', side_effect=lambda path: 30 if path.is_file() else 0):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [iran]), 1)
        self.assertEqual(project.clips[0].path, iran.path)

    def test_iran_mention_in_whole_story_permits_terminal_source(self):
        old, iran = self.item('old.mp4'), self.item('Iran_port.mp4')
        project = self.project([self.clip(old)])
        with patch.object(bridge, 'probe_media_duration', return_value=10), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             patch.object(bridge, '_replacement_candidates_for_clip', return_value=[iran]):
            self.assertEqual(bridge._complete_project_visual_tail(project, self.index(story='Иран'), self.settings), 1)
        self.assertEqual((project.clips[-1].path, project.clips[-1].duration), (iran.path, 4))

    def test_repair_uses_full_narration_context_even_when_saved_rows_are_partial(self):
        iran = self.item('Iran_port.mp4')
        project = self.project([TimelineClip(str(self.root / 'missing.mp4'), 'Погрузка', 'seaport cargo cranes ships', 6)])
        with patch.object(bridge, '_validated_montage_clip_duration', side_effect=lambda path: 30 if path.is_file() else 0):
            self.assertEqual(bridge._repair_missing_project_clips(
                project, lambda *_: [iran], story_context='Погрузка. Далее обсуждается Иран.'), 1)
        self.assertEqual(project.clips[0].path, iran.path)

    def test_replacement_search_and_download_both_keep_transient_story_filter(self):
        iran = self.item('Iran_port.mp4')
        clip = TimelineClip('missing.mp4', 'Погрузка', 'seaport cargo cranes ships', 6)
        self.settings.montage_auto_web = True
        with patch.object(bridge, '_montage_screen_text_safe', return_value=True), \
             patch.object(bridge, '_download_scene_fallback', return_value=iran):
            self.assertEqual(bridge._replacement_candidates_for_clip(self.index([iran]), clip, self.settings), [])

    def test_complete_authored_plan_never_adds_old_per_clip_safety_extension(self):
        old = self.item('port.mp4')
        project = self.project([self.clip(old, source_start=4)])
        with patch.object(bridge, 'probe_media_duration', return_value=6), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30):
            self.assertEqual(bridge._complete_project_visual_tail(project, self.index(), self.settings), 0)
        self.assertEqual([(clip.source_start, clip.duration) for clip in project.clips], [(4, 6)])

    def test_missing_tail_preserves_old_window_and_rejects_iran_candidate(self):
        old, iran, good = self.item('old.mp4'), self.item('Iran_port.mp4'), self.item('other_port.mp4')
        project = self.project([self.clip(old, source_start=4)])
        with patch.object(bridge, 'probe_media_duration', return_value=10), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             patch.object(bridge, '_replacement_candidates_for_clip', return_value=[iran, good]):
            self.assertEqual(bridge._complete_project_visual_tail(project, self.index(), self.settings), 1)
        self.assertEqual([(clip.path, clip.source_start, clip.duration) for clip in project.clips],
                         [(old.path, 4, 6), (good.path, 0, 4)])

    def test_tail_checks_the_actual_fractional_window_and_retains_curated_start(self):
        old = self.item('old.mp4')
        tail = self.item('curated_port.mp4', valid_start=9, valid_duration=4)
        project = self.project([self.clip(old)])
        with patch.object(bridge, 'probe_media_duration', return_value=10), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             patch.object(bridge, '_replacement_candidates_for_clip', return_value=[tail]):
            self.assertEqual(bridge._complete_project_visual_tail(project, self.index(), self.settings), 1)
        self.assertEqual([(clip.source_start, clip.duration) for clip in project.clips], [(0, 6), (9, 4)])

    def test_subframe_audio_remainder_gets_a_real_bounded_source_window(self):
        old, tail = self.item('old.mp4'), self.item('tail.mp4', valid_start=9, valid_duration=4)
        project = self.project([self.clip(old)])
        with patch.object(bridge, 'probe_media_duration', return_value=6.03), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             patch.object(bridge, '_replacement_candidates_for_clip', return_value=[tail]):
            self.assertEqual(bridge._complete_project_visual_tail(project, self.index(), self.settings), 1)
        self.assertEqual(project.clips[-1].source_start, 9)
        self.assertAlmostEqual(project.clips[-1].duration, .03)
        self.assertAlmostEqual(sum(clip.duration for clip in project.clips), 6.03)

    def test_repair_checks_actual_selected_duration_and_curated_start(self):
        good = self.item('curated_port.mp4', valid_start=9, valid_duration=4)
        project = self.project([TimelineClip(str(self.root / 'missing.mp4'), 'Погрузка', 'seaport cargo cranes ships', 4)])
        with patch.object(bridge, '_validated_montage_clip_duration', side_effect=lambda path: 30 if path.is_file() else 0):
            self.assertEqual(bridge._repair_missing_project_clips(project, lambda *_: [good]), 1)
        self.assertEqual((project.clips[0].source_start, project.clips[0].duration), (9, 4))

    def test_real_manual_index_short_intervals_cannot_fall_back_to_metadata_outside_them(self):
        old, first, second = self.item('old.mp4'), self.item('first_port.mp4'), self.item('second_port.mp4')
        index = ClipIndex(self.root / 'manual-index.sqlite3')
        for item in (first, second):
            index.add_item(item)
            index.set_visual_evidence(item.path, [{'start': 9, 'end': 13, 'kind': 'port', 'source': 'manual'}])
        candidates = index.all_items()
        project = self.project([self.clip(old)])
        with patch.object(bridge, 'probe_media_duration', return_value=14), \
             patch.object(bridge, '_cached_or_probed_montage_duration', return_value=30), \
             patch.object(bridge, '_replacement_candidates_for_clip', return_value=candidates):
            self.assertEqual(bridge._complete_project_visual_tail(project, index, self.settings), 2)
        self.assertEqual([(clip.source_start, clip.duration) for clip in project.clips], [(0, 6), (9, 4), (9, 4)])
        missing = self.project([TimelineClip(str(self.root / 'missing.mp4'), 'Погрузка', 'seaport cargo cranes ships', 6)])
        with patch.object(bridge, '_validated_montage_clip_duration', side_effect=lambda path: 30 if path.is_file() else 0):
            self.assertEqual(bridge._repair_missing_project_clips(missing, lambda *_: candidates), 0)

    def test_external_raw_title_cannot_escape_via_neutral_cached_name(self):
        cached = self.item('cached_port.mp4')
        raw = {'title': 'Iran oil tanker port', 'url': 'https://example.test/source.mp4'}
        self.settings.montage_auto_web = True
        with patch.object(bridge, 'search_wikimedia_videos', return_value=[raw]), \
             patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {raw['url']: cached}, clear=True):
            self.assertIsNone(bridge._download_scene_fallback({'visual_query_en': 'seaport cargo cranes ships'},
                                                            self.settings, self.index()))

    def test_external_cached_return_rechecks_current_whole_story(self):
        cached = self.item('Iran_cached_port.mp4')
        raw = {'title': 'Oil tanker port', 'url': 'https://example.test/source.mp4'}
        self.settings.montage_auto_web = True
        with patch.object(bridge, 'search_wikimedia_videos', return_value=[raw]), \
             patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {raw['url']: cached}, clear=True):
            self.assertIsNone(bridge._download_scene_fallback({'visual_query_en': 'seaport cargo cranes ships'},
                                                            self.settings, self.index()))

    def test_external_iran_is_permitted_when_whole_story_mentions_iran(self):
        cached = self.item('Iran_cached_port.mp4')
        raw = {'title': 'Iran oil tanker port', 'url': 'https://example.test/source.mp4'}
        self.settings.montage_auto_web = True
        with patch.object(bridge, 'search_wikimedia_videos', return_value=[raw]), \
             patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {raw['url']: cached}, clear=True):
            self.assertIs(bridge._download_scene_fallback({'visual_query_en': 'seaport cargo cranes ships'},
                                                         self.settings, self.index(story='Также упоминается Иран')), cached)

    def test_legacy_direct_download_uses_real_narration_when_no_full_story_context_exists(self):
        cached = self.item('Iran_cached_port.mp4')
        raw = {'title': 'Iran oil tanker port', 'url': 'https://example.test/source.mp4'}
        self.settings.montage_auto_web = True
        with patch.object(bridge, 'search_wikimedia_videos', return_value=[raw]), \
             patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {raw['url']: cached}, clear=True):
            self.assertIs(bridge._download_scene_fallback(
                {'visual_query_en': 'seaport cargo cranes ships', 'narration': 'Обсуждается Иран'},
                self.settings, SimpleNamespace()), cached)

    def test_external_download_and_retained_cut_are_rechecked_before_publication(self):
        raw = {'title': 'Oil tanker port', 'url': 'https://example.test/unlabeled-source.mp4'}
        self.settings.montage_auto_web = True
        self.settings.footage_download_folder = str(self.root / 'downloads')
        self.settings.cutter_output_folder = str(self.root / 'cuts')
        for source_name, source_url, cut_name in [
            ('download.mp4', 'https://example.test/Iran-source.mp4', 'neutral_cut.mp4'),
            ('download.mp4', '', 'Iran_cut.mp4'),
        ]:
            with self.subTest(source_url=source_url, cut=cut_name):
                downloaded = self.item(source_name, source_url=source_url)
                cut = self.item(cut_name)
                with patch.object(bridge, 'search_wikimedia_videos', return_value=[raw]), \
                     patch.dict(bridge._EXTERNAL_FOOTAGE_CACHE, {}, clear=True), \
                     patch.object(bridge, 'download_footage', return_value=downloaded), \
                     patch.object(bridge, 'cut_single_clip', return_value=Path(cut.path)), \
                     patch.object(bridge, '_production_staging_folder', side_effect=lambda folder, *_: Path(folder) / 'staging'), \
                     patch.object(bridge, '_publish_staged_paths', side_effect=AssertionError('forbidden cut must not be published')):
                    self.assertIsNone(bridge._download_scene_fallback({'visual_query_en': 'seaport cargo cranes ships'},
                                                                    self.settings, self.index()))
