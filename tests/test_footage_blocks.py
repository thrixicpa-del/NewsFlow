"""Manual block domain and stale-worker persistence using disposable storage."""
from __future__ import annotations

import importlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scriptor import config


def test_manual_block_domain_is_available():
    assert importlib.util.find_spec("scriptor.footage_blocks"), "manual footage block domain is missing"


def test_saved_block_settings_survive_restart(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "settings.json")
    settings.footage_blocks = [{"id": "stable-id", "name": "Manual", "root": str(tmp_path), "videoCount": 0}]
    settings.footage_block_assignments = {"p-1": {"blockId": "stable-id", "origin": "manual"}}
    settings.montage_use_footage_blocks = True
    config.save_settings(settings)
    restarted = config.load_settings()
    assert getattr(restarted, "footage_blocks", []) == settings.footage_blocks
    assert getattr(restarted, "footage_block_assignments", {}) == settings.footage_block_assignments
    assert getattr(restarted, "montage_use_footage_blocks", False) is True


@pytest.fixture
def domain():
    assert importlib.util.find_spec("scriptor.footage_blocks"), "manual footage block domain is missing"
    return importlib.import_module("scriptor.footage_blocks")


@pytest.fixture
def settings():
    return config.Settings(montage_renderer="ffmpeg")


def make_block(domain, settings, tmp_path, name="First"):
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / "clip.mp4").write_bytes(b"synthetic")
    return domain.upsert_block(settings, {"name": name, "root": str(folder)})


