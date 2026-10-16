"""Independent lexical expectations and real selector/storage regressions.

These tests do not establish visual recognition of people or real events.
"""
import json
import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from scriptor import bridge
from scriptor.ai_index import ClipIndex, SearchHit
from scriptor.footage import FootageItem
from scriptor.timeline import fallback_scene_plan, fallback_visual_query


@pytest.mark.parametrize("text,wanted,forbidden", [
    ("Делегации Армении и Азербайджана начали переговоры", "diplomatic", "army soldiers"),
    ("Танкер прибыл в порт", "cargo ship", "tanks armored"),
    ("Танк движется по позиции", "tanks armored", "cargo ship"),
    ("Армия начала наступление", "army soldiers", "diplomatic"),
    ("Армейский конвой прибыл", "army soldiers", "cargo ship"),
    ("Санкции нанесли удар по экономике", "economic sanctions", "explosion"),
    ("Обсуждают прекращение огня", "diplomatic", "artillery firing"),
    ("Начался артиллерийский обстрел", "artillery", "diplomatic"),
    ("Кибератака нарушила работу серверов", "servers", "artillery"),
    ("Поезд перевозит зерно к порту", "rail", "tanks armored"),
    ("Фермеры собирают урожай", "harvest", "protest"),
    ("Фермеры вышли на протест", "protest", "harvest"),
    ("Стороны отказались от удара и начали переговоры", "diplomatic", "explosion"),
    ("Удар по порту отменили, делегации начали переговоры", "diplomatic", "explosion"),
    ("Удар по порту не отменили", "explosion", "diplomatic"),
    ("Армия не наносила удар по городу", "army soldiers", "explosion"),
    ("Несмотря на прекращение огня, артиллерийский обстрел продолжился", "artillery", "international news"),
    ("Трамп отправился в поездку в Европу", "Trump", "rail freight"),
])
def test_scene_action_not_accidental_substring(text, wanted, forbidden):
    query = fallback_visual_query(text)
    assert wanted in query
    assert forbidden not in query


def test_local_action_changes_without_title_leaking_into_each_scene():
    scenes = fallback_scene_plan(
        "Делегации начали переговоры. Начался артиллерийский обстрел. Санкции ударили по экономике.",
        "Армия начала наступление",
    )
    assert "army soldiers" not in scenes[0]["visual_query_en"]
    assert "diplomatic" in scenes[0]["visual_query_en"]
    assert "artillery" in scenes[1]["visual_query_en"]
    assert "explosion" not in scenes[2]["visual_query_en"]


def test_primary_speaker_and_pronoun_context_reset_at_object_change():
    scenes = fallback_scene_plan(
        "Зеленский ответил Путину. Он выступил перед журналистами. "
        "По решению Путина увеличено производство на заводе. Трамп провёл переговоры.",
        "Путин и Зеленский",
    )
    assert "Zelensky" in scenes[0]["visual_query_en"]
    assert "Putin" not in scenes[0]["visual_query_en"]
    assert "Zelensky" in scenes[1]["visual_query_en"]
    assert "factory" in scenes[2]["visual_query_en"]
    assert "Putin" not in scenes[2]["visual_query_en"]
    assert "Trump" in scenes[3]["visual_query_en"]
    assert "Zelensky" not in scenes[3]["visual_query_en"]


@pytest.mark.parametrize("text,wanted,other", [
    ("На заявление Путина ответил Зеленский.", "Zelensky", "Putin"),
    ("В ответ Путину Зеленский выступил перед журналистами.", "Zelensky", "Putin"),
    ("На слова Зеленского ответил Путин.", "Putin", "Zelensky"),
    ("Макрону ответил Трамп.", "Trump", "Macron"),
    ("Трампу ответил Макрон.", "Macron", "Trump"),
    ("Зеленский ответил Путину.", "Zelensky", "Putin"),
    ("Путин ответил Зеленскому.", "Putin", "Zelensky"),
    ("Путин заявил о встрече с Трампом.", "Putin", "Trump"),
    ("В заявлении Путина говорится, что Зеленский прибыл в город.", "Putin", "Zelensky"),
])
def test_speaker_is_subject_rather_than_first_indirect_person(text, wanted, other):
    query = fallback_visual_query(text)
    assert wanted in query
    assert other not in query


