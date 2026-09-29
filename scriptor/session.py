from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from hashlib import sha256
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
            job.story_plan, job.accepted_story_parts, job.story_planner_status,
            job.story_planner_failure,
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
                job.story_plan, job.accepted_story_parts, job.story_planner_status,
                job.story_planner_failure,
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
                "story_plan": job.story_plan,
                "accepted_story_parts": job.accepted_story_parts,
                "story_planner_status": job.story_planner_status,
                "story_planner_failure": job.story_planner_failure,
            }
            # Keep in-progress jobs too: the Electron UI reads this file from
            # a separate lightweight snapshot process and can therefore show
            # live per-scenario status while the worker process is running.
            for job in jobs
        ],
    }


_SESSION_REPLACE_TIMEOUT_SECONDS = 3.0
_SESSION_REPLACE_RETRY_SECONDS = 0.05
_SESSION_WRITE_LOCK_GUARD = threading.Lock()
_SESSION_WRITE_LOCKS: dict[str, threading.Lock] = {}
_SESSION_OBSERVED_REVISIONS: dict[str, str | None] = {}
_TRANSIENT_WINDOWS_REPLACE_ERRORS = frozenset({5, 32})


class SessionWriteConflictError(RuntimeError):
    """A stale bridge attempted to overwrite a session it did not load."""


class _SessionSnapshotReadError(ValueError):
    """A malformed snapshot whose locked byte revision remains useful to recovery."""

    def __init__(self, error: Exception, revision: str):
        super().__init__(str(error))
        self.revision = revision


def _session_revision(path: Path) -> str | None:
    """Return an opaque content revision without parsing user session data."""
    if not path.is_file():
        return None
    return sha256(path.read_bytes()).hexdigest()


def _remember_session_revision(path: Path, revision: str | None) -> None:
    """Remember the revision of the exact snapshot or publication already locked."""
    _SESSION_OBSERVED_REVISIONS[str(path.resolve()).casefold()] = revision


@contextmanager
def _exclusive_session_write(path: Path, timeout: float = 12.0):
    """Serialize publication across threads and independent Windows bridge processes."""
    key = str(path.resolve()).casefold()
    with _SESSION_WRITE_LOCK_GUARD:
        thread_lock = _SESSION_WRITE_LOCKS.setdefault(key, threading.Lock())
    with thread_lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with lock_path.open("xb") as initializer:
                initializer.write(b"0")
                initializer.flush()
                os.fsync(initializer.fileno())
        except FileExistsError:
            pass
        with lock_path.open("r+b") as handle:
            acquired = False
            deadline = time.monotonic() + timeout
            if os.name == "nt":
                import msvcrt
                while not acquired:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Не удалось дождаться сохранения сессии NewsFlow")
                        time.sleep(0.08)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                acquired = True
            try:
                yield
            finally:
                if acquired:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass


def _replace_session_file(source: Path, target: Path) -> None:
    """Publish a staged session while tolerating short Windows reader locks.

    Electron snapshots use a separate bridge process.  On Windows that reader
    can briefly hold ``session.json`` without delete sharing, so retry the
    atomic replace instead of failing scenario generation.  The source is
    unique per write, making a retry safe across independent bridge processes.
    """
    deadline = time.monotonic() + _SESSION_REPLACE_TIMEOUT_SECONDS
    last_error: OSError | None = None
    while True:
        try:
            os.replace(source, target)
            return
        except OSError as error:
            if getattr(error, "winerror", None) not in _TRANSIENT_WINDOWS_REPLACE_ERRORS:
                raise
            last_error = error
            if time.monotonic() >= deadline:
                raise last_error
            time.sleep(_SESSION_REPLACE_RETRY_SECONDS)


