"""Opt-in deterministic selector comparison; labelled synthetic candidate pools."""
import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from itertools import pairwise
from pathlib import Path

from scriptor import bridge
from scriptor.ai_index import SearchHit
from scriptor.footage import FootageItem


@unittest.skipUnless(os.environ.get("NEWSFLOW_FOOTAGE_DIVERSITY"), "opt-in BASE/AFTER diversity comparison")
class FootageDiversityComparison(unittest.TestCase):
    def test_fixed_suitable_pools(self):
        result = []
        for parallel in (False, True):
            for fast in (False, True):
                for scarce in (False, True):
                    history_paths, history_families = set(), set()
                    history_lock = threading.RLock()
                    # Restore initial history between modes; retain it within each series.
                    pools = {}
                    count = 3 if scarce else 96
                    topics = (("diplomatic negotiations", "diplomatic-negotiations"),
                              ("data center servers cybersecurity", "technology-datacenter"))
                    if os.environ.get("NEWSFLOW_FOOTAGE_DIVERSITY_TOPICS") == "protest":
                        topics = (("peaceful civilian protest rally placards", "protest-crowd"),
                                  ("workers labor strike picket line", "workers-strike"),
                                  *topics)
                    for topic, tag in topics:
                        pools[topic] = [SearchHit(
                            FootageItem(f"/synthetic/{tag}/clip_{i:03}.mp4", f"clip_{i:03}.mp4", tags=[tag]),
                            .5 + (i % 5) * .001, 6, source_family=f"{tag}-{i // 2}",
                        ) for i in range(count)]

                    def make_video(number, pools=pools, fast=fast, history_lock=history_lock,
                                   history_paths=history_paths, history_families=history_families):
                        used, families, prepared = set(), set(), {}
                        sequence, sequence_families = [], []
                        for position in range(24):
                            query = list(pools)[(position // 3) % 2]
                            original = pools[query]
                            pool = [hit for hit in original if hit.item.path in prepared] if fast and position >= 12 else original
                            if not pool:
                                pool = original
                            with history_lock:
                                selection = bridge._select_montage_candidate(
                                    query, strict_hits=pool, fallback_hits=[], required_duration=6, match_threshold=.22,
                                    used_paths=set(history_paths), used_families=set(history_families),
                                    project_used_paths=used, project_used_families=families,
                                    reserved_paths=set(), reserved_families=set(), source_exists=lambda _: True,
                                    source_duration=lambda _: 6,
                                    immediately_previous_path=sequence[-1] if sequence else "",
                                    position_bucket=bridge._montage_position_bucket(position, 24),
                                    diversity_seed=f"fixed-video-{number}", allow_safe_reuse=True,
                                )
                                key = bridge._montage_clip_key(selection.item.path)
                                used.add(key)
                                families.add(selection.source_family)
                                history_paths.add(key)
                                history_families.add(selection.source_family)
                                prepared[selection.item.path] = selection
                            sequence.append(selection.item.path)
                            sequence_families.append(selection.source_family)
                        return sequence, sequence_families

                    if parallel:
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            sequences = list(executor.map(make_video, range(4)))
                    else:
                        sequences = [make_video(number) for number in range(4)]
                    rows = []
                    for paths, families in sequences:
                        adjacent = sum(a == b for a, b in pairwise(paths))
                        if not scarce:
                            self.assertEqual(adjacent, 0)
                        rows.append({"distinct_clips": len(set(paths)), "distinct_families": len(set(families)),
                                     "adjacent_repeats": adjacent,
                                     "repeated_triples": len(paths) - 2 - len(set(zip(paths, paths[1:], paths[2:]))),
                                     "actual_distinct_path_percent": round(len(set(paths)) / 24 * 100, 2)})
                    pairs = [(sequences[a][0], sequences[b][0]) for a in range(4) for b in range(a + 1, 4)]
                    result.append({"parallel": parallel, "fast_reuse": fast, "scarce": scarce,
                                   "configured_duration_target_percent": 50 if fast else None,
                                   "videos": rows,
                                   "pair_intersection_clips": [len(set(a) & set(b)) for a, b in pairs],
                                   "identical_openings": sum(a[:3] == b[:3] for a, b in pairs)})
        target = Path(os.environ["NEWSFLOW_FOOTAGE_DIVERSITY"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"scope": "deterministic suitable-pool selector/history simulation; no visual acceptance",
                                      "seed": "fixed-video-N", "topics": os.environ.get("NEWSFLOW_FOOTAGE_DIVERSITY_TOPICS", "original"),
                                      "results": result}, indent=2), encoding="utf-8")