@pytest.mark.parametrize("text", [
    "Армия не начала наступление.",
    "Армия не начнёт наступление.",
    "Наступление не состоялось.",
])
def test_explicitly_denied_offensive_keeps_army_context_without_advancing_event(text):
    query = fallback_visual_query(text)
    if "Армия" in text:
        assert "army soldiers" in query
    assert "advancing" not in query


def test_denied_proposal_does_not_erase_a_later_actual_offensive():
    query = fallback_visual_query("Армия не начала переговоры, затем началось наступление.")
    assert "advancing" in query


def test_denied_end_of_offensive_is_not_a_denied_offensive():
    assert "advancing" in fallback_visual_query("Армия не прекратила наступление.")


def test_voice_map_keeps_authored_speaker_after_indirect_person_mention():
    from scriptor.voice_map import VoiceMapStatus
    authored = "Volodymyr Zelensky press conference journalists Kyiv"
    status = VoiceMapStatus("ready", "ready", path="test-map.json", data={
        "audioDuration": 6, "timingMode": "aligned", "schemaVersion": 1,
        "productionItemId": "test", "scriptSha256": "test", "audioSha256": "test",
        "alignmentEngine": "test", "segments": [{
            "id": 1, "start": 0, "end": 6, "duration": 6,
            "text": "На заявление Путина ответил Зеленский.", "visualQuery": authored,
        }],
    })
    scenes, _ = bridge._voice_map_scenes(status)
    assert scenes[0]["visual_query_en"] == authored
    assert scenes[0]["scene_intent"]["target_people"] == ["zelensky"]
    assert scenes[0]["duration"] == 6


def test_continuity_cannot_fill_diplomacy_with_known_combat():
    tank = FootageItem("/test/tank.mp4", "tank.mp4", tags=["military-vehicles"])
    result = bridge._select_visual_continuity_candidate(
        [tank], scene_query="diplomatic negotiations delegations", required_duration=6,
        project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
        source_allowed=lambda _: True, diversity_seed="fixed",
    )
    assert result is None


def test_continuity_skips_visual_work_for_existing_cheap_rejections():
    query = "seaport cargo cranes ships"
    calls = []

    def candidate(name, tags=()):
        item = FootageItem(f"/test/{name}.mp4", f"{name}.mp4", tags=list(tags))
        item._visual_assessor = lambda *_args, **_kwargs: (calls.append(name) or {"relation": "direct"})
        return item

    irrelevant = candidate("hospital_doctors")
    used = candidate("cargo_port")
    fresh = candidate("fresh_cargo")
    options = {"scene_query": query, "required_duration": 6, "project_used_families": set(),
               "recent_project_paths": set(), "source_exists": lambda _: True,
               "source_duration": lambda _: 6, "source_allowed": lambda _: True,
               "diversity_seed": "fixed", "allow_project_reuse": False}
    assert bridge._select_visual_continuity_candidate(
        [irrelevant], project_used_paths=set(), **options) is None
    assert calls == []
    assert bridge._select_visual_continuity_candidate(
        [used], project_used_paths={bridge._montage_clip_key(used.path)}, **options) is None
    assert calls == []
    result = bridge._select_visual_continuity_candidate(
        [fresh], project_used_paths=set(), **options)
    assert result is not None and result[0] is fresh
    assert calls == ["fresh_cargo"]


