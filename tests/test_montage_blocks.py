"""Curated block selection keeps the existing voice scene map and isolated roots."""
from __future__ import annotations

import importlib
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import RLock

import pytest

from scriptor.timeline import TimelineClip, TimelineProject


@pytest.fixture
def selection():
    assert importlib.util.find_spec("scriptor.montage_blocks"), "curated block selection is missing"
    return importlib.import_module("scriptor.montage_blocks")


def scenes(count=3, duration=3):
    return [{"narration": f"Voice {i}", "visual_query_en": "unrelated query must not rank curated videos",
             "duration": duration, "minimum_footage_duration": duration,
             "voice_segment_id": 40 + i, "voice_segment_ids": [40 + i, 90 + i],
             "narration_start": i * duration, "narration_end": (i + 1) * duration,
             "visual_beat_index": i, "visual_beat_count": count} for i in range(count)]


def block(tmp_path, count=6, seed="known-seed"):
    root = tmp_path / "curated"
    root.mkdir(exist_ok=True)
    for i in range(count):
        folder = root / f"part-{i}"
        folder.mkdir(exist_ok=True)
        (folder / f"source-{i}.mp4").write_bytes(f"original {i}".encode())
    return {"enabled": True, "blockId": "block-a", "name": "User curated",
            "root": str(root), "productionItemId": "product-a", **({"seed": seed} if seed is not None else {})}


def build(selection, tmp_path, policy, plan=None, **kwargs):
    return selection.build_block_clips(scenes() if plan is None else plan, policy,
        history_root=tmp_path / "history", duration_probe=lambda _path: 20, **kwargs)


def test_curated_random_selection_preserves_scene_metadata_and_nested_root(selection, tmp_path):
    policy = block(tmp_path)
    plan = scenes()
    original = deepcopy(plan)
    clips = build(selection, tmp_path, policy, plan)
    assert plan == original
    assert len(clips) == 3
    assert len({clip.source_family for clip in clips}) == 3
    for i, clip in enumerate(clips):
        assert Path(clip.path).is_relative_to(Path(policy["root"]))
        assert clip.narration == f"Voice {i}"
        assert clip.visual_query_en == plan[i]["visual_query_en"]
        assert clip.duration == 3
        assert clip.minimum_source_duration == 3
        assert clip.voice_segment_id == 40 + i
        assert clip.voice_segment_ids == [40 + i, 90 + i]
        assert (clip.narration_start, clip.narration_end) == (i * 3, (i + 1) * 3)
        assert (clip.visual_beat_index, clip.visual_beat_count) == (i, 3)
        assert clip.reused is False
    assert [clip.position_bucket for clip in clips] == ["EARLY", "MIDDLE", "LATE"]


def test_saved_seed_reproduces_order_and_fragments_and_different_seed_reshuffles(selection, tmp_path):
    policy = block(tmp_path, count=12, seed=None)
    clips = build(selection, tmp_path, policy, scenes(8))
    assert policy["seed"]
    assert clips == build(selection, tmp_path, deepcopy(policy), scenes(8))
    different = build(selection, tmp_path, {**policy, "seed": "other"}, scenes(8))
    assert [c.path for c in clips] != [c.path for c in different]
    project = TimelineProject("Curated", clips=clips, source_policy={"footageBlock": policy})
    project.save(tmp_path / "saved.newsflow")
    assert TimelineProject.load(tmp_path / "saved.newsflow") == project


def test_full_uniqueness_exhausts_families_into_explicit_gaps_without_foreign_sources(selection, tmp_path):
    policy = block(tmp_path, count=3)
    clips = build(selection, tmp_path, policy, scenes(4), family_of=lambda _path: "one-family")
    assert sum(bool(c.path) for c in clips) == 1
    assert all(c.duration == 3 and c.narration == f"Voice {i}" for i, c in enumerate(clips))
    assert all(c.fallback_level == "BLOCK_MISSING" for c in clips if not c.path)


