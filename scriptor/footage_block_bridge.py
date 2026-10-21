"""Canonical manual block actions; use the existing production identity/storage."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from copy import deepcopy
from pathlib import Path

from . import footage_blocks as blocks
from .config import (
    _exclusive_settings_write,
    app_data_root,
    load_settings,
    save_settings,
)


def _runtime():
    from . import bridge

    return bridge


def topics(settings):
    runtime = _runtime()
    deleted = set(settings.idea_deleted_production_ids) | set(
        settings.deleted_scenario_production_ids
    )
    rows = {}
    for row in settings.idea_production_items:
        if isinstance(row, dict) and row.get("id") and row["id"] not in deleted:
            identity = str(row["id"])
            if identity in rows:
                raise ValueError("Product ID повторяется в текущем производстве")
            rows[identity] = {"id": identity, "title": str(row.get("title", ""))}
    titles, jobs = runtime.load_session()
    for job in jobs:
        identity = str(job.request.production_item_id or "")
        if (
            identity
            and identity not in deleted
            and identity not in rows
            and 0 <= job.request.index < len(titles)
            and job.request.title == titles[job.request.index]
        ):
            rows[identity] = {"id": identity, "title": str(job.request.title)}
    return list(rows.values())


def projection(settings):
    block_rows = blocks.list_blocks(settings)
    by_id = {row["id"]: row for row in block_rows}
    topic_rows = []
    for topic in topics(settings):
        assignment = settings.footage_block_assignments.get(topic["id"], {})
        block = by_id.get(assignment.get("blockId"), {})
        topic_rows.append(
            {
                "productionItemId": topic["id"],
                "title": topic["title"],
                "blockId": assignment.get("blockId", ""),
                "blockName": block.get("name", ""),
                "root": block.get("root", ""),
                "origin": assignment.get("origin", ""),
            }
        )
    return {"footageBlocks": block_rows, "footageBlockTopics": topic_rows}


def _result(message, **extra):
    return {
        **_runtime().snapshot(),
        "operationResult": {"kind": "footage-blocks", "message": message},
        **extra,
    }


def save_footage_block(payload):
    with (
        _runtime()._production_artifact_fence(),
        _exclusive_settings_write(app_data_root() / "footage-block-commands.json"),
    ):
        settings = load_settings()
        blocks.upsert_block(settings, payload)
        save_settings(settings)
    return _result("Блок футажей сохранён")


def delete_footage_block(payload):
    with (
        _runtime()._production_artifact_fence(),
        _exclusive_settings_write(app_data_root() / "footage-block-commands.json"),
    ):
        settings = load_settings()
        blocks.delete_block(settings, str(payload.get("blockId", "")))
        save_settings(settings)
    return _result("Блок удалён из настроек; исходные видео сохранены")


def assign_footage_block(payload):
    with (
        _runtime()._production_artifact_fence(),
        _exclusive_settings_write(app_data_root() / "footage-block-commands.json"),
    ):
        settings = load_settings()
        blocks.assign_block(
            settings,
            str(payload.get("productionItemId", "")),
            str(payload.get("blockId", "")),
            topics(settings),
        )
        save_settings(settings)
    return _result("Блок темы изменён; выполняющиеся задания сохраняют прежний снимок")


def _fingerprint(settings):
    value = [
        settings.production_reset_generation,
        settings.footage_blocks,
        settings.footage_block_assignments,
        # ID-less supported rows are migrated by position; include their raw
        # order/content so a preview cannot overwrite a subsequently edited row.
        settings.idea_production_items,
        topics(settings),
    ]
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _preview(settings, text):
    pairs = blocks.parse_topic_block_pairs(text)
    current = topics(settings)
    known = {" ".join(row["title"].split()).casefold() for row in current}
    new_titles = list(
        dict.fromkeys(
            " ".join(title.split())
            for title, _ in pairs
            if " ".join(title.split()).casefold() not in known
        )
    )
    staged = deepcopy(settings)
    _runtime().ensure_idea_production_items(staged, active_titles=new_titles)
    resolved = blocks.resolve_assignments(
        staged, pairs, topics(staged), confirm_overwrite=True
    )
    new_keys = {title.casefold() for title in new_titles}
    imported_keys = {" ".join(title.split()).casefold() for title, _ in pairs}
    added = [
        row
        for row in staged.idea_production_items[len(settings.idea_production_items) :]
        if str(row.get("title", "")).casefold() in new_keys
    ]
    legacy_updates = []
    for position, old in enumerate(settings.idea_production_items):
        if (
            not str(old.get("id", "")).strip()
            and " ".join(str(old.get("title", "")).split()).casefold() in imported_keys
        ):
            migrated = staged.idea_production_items[position]
            if migrated.get("id"):
                legacy_updates.append(
                    {"position": position, "item": deepcopy(migrated)}
                )
    conflicts = []
    for row in resolved:
        prior = settings.footage_block_assignments.get(row["productionItemId"], {})
        if prior.get("origin") == "manual" and prior.get("blockId") != row["blockId"]:
            conflicts.append({**row, "currentBlockId": prior["blockId"]})
    return {
        "fingerprint": _fingerprint(settings),
        "textSha256": hashlib.sha256(text.encode()).hexdigest(),
        "pairs": pairs,
        "rows": resolved,
        "newItems": added,
        "legacyUpdates": legacy_updates,
        "conflicts": conflicts,
    }


def _preview_path(token):
    try:
        identity = str(uuid.UUID(str(token)))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Недействительный предпросмотр TXT") from error
    return app_data_root() / "footage-block-previews" / f"{identity}.json"


def preview_footage_block_import(payload):
    text = payload.get("text", "")
    with (
        _runtime()._production_artifact_fence(),
        _exclusive_settings_write(app_data_root() / "footage-block-commands.json"),
    ):
        preview = _preview(load_settings(), text)
        token = str(uuid.uuid4())
        path = _preview_path(token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(preview, ensure_ascii=False), encoding="utf-8")
    return _result(
        "Проверьте темы, Product ID и папки перед импортом",
        footageBlockImportPreview=preview["rows"],
        footageBlockImportConflicts=preview["conflicts"],
        footageBlockImportToken=token,
    )


def import_footage_block_pairs(payload):
    text = payload.get("text", "")
    confirm = payload.get("confirmOverwrite", False)
    if not isinstance(confirm, bool):
        raise TypeError("Подтверждение замены должно быть включено или выключено")
    with (
        _runtime()._production_artifact_fence(),
        _exclusive_settings_write(app_data_root() / "footage-block-commands.json"),
    ):
        settings = load_settings()
        if payload.get("previewToken"):
            path = _preview_path(payload["previewToken"])
            try:
                preview = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise ValueError(
                    "Предпросмотр недоступен; проверьте TXT заново"
                ) from error
            if (
                preview["fingerprint"] != _fingerprint(settings)
                or preview["textSha256"]
                != hashlib.sha256(str(text).encode()).hexdigest()
            ):
                raise ValueError("Темы или блоки изменились; обновите предпросмотр TXT")
        else:
            preview = _preview(settings, text)
        if preview["conflicts"] and not confirm:
            raise ValueError("Подтвердите замену индивидуальных ручных назначений")
        for migrated in preview.get("legacyUpdates", []):
            item = migrated["item"]
            settings.idea_production_items[migrated["position"]] = deepcopy(item)
            settings.idea_scenario_context[item["title"]] = deepcopy(item)
        for item in preview["newItems"]:
            settings.idea_production_items.append(deepcopy(item))
            settings.idea_scenario_context[item["title"]] = deepcopy(item)
            if item["title"] not in settings.idea_results:
                settings.idea_results.append(item["title"])
        resolved = blocks.resolve_assignments(
            settings, preview["pairs"], topics(settings), confirm_overwrite=confirm
        )
        if [row["productionItemId"] for row in resolved] != [
            row["productionItemId"] for row in preview["rows"]
        ]:
            raise ValueError("Product ID изменился; обновите предпросмотр TXT")
        blocks.apply_assignments(settings, resolved)
        save_settings(settings)
    return _result(
        f"Назначены блоки для тем: {len(resolved)}", footageBlockImportPreview=resolved
    )


def prepare_block_project(
    settings,
    scenes,
    policy,
    *,
    title,
    voice_path,
    aspect_ratio,
    index,
    scenario_index,
    batch_usage=None,
    checkpoint=None,
    progress=None,
    voice_map_provenance=None,
    preparation_metrics=None,
    preparation_started=None,
):
    """Consume the native scene list; publish through existing production fences."""
    from .montage_blocks import block_history, build_block_clips, fill_block_continuity
    from .timeline import TimelineProject, export_fcpxml

    runtime = _runtime()
    percent = runtime._fast_reuse_percent_for_scenario(settings, scenario_index)
    percent = 100 if percent is None else percent
    policy = deepcopy(policy)
    duration = lambda path: runtime._cached_or_probed_montage_duration(index, path)
    allowed = lambda item: runtime._montage_screen_text_safe(index, item)
    clips = build_block_clips(
        scenes,
        policy,
        unique_percent=percent,
        history_root=app_data_root(),
        scenario_index=scenario_index,
        batch_usage=batch_usage,
        checkpoint=checkpoint,
        duration_probe=duration,
        source_allowed=allowed,
        family_of=runtime._montage_clip_family_key,
    )
    intro = (
        runtime._random_video(settings.montage_intro_folder)
        if settings.montage_intro_enabled
        else ""
    )
    project = TimelineProject(
        title,
        aspect_ratio=aspect_ratio,
        clips=clips,
        voiceover_path=voice_path,
        intro_path=intro,
        intro_duration=runtime._full_intro_duration(
            intro, settings.montage_intro_duration
        )
        if intro
        else 0,
        overlay_path=runtime._random_video(settings.montage_overlay_folder)
        if settings.montage_overlay_enabled
        else "",
        transition_style=settings.montage_transition_style,
        transition_frames=settings.montage_transition_frames,
        source_policy={
            "mode": "block",
            "footageBlock": policy,
            "useFootageBlocks": True,
            "productionItemId": policy["productionItemId"],
            "uniquePercent": percent,
            "autoFillGaps": True,
        },
    )
    fill_block_continuity(
        project,
        app_data_root(),
        checkpoint=checkpoint,
        duration_probe=duration,
        source_allowed=allowed,
    )
    project.selection_summary = runtime._montage_selection_summary(project.clips)
    project.selection_summary["uniqueTargetPercent"] = percent
    project.voice_map_provenance = deepcopy(voice_map_provenance or {})
    project.preparation_metrics_ms = deepcopy(preparation_metrics or {})
    if preparation_started is not None:
        project.preparation_metrics_ms["total"] = round(
            (time.perf_counter() - preparation_started) * 1000, 3
        )
    stem = f"{runtime.safe_filename(title)}-{runtime.safe_filename(policy['productionItemId'])}"
    folder = Path(settings.montage_project_folder)
    target = folder / f"{stem}.newsflow"
    staging = runtime._production_staging_folder(
        folder, settings.production_reset_generation, "project"
    )
    staged = staging / target.name
    project.save(staged)
    targets = [(staged, target)]
    if settings.montage_export_davinci_xml:
        export_fcpxml(project, staged.with_suffix(".fcpxml"))
        targets.append((staged.with_suffix(".fcpxml"), target.with_suffix(".fcpxml")))
    if len(runtime._publish_staged_paths(settings, targets)) != len(targets):
        raise InterruptedError("Подготовка блока отменена: производство очищено")
    block_history(app_data_root()).record(str(target.resolve()), project.clips)
    settings.montage_recent_clip_paths = list(
        dict.fromkeys(
            [
                *settings.montage_recent_clip_paths,
                *(clip.path for clip in project.clips if not clip.continuity),
            ]
        )
    )[-3000:]
    save_settings(settings)
    if progress:
        progress(
            "Подбор футажей",
            f"Блок «{policy['name']}»: {len(clips)} сцен; исходники только из {policy['root']}",
        )
    return {
        **runtime.snapshot(),
        "preparedProject": {
            "title": title,
            "path": str(target),
            "clips": len(project.clips),
            "duration": round(project.duration, 1),
            "summary": project.selection_summary,
            "summaryText": f"Блок «{policy['name']}»: {len(clips)} сцен",
            "manualReplacements": [],
            "timingsMs": project.preparation_metrics_ms,
        },
    }


def montage_project_stem(project):
    runtime = _runtime()
    stem = runtime.safe_filename(project.title)
    if project.source_policy.get("mode") == "block":
        identity = str(project.source_policy.get("productionItemId") or "")
        if not identity.strip():
            raise ValueError("В проекте блока отсутствует Product ID")
        stem += f"-{runtime.safe_filename(identity)}"
    return stem