def test_continuity_inventory_keeps_all_rows_and_validates_only_finalists(tmp_path):
    index = ClipIndex(tmp_path / "continuity.sqlite3")
    index.allowed_roots = [str(tmp_path)]
    late = tmp_path / "zz_cargo.mp4"
    late.write_bytes(b"disposable legacy candidate")
    with index._connect() as connection:
        for number in range(80):
            connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding) VALUES(?,?,?,?,?)",
                               (str(tmp_path / f"missing_{number:03}.mp4"),
                                f"missing_{number:03}.mp4", 0, 0, bytes(2048)))
        stat = late.stat()
        connection.execute("INSERT INTO clips(path,name,size,mtime_ns,tags) VALUES(?,?,?,?,?)",
                           (str(late), late.name, stat.st_size, stat.st_mtime_ns, '["cargo"]'))
    assert hasattr(index, "continuity_items")
    with patch.object(index, "path_allowed", wraps=index.path_allowed) as allowed:
        inventory = index.continuity_items(exclude_english_text=True)
        assert len(inventory) == 81
        assert allowed.call_count == 0
        chosen = next(item for item in inventory if item.path == str(late))
        current = index.current_continuity_item(chosen, exclude_english_text=True)
        assert current is not None and current.path == str(late)
        assert allowed.call_count == 1
        assert index.current_continuity_item(inventory[0], exclude_english_text=True) is None
    result = bridge._select_visual_continuity_candidate(
        inventory, scene_query="cargo shipping", required_duration=6,
        project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
        source_allowed=lambda _: True, diversity_seed="fixed", allow_project_reuse=False,
        current_candidate=lambda item: index.current_continuity_item(item, exclude_english_text=True),
    )
    assert result is not None and result[0].path == str(late)


def test_continuity_finalist_observes_current_db_file_root_and_quarantine(tmp_path):
    from scriptor.ai_index import SCREEN_TEXT_CLASSIFIER_VERSION
    from scriptor.media_health import MediaHealth

    index = ClipIndex(tmp_path / "continuity.sqlite3")
    other = ClipIndex(index.db_path)
    clip = tmp_path / "cargo.mp4"
    clip.write_bytes(b"disposable embedded source")
    stat = clip.stat()
    with index._connect() as connection:
        connection.execute("INSERT INTO clips(path,name,size,mtime_ns,embedding,source_url) VALUES(?,?,?,?,?,?)",
                           (str(clip), clip.name, stat.st_size, stat.st_mtime_ns,
                            bytes(2048), "original"))
    assert hasattr(index, "continuity_items")
    with index.read_session():
        item = index.continuity_items(exclude_english_text=True)[0]
        with other._connect() as connection:
            connection.execute("UPDATE clips SET source_url='changed' WHERE path=?", (str(clip),))
        assert index.current_continuity_item(item, exclude_english_text=True).source_url == "changed"
        other.set_visual_evidence(str(clip), [{"kind": "leisure", "start": 0, "end": 6,
                                               "source": "manual"}])
        fresh = index.current_continuity_item(item, exclude_english_text=True)
        assert fresh.visual_evidence["observations"][0]["kind"] == "leisure"
        with other._connect() as connection:
            connection.execute("UPDATE clips SET disabled=1 WHERE path=?", (str(clip),))
        assert index.current_continuity_item(item, exclude_english_text=True) is None
        with other._connect() as connection:
            connection.execute("UPDATE clips SET disabled=0,english_text=1,english_text_version=? WHERE path=?",
                               (SCREEN_TEXT_CLASSIFIER_VERSION, str(clip)))
        assert index.current_continuity_item(item, exclude_english_text=True) is None
        with other._connect() as connection:
            connection.execute("UPDATE clips SET english_text=0 WHERE path=?", (str(clip),))
        assert index.current_continuity_item(item, exclude_english_text=True) is not None
        index.allowed_roots = [str(tmp_path / "different-root")]
        assert index.current_continuity_item(item, exclude_english_text=True) is None
        index.allowed_roots = [str(tmp_path)]
        clip.write_bytes(b"changed embedded source")
        assert index.current_continuity_item(item, exclude_english_text=True) is None
        stat = clip.stat()
        with other._connect() as connection:
            connection.execute("UPDATE clips SET size=?,mtime_ns=? WHERE path=?",
                               (stat.st_size, stat.st_mtime_ns, str(clip)))
        assert index.current_continuity_item(item, exclude_english_text=True) is not None
        index.media_health.record(clip, MediaHealth("invalid", "fixture"))
        assert index.current_continuity_item(item, exclude_english_text=True) is None


