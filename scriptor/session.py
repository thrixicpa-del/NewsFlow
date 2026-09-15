from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .config import app_data_root, load_settings
from .core import ScenarioRequest
from .runner import Job, RunState


def session_path() -> Path:
    """The durable NewsFlow location, independent of the installed app version."""
    return app_data_root() / "session.json"


def backup_session_path() -> Path:
    return app_data_root() / "session.backup.json"


def legacy_session_path() -> Path:
    """Session location used by the early Scriptor builds."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Scriptor" / "session.json"


def remove_scenarios(titles: list[str], jobs: list[Job], indices: set[int]) -> tuple[list[str], list[Job]]:
    kept_old_indices = [index for index in range(len(titles)) if index not in indices]
    new_titles = [titles[index] for index in kept_old_indices]
    new_index_by_old = {old: new for new, old in enumerate(kept_old_indices)}
    new_jobs = []
    for job in jobs:
        old_index = job.request.index
        if old_index not in new_index_by_old:
            continue
        request = ScenarioRequest(
            new_index_by_old[old_index],
            job.request.title,
            job.request.prompt,
            job.request.production_item_id,
            job.request.target_chars,
            job.request.allowed_min,
            job.request.allowed_max,
        )
        new_jobs.append(Job(
            request, job.state, job.result, job.error,
            job.actual_chars, job.length_status, job.length_repair_attempts,
        ))
    return new_titles, new_jobs


def rename_scenario(titles: list[str], jobs: list[Job], index: int, new_title: str) -> tuple[list[str], list[Job]]:
    cleaned = " ".join(new_title.split())
    if not cleaned:
        raise ValueError("Название темы не может быть пустым")
    updated_titles = list(titles)
    updated_titles[index] = cleaned
    updated_jobs = []
    for job in jobs:
        if job.request.index == index:
            request = ScenarioRequest(index, cleaned, job.request.prompt, job.request.production_item_id,
                                      job.request.target_chars, job.request.allowed_min, job.request.allowed_max)
            updated_jobs.append(Job(
                request, job.state, job.result, job.error,
                job.actual_chars, job.length_status, job.length_repair_attempts,
            ))
        else:
            updated_jobs.append(job)
    return updated_titles, updated_jobs


def _session_data(titles: list[str], jobs: list[Job]) -> dict:
    return {
        "version": 2,
        "titles": titles,
        "jobs": [
            {
                "index": job.request.index,
                "title": job.request.title,
                "prompt": job.request.prompt,
                "production_item_id": job.request.production_item_id,
                "target_chars": job.request.target_chars,
                "allowed_min": job.request.allowed_min,
                "allowed_max": job.request.allowed_max,
                "state": job.state.value,
                "result": job.result,
                "error": job.error,
                "actual_chars": job.actual_chars,
                "length_status": job.length_status,
                "length_repair_attempts": job.length_repair_attempts,
            }
            # Keep in-progress jobs too: the Electron UI reads this file from
            # a separate lightweight snapshot process and can therefore show
            # live per-scenario status while the worker process is running.
            for job in jobs
        ],
    }


def _write_session_file(path: Path, data: dict) -> None:
    """Atomically write JSON so a crash cannot leave a half-written session."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def save_session(titles: list[str], jobs: list[Job]):
    data = _session_data(titles, jobs)
    path = session_path()
    # Retain the previously good file.  The backup is intentionally outside
    # the installed application directory, so updating/reinstalling NewsFlow
    # never touches completed scripts.
    if path.is_file():
        try:
            shutil.copy2(path, backup_session_path())
        except OSError:
            # The primary atomic write still protects the latest state.  A
            # backup failure must never prevent the user from saving work.
            pass
    _write_session_file(path, data)