def test_block_crud_keeps_identity_assignment_and_originals(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    domain.assign_block(settings, "p-1", block["id"], [{"id": "p-1", "title": "Topic"}])
    renamed = domain.upsert_block(settings, {"blockId": block["id"], "name": "Renamed", "root": block["root"]})
    assert renamed["id"] == block["id"]
    assert domain.list_blocks(settings) == [{**renamed, "available": True}]
    domain.delete_block(settings, block["id"])
    assert settings.footage_blocks == []
    assert settings.footage_block_assignments == {"p-1": {"blockId": block["id"], "origin": "manual"}}
    assert (Path(block["root"]) / "clip.mp4").read_bytes() == b"synthetic"


def test_duplicate_names_and_missing_root_do_not_mutate(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    before = deepcopy(settings.footage_blocks)
    for payload in ({"name": " first ", "root": block["root"]}, {"name": "Other", "root": str(tmp_path / "missing")},
                    {"blockId": "missing", "name": "Other", "root": block["root"]}, {"name": " ", "root": block["root"]}):
        with pytest.raises(ValueError):
            domain.upsert_block(settings, payload)
        assert settings.footage_blocks == before


def test_count_nested_videos_only_at_crud_not_snapshot(domain, settings, tmp_path, monkeypatch):
    nested = tmp_path / "root" / "nested"
    nested.mkdir(parents=True)
    (nested / "a.MP4").write_bytes(b"synthetic")
    (nested / "ignored.txt").write_text("not video")
    block = domain.upsert_block(settings, {"name": "Nested", "root": str(nested.parent / ".")})
    assert block["videoCount"] == 1
    assert block["root"] == str(nested.parent.resolve())
    monkeypatch.setattr(domain, "block_files", lambda *_: pytest.fail("snapshot rescanned files"))
    assert domain.list_blocks(settings)[0]["videoCount"] == 1


def test_offline_block_is_visible_and_does_not_use_another_root(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    Path(block["root"], "clip.mp4").unlink()
    Path(block["root"]).rmdir()
    assert domain.list_blocks(settings)[0]["available"] is False
    with pytest.raises(ValueError):
        domain.block_files(block["root"])


def test_block_files_reject_canonical_escape(domain, tmp_path, monkeypatch):
    from scriptor.footage import FootageItem
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"synthetic")
    monkeypatch.setattr(domain, "scan_folders", lambda _: [FootageItem(str(outside), outside.name)])
    with pytest.raises(ValueError):
        domain.block_files(str(root))


def test_parser_alternates_paragraphs_handles_bom_crlf_and_multiline(domain):
    assert domain.parse_topic_block_pairs("\ufeff Topic\r\ncontinued\r\n  \r\nFirst\r\n\r\n\r\nSecond topic\r\n\r\nFirst\r\n") == [
        ("Topic\ncontinued", "First"), ("Second topic", "First")]


@pytest.mark.parametrize("text", ["", " \n\n", "Topic\nBlock", "Topic\n\nBlock\n\nDangling"])
def test_parser_rejects_empty_or_odd_paragraphs(domain, text):
    with pytest.raises(ValueError):
        domain.parse_topic_block_pairs(text)


def test_import_resolves_durable_ids_in_title_order_and_is_idempotent(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    topics = [{"id": "p-2", "title": "Second"}, {"id": "p-1", "title": "First topic"}]
    pairs = [("First topic", "First"), ("Second", "First"), ("First topic", "First")]
    resolved = domain.resolve_assignments(settings, pairs, topics)
    assert resolved == [
        {"title": "First topic", "productionItemId": "p-1", "blockId": block["id"], "blockName": "First", "root": block["root"]},
        {"title": "Second", "productionItemId": "p-2", "blockId": block["id"], "blockName": "First", "root": block["root"]}]
    assert settings.footage_block_assignments == {}
    domain.apply_assignments(settings, resolved)
    domain.apply_assignments(settings, resolved)
    assert settings.footage_block_assignments == {
        "p-1": {"blockId": block["id"], "origin": "import"}, "p-2": {"blockId": block["id"], "origin": "import"}}
    assert settings.montage_use_footage_blocks is False


@pytest.mark.parametrize("problem", ["unknown-block", "unknown-topic", "ambiguous-topic", "duplicate-id", "ambiguous-block", "conflicting-pair"])
def test_bad_import_is_fully_validated_without_mutation(domain, settings, tmp_path, problem):
    block = make_block(domain, settings, tmp_path)
    make_block(domain, settings, tmp_path, "Other")
    topics = [{"id": "p-1", "title": "Topic"}, {"id": "p-2", "title": "Second"}]
    pairs = [("Topic", "First"), ("Second", "First")]
    if problem == "unknown-block": pairs[1] = ("Second", "Missing")
    if problem == "unknown-topic": pairs[1] = ("Missing", "First")
    if problem == "ambiguous-topic": topics.append({"id": "p-3", "title": " Topic "})
    if problem == "duplicate-id": topics.append({"id": "p-1", "title": "Third"})
    if problem == "ambiguous-block": settings.footage_blocks.append({**block, "id": "other", "name": " first "})
    if problem == "conflicting-pair": pairs.append(("Topic", "Other"))
    before = deepcopy(settings.footage_block_assignments)
    with pytest.raises(ValueError):
        domain.resolve_assignments(settings, pairs, topics)
    assert settings.footage_block_assignments == before


def test_manual_assignment_requires_confirmation_before_import_overwrite(domain, settings, tmp_path):
    first = make_block(domain, settings, tmp_path)
    other = make_block(domain, settings, tmp_path, "Other")
    topics = [{"id": "p-1", "title": "Topic"}, {"id": "p-2", "title": "Second"}]
    domain.assign_block(settings, "p-1", first["id"], topics)
    domain.assign_block(settings, "p-2", first["id"], topics)
    domain.apply_assignments(settings, domain.resolve_assignments(settings, [("Topic", "First")], topics))
    assert settings.footage_block_assignments["p-1"]["origin"] == "manual"
    with pytest.raises(ValueError):
        domain.resolve_assignments(settings, [("Topic", "Other")], topics)
    domain.apply_assignments(settings, domain.resolve_assignments(settings, [("Topic", "Other")], topics, confirm_overwrite=True))
    assert settings.footage_block_assignments["p-1"] == {"blockId": other["id"], "origin": "import"}
    assert settings.footage_block_assignments["p-2"] == {"blockId": first["id"], "origin": "manual"}


def test_manual_assignment_rejects_unknown_id_and_offline_root(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    with pytest.raises(ValueError):
        domain.assign_block(settings, "absent", block["id"], [{"id": "p-1", "title": "Topic"}])
    Path(block["root"], "clip.mp4").unlink()
    Path(block["root"]).rmdir()
    with pytest.raises(ValueError):
        domain.assign_block(settings, "p-1", block["id"], [{"id": "p-1", "title": "Topic"}])
    assert settings.footage_block_assignments == {}


def test_snapshot_captures_enabled_assignment_and_disabled_mode_ignores_dangling(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    domain.assign_block(settings, "p-1", block["id"], [{"id": "p-1", "title": "Topic"}])
    settings.montage_use_footage_blocks = True
    snapshot = domain.get_block_snapshot(settings, "p-1")
    assert snapshot == {"enabled": True, "blockId": block["id"], "name": "First", "root": block["root"], "productionItemId": "p-1"}
    domain.delete_block(settings, block["id"])
    assert snapshot["name"] == "First"
    with pytest.raises(ValueError): domain.get_block_snapshot(settings, "p-1")
    with pytest.raises(ValueError): domain.get_block_snapshot(settings, "p-2")
    settings.montage_use_footage_blocks = False
    assert domain.get_block_snapshot(settings, "p-1")["enabled"] is False


def test_settings_roundtrip_and_stale_worker_preserve_block_deletion_and_manual_choice(domain, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "settings.json")
    first = make_block(domain, settings, tmp_path)
    other = make_block(domain, settings, tmp_path, "Other")
    topics = [{"id": "p-1", "title": "Topic"}]
    domain.assign_block(settings, "p-1", first["id"], topics)
    config.save_settings(settings)
    worker = config.load_settings()
    operator = config.load_settings()
    operator.montage_use_footage_blocks = True
    domain.assign_block(operator, "p-1", other["id"], topics)
    domain.delete_block(operator, first["id"])
    config.save_settings(operator)
    worker.montage_task_statuses = {"p-1": {"status": "Готово", "progress": 100}}
    config.save_settings(worker)
    config.save_settings(worker)
    actual = config.load_settings()
    assert [row["id"] for row in actual.footage_blocks] == [other["id"]]
    assert actual.footage_block_assignments == {"p-1": {"blockId": other["id"], "origin": "manual"}}
    assert actual.montage_use_footage_blocks is True
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["montage_use_footage_blocks"] is True


def test_two_loaded_editors_merge_changes_by_block_and_product_id(domain, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "settings.json")
    first = make_block(domain, settings, tmp_path)
    other = make_block(domain, settings, tmp_path, "Other")
    config.save_settings(settings)
    left, right = config.load_settings(), config.load_settings()
    topics = [{"id": "p-1", "title": "Topic"}, {"id": "p-2", "title": "Second"}]
    domain.upsert_block(left, {"blockId": first["id"], "name": "Renamed first", "root": first["root"]})
    domain.assign_block(left, "p-1", first["id"], topics)
    config.save_settings(left)
    domain.upsert_block(right, {"blockId": other["id"], "name": "Renamed other", "root": other["root"]})
    domain.assign_block(right, "p-2", other["id"], topics)
    config.save_settings(right)
    actual = config.load_settings()
    assert {row["name"] for row in actual.footage_blocks} == {"Renamed first", "Renamed other"}
    assert set(actual.footage_block_assignments) == {"p-1", "p-2"}


def test_stale_import_cannot_overwrite_newer_manual_assignment(domain, settings, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "settings.json")
    first = make_block(domain, settings, tmp_path)
    other = make_block(domain, settings, tmp_path, "Other")
    topics = [{"id": "p-1", "title": "Topic"}]
    config.save_settings(settings)
    importer, operator = config.load_settings(), config.load_settings()
    batch = domain.resolve_assignments(importer, [("Topic", "First")], topics)
    domain.assign_block(operator, "p-1", other["id"], topics)
    config.save_settings(operator)
    domain.apply_assignments(importer, batch)
    before = (tmp_path / "settings.json").read_bytes()
    with pytest.raises(ValueError):
        config.save_settings(importer)
    assert (tmp_path / "settings.json").read_bytes() == before
    assert config.load_settings().footage_block_assignments["p-1"] == {"blockId": other["id"], "origin": "manual"}
    assert first["id"] != other["id"]


def test_invalid_late_assignment_does_not_partially_write(domain, settings, tmp_path):
    block = make_block(domain, settings, tmp_path)
    with pytest.raises(ValueError):
        domain.apply_assignments(settings, [{"productionItemId": "p-1", "blockId": block["id"]},
                                           {"productionItemId": "p-2", "blockId": "missing"}])
    assert settings.footage_block_assignments == {}


@pytest.mark.parametrize("field,value", [
    ("footage_blocks", None), ("footage_blocks", [{"id": "x"}]),
    ("footage_block_assignments", []), ("footage_block_assignments", {"p-1": "bad"}),
    ("montage_use_footage_blocks", "false"),
])
def test_corrupt_block_settings_fail_visibly_without_overwriting(settings, tmp_path, monkeypatch, field, value):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: path)
    config.save_settings(settings)
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved[field] = value
    path.write_text(json.dumps(saved), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(config.SettingsFileCorruptError):
        config.load_settings()
    assert path.read_bytes() == before


def test_concurrent_duplicate_names_fail_before_storage_write(domain, settings, tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "config_path", lambda: path)
    first = make_block(domain, settings, tmp_path)
    other = make_block(domain, settings, tmp_path, "Other")
    config.save_settings(settings)
    left, right = config.load_settings(), config.load_settings()
    domain.upsert_block(left, {"blockId": first["id"], "name": "Shared", "root": first["root"]})
    domain.upsert_block(right, {"blockId": other["id"], "name": " shared ", "root": other["root"]})
    config.save_settings(left)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        config.save_settings(right)
    assert path.read_bytes() == before