def test_continuity_finalist_rechecks_changed_metadata_before_selection(tmp_path):
    index = ClipIndex(tmp_path / "continuity.sqlite3")
    clip = tmp_path / "cargo.mp4"
    clip.write_bytes(b"disposable source")
    index.add_item(FootageItem(str(clip), clip.name, tags=["cargo"]))
    assert hasattr(index, "continuity_items")
    item = index.continuity_items(exclude_english_text=True)[0]
    with index._connect() as connection:
        connection.execute("UPDATE clips SET name='hospital.mp4',tags='[\"healthcare\"]' WHERE path=?", (str(clip),))
    result = bridge._select_visual_continuity_candidate(
        [item], scene_query="cargo shipping", required_duration=6,
        project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
        source_allowed=lambda _: True, diversity_seed="fixed", allow_project_reuse=False,
        current_candidate=lambda value: index.current_continuity_item(value, exclude_english_text=True),
    )
    assert result is None


def test_continuity_finalist_cannot_be_disabled_during_visual_check(tmp_path):
    index = ClipIndex(tmp_path / "continuity.sqlite3")
    writer = ClipIndex(index.db_path)
    clip = tmp_path / "cargo.mp4"
    clip.write_bytes(b"disposable source")
    index.add_item(FootageItem(str(clip), clip.name, tags=["cargo"]))
    item = index.continuity_items(exclude_english_text=True)[0]

    def current(value):
        fresh = index.current_continuity_item(value, exclude_english_text=True)
        if fresh is not None:
            def assess(*_args, **_kwargs):
                with writer._connect() as connection:
                    connection.execute("UPDATE clips SET disabled=1 WHERE path=?", (str(clip),))
                return {"relation": "direct"}
            fresh._visual_assessor = assess
        return fresh

    with index.read_session():
        result = bridge._select_visual_continuity_candidate(
            [item], scene_query="cargo shipping", required_duration=6,
            project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
            source_exists=lambda _: True, source_duration=lambda _: 6,
            source_allowed=lambda _: True, diversity_seed="fixed", allow_project_reuse=False,
            current_candidate=current,
        )
    assert result is None


class CountingText:
    def __init__(self):
        self.calls = []

    def query_embed(self, queries):
        values = [queries] if isinstance(queries, str) else queries
        self.calls.extend(values)
        for _ in values:
            yield np.array([1, 0], dtype=np.float32)


def seeded_index(root, paths):
    text = CountingText()
    index = ClipIndex(root / "index.sqlite3", embedder_factory=lambda: (object(), text))
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        with index._connect() as connection:
            connection.execute(
                "INSERT INTO clips(path,name,size,mtime_ns,tags,embedding,duration) VALUES(?,?,?,?,?,?,?)",
                (str(path), path.name, path.stat().st_size, path.stat().st_mtime_ns,
                 json.dumps(["diplomatic-negotiations"]),
                 np.array([1, 0], dtype=np.float32).tobytes(), 6),
            )
    return index, text


