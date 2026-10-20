"""Archive rotation contracts: no decoded media or original/user-data writes."""
import threading
import unittest
from unittest.mock import patch

from scriptor import bridge
from tests import test_footage_political_context as contracts


class ArchiveDiversityTests(unittest.TestCase):
    def setUp(self):
        self.fixture=contracts.PoliticalContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def direct(self):
        item=self.fixture.item('Belarus_peaceful_protest_placards.mp4')
        item._visual_assessor=lambda _q,start,duration,**_kw: {
            'relation':'direct','dominant_kind':'peaceful_protest',
            'source_start':start,'duration':duration,'source':'synthetic-contract'}
        return item

    def test_mentioned_portraits_diversify_repeated_action_without_leaking_claims(self):
        direct=self.direct()
        portraits=[self.fixture.item('Lukashenko_address_source_a.mp4'),
                   self.fixture.item('Lukashenko_interview_source_b.mp4')]
        usage={'lock':threading.RLock(),'claims':{},'placements':{},'windows':{}}
        original=bridge.prepare_montage
        with patch.object(bridge,'prepare_montage',side_effect=lambda payload:original(
                {**payload,'_batchFootageUsage':usage})):
            project=self.fixture.prepare('В Беларуси прошёл митинг. Лукашенко прокомментировал требования.',
                ['Belarus peaceful civilian protest placards street rally']*4,[direct,*portraits])
        self.assertEqual(direct.path,project.clips[0].path,'Fresh exact action still wins')
        self.assertEqual(3,len({c.path for c in project.clips}))
        self.assertEqual(direct.path,project.clips[-1].path,'After fresh archive exhaustion retain original exact fallback')
        self.assertEqual(4,sum(len(values) for values in usage['placements'].values()),'Only final selected material may consume placements')
        for clip in project.clips[1:3]:
            context=clip.selection_diagnostics['political_context']
            self.assertTrue(context['archival_context'])
            self.assertFalse(context['event_confirmed'])
            self.assertEqual('Belarus peaceful civilian protest placards street rally',context['requested_visual_query'])

    def test_failed_archive_probe_retains_original_query_and_valid_action(self):
        direct=self.direct()
        mixed=self.fixture.item('Lukashenko_Putin_mixed_meeting.mp4')
        query='Belarus peaceful protest placards'
        project=self.fixture.prepare('В Беларуси митинг. Лукашенко прокомментировал требования.',
                                     [query]*3,[direct,mixed])
        self.assertEqual([direct.path]*3,[c.path for c in project.clips])
        self.assertEqual([query]*3,[c.visual_query_en for c in project.clips])
        self.assertTrue(all('political_context' not in c.selection_diagnostics for c in project.clips))

    def test_used_portraits_still_break_adjacent_action_replay_after_pool_exhaustion(self):
        direct=self.direct()
        portraits=[self.fixture.item('Lukashenko_address_source_a.mp4'),
                   self.fixture.item('Lukashenko_interview_source_b.mp4')]
        project=self.fixture.prepare('В Беларуси митинг. Лукашенко прокомментировал требования.',
            ['Belarus peaceful protest placards']*7,[direct,*portraits])
        self.assertEqual(3,len({c.path for c in project.clips}))
        self.assertTrue(all(a.path!=b.path for a,b in zip(project.clips,project.clips[1:])))

    def test_country_alone_never_invents_portrait_to_raise_diversity(self):
        direct=self.direct()
        project=self.fixture.prepare('В Беларуси прошёл мирный митинг.',
            ['Belarus peaceful protest placards']*3,[direct,self.fixture.item('Lukashenko_address.mp4')])
        self.assertEqual([direct.path]*3,[c.path for c in project.clips])

if __name__=='__main__':unittest.main()