def _read_session(path: Path) -> tuple[list[str], list[Job]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    titles = [str(item) for item in data.get("titles", [])]
    jobs = []
    for item in data.get("jobs", []):
        request = ScenarioRequest(
            int(item["index"]), str(item["title"]), str(item.get("prompt", "")),
            str(item.get("production_item_id", "") or ""),
            max(0, int(item.get("target_chars", 0) or 0)),
            max(0, int(item.get("allowed_min", 0) or 0)),
            max(0, int(item.get("allowed_max", 0) or 0)),
        )
        state = RunState(item.get("state", RunState.WAITING.value))
        jobs.append(Job(
            request,
            state,
            str(item.get("result", "")),
            str(item.get("error", "")),
            max(0, int(item.get("actual_chars", 0) or 0)),
            str(item.get("length_status", "") or ""),
            max(0, int(item.get("length_repair_attempts", 0) or 0)),
        ))
    return titles, jobs


def _title_key(value: str) -> str:
    """Stable comparison key used only for a one-time legacy recovery."""
    return " ".join(str(value).split()).casefold()


def _same_title_batch(left: list[str], right: list[str]) -> bool:
    """Compare the active batch without trusting whitespace/case differences."""
    return bool(left) and len(left) == len(right) and [
        _title_key(item) for item in left
    ] == [
        _title_key(item) for item in right]


def _recover_empty_primary_from_backup() -> tuple[list[str], list[Job]] | None:
    """Recover only when settings prove the backup belongs to the active batch.

    A zero-byte/empty primary session was produced by an interrupted legacy
    migration.  It must not hide completed scripts, but an operator who has
    intentionally removed every scenario must still be able to keep an empty
    queue.  ``idea_results`` is the durable active-batch identity here.
    """
    backup = backup_session_path()
    if not backup.is_file():
        return None
    try:
        backup_titles, backup_jobs = _read_session(backup)
        settings = load_settings()
        active_titles = [str(item) for item in settings.idea_results]
        cover_titles = [
            str(item.get("title", "")) for item in getattr(settings, "cover_queue", [])
            if isinstance(item, dict) and str(item.get("title", "")).strip()
        ]
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
    # A delete tombstone is a newer user decision than the emergency backup.
    # Do not partially recover this batch: compacted indexes would otherwise
    # associate its retained rows with the wrong scripts, while a stale cover
    # record could resurrect the deleted row on the next start.
    deleted_titles = {
        str(value).strip().casefold()
        for value in getattr(settings, "deleted_scenario_titles", [])
        if str(value).strip()
    }
    deleted_production_ids = {
        str(value).strip()
        for value in getattr(settings, "deleted_scenario_production_ids", [])
        if str(value).strip()
    }
    if deleted_titles or deleted_production_ids:
        jobs_by_index = {job.request.index: job for job in backup_jobs}
        if any(
            _title_key(title) in deleted_titles
            or str(jobs_by_index.get(index).request.production_item_id
                   if jobs_by_index.get(index) else "").strip() in deleted_production_ids
            for index, title in enumerate(backup_titles)
        ):
            return None
    # The title list was historically written by a different worker than the
    # scenario/cover queue.  If it points to another batch, the persistent
    # cover queue is the stronger recovery proof: it carries the scripts and
    # must have the same ordered identity as the session backup.
    belongs_to_active_batch = (
        _same_title_batch(active_titles, backup_titles)
        or _same_title_batch(cover_titles, backup_titles)
    )
    if not backup_jobs or not belongs_to_active_batch:
        return None
    # Do not call save_session here: it would replace the verified backup with
    # the empty primary.  Keep the independent last-known-good backup intact.
    _write_session_file(session_path(), _session_data(backup_titles, backup_jobs))
    return backup_titles, backup_jobs


def _recover_legacy_jobs(current_titles: list[str]) -> list[Job]:
    """Recover finished legacy texts if a migration saved titles but lost jobs.

    Older NewsFlow previews could create the new session file after moving the
    title list, but before persisting the completed jobs.  We only recover if
    *every* current title has an exact counterpart in the legacy file; this
    prevents an old project from being mixed into a different new queue.
    """
    legacy = legacy_session_path()
    if not current_titles or not legacy.is_file():
        return []
    try:
        _legacy_titles, legacy_jobs = _read_session(legacy)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return []
    by_title = {_title_key(job.request.title): job for job in legacy_jobs if job.result.strip()}
    keys = [_title_key(title) for title in current_titles]
    if not keys or any(not key or key not in by_title for key in keys):
        return []
    return [
        Job(
            ScenarioRequest(
                index, title, by_title[_title_key(title)].request.prompt,
                by_title[_title_key(title)].request.production_item_id,
                by_title[_title_key(title)].request.target_chars,
                by_title[_title_key(title)].request.allowed_min,
                by_title[_title_key(title)].request.allowed_max,
            ),
            by_title[_title_key(title)].state,
            by_title[_title_key(title)].result,
            by_title[_title_key(title)].error,
            by_title[_title_key(title)].actual_chars,
            by_title[_title_key(title)].length_status,
            by_title[_title_key(title)].length_repair_attempts,
        )
        for index, title in enumerate(current_titles)
    ]


def migrate_legacy_session() -> tuple[list[str], list[Job]]:
    """Explicitly import a legacy Scriptor session without replacing current work.

    This is intentionally never called by normal startup or ``load_session``.
    A current NewsFlow session remains authoritative; only its documented
    interrupted-migration shape (titles with no jobs) may be completed from
    an exact matching legacy batch after an explicit operator migration.
    """
    path = session_path()
    if path.is_file():
        try:
            titles, jobs = _read_session(path)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return [], []
        if titles and not jobs:
            recovered = _recover_legacy_jobs(titles)
            if recovered:
                save_session(titles, recovered)
                return titles, recovered
        return titles, jobs
    legacy = legacy_session_path()
    if not legacy.is_file():
        return [], []
    try:
        titles, jobs = _read_session(legacy)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return [], []
    save_session(titles, jobs)
    return titles, jobs


def load_session() -> tuple[list[str], list[Job]]:
    path = session_path()
    # Prefer the NewsFlow file.  If an interrupted write or disk problem ever
    # damages it, recover from the last good NewsFlow backup instead of showing
    # an empty queue.  Legacy Scriptor state is deliberately excluded: it can
    # only enter through ``migrate_legacy_session()`` after explicit action.
    candidates = [path, backup_session_path()]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            titles, jobs = _read_session(candidate)
            # A session backup is an emergency recovery artifact, not an
            # authority that can undo an explicit user deletion.
            if candidate == backup_session_path():
                settings = load_settings()
                deleted_titles = {str(value).strip().casefold() for value in settings.deleted_scenario_titles}
                deleted_production_ids = {
                    str(value).strip() for value in settings.deleted_scenario_production_ids if str(value).strip()
                }
                if deleted_titles or deleted_production_ids:
                    jobs_by_index = {job.request.index: job for job in jobs}
                    removed = {
                        index for index, title in enumerate(titles)
                        if _title_key(title) in deleted_titles
                        or str(jobs_by_index.get(index).request.production_item_id
                               if jobs_by_index.get(index) else "").strip() in deleted_production_ids
                    }
                    if removed:
                        titles, jobs = remove_scenarios(titles, jobs, removed)
            if candidate == path and not titles and not jobs:
                recovered_empty = _recover_empty_primary_from_backup()
                if recovered_empty:
                    return recovered_empty
            return titles, jobs
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return [], []