def test_usage_changes_rank_without_decoding_all_vectors_again(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    index, _ = seeded_index(tmp_path, [a, b])
    index.search("diplomatic negotiations", limit=2)
    vectors = index._search_corpus().vectors
    index.mark_used([str(b)] * 20)
    hits = index.search("diplomatic negotiations", limit=2)
    assert hits[0].item.path == str(a)
    assert index._search_corpus().vectors is vectors


def test_query_embedding_reused_but_final_selection_not_cached(tmp_path):
    index, text = seeded_index(tmp_path, [tmp_path / "a.mp4", tmp_path / "b.mp4"])
    first = index.search("diplomatic negotiations")
    index.mark_used([first[0].item.path] * 20)
    second = index.search("diplomatic negotiations")
    assert second[0].item.path != first[0].item.path
    assert text.calls == ["diplomatic negotiations"]


def test_selected_roots_applied_before_top_k_and_on_all_items(tmp_path):
    allowed = tmp_path / "Media"
    outside = tmp_path / "Media-old"
    index, _ = seeded_index(tmp_path, [allowed / "a.mp4", outside / "a.mp4"])
    index.allowed_roots = [str(allowed)]
    for results in (index.search("diplomatic negotiations", limit=1),):
        assert [hit.item.path for hit in results] == [str(allowed / "a.mp4")]
    assert [item.path for item in index.all_items()] == [str(allowed / "a.mp4")]


def test_disabled_candidate_never_returns_via_continuity_inventory(tmp_path):
    path = tmp_path / "a.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.rate(str(path), -10)
    assert index.all_items() == []


def test_offline_root_does_not_mass_delete_index(tmp_path):
    root = tmp_path / "library"
    index, _ = seeded_index(tmp_path, [root / "a.mp4"])
    offline = tmp_path / "offline"
    root.rename(offline)
    assert index.remove_missing() == 0
    assert index.count() == 1


def test_metadata_built_once_for_warm_search(tmp_path):
    index, _ = seeded_index(tmp_path, [tmp_path / "a.mp4"])
    index.search("diplomatic negotiations")
    with patch.object(index, "_metadata_tokens", side_effect=AssertionError("warm metadata rebuild")):
        assert index.search("different diplomatic meeting")


def test_person_aliases_are_not_limited_to_three_politicians():
    query = fallback_visual_query("Пашинян провёл переговоры с Токаевым")
    assert "Pashinyan" in query
    assert "Tokayev" in query


def test_joint_frame_with_target_is_not_rejected_as_other_person():
    item = FootageItem("/test/joint.mp4", "Vladimir Putin and Donald Trump meeting.mp4",
                       tags=["diplomatic-negotiations"])
    assert bridge._semantic_clip_ok("Vladimir Putin diplomatic negotiations", item)


def test_confirmed_person_outranks_higher_score_filename_hint(tmp_path):
    from scriptor.scene_intent import person_evidence
    a, b = tmp_path / "a.mp4", tmp_path / "Vladimir_Putin.mp4"
    index, _ = seeded_index(tmp_path, [a, b])
    index.set_person_evidence(str(a), [{
        "person_id": "putin", "start": 0, "end": 6, "source": "curated", "complete": True,
    }])
    indexed = {hit.item.path: hit for hit in index.search("Vladimir Putin press conference")}
    assert person_evidence("Vladimir Putin", indexed[str(a)].item, 0, 6)["status"] == "confirmed"
    assert person_evidence("Vladimir Putin", indexed[str(b)].item, 0, 6)["status"] != "confirmed"
    result = bridge._select_montage_candidate(
        "Vladimir Putin press conference", strict_hits=[
            SearchHit(indexed[str(b)].item, .95), SearchHit(indexed[str(a)].item, .50),
        ], fallback_hits=[], required_duration=6, match_threshold=.22,
        used_paths=set(), used_families=set(), project_used_paths=set(), project_used_families=set(),
        reserved_paths=set(), reserved_families=set(), source_exists=lambda _: True,
        source_duration=lambda _: 6,
    )
    assert result.item.path == str(a)
    assert result.diagnostics["person"]["status"] == "confirmed"


def test_person_evidence_is_signature_and_interval_bound(tmp_path):
    from scriptor.scene_intent import person_evidence
    path = tmp_path / "a.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [{
        "person_id": "putin", "start": 0, "end": 3, "source": "manual", "complete": True,
    }])
    item = index.search("Vladimir Putin")[0].item
    assert person_evidence("Vladimir Putin", item, 0, 3)["status"] == "confirmed"
    assert person_evidence("Vladimir Putin", item, 3, 3)["status"] == "unknown"
    assert person_evidence("Donald Trump", item, 0, 3)["status"] == "contradiction"
    path.write_bytes(b"changed file bytes")
    assert person_evidence("Vladimir Putin", item, 0, 3)["status"] == "unknown"


@pytest.mark.parametrize("semantic", [True, False])
def test_reindexed_replacement_does_not_keep_old_person_retrieval_priority(tmp_path, semantic):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    index, _ = seeded_index(tmp_path, [a, b])
    for path in (a, b):
        index.set_person_evidence(str(path), [{
            "person_id": "putin", "start": 0, "end": 6, "source": "curated", "complete": True,
        }])
    a.write_bytes(b"replacement with no person annotation")
    # Reindexing refreshes the media identity/vector but must not transfer a
    # previous file's independent annotation to the new bytes at this path.
    with index._connect() as connection:
        connection.execute("UPDATE clips SET size=?,mtime_ns=? WHERE path=?",
                           (a.stat().st_size, a.stat().st_mtime_ns, str(a)))
        connection.execute("UPDATE clips SET embedding=? WHERE path=?",
                           (np.array([.8, .6], dtype=np.float32).tobytes(), str(b)))
    with patch.object(index, "_text_model_is_cached", return_value=semantic):
        assert index.search("Vladimir Putin press conference", limit=1)[0].item.path == str(b)


