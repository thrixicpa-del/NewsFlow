"""Persist real isolated montage history across planner and queue snapshots.

No media or providers are used. A planner records the actual paths used by its
project separately from its earlier settings snapshot; that usage must merge
under the settings lock rather than replacing another writer's newer history.
"""
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scriptor import bridge, config


@pytest.fixture(autouse=True)
def disposable_history_profile(tmp_path, monkeypatch):
    boundary = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
    profile = tmp_path / "montage-history"
    assert profile.resolve().is_relative_to(boundary)
    monkeypatch.setenv("LOCALAPPDATA", str(profile))
    monkeypatch.setenv("NEWSFLOW_TEST_ROOT", str(profile))
    monkeypatch.setenv("NEWSFLOW_RENDER_TEMP_ROOT", str(profile / "render"))
    config.save_settings(config.Settings(montage_renderer="ffmpeg"))


def seed_history(paths):
    settings = config.load_settings()
    settings.montage_recent_clip_paths = list(paths)
    config.save_settings(settings)


def persist_planner_usage(snapshot, used_paths, locally_planned_history):
    # prepare_montage already assigns its locally computed history. The explicit
    # usage list lets persistence distinguish newly used footage from old rows.
    snapshot.montage_recent_clip_paths = list(locally_planned_history)
    snapshot._montage_recent_clip_usage = list(used_paths)
    config.save_settings(snapshot)


def test_stale_queue_progress_preserves_history_saved_by_separate_planner():
    queue = config.load_settings()
    planner = config.load_settings()
    persist_planner_usage(planner, ["scene-a.mp4"], ["scene-a.mp4"])

    bridge._montage_task_update(queue, 0, status="Рендер", phase="Склейка", progress=70)

    persisted = config.load_settings()
    assert persisted.montage_recent_clip_paths == ["scene-a.mp4"]
    assert persisted.montage_task_statuses["0"]["progress"] == 70


def test_stale_queue_final_save_preserves_two_completed_planners_history():
    queue = config.load_settings()
    first = config.load_settings()
    persist_planner_usage(first, ["scene-a.mp4"], ["scene-a.mp4"])
    second = config.load_settings()
    persist_planner_usage(second, ["scene-b.mp4"], ["scene-a.mp4", "scene-b.mp4"])

    queue.pipeline_montage_outputs = ["first.mp4", "second.mp4"]
    config.save_settings(queue)

    persisted = config.load_settings()
    assert persisted.montage_recent_clip_paths == ["scene-a.mp4", "scene-b.mp4"]
    assert persisted.pipeline_montage_outputs == ["first.mp4", "second.mp4"]


def test_two_concurrent_planners_merge_usage_under_the_settings_lock():
    seed_history(["older.mp4"])
    first, second = config.load_settings(), config.load_settings()
    rendezvous = threading.Barrier(2)

    def commit(snapshot, path):
        rendezvous.wait(timeout=10)
        persist_planner_usage(snapshot, [path], ["older.mp4", path])

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(commit, first, "scene-a.mp4"),
                   workers.submit(commit, second, "scene-b.mp4")]
        for future in futures:
            future.result(timeout=20)

    actual = config.load_settings().montage_recent_clip_paths
    assert actual in (["older.mp4", "scene-a.mp4", "scene-b.mp4"],
                      ["older.mp4", "scene-b.mp4", "scene-a.mp4"])
    assert getattr(first, "_montage_recent_clip_usage", []) == []
    assert getattr(second, "_montage_recent_clip_usage", []) == []


def test_reusing_previous_path_refreshes_it_after_another_planners_new_path():
    seed_history(["old-a.mp4", "old-b.mp4"])
    other, reuse = config.load_settings(), config.load_settings()
    persist_planner_usage(other, ["new-c.mp4"], ["old-a.mp4", "old-b.mp4", "new-c.mp4"])

    persist_planner_usage(reuse, ["old-a.mp4"], ["old-b.mp4", "old-a.mp4"])

    assert config.load_settings().montage_recent_clip_paths == ["old-b.mp4", "new-c.mp4", "old-a.mp4"]


def test_history_cap_applies_after_merging_and_preserves_recent_foreign_usage():
    original = [f"clip-{number:04d}.mp4" for number in range(3000)]
    seed_history(original)
    other, reuse = config.load_settings(), config.load_settings()
    persist_planner_usage(other, ["clip-3000.mp4"], [*original[1:], "clip-3000.mp4"])
    persist_planner_usage(reuse, ["clip-0000.mp4"], [*original[1:], "clip-0000.mp4"])

    actual = config.load_settings().montage_recent_clip_paths
    assert actual == [*(f"clip-{number:04d}.mp4" for number in range(2, 3001)), "clip-0000.mp4"]
    assert len(actual) == 3000