def _write_session_file(path: Path, data: dict) -> None:
    """Atomically write JSON so a crash cannot leave a half-written session."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_session_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_session(titles: list[str], jobs: list[Job]):
    data = _session_data(titles, jobs)
    path = session_path()
    key = str(path.resolve()).casefold()
    with _exclusive_session_write(path):
        current_revision = _session_revision(path)
        observed_revision = _SESSION_OBSERVED_REVISIONS.get(key)
        if observed_revision is not None and observed_revision != current_revision:
            raise SessionWriteConflictError(
                "Сессия NewsFlow была обновлена другим процессом; устаревшая запись не опубликована."
            )
        # Retain the previously committed file while holding the same lock as
        # publication.  A failed replacement therefore leaves both primary
        # and LKG intact, and a later writer cannot interleave a new backup.
        if path.is_file() and _is_valid_session_file(path):
            shutil.copy2(path, backup_session_path())
        _write_session_file(path, data)
        _remember_session_revision(path, _session_revision(path))


def _read_session_bytes(path: Path) -> bytes:
    """Read through the same short Windows sharing violations as publication."""
    deadline = time.monotonic() + _SESSION_REPLACE_TIMEOUT_SECONDS
    while True:
        try:
            return path.read_bytes()
        except OSError as error:
            if (getattr(error, "winerror", None) not in _TRANSIENT_WINDOWS_REPLACE_ERRORS
                    or time.monotonic() >= deadline):
                raise
            time.sleep(_SESSION_REPLACE_RETRY_SECONDS)


def _is_valid_session_file(path: Path) -> bool:
    """Only let a parseable primary replace the independent LKG backup."""
    try:
        data = json.loads(_read_session_bytes(path).decode("utf-8"))
    except (OSError, ValueError, TypeError, UnicodeDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("titles", []), list) and isinstance(data.get("jobs", []), list)


def _read_session_snapshot(path: Path) -> tuple[list[str], list[Job], str]:
    # Snapshot bridge processes use this path too.  Taking the same very short
    # sidecar lock as a publisher means they observe a complete old or new JSON
    # file rather than racing a Windows replace operation.
    with _exclusive_session_write(path):
        payload = _read_session_bytes(path)
        revision = sha256(payload).hexdigest()
    try:
        data = json.loads(payload.decode("utf-8"))
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
            story_plan = item.get("story_plan")
            accepted_parts = item.get("accepted_story_parts")
            planner_status = str(item.get("story_planner_status", "") or "")
            raw_planner_failure = item.get("story_planner_failure")
            planner_failure = {
                key: str(raw_planner_failure[key])
                for key in ("phase", "reason", "response_chars", "response_sha256")
                if isinstance(raw_planner_failure, dict)
                and isinstance(raw_planner_failure.get(key), str)
                and len(raw_planner_failure[key]) <= 128
            }
            # r27 persisted a Covers-only marker beside scenario progress.
            # It is intentionally discarded when reading a scenario session.
            if planner_status == "FACE_REPAIR_DEFERRED":
                planner_status = ""
            jobs.append(Job(
                request,
                state,
                str(item.get("result", "")),
                str(item.get("error", "")),
                max(0, int(item.get("actual_chars", 0) or 0)),
                str(item.get("length_status", "") or ""),
                max(0, int(item.get("length_repair_attempts", 0) or 0)),
                story_plan if isinstance(story_plan, dict) else None,
                accepted_parts if isinstance(accepted_parts, list) and all(isinstance(part, dict) for part in accepted_parts) else [],
                planner_status,
                planner_failure,
            ))
    except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
        raise _SessionSnapshotReadError(error, revision) from error
    return titles, jobs, revision


def _read_session(path: Path) -> tuple[list[str], list[Job]]:
    """Read the current snapshot without exposing its concurrency revision."""
    titles, jobs, _revision = _read_session_snapshot(path)
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


def _apply_scenario_tombstones(titles: list[str], jobs: list[Job], settings=None) -> tuple[list[str], list[Job]]:
    """Project explicit scenario deletions over any persisted session snapshot.

    Detached workers may save stale pre-delete state after the user has removed
    scenarios or reset production. Tombstones are the newer durable authority
    and therefore apply to both the primary session and the emergency backup.

    Title tombstones are compatibility protection for legacy rows that have no
    durable ProductionItem ID. A newly-created scenario may reuse the same
    human title when it carries a new non-deleted ID.
    """
    if settings is None:
        try:
            settings = load_settings()
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return titles, jobs

    deleted_titles = {
        _title_key(value)
        for value in getattr(settings, "deleted_scenario_titles", [])
        if str(value).strip()
    }
    deleted_ids = {
        str(value).strip()
        for value in getattr(settings, "deleted_scenario_production_ids", [])
        if str(value).strip()
    }
    if not deleted_titles and not deleted_ids:
        return titles, jobs

    jobs_by_index = {job.request.index: job for job in jobs}
    removed: set[int] = set()
    for index, title in enumerate(titles):
        job = jobs_by_index.get(index)
        production_id = str(job.request.production_item_id if job else "").strip()
        if production_id:
            if production_id in deleted_ids:
                removed.add(index)
        elif _title_key(title) in deleted_titles:
            removed.add(index)
    return remove_scenarios(titles, jobs, removed) if removed else (titles, jobs)


def _conditionally_restore_primary_from_backup(expected_primary_revision: str, titles: list[str], jobs: list[Job]) -> str:
    """Restore LKG only if the primary is still the snapshot this loader saw.

    Return the authoritative revision for the returned state: the healed
    primary when this loader published it, otherwise the original observed
    revision so a later save detects that another writer won the race.
    """
    primary = session_path()
    with _exclusive_session_write(primary):
        if _session_revision(primary) != expected_primary_revision:
            return expected_primary_revision
        _write_session_file(primary, _session_data(titles, jobs))
        healed_revision = _session_revision(primary)
        if healed_revision is None:
            raise OSError("NewsFlow session recovery did not publish a primary revision")
        return healed_revision


def _recover_empty_primary_from_backup(expected_primary_revision: str) -> tuple[list[str], list[Job], str] | None:
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
    # A delete/reset tombstone is newer than the emergency backup. Do not
    # partially recover a compacted batch: that could remap retained rows onto
    # the wrong scenario indexes.
    filtered_titles, _filtered_jobs = _apply_scenario_tombstones(
        backup_titles, backup_jobs, settings=settings,
    )
    if len(filtered_titles) != len(backup_titles):
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
    # A writer may have published newer work after the empty primary snapshot;
    # never replace that work with this older LKG recovery.
    authoritative_revision = _conditionally_restore_primary_from_backup(
        expected_primary_revision, backup_titles, backup_jobs,
    )
    return backup_titles, backup_jobs, authoritative_revision


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
            by_title[_title_key(title)].story_plan,
            by_title[_title_key(title)].accepted_story_parts,
            by_title[_title_key(title)].story_planner_status,
            by_title[_title_key(title)].story_planner_failure,
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
    invalid_primary_revision: str | None = None
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            titles, jobs, revision = _read_session_snapshot(candidate)
            titles, jobs = _apply_scenario_tombstones(titles, jobs)
            if candidate == path and not titles and not jobs:
                recovered_empty = _recover_empty_primary_from_backup(revision)
                if recovered_empty:
                    recovered_titles, recovered_jobs, authoritative_revision = recovered_empty
                    _remember_session_revision(path, authoritative_revision)
                    return _apply_scenario_tombstones(recovered_titles, recovered_jobs)
            if candidate == path:
                _remember_session_revision(path, revision)
            elif invalid_primary_revision is not None:
                # The backup is authoritative only when it can conditionally
                # self-heal the exact malformed primary snapshot. If another
                # writer already committed, retain the old observed revision
                # so the returned LKG state is correctly rejected as stale.
                authoritative_revision = _conditionally_restore_primary_from_backup(
                    invalid_primary_revision, titles, jobs,
                )
                _remember_session_revision(path, authoritative_revision)
            return titles, jobs
        except _SessionSnapshotReadError as error:
            if candidate == path:
                invalid_primary_revision = error.revision
            continue
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
    return [], []