def test_wrong_confirmed_person_overrides_misleading_filename(tmp_path):
    from scriptor.scene_intent import person_evidence
    path = tmp_path / "Vladimir Putin.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [{
        "person_id": "zelensky", "start": 0, "end": 6, "source": "manual", "complete": True,
    }])
    item = index.search("Vladimir Putin")[0].item
    assert person_evidence("Vladimir Putin", item, 0, 6)["status"] == "contradiction"
    assert bridge._semantic_clip_ok("Volodymyr Zelensky press conference", item)


def test_person_outside_initial_top_k_is_found_in_another_allowed_root(tmp_path):
    target = tmp_path / "second" / "unlabelled.mp4"
    distractions = [tmp_path / "first" / f"press_{i:03}.mp4" for i in range(36)]
    index, _ = seeded_index(tmp_path, [target, *distractions])
    # The correct annotated person has lower CLIP similarity than the crowd.
    with index._connect() as connection:
        connection.execute("UPDATE clips SET embedding=? WHERE path=?",
                           (np.array([.4, .9165], dtype=np.float32).tobytes(), str(target)))
    index.set_person_evidence(str(target), [{
        "person_id": "putin", "start": 0, "end": 6, "source": "curated", "complete": True,
    }])
    index.allowed_roots = [str(tmp_path / "first"), str(tmp_path / "second")]
    hits = index.search("Vladimir Putin press conference", limit=3)
    assert str(target) in [hit.item.path for hit in hits]
    assert next(hit.score for hit in hits if hit.item.path == str(target)) < 1


def test_external_usage_update_refreshes_shared_corpus_without_stale_order(tmp_path):
    paths = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    index, _ = seeded_index(tmp_path, paths)
    first = index.search("diplomatic negotiations")[0].item.path
    vectors = index._search_corpus().vectors
    other = ClipIndex(index.db_path)
    other.mark_used([first] * 20)
    assert index.search("diplomatic negotiations")[0].item.path != first
    assert index._search_corpus().vectors is vectors


def test_late_verified_person_window_selected_without_claiming_first_window(tmp_path):
    path = tmp_path / "anonymous.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [{
        "person_id": "putin", "start": 9, "end": 15, "source": "curated", "complete": True,
    }])
    hit = index.search("Vladimir Putin press conference")[0]
    hit.duration = 18
    result = bridge._select_montage_candidate(
        "Vladimir Putin press conference", strict_hits=[hit], fallback_hits=[],
        required_duration=6, match_threshold=.22, used_paths=set(), used_families=set(),
        project_used_paths=set(), project_used_families=set(), reserved_paths=set(), reserved_families=set(),
        source_exists=lambda _: True, source_duration=lambda _: 18,
    )
    assert result.source_start == 9
    assert result.diagnostics["person"]["status"] == "confirmed"


def test_continuity_rejects_curated_wrong_person_even_with_anonymous_filename(tmp_path):
    path = tmp_path / "anonymous.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [{
        "person_id": "zelensky", "start": 0, "end": 6, "source": "manual", "complete": True,
    }])
    item = index.search("Vladimir Putin")[0].item
    result = bridge._select_visual_continuity_candidate(
        [item], scene_query="Vladimir Putin press conference", required_duration=6,
        project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
        source_allowed=lambda _: True, diversity_seed="fixed",
    )
    assert result is None


def test_continuity_requires_positive_context_evidence_for_unknown_item():
    item = FootageItem("/test/clip_001.mp4", "clip_001.mp4", tags=[])
    assert bridge._select_visual_continuity_candidate(
        [item], scene_query="data center servers cybersecurity", required_duration=6,
        project_used_paths=set(), project_used_families=set(), recent_project_paths=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
        source_allowed=lambda _: True, diversity_seed="fixed",
    ) is None