def test_low_uniqueness_reuses_prepared_pool_and_exact_windows_after_target(selection, tmp_path):
    clips = build(selection, tmp_path, block(tmp_path), scenes(8), unique_percent=25)
    assert len({c.source_family for c in clips}) == 2
    assert all(c.path for c in clips)
    assert [c.reused for c in clips] == [False, False, True, True, True, True, True, True]
    windows = {(c.path, c.source_start) for c in clips[:2]}
    assert all((c.path, c.source_start) in windows for c in clips)


def test_small_block_allows_explicit_lower_uniqueness_reuse_without_inventing_new_families(selection, tmp_path):
    clips = build(selection, tmp_path, block(tmp_path, count=1), scenes(8), unique_percent=25)
    assert all(c.path for c in clips)
    assert len({c.source_family for c in clips}) == 1
    assert [c.reused for c in clips] == [False, True, True, True, True, True, True, True]


def test_random_fragment_respects_minimum_source_duration_beyond_voice_duration(selection, tmp_path):
    policy = block(tmp_path, count=1)
    plan = [{**scenes(1)[0], "minimum_footage_duration": 19}]
    clip = build(selection, tmp_path, policy, plan)[0]
    assert clip.minimum_source_duration == 19
    assert 0 <= clip.source_start <= 1


@pytest.mark.parametrize("percent", [-1, 101, float("nan"), float("inf")])
def test_invalid_uniqueness_is_explicit_error(selection, tmp_path, percent):
    with pytest.raises(ValueError):
        build(selection, tmp_path, block(tmp_path), unique_percent=percent)


def test_history_deprioritizes_families_and_rotates_source_windows(selection, tmp_path):
    policy = block(tmp_path, count=2)
    first = build(selection, tmp_path, policy, scenes(1))[0]
    history = selection.block_history(tmp_path / "history")
    history.record("published-one", [first])
    next_clip = build(selection, tmp_path, policy, scenes(1))[0]
    assert next_clip.source_family != first.source_family
    history.record("published-two", [next_clip])
    rotated = build(selection, tmp_path, policy, scenes(1))[0]
    previous = first if rotated.source_family == first.source_family else next_clip
    assert abs(rotated.source_start - previous.source_start) >= 3
    assert all(c.path for c in (first, next_clip, rotated))


def test_batch_reservations_choose_different_openings_and_windows_atomically(selection, tmp_path):
    policy = block(tmp_path, count=4)
    usage = {"lock": RLock(), "placements": {}, "windows": {}}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(build, selection, tmp_path, deepcopy(policy), scenes(1),
                                   batch_usage=usage, scenario_index=i) for i in range(4)]
        clips = [future.result()[0] for future in futures]
    assert len({c.source_family for c in clips}) == 4
    assert sum(len(v) for v in usage["placements"].values()) == 4
    assert sum(len(v) for v in usage["windows"].values()) == 4


def test_short_damaged_and_text_blocked_sources_are_rejected_once_without_looping(selection, tmp_path):
    policy = block(tmp_path, count=3)
    probes, screened = [], []
    def allowed(item):
        screened.append(item.path)
        return not item.path.endswith("source-0.mp4")
    def duration(path):
        probes.append(str(path))
        if path.name == "source-1.mp4":
            raise RuntimeError("damaged fixture")
        return 1
    clips = selection.build_block_clips(scenes(5), policy, history_root=tmp_path / "history",
        duration_probe=duration, source_allowed=allowed)
    assert all(not c.path for c in clips)
    assert len(probes) == len(set(probes))
    assert len(screened) == len(set(screened)) == 3
    assert not (Path(policy["root"]) / "selection-usage.sqlite3").exists()


def test_large_block_only_screens_and_probes_selected_candidates(selection, tmp_path):
    policy = block(tmp_path, count=100)
    probed, screened = [], []
    def duration(path):
        probed.append(str(path))
        return 20
    def allowed(item):
        screened.append(item.path)
        return True
    clips = selection.build_block_clips(scenes(), policy, history_root=tmp_path / "history",
        duration_probe=duration, source_allowed=allowed)
    assert len({c.source_family for c in clips}) == 3
    assert len(probed) == len(screened) == 3


