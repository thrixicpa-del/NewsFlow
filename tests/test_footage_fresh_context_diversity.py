"""Synthetic selector contracts; no media decoding, models, or production data."""
import os
import tempfile
import unittest
from pathlib import Path

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.footage import FootageItem


class FreshContextDiversityTests(unittest.TestCase):
    query = "seaport cargo cranes ships"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ["NEWSFLOW_TEST_ROOT"])
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def hit(self, name, *, relation="context", score=.4, family=None, duration=8., person=None,
            dominant_kind="port"):
        path = self.root / name
        path.write_bytes(b"disposable selector evidence; not a media file")
        item = FootageItem(str(path), name,
                           tags=["press-conference" if dominant_kind in {"official", "meeting"}
                                 else "port-logistics"])

        def assess(_query, start, duration, **_kwargs):
            return {"relation": relation, "source": "synthetic-contract",
                    "source_start": start, "duration": duration,
                    "dominant_kind": dominant_kind,
                    "event_confirmed": False, "motion_verified": False}

        item._visual_assessor = assess
        if person:
            stat = path.stat()
            item.person_evidence = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                "observations": [{"person_id": person, "source": "manual", "complete": True,
                                  "start": 0., "end": 8.}]}
        return SearchHit(item, score, duration, source_family=family or name)

    def select(self, hits, *, paths=None, families=None, history_paths=None,
               history_families=None, previous="", query=None, **overrides):
        options = {"strict_hits":hits,"relaxed_hits":[],"category_hits":[],"safe_context_hits":[],
            "fallback_hits":[],"required_duration":6.,"assessment_duration":6.,"match_threshold":.22,
            "used_paths":set(history_paths or ()),"used_families":set(history_families or ()),
            "project_used_paths":set(paths or ()),"project_used_families":set(families or ()),
            "reserved_paths":set(),"reserved_families":set(),"source_exists":lambda _:True,
            "source_duration":lambda _:8.,"immediately_previous_path":previous,
            "diversity_seed":"fresh-context-contract","allow_safe_reuse":True}
        options.update(overrides)
        return bridge._select_montage_candidate(query or self.query, **options)

    def key(self, hit):
        return bridge._montage_clip_key(hit.item.path)

    def test_fresh_context_precedes_repeated_direct_path(self):
        direct = self.hit("used_ship.mp4", relation="direct", score=.9)
        context = self.hit("unseen_warehouse.mp4")
        selected = self.select([direct, context], paths={self.key(direct)},
                               families={direct.source_family})
        self.assertEqual(context.item.path, selected.item.path)
        self.assertEqual("SAFE_CONTEXT", selected.fallback_level)

    def test_unseen_direct_sibling_precedes_new_context_family(self):
        used = self.hit("used_ship.mp4", relation="direct", score=.9, family="ships")
        sibling = self.hit("unseen_ship.mp4", relation="direct", family="ships")
        context = self.hit("new_warehouse.mp4", score=.95)
        selected = self.select([used, sibling, context], paths={self.key(used)}, families={"ships"})
        self.assertEqual(sibling.item.path, selected.item.path)

    def test_new_family_precedes_unseen_sibling_when_action_evidence_matches(self):
        used = self.hit("used_ship.mp4", relation="direct", family="ships")
        sibling = self.hit("unseen_ship.mp4", relation="direct", score=.95, family="ships")
        fresh = self.hit("new_ship_family.mp4", relation="direct")
        selected = self.select([used, sibling, fresh], paths={self.key(used)}, families={"ships"})
        self.assertEqual(fresh.item.path, selected.item.path)

    def test_fresh_direct_in_later_retrieval_precedes_fresh_strict_context(self):
        context = self.hit("warehouse.mp4", score=.95)
        direct = self.hit("ship.mp4", relation="direct")
        selected = self.select([context], relaxed_hits=[direct])
        self.assertEqual(direct.item.path, selected.item.path)

    def test_heterogeneous_pool_exhausts_unseen_paths_before_repetition(self):
        direct = [self.hit(f"ship_{number}.mp4", relation="direct", score=.9)
                  for number in range(2)]
        contexts = [self.hit(f"warehouse_{number:02}.mp4", score=.4 + number * .001)
                    for number in range(30)]
        hits = direct + contexts
        for count in (24, 50):
            with self.subTest(scene_count=count):
                paths, families, sequence = set(), set(), []
                for position in range(count):
                    selected = self.select(hits, paths=paths, families=families,
                        previous=sequence[-1] if sequence else "",
                        position_bucket=bridge._montage_position_bucket(position, count))
                    key = bridge._montage_clip_key(selected.item.path)
                    if position < len(hits):
                        self.assertNotIn(key, paths, f"repeated at scene {position + 1} before pool exhaustion")
                    if sequence:
                        self.assertNotEqual(sequence[-1], key)
                    paths.add(key)
                    families.add(selected.source_family)
                    sequence.append(key)
                self.assertEqual(min(count, len(hits)), len(paths))

    def test_repeated_confirmed_identity_precedes_fresh_probable_or_unknown_context(self):
        confirmed = self.hit("checked_statement.mp4", relation="direct", person="pashinyan",
                             dominant_kind="official")
        for name in ("Nikol Pashinyan meeting.mp4", "anonymous_delegation.mp4"):
            with self.subTest(name=name):
                context = self.hit(name, score=.95, dominant_kind="meeting")
                selected = self.select([confirmed, context], query="Nikol Pashinyan official statement",
                    paths={self.key(confirmed)}, families={confirmed.source_family})
                self.assertEqual(confirmed.item.path, selected.item.path)
                self.assertEqual("confirmed", selected.diagnostics["person"]["status"])

    def test_single_direct_source_rotates_with_context_after_unseen_pool_exhaustion(self):
        direct = self.hit("sole_checked_ship.mp4", relation="direct", score=.9)
        contexts = [self.hit("checked_warehouse_a.mp4", score=.4),
                    self.hit("checked_warehouse_b.mp4", score=.41)]
        hits = [direct, *contexts]
        for count in (24, 50):
            with self.subTest(scene_count=count):
                paths, families, sequence = set(), set(), []
                for position in range(count):
                    selected = self.select(hits, paths=paths, families=families,
                        previous=sequence[-1] if sequence else "",
                        position_bucket=bridge._montage_position_bucket(position, count))
                    key = bridge._montage_clip_key(selected.item.path)
                    if position < 3:
                        self.assertNotIn(key, paths)
                    if sequence:
                        self.assertNotEqual(sequence[-1], key,
                            f"adjacent repeat at scene {position + 1} despite checked alternatives")
                    paths.add(key)
                    families.add(selected.source_family)
                    sequence.append(key)
                self.assertEqual(3, len(paths))

    def test_immediately_previous_confirmed_identity_beats_probable_or_unknown_context(self):
        confirmed = self.hit("previous_checked_statement.mp4", relation="direct",
                             person="pashinyan", dominant_kind="official")
        for name in ("Nikol Pashinyan fresh meeting.mp4", "fresh_anonymous_delegation.mp4"):
            with self.subTest(name=name):
                context = self.hit(name, score=.95, dominant_kind="meeting")
                selected = self.select([confirmed, context],
                    query="Nikol Pashinyan official statement",
                    paths={self.key(confirmed)}, families={confirmed.source_family},
                    previous=confirmed.item.path)
                self.assertEqual(confirmed.item.path, selected.item.path)
                self.assertEqual("confirmed", selected.diagnostics["person"]["status"])

    def test_fresh_wrong_person_cannot_displace_repeated_requested_identity(self):
        requested = self.hit("checked_statement.mp4", relation="direct", person="pashinyan",
                             dominant_kind="official")
        wrong = self.hit("wrong_person.mp4", relation="direct", person="putin", score=.95,
                         dominant_kind="official")
        selected = self.select([requested, wrong], query="Nikol Pashinyan official statement",
            paths={self.key(requested)}, families={requested.source_family})
        self.assertEqual(requested.item.path, selected.item.path)

    def test_fresh_context_cannot_bypass_hard_guards(self):
        for defect in ("below-floor", "contradiction", "missing", "short-source",
                       "short-declared", "screen-blocked", "foreign-geography"):
            with self.subTest(defect=defect):
                direct = self.hit(f"used_{defect}.mp4", relation="direct", score=.9)
                fresh = self.hit("Russia_warehouse.mp4" if defect == "foreign-geography"
                                 else f"fresh_{defect}.mp4",
                    relation="contradiction" if defect == "contradiction" else "context",
                    score=.01 if defect == "below-floor" else .95,
                    duration=2. if defect == "short-declared" else 8.)
                selected = self.select([direct, fresh], paths={self.key(direct)},
                    families={direct.source_family},
                    query="Ukraine seaport cargo cranes ships" if defect == "foreign-geography" else None,
                    source_exists=lambda item,kind=defect,path=fresh.item.path: kind != "missing" or item.path != path,
                    source_duration=lambda item,kind=defect,path=fresh.item.path: 2. if kind == "short-source" and item.path == path else 8.,
                    source_allowed=lambda item,kind=defect,path=fresh.item.path: kind != "screen-blocked" or item.path != path)
                self.assertEqual(direct.item.path, selected.item.path)

    def test_each_retrieval_level_keeps_its_score_floor_for_fresh_context(self):
        floors = {"STRICT_MATCH": .22, "RELAXED_SEMANTIC": .121,
                  "CATEGORY_MATCH": .099, "SAFE_CONTEXT": .077}
        arguments = {"STRICT_MATCH": "strict_hits", "RELAXED_SEMANTIC": "relaxed_hits",
                     "CATEGORY_MATCH": "category_hits", "SAFE_CONTEXT": "safe_context_hits"}
        direct = self.hit("used_ship.mp4", relation="direct", score=.9)
        for level, floor in floors.items():
            for accepted in (False, True):
                with self.subTest(level=level, accepted=accepted):
                    context = self.hit(f"warehouse_{level}_{accepted}.mp4",
                                       score=floor + (1e-9 if accepted else -1e-9))
                    pools = {arguments[level]: [context]}
                    pools["strict_hits"] = [direct, *pools.get("strict_hits", [])]
                    selected = self.select([], paths={self.key(direct)},
                        families={direct.source_family}, **pools)
                    expected = context if accepted else direct
                    self.assertEqual(expected.item.path, selected.item.path)

    def test_other_project_history_does_not_force_current_video_path_repetition(self):
        direct = self.hit("used_ship.mp4", relation="direct", score=.9)
        context = self.hit("historical_warehouse.mp4")
        selected = self.select([direct, context], paths={self.key(direct)},
            families={direct.source_family}, history_paths={self.key(context)},
            history_families={context.source_family},
            reserved_paths={self.key(context)}, reserved_families={context.source_family})
        self.assertEqual(context.item.path, selected.item.path)
        self.assertTrue(selected.reused)

    def test_sole_safe_source_completes_repeated_beats(self):
        only = self.hit("sole_ship.mp4", relation="direct")
        paths, families = set(), set()
        for _ in range(5):
            selected = self.select([only], paths=paths, families=families,
                                   previous=only.item.path if paths else "")
            self.assertEqual(only.item.path, selected.item.path)
            paths.add(self.key(only))
            families.add(only.source_family)

    def test_similar_stories_use_unseen_siblings_before_replaying_history(self):
        hits = [self.hit(f"logistics_{n}.mp4", relation="direct" if n < 2 else "context",
                         score=.9 if n < 2 else .4, family=f"source-{n // 2}")
                for n in range(12)]
        history_paths, history_families, stories = set(), set(), []
        for story in range(2):
            paths, families, sequence = set(), set(), []
            for scene in range(6):
                selected = self.select(hits, paths=paths, families=families,
                    history_paths=history_paths, history_families=history_families,
                    previous=sequence[-1] if sequence else "",
                    diversity_seed=f"similar-story-{story}",
                    position_bucket=bridge._montage_position_bucket(scene, 6))
                key = bridge._montage_clip_key(selected.item.path)
                self.assertNotIn(key, paths)
                self.assertNotIn(key, history_paths, "unused safe siblings remain in known families")
                paths.add(key)
                families.add(selected.source_family)
                sequence.append(key)
            stories.append(paths)
            history_paths.update(paths)
            history_families.update(families)
        self.assertFalse(stories[0] & stories[1])

    def test_historical_confirmed_person_beats_fresh_unknown_person(self):
        checked = self.hit("historical_statement.mp4", relation="direct", person="pashinyan",
                           dominant_kind="official")
        unknown = self.hit("fresh_delegation.mp4", score=.95, dominant_kind="meeting")
        selected = self.select([checked, unknown], query="Nikol Pashinyan official statement",
            history_paths={self.key(checked)}, history_families={checked.source_family})
        self.assertEqual(checked.item.path, selected.item.path)
        self.assertEqual("confirmed", selected.diagnostics["person"]["status"])