def test_repair_does_not_keep_previous_files_confirmed_identity():
    from scriptor.timeline import TimelineClip, TimelineProject
    clip = TimelineClip("missing.mp4", "Путин выступил", "Vladimir Putin press conference", duration=6,
                        selection_diagnostics={"person": {"status": "confirmed"}})
    replacement = FootageItem("context.mp4", "government building.mp4")
    project = TimelineProject("repair", clips=[clip])
    with patch.object(bridge, "_validated_montage_clip_duration",
                      side_effect=lambda path: 0 if str(path) == "missing.mp4" else 6):
        assert bridge._repair_missing_project_clips(project, lambda *_: [replacement]) == 1
    assert project.clips[0].selection_diagnostics["person"]["status"] != "confirmed"


def test_usage_refresh_reads_one_snapshot_during_concurrent_deletion(tmp_path):
    paths = [tmp_path / "a.mp4", tmp_path / "b.mp4"]
    index, _ = seeded_index(tmp_path, paths)
    index.search("diplomatic negotiations")
    index.mark_used([str(paths[0])])
    original_connect = index._connect
    deleted = False

    @contextmanager
    def interleaved_connect():
        with original_connect() as connection:
            class Interleaved:
                def execute(self, sql, *args):
                    nonlocal deleted
                    if sql.startswith("SELECT path,used_count,rating") and not deleted:
                        with original_connect() as writer:
                            writer.execute("DELETE FROM clips WHERE path=?", (str(paths[0]),))
                        deleted = True
                    return connection.execute(sql, *args)
            yield Interleaved()

    with patch.object(index, "_connect", interleaved_connect):
        assert index.search("diplomatic negotiations")
    assert [hit.item.path for hit in index.search("diplomatic negotiations")] == [str(paths[1])]


def test_fast_reuse_checks_person_in_cached_window_not_other_interval(tmp_path):
    from scriptor.timeline import TimelineClip
    path = tmp_path / "joint-source.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [
        {"person_id": "zelensky", "start": 0, "end": 6, "source": "manual", "complete": True},
        {"person_id": "putin", "start": 9, "end": 15, "source": "manual", "complete": True},
    ])
    hit = index.search("Vladimir Putin")[0]
    pool = {bridge._montage_clip_key(str(path)): TimelineClip(str(path), "", "", duration=6, source_start=0)}
    result = bridge._fast_reuse_pool_hits(
        {"STRICT_MATCH": [hit]}, pool, 6, lambda _: 18,
        scene_query="Vladimir Putin press conference",
    )
    assert result["STRICT_MATCH"] == []