@pytest.mark.parametrize("stage", ["probe", "screen", "checkpoint"])
def test_cancellation_propagates_without_partial_history(selection, tmp_path, stage):
    policy = block(tmp_path)
    def cancelled(*_args):
        raise InterruptedError("cancelled fixture")
    kwargs = {"duration_probe": lambda _path: 20, "source_allowed": lambda _item: True,
              "checkpoint": lambda: None}
    kwargs[{"probe": "duration_probe", "screen": "source_allowed", "checkpoint": "checkpoint"}[stage]] = cancelled
    with pytest.raises(InterruptedError, match="cancelled fixture"):
        selection.build_block_clips(scenes(), policy, history_root=tmp_path / "history", **kwargs)
    counts, windows = selection.block_history(tmp_path / "history").snapshot([])
    assert (counts, windows) == ({}, {})


def test_empty_root_returns_gaps_but_unavailable_root_is_explicit_error(selection, tmp_path):
    policy = block(tmp_path, count=0)
    assert all(not c.path for c in build(selection, tmp_path, policy))
    Path(policy["root"]).rmdir()
    with pytest.raises(ValueError):
        build(selection, tmp_path, policy)


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf")])
def test_invalid_scene_duration_cannot_be_silently_truncated(selection, tmp_path, duration):
    with pytest.raises(ValueError):
        build(selection, tmp_path, block(tmp_path), scenes(1, duration))


def test_continuity_uses_existing_resolver_and_keeps_voice_metadata_and_excludes_held_seconds(selection, tmp_path, monkeypatch):
    from scriptor import montage_continuity
    policy = block(tmp_path, count=1)
    clips = build(selection, tmp_path, policy, scenes(3))
    project = TimelineProject("Small block", clips=clips, source_policy={"footageBlock": policy})
    prepared_sources = []
    def prepare(source, output_root, **_kwargs):
        prepared_sources.append(source)
        path = Path(output_root) / f"still-{len(prepared_sources)}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic held frame")
        return path
    monkeypatch.setattr(montage_continuity, "prepare_continuity_media", prepare)
    assert selection.fill_block_continuity(project, tmp_path / "history",
        duration_probe=lambda _path: 20, source_allowed=lambda item: not Path(item.path).name.startswith("still")) == 2
    assert [c.continuity.get("mode") for c in project.clips] == [None, "background", "background"]
    assert project.duration == 9
    for i, c in enumerate(project.clips):
        assert (c.visual_beat_index, c.visual_beat_count) == (i, 3)
        assert c.voice_segment_ids == [40 + i, 90 + i]
    history = selection.block_history(tmp_path / "history")
    history.record("accepted", project.clips)
    counts, windows = history.snapshot([project.clips[0].source_family])
    assert sum(count for count, _last in counts.values()) == 1
    assert len(windows) == 1
    assert (Path(policy["root"]) / "part-0" / "source-0.mp4").read_bytes() == b"original 0"


def test_continuity_rejects_foreign_original_even_if_healthy_and_text_allowed(selection, tmp_path, monkeypatch):
    from scriptor import montage_continuity
    policy = block(tmp_path, count=0)
    foreign = tmp_path / "foreign.mp4"
    foreign.write_bytes(b"outside original")
    project = TimelineProject("Wrong saved source", clips=[
        TimelineClip(str(foreign), "First", "", duration=3),
        TimelineClip("", "Second", "", duration=3)], source_policy={"footageBlock": policy})
    sources = []
    def prepare(source, output, **_kwargs):
        sources.append(source)
        path = Path(output) / f"neutral-{len(sources)}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"neutral")
        return path
    monkeypatch.setattr(montage_continuity, "prepare_continuity_media", prepare)
    assert selection.fill_block_continuity(project, tmp_path / "history", duration_probe=lambda _: 20) == 2
    assert sources == [None, None]
    assert all(c.continuity["mode"] == "background" for c in project.clips)