def test_saved_usage_is_consumed_so_later_progress_cannot_replay_its_recency():
    first, second = config.load_settings(), config.load_settings()
    persist_planner_usage(first, ["scene-a.mp4"], ["scene-a.mp4"])
    assert getattr(first, "_montage_recent_clip_usage", []) == []
    persist_planner_usage(second, ["scene-b.mp4"], ["scene-b.mp4"])

    first.montage_task_statuses["0"] = {"status": "Готово", "progress": 100}
    config.save_settings(first)

    assert config.load_settings().montage_recent_clip_paths == ["scene-a.mp4", "scene-b.mp4"]


def test_explicit_clear_stays_empty_after_an_older_queue_snapshot_saves():
    seed_history(["scene-a.mp4", "scene-b.mp4"])
    queue, operator = config.load_settings(), config.load_settings()
    operator.montage_recent_clip_paths = []
    config.save_settings(operator)
    assert config.load_settings().montage_recent_clip_paths == []

    bridge._montage_task_update(queue, 0, status="Готово", progress=100)

    assert config.load_settings().montage_recent_clip_paths == []


def test_new_empty_profile_remains_compatible_without_usage_metadata():
    untouched = config.load_settings()
    config.save_settings(untouched)

    assert config.load_settings().montage_recent_clip_paths == []


def test_failed_atomic_write_retains_usage_for_retry_without_replaying_history(monkeypatch):
    seed_history(["old.mp4"])
    planner = config.load_settings()
    planner.montage_recent_clip_paths = ["old.mp4", "scene-a.mp4"]
    planner._montage_recent_clip_usage = ["scene-a.mp4"]

    def fail_replace(_source, _destination):
        raise OSError("synthetic atomic write failure")

    with monkeypatch.context() as failing_write:
        failing_write.setattr(config.os, "replace", fail_replace)
        with pytest.raises(OSError, match="synthetic atomic write failure"):
            config.save_settings(planner)

    assert config.load_settings().montage_recent_clip_paths == ["old.mp4"]
    assert planner._montage_recent_clip_usage == ["scene-a.mp4"]
    assert planner._observed_montage_history == ["old.mp4"]
    other = config.load_settings()
    persist_planner_usage(other, ["scene-b.mp4"], ["old.mp4", "scene-b.mp4"])
    config.save_settings(planner)
    assert config.load_settings().montage_recent_clip_paths == ["old.mp4", "scene-b.mp4", "scene-a.mp4"]
    assert planner._montage_recent_clip_usage == []
    config.save_settings(other)
    assert config.load_settings().montage_recent_clip_paths == ["old.mp4", "scene-b.mp4", "scene-a.mp4"]


def test_stale_planner_after_explicit_clear_records_only_its_actual_new_usage():
    seed_history(["old-a.mp4", "old-b.mp4"])
    planner, operator = config.load_settings(), config.load_settings()
    operator.montage_recent_clip_paths = []
    config.save_settings(operator)

    persist_planner_usage(planner, ["new-c.mp4"], ["old-a.mp4", "old-b.mp4", "new-c.mp4"])

    assert config.load_settings().montage_recent_clip_paths == ["new-c.mp4"]
    config.save_settings(planner)
    assert config.load_settings().montage_recent_clip_paths == ["new-c.mp4"]


def test_narrow_credential_replacement_does_not_commit_or_consume_pending_usage():
    seed_history(["old.mp4"])
    initial = config.load_settings()
    initial.youtube_api_key = "synthetic-old-key"
    config.save_settings(initial)
    editor = config.load_settings()
    editor.montage_recent_clip_paths = ["old.mp4", "pending.mp4"]
    editor._montage_recent_clip_usage = ["pending.mp4"]
    other = config.load_settings()
    persist_planner_usage(other, ["newer.mp4"], ["old.mp4", "newer.mp4"])
    editor._api_key_replacement = {
        "field": "youtube_api_key_protected", "index": 0,
        "revision": hashlib.sha256(b"synthetic-old-key\0YouTube Data API").hexdigest(),
        "secret": "synthetic-new-key", "label": "YouTube Data API",
    }

    config.save_settings(editor)

    persisted = config.load_settings()
    assert persisted.youtube_api_key == "synthetic-new-key"
    assert persisted.montage_recent_clip_paths == ["old.mp4", "newer.mp4"]
    assert editor._montage_recent_clip_usage == ["pending.mp4"]
    assert editor._observed_montage_history == ["old.mp4"]
    del editor._api_key_replacement
    config.save_settings(editor)
    assert config.load_settings().montage_recent_clip_paths == ["old.mp4", "newer.mp4", "pending.mp4"]
    assert editor._montage_recent_clip_usage == []