def test_changed_file_cannot_use_stale_visual_embedding_or_continuity_tags(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    index, _ = seeded_index(tmp_path, [a, b])
    index.search("diplomatic negotiations")
    a.write_bytes(b"replacement content")
    assert [hit.item.path for hit in index.search("diplomatic negotiations")] == [str(b)]
    assert [item.path for item in index.all_items()] == [str(b)]


def test_rating_update_reorders_without_reloading_visual_vectors(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    index, _ = seeded_index(tmp_path, [a, b])
    index.search("diplomatic negotiations")
    vectors = index._search_corpus().vectors
    index.rate(str(a), 2)
    assert index.search("diplomatic negotiations")[0].item.path == str(a)
    assert index._search_corpus().vectors is vectors


def test_partial_known_wrong_person_still_contradicts_whole_beat(tmp_path):
    from scriptor.scene_intent import person_evidence
    path = tmp_path / "partial.mp4"
    index, _ = seeded_index(tmp_path, [path])
    index.set_person_evidence(str(path), [
        {"person_id": "zelensky", "start": 0, "end": 3, "source": "curated", "complete": True},
    ])
    item = index.search("Vladimir Putin")[0].item
    assert person_evidence("Vladimir Putin", item, 0, 6)["status"] == "contradiction"
    assert not bridge._semantic_clip_ok("Vladimir Putin press conference", item)


def test_tail_keeps_verified_interval_and_does_not_extend_past_it(tmp_path):
    from scriptor.config import Settings
    from scriptor.timeline import TimelineClip, TimelineProject
    old, tail, voice = tmp_path / "old.mp4", tmp_path / "tail.mp4", tmp_path / "voice.wav"
    index, _ = seeded_index(tmp_path, [old, tail])
    voice.touch()
    index.set_person_evidence(str(tail), [
        {"person_id": "zelensky", "start": 0, "end": 6, "source": "manual", "complete": True},
        {"person_id": "putin", "start": 9, "end": 15, "source": "manual", "complete": True},
    ])
    item = next(hit.item for hit in index.search("Vladimir Putin") if hit.item.path == str(tail))
    project = TimelineProject("tail", voiceover_path=str(voice), clips=[
        TimelineClip(str(old), "Путин выступил", "Vladimir Putin press conference", duration=6),
    ])
    with (patch.object(bridge, "probe_media_duration", return_value=10),
          patch.object(bridge, "_cached_or_probed_montage_duration", side_effect=lambda _i, path, _m: 6 if path == old else 18),
          patch.object(bridge, "_replacement_candidates_for_clip", return_value=[item])):
        assert bridge._complete_project_visual_tail(project, index, Settings()) == 1
    assert project.clips[-1].source_start == 9
    assert project.clips[-1].source_start + project.clips[-1].duration <= 15
    assert project.clips[-1].selection_diagnostics["person"]["status"] == "confirmed"


def test_exhausted_search_preserves_incomplete_draft_without_ready_project(tmp_path):
    from scriptor.config import Settings
    from scriptor.timeline import TimelineClip, TimelineProject
    settings = Settings(montage_project_folder=str(tmp_path / "projects"))
    clip = TimelineClip("selected.mp4", "Стороны ведут переговоры", "diplomatic negotiations", duration=6)
    saved = bridge._preserve_montage_draft(settings, "draft", [clip], "voice.wav", 2)
    assert saved.is_file()
    assert saved.suffix != ".newsflow"
    draft = TimelineProject.load(saved)
    assert draft.clips[0].path == "selected.mp4"
    assert draft.selection_summary["state"] == "INCOMPLETE"
    assert draft.selection_summary["failedScene"] == 2


def test_renderer_cache_is_inside_disposable_test_boundary():
    assert Path(os.environ["NEWSFLOW_RENDER_TEMP_ROOT"]).resolve().is_relative_to(
        Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve())


def test_replacing_database_with_same_revision_counters_invalidates_vectors(tmp_path):
    first = tmp_path / "first"
    replacement = tmp_path / "replacement"
    first.mkdir()
    replacement.mkdir()
    a, b = first / "a.mp4", replacement / "b.mp4"
    index, _ = seeded_index(first, [a])
    other, _ = seeded_index(replacement, [b])
    # Exercise an adversarial restore with equal revisions as well as paths
    # whose metadata signatures are individually valid.
    for database in (index, other):
        with database._connect() as connection:
            connection.execute("UPDATE search_revision SET value=17 WHERE id=1")
    assert index.search("diplomatic negotiations")[0].item.path == str(a)
    # Restore by atomic replacement, including the equal-write-count case.
    # File identity must participate even on coarse timestamp filesystems.
    other.db_path.replace(index.db_path)
    assert index.search("diplomatic negotiations")[0].item.path == str(b)


def test_named_statement_does_not_accept_unrelated_known_category():
    server = FootageItem("/test/anonymous.mp4", "anonymous.mp4", tags=["technology-datacenter"])
    assert not bridge._semantic_clip_ok("Vladimir Putin press conference statement", server)


def test_refinery_fire_has_local_object_and_resets_previous_person():
    scenes = fallback_scene_plan("Пашинян выступил с заявлением. На НПЗ произошёл пожар.")
    assert "refinery" in scenes[1]["visual_query_en"]
    assert "Pashinyan" not in scenes[1]["visual_query_en"]


def test_missing_person_is_reported_as_context_rather_than_direct_match():
    item = FootageItem("/test/building.mp4", "government building.mp4", tags=["parliament-government"])
    result = bridge._select_montage_candidate(
        "Vladimir Putin press conference", strict_hits=[SearchHit(item, .8)], fallback_hits=[],
        required_duration=6, match_threshold=.22, used_paths=set(), used_families=set(),
        project_used_paths=set(), project_used_families=set(), reserved_paths=set(), reserved_families=set(),
        source_exists=lambda _: True, source_duration=lambda _: 6,
    )
    assert result.fallback_level == "SAFE_CONTEXT"
    assert result.diagnostics["person"]["status"] == "unknown"
