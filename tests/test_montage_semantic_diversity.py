import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scriptor import bridge
from scriptor.ai_index import SearchHit, source_family_identity
from scriptor.footage import FootageItem
from scriptor.timeline import TimelineClip, TimelineProject


class MontageSemanticDiversityTests(unittest.TestCase):
    @staticmethod
    def _select(*, query="oil tanker port", strict=(), relaxed=(), category=(), context=(),
                used_paths=None, used_families=None, project_paths=None, project_families=None,
                reserved_paths=None, reserved_families=None, bucket="EARLY", family_buckets=None,
                seed="seed", allow_safe_reuse=True, source_allowed=None):
        try:
            return bridge._select_montage_candidate(
                query,
                strict_hits=list(strict),
                relaxed_hits=list(relaxed),
                category_hits=list(category),
                safe_context_hits=list(context),
                fallback_hits=[],
                required_duration=6.0,
                match_threshold=.22,
                used_paths=set(used_paths or ()),
                used_families=set(used_families or ()),
                project_used_paths=set(project_paths or ()),
                project_used_families=set(project_families or ()),
                reserved_paths=set(reserved_paths or ()),
                reserved_families=set(reserved_families or ()),
                source_exists=lambda item: "missing" not in item.path,
                source_duration=lambda item: 4.0 if "short" in item.path else 30.0,
                source_allowed=source_allowed,
                position_bucket=bucket,
                batch_family_buckets=family_buckets or {},
                diversity_seed=seed,
                allow_safe_reuse=allow_safe_reuse,
            )
        except TypeError as error:
            raise AssertionError(f"selector does not expose MONTAGE-003 contract: {error}") from error

    def test_fallback_ladder_skips_missing_and_short_exact_candidates(self):
        missing = FootageItem("D:/oil/missing.mp4", "missing.mp4", tags=["oil-tanker-port"])
        short = FootageItem("D:/oil/short.mp4", "short.mp4", tags=["oil-tanker-port"])
        context = FootageItem("D:/oil/port-wide.mp4", "port-wide.mp4", tags=["port-logistics"])

        selection = self._select(
            strict=[SearchHit(missing, .95, 6.0), SearchHit(short, .90, 6.0)],
            context=[SearchHit(context, .18, 30.0, source_family="port-family")],
        )

        self.assertEqual(selection.item.path, context.path)
        self.assertEqual(selection.fallback_level, "SAFE_CONTEXT")
        self.assertGreaterEqual(selection.diagnostics["rejected_missing"], 1)
        self.assertGreaterEqual(selection.diagnostics["rejected_duration"], 1)

    def test_ladder_reports_relaxed_and_category_levels_explicitly(self):
        relaxed = FootageItem("D:/oil/relaxed.mp4", "relaxed.mp4", tags=["oil-tanker-port"])
        category = FootageItem("D:/oil/category.mp4", "category.mp4", tags=["port-logistics"])

        relaxed_result = self._select(relaxed=[SearchHit(relaxed, .17, 30.0)])
        category_result = self._select(category=[SearchHit(category, .16, 30.0)])

        self.assertEqual(relaxed_result.fallback_level, "RELAXED_SEMANTIC")
        self.assertEqual(category_result.fallback_level, "CATEGORY_MATCH")

    def test_semantic_safety_remains_authoritative_at_every_level(self):
        agriculture = FootageItem(
            "D:/unsafe/tractor.mp4", "tractor harvest.mp4", tags=["agriculture-farming"]
        )
        office = FootageItem(
            "D:/unsafe/podium.mp4", "government podium.mp4", tags=["political-office"]
        )
        safe = FootageItem(
            "D:/safe/emergency.mp4", "damaged city.mp4", tags=["emergency-aftermath"]
        )

        selection = self._select(
            query="frontline missile strike damaged buildings",
            strict=[SearchHit(agriculture, .99, 30.0), SearchHit(office, .98, 30.0)],
            context=[SearchHit(safe, .12, 30.0, source_family="safe-family")],
        )

        self.assertEqual(selection.item.path, safe.path)
        self.assertEqual(selection.fallback_level, "SAFE_CONTEXT")
        self.assertEqual(selection.diagnostics["unique_rejected_safety"], 2)

    def test_oil_context_rejects_unrelated_agriculture_even_with_higher_score(self):
        agriculture = FootageItem(
            "D:/unsafe/tractor.mp4", "tractor harvest.mp4", tags=["agriculture-farming"]
        )
        port = FootageItem(
            "D:/safe/tanker.mp4", "oil tanker port.mp4", tags=["oil-tanker-port"]
        )

        selection = self._select(
            query="oil tanker traffic through the Strait of Hormuz",
            strict=[SearchHit(agriculture, .99, 30.0)],
            context=[SearchHit(port, .14, 30.0, source_family="port-family")],
        )

        self.assertEqual(selection.item.path, port.path)
        self.assertEqual(selection.fallback_level, "SAFE_CONTEXT")

    def test_hormuz_context_rejects_english_ukraine_metadata(self):
        wrong_country = FootageItem(
            "D:/unsafe/ukraine_oil_tanker.mp4", "ukraine oil tanker.mp4"
        )
        safe = FootageItem("D:/safe/hormuz.mp4", "Persian Gulf tanker.mp4")

        selection = self._select(
            query="Strait of Hormuz oil tankers Persian Gulf",
            strict=[SearchHit(wrong_country, .99, 30.0)],
            context=[SearchHit(safe, .14, 30.0, source_family="hormuz-family")],
        )

        self.assertEqual(selection.item.path, safe.path)
        self.assertEqual(selection.diagnostics["unique_rejected_safety"], 1)

    def test_named_person_context_never_substitutes_another_named_politician(self):
        wrong_person = FootageItem("D:/unsafe/trump.mp4", "Donald Trump press conference.mp4")
        requested_person = FootageItem("D:/safe/putin.mp4", "Vladimir Putin meeting.mp4")

        selection = self._select(
            query="Vladimir Putin comments at a press conference",
            strict=[SearchHit(wrong_person, .99, 30.0)],
            context=[SearchHit(requested_person, .14, 30.0, source_family="putin-family")],
        )

        self.assertEqual(selection.item.path, requested_person.path)
        self.assertEqual(selection.diagnostics["unique_rejected_safety"], 1)

    def test_explicit_entity_focus_rejects_disjoint_government_geography(self):
        query = "Washington US government changes support conditions for Ukraine"
        wrong_summit = FootageItem(
            "D:/wrong/processed_пашинян путин саммит_slice_9.mp4",
            "Pashinyan Putin summit.mp4",
            tags=["press-conference"],
        )
        wrong_iran = FootageItem(
            "D:/wrong/iran-corridor.mp4",
            "government corridor.mp4",
            tags=["iran-government-tehran", "parliament-government"],
        )
        right = FootageItem(
            "D:/right/white-house.mp4",
            "White House briefing.mp4",
            tags=["us-government-washington", "press-conference"],
        )

        self.assertFalse(bridge._semantic_clip_ok(query, wrong_summit))
        self.assertFalse(bridge._semantic_clip_ok(query, wrong_iran))
        self.assertTrue(bridge._semantic_clip_ok(query, right))

    def test_safe_reuse_prefers_the_less_repeated_safe_family(self):
        frequent = FootageItem(
            "D:/safe/frequent/shot.mp4", "frequent tanker.mp4", tags=["oil-tanker-port"],
        )
        alternate = FootageItem(
            "D:/safe/alternate/shot.mp4", "alternate tanker.mp4", tags=["oil-tanker-port"],
        )
        frequent_key = bridge._montage_clip_key(frequent.path)
        alternate_key = bridge._montage_clip_key(alternate.path)
        selection = self._select(
            strict=[
                SearchHit(frequent, .55, 30.0, source_family="family-frequent"),
                SearchHit(alternate, .50, 30.0, source_family="family-alternate"),
            ],
            used_paths={frequent_key, alternate_key},
            used_families={"family-frequent", "family-alternate"},
            project_paths={frequent_key, alternate_key},
            project_families={"family-frequent", "family-alternate"},
            family_buckets={
                "family-frequent": ["EARLY", "EARLY", "MIDDLE", "MIDDLE", "LATE"],
                "family-alternate": ["EARLY"],
            },
            bucket="LATE",
        )

        self.assertEqual(selection.source_family, "family-alternate")
        self.assertEqual(selection.fallback_level, "SAFE_REUSE")

    def test_all_ladder_queries_use_one_batched_index_request(self):
        ladders = [
            bridge._montage_query_ladder("oil tanker traffic"),
            bridge._montage_query_ladder("oil tanker insurance rates"),
        ]

        class FakeIndex:
            def __init__(self):
                self.calls = []

            def search_many(self, queries, limit=20):
                self.calls.append((list(queries), limit))
                return {query: [] for query in queries}

        index = FakeIndex()
        try:
            result = bridge._montage_search_ladders(index, ladders, limit=256)
        except AttributeError as error:
            self.fail(f"batched ladder retrieval is missing: {error}")

        self.assertEqual(len(index.calls), 1)
        self.assertEqual(index.calls[0][1], 256)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(set(bridge._MONTAGE_FALLBACK_LEVELS) <= set(row) for row in result))

    def test_scarce_library_completes_with_truthful_safe_reuse(self):
        only = FootageItem("D:/safe/only.mp4", "only.mp4", tags=["oil-tanker-port"])
        hit = SearchHit(only, .30, 30.0, source_family="only-family")

        selection = self._select(
            strict=[hit],
            used_paths={bridge._montage_clip_key(only.path)},
            used_families={"only-family"},
            project_paths={bridge._montage_clip_key(only.path)},
            project_families={"only-family"},
            reserved_paths={bridge._montage_clip_key(only.path)},
            reserved_families={"only-family"},
            family_buckets={"only-family": ["EARLY", "MIDDLE"]},
            bucket="LATE",
        )

        self.assertEqual(selection.item.path, only.path)
        self.assertEqual(selection.fallback_level, "SAFE_REUSE")
        self.assertTrue(selection.reused)
        self.assertIn("единственный", selection.position_rotation_reason)

    def test_labor_strike_does_not_expand_into_military_fallback(self):
        ladder = bridge._montage_query_ladder("workers labor strike at factory gate picket line")
        expanded = " ".join([
            *ladder["CATEGORY_MATCH"],
            *ladder["SAFE_CONTEXT"],
        ]).casefold()

        self.assertNotIn("military", expanded)
        self.assertNotIn("battle", expanded)
        self.assertNotIn("damaged buildings", expanded)

        military = FootageItem(
            "D:/unsafe/frontline.mp4", "frontline.mp4", tags=["frontline-combat"]
        )
        workers = FootageItem(
            "D:/safe/workers.mp4", "workers picket.mp4", tags=["workers-strike"]
        )
        selection = self._select(
            query="workers labor strike at factory gate picket line",
            strict=[SearchHit(military, .95, 30.0, source_family="military")],
            category=[SearchHit(workers, .20, 30.0, source_family="workers")],
        )
        self.assertEqual(selection.item.path, workers.path)
        self.assertEqual(selection.fallback_level, "CATEGORY_MATCH")

    def test_specific_semantic_tag_mismatch_cannot_beat_safe_reuse(self):
        safe = FootageItem("D:/safe/tanker.mp4", "oil tanker port.mp4", tags=["oil-tanker-port"])
        wrong = FootageItem(
            "D:/unsafe/hospital.mp4", "hospital doctors surgery.mp4", tags=["healthcare-hospital"]
        )
        safe_key = bridge._montage_clip_key(safe.path)

        selection = self._select(
            strict=[SearchHit(safe, .45, 30.0, source_family="oil-family")],
            context=[SearchHit(wrong, .95, 30.0, source_family="hospital-family")],
            used_paths={safe_key},
            used_families={"oil-family"},
            project_paths={safe_key},
            project_families={"oil-family"},
            reserved_paths={safe_key},
            reserved_families={"oil-family"},
        )

        self.assertEqual(selection.item.path, safe.path)
        self.assertEqual(selection.fallback_level, "SAFE_REUSE")
        self.assertTrue(selection.reused)

    def test_near_zero_unknown_context_cannot_beat_safe_reuse(self):
        safe = FootageItem("D:/safe/tanker.mp4", "oil tanker port.mp4", tags=["oil-tanker-port"])
        unknown = FootageItem("D:/unknown/random.mp4", "random scene.mp4", tags=[])
        safe_key = bridge._montage_clip_key(safe.path)

        selection = self._select(
            strict=[SearchHit(safe, .45, 30.0, source_family="oil-family")],
            context=[SearchHit(unknown, .01, 30.0, source_family="unknown-family")],
            used_paths={safe_key},
            used_families={"oil-family"},
            project_paths={safe_key},
            project_families={"oil-family"},
            reserved_paths={safe_key},
            reserved_families={"oil-family"},
        )

        self.assertEqual(selection.item.path, safe.path)
        self.assertEqual(selection.fallback_level, "SAFE_REUSE")

    def test_nato_cyber_scene_rejects_unrelated_specific_semantic_family(self):
        wrong = FootageItem(
            "D:/wrong/tanker.mp4", "oil tanker port.mp4", tags=["oil-tanker-port", "port-logistics"]
        )
        frontline = FootageItem(
            "D:/wrong/frontline.mp4", "frontline soldiers.mp4", tags=["frontline-combat"]
        )
        right = FootageItem(
            "D:/right/cyber.mp4", "network security operations.mp4",
            tags=["cybersecurity-network", "nato-alliance"],
        )
        query = "NATO hybrid cyber attack Europe network security"

        self.assertFalse(bridge._montage_has_war_action(query))
        self.assertFalse(bridge._semantic_clip_ok(query, wrong))
        self.assertFalse(bridge._semantic_clip_ok(query, frontline))
        self.assertTrue(bridge._semantic_clip_ok(query, right))

    def test_screen_text_safety_rejects_high_score_candidate(self):
        blocked = FootageItem("D:/unsafe/english.mp4", "english lower third.mp4", tags=["political-office"])
        safe = FootageItem("D:/safe/clean.mp4", "clean government.mp4", tags=["political-office"])

        selection = self._select(
            query="government press conference",
            strict=[
                SearchHit(blocked, .60, 30.0, source_family="blocked-family"),
                SearchHit(safe, .35, 30.0, source_family="safe-family"),
            ],
            source_allowed=lambda item: item.path != blocked.path,
        )

        self.assertEqual(selection.item.path, safe.path)
        self.assertGreaterEqual(selection.diagnostics["unique_rejected_safety"], 1)

    def test_cross_video_family_rotation_penalizes_near_equal_reuse(self):
        reused = FootageItem("D:/old/shot.mp4", "government.mp4", tags=["parliament-government"])
        fresh = FootageItem("D:/fresh/shot.mp4", "government.mp4", tags=["parliament-government"])

        selection = self._select(
            query="government parliament officials",
            strict=[
                SearchHit(reused, .400, 30.0, source_family="old-family"),
                SearchHit(fresh, .395, 30.0, source_family="fresh-family"),
            ],
            family_buckets={"old-family": ["MIDDLE"]},
            bucket="EARLY",
            seed="cross-video-diversity",
        )

        self.assertEqual(selection.source_family, "fresh-family")

    def test_rotation_never_overrides_a_materially_better_same_level_match(self):
        strong = FootageItem("D:/safe/strong.mp4", "oil tanker port.mp4", tags=["oil-tanker-port"])
        weak = FootageItem("D:/safe/weak.mp4", "generic port.mp4", tags=["port-logistics"])

        selection = self._select(
            strict=[
                SearchHit(strong, .50, 30.0, source_family="family-a"),
                SearchHit(weak, .46, 30.0, source_family="family-b"),
            ],
            family_buckets={"family-a": ["EARLY", "EARLY", "EARLY"]},
            bucket="EARLY",
            seed="quality-first",
        )

        self.assertEqual(selection.item.path, strong.path)

    def test_bridge_family_identity_matches_index_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cutter = root / "evening_report"
            first = cutter / "evening_report_0001.mp4"
            second = cutter / "evening_report_0002.mp4"
            generic_one = root / "clip_001.mp4"
            generic_two = root / "clip_002.mp4"

            self.assertEqual(bridge._montage_clip_family_key(str(first)), source_family_identity(first))
            self.assertEqual(bridge._montage_clip_family_key(str(second)), source_family_identity(second))
            self.assertEqual(
                bridge._montage_clip_family_key(str(first)),
                bridge._montage_clip_family_key(str(second)),
            )
            self.assertNotEqual(
                bridge._montage_clip_family_key(str(generic_one)),
                bridge._montage_clip_family_key(str(generic_two)),
            )

    def test_no_index_metadata_relevance_requires_actual_overlap(self):
        relevant = FootageItem("D:/oil_tanker_port.mp4", "oil_tanker_port.mp4", tags=[])
        unrelated = FootageItem("D:/hospital_doctors.mp4", "hospital_doctors.mp4", tags=[])

        self.assertGreater(bridge._montage_metadata_relevance("oil tanker port", relevant), 0.0)
        self.assertEqual(bridge._montage_metadata_relevance("oil tanker port", unrelated), 0.0)

    def test_broken_clip_recovery_stays_bounded_and_rejects_weak_context(self):
        weak = FootageItem(
            "D:/unsafe/hospital.mp4", "hospital doctors.mp4", tags=["healthcare-hospital"]
        )

        class WeakIndex:
            def search_many(self, queries, limit=20):
                self.queries = list(queries)
                self.limit = limit
                return [[SearchHit(weak, .95, 30.0, source_family="hospital-family")]]

            def all_items(self, *args, **kwargs):
                raise AssertionError("full-library fallback is forbidden")

        settings = SimpleNamespace(
            montage_match_threshold=.22,
            montage_auto_web=False,
            montage_exclude_english_text=False,
        )
        clip = TimelineClip("D:/missing.mp4", "voice", "oil tanker port", duration=6.0)
        self.assertEqual(bridge._replacement_candidates_for_clip(WeakIndex(), clip, settings), [])

        class EmptyIndex(WeakIndex):
            def search_many(self, queries, limit=20):
                return [[]]

        self.assertEqual(bridge._replacement_candidates_for_clip(EmptyIndex(), clip, settings), [])

    def test_position_rotation_prefers_family_unused_in_current_bucket(self):
        repeated_early = FootageItem("D:/a/shot.mp4", "a.mp4", tags=["oil-tanker-port"])
        rotated = FootageItem("D:/b/shot.mp4", "b.mp4", tags=["oil-tanker-port"])

        selection = self._select(
            strict=[
                SearchHit(repeated_early, .40, 30.0, source_family="family-a"),
                SearchHit(rotated, .40, 30.0, source_family="family-b"),
            ],
            family_buckets={"family-a": ["EARLY"], "family-b": ["MIDDLE"]},
            bucket="EARLY",
        )

        self.assertEqual(selection.source_family, "family-b")
        self.assertEqual(selection.position_bucket, "EARLY")

    def test_batch_history_is_frozen_and_family_claims_are_global_until_opening_fallback(self):
        usage = {"lock": __import__("threading").RLock(), "claims": {}}

        self.assertEqual(
            bridge._batch_history_paths(usage, ["D:/old/a.mp4"]),
            ("D:/old/a.mp4",),
        )
        self.assertEqual(
            bridge._batch_history_paths(usage, ["D:/old/a.mp4", "D:/new/in-batch.mp4"]),
            ("D:/old/a.mp4",),
        )

        self.assertTrue(bridge._claim_batch_family(usage, "family-a", "MIDDLE", 0))
        self.assertEqual(bridge._batch_reserved_families(usage, "EARLY"), {"family-a"})
        self.assertEqual(
            bridge._batch_reserved_families(usage, "EARLY", opening_only=True),
            set(),
        )
        self.assertFalse(bridge._claim_batch_family(usage, "family-a", "EARLY", 1))
        self.assertTrue(bridge._claim_batch_family(
            usage, "family-a", "EARLY", 1, allow_cross_bucket_reuse=True,
        ))
        self.assertEqual(
            bridge._batch_reserved_families(usage, "EARLY", opening_only=True),
            {"family-a"},
        )
        self.assertFalse(bridge._claim_batch_family(
            usage, "family-a", "EARLY", 2, allow_cross_bucket_reuse=True,
        ))

    def test_ten_similar_projects_do_not_repeat_the_same_opening_family(self):
        hits = [
            SearchHit(
                FootageItem(f"D:/safe/family-{number}/shot.mp4", f"shot-{number}.mp4",
                            tags=["oil-tanker-port"]),
                .50 - number * .001,
                30.0,
                source_family=f"family-{number}",
            )
            for number in range(24)
        ]
        used_paths: set[str] = set()
        used_families: set[str] = set()
        family_buckets: dict[str, list[str]] = {}
        openings = []

        for project in range(10):
            selection = self._select(
                strict=hits,
                used_paths=used_paths,
                used_families=used_families,
                reserved_paths=used_paths,
                reserved_families=used_families,
                family_buckets=family_buckets,
                bucket="EARLY",
                seed=f"project-{project}",
            )
            openings.append(selection.source_family)
            used_paths.add(bridge._montage_clip_key(selection.item.path))
            used_families.add(selection.source_family)
            family_buckets.setdefault(selection.source_family, []).append("EARLY")

        self.assertEqual(len(set(openings)), 10)

    def test_weighted_variation_is_reproducible_for_the_same_project_seed(self):
        hits = [
            SearchHit(
                FootageItem(f"D:/safe/family-{number}.mp4", f"family-{number}.mp4",
                            tags=["oil-tanker-port"]),
                .4,
                30.0,
                source_family=f"family-{number}",
            )
            for number in range(12)
        ]

        first = self._select(strict=hits, seed="stable-project")
        repeated = self._select(strict=hits, seed="stable-project")
        another_project = self._select(strict=hits, seed="another-project")

        self.assertEqual(first.source_family, repeated.source_family)
        self.assertNotEqual(first.source_family, another_project.source_family)

    def test_reused_long_source_gets_a_different_nonzero_window(self):
        try:
            first = bridge._montage_source_start(30.0, 6.0, [], "EARLY", "family-a", "seed")
            second = bridge._montage_source_start(30.0, 6.0, [first], "MIDDLE", "family-a", "seed")
        except AttributeError as error:
            self.fail(f"source-window rotation is missing: {error}")

        self.assertEqual(first, 0.0)
        self.assertGreater(second, 0.0)
        self.assertLessEqual(second + 6.0, 30.0)
        self.assertNotEqual(first, second)

    def test_timeline_persists_selection_diagnostics(self):
        try:
            clip = TimelineClip(
                "D:/safe/shot.mp4", "voice", "oil tanker", duration=6.0,
                source_start=8.0, fallback_level="SAFE_REUSE", source_family="family-a",
                reused=True, position_bucket="MIDDLE", position_rotation_reason="другой сегмент",
            )
        except TypeError as error:
            self.fail(f"timeline diagnostics are not persisted: {error}")

        self.assertEqual(clip.fallback_level, "SAFE_REUSE")
        self.assertEqual(clip.source_start, 8.0)
        self.assertTrue(clip.reused)

    def test_project_persists_summary_and_preparation_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.newsflow"
            try:
                project = TimelineProject(
                    "Тема",
                    selection_summary={"scenes": 12, "strict": 7, "semantic": 3, "reuse": 2},
                    preparation_metrics_ms={"retrieval": 4.2, "selection": 1.8, "total": 9.1},
                )
            except TypeError as error:
                self.fail(f"project summary is not persisted: {error}")
            project.save(path)
            reopened = TimelineProject.load(path)

        self.assertEqual(reopened.selection_summary["reuse"], 2)
        self.assertEqual(reopened.preparation_metrics_ms["retrieval"], 4.2)


if __name__ == "__main__":
    unittest.main()
