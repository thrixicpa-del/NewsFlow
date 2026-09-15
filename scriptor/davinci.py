"""Optional DaVinci Resolve Scripting API bridge for NewsFlow timelines.

Resolve owns the project database and must be running for its scripting API to
answer.  NewsFlow therefore never makes XML export depend on it: FCPXML is
always produced first, then this module can import it into the current Resolve
project when the user enables automatic import.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


_DEFAULT_MODULES = (
    Path(r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"),
    Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Developer\Scripting\Modules"),
)
_DEFAULT_LIBRARIES = (
    Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"),
    Path(r"C:\Program Files (x86)\Blackmagic Design\DaVinci Resolve\fusionscript.dll"),
)


def _module_paths() -> list[Path]:
    configured = os.environ.get("RESOLVE_SCRIPT_API", "").strip()
    roots = ([Path(configured)] if configured else []) + list(_DEFAULT_MODULES)
    return [path for path in roots if str(path) and path.is_dir()]


def _configure_native_library() -> Path | None:
    """Tell Resolve's official Python bridge where its native DLL is.

    The module installed in ProgramData is only a thin Python shim.  It needs
    ``fusionscript.dll`` from a *real Resolve installation*.  Packaging the
    shim with NewsFlow or copying it to another computer is not enough.
    """
    configured = os.environ.get("RESOLVE_SCRIPT_LIB", "").strip()
    if configured and Path(configured).is_file():
        return Path(configured)
    for path in _DEFAULT_LIBRARIES:
        if path.is_file():
            os.environ.setdefault("RESOLVE_SCRIPT_LIB", str(path))
            return path
    return None


def resolve_status() -> dict:
    """Return actionable availability details without raising in the UI."""
    paths = _module_paths()
    if not paths:
        return {"available": False, "connected": False,
                "message": "DaVinci Scripting API не найден. Установите DaVinci Resolve или задайте RESOLVE_SCRIPT_API."}
    library = _configure_native_library()
    if not library:
        return {"available": False, "connected": False,
                "message": "Найдены только файлы API, но нет fusionscript.dll. Установите DaVinci Resolve полностью."}
    try:
        module = _load_module(paths)
        resolve = module.scriptapp("Resolve")
        if not resolve:
            return {"available": True, "connected": False,
                    "message": "DaVinci API найден, но Resolve не отвечает. Откройте DaVinci Resolve."}
        return {"available": True, "connected": True, "message": "DaVinci Resolve подключён."}
    except Exception as error:
        return {"available": False, "connected": False,
                "message": f"DaVinci API не удалось подключить: {error}"}


def _load_module(paths: list[Path] | None = None):
    _configure_native_library()
    for path in paths if paths is not None else _module_paths():
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    try:
        return importlib.import_module("DaVinciResolveScript")
    except Exception as error:
        raise RuntimeError(
            "Установите DaVinci Resolve с Developer/Scripting или задайте RESOLVE_SCRIPT_API."
        ) from error


def import_fcpxml(xml_path: Path, timeline_name: str) -> dict:
    """Import one FCPXML into the open Resolve project using its public API."""
    if not xml_path.is_file():
        raise FileNotFoundError(f"DaVinci XML не найден: {xml_path}")
    module = _load_module()
    resolve = module.scriptapp("Resolve")
    if not resolve:
        raise RuntimeError("DaVinci Resolve не отвечает. Откройте программу и включите External scripting.")
    manager = resolve.GetProjectManager()
    project = manager.GetCurrentProject() if manager else None
    if not project:
        raise RuntimeError("В DaVinci Resolve нет открытого проекта. Откройте или создайте проект и повторите.")
    media_pool = project.GetMediaPool()
    if not media_pool:
        raise RuntimeError("DaVinci Resolve не вернул Media Pool.")
    # The Resolve API imports FCPXML as a native editable timeline.  The
    # options object is intentionally empty: it lets Resolve preserve media
    # paths from the XML instead of treating them as a flattened movie.
    timeline = media_pool.ImportTimelineFromFile(str(xml_path), {})
    if not timeline:
        raise RuntimeError("DaVinci Resolve не импортировал XML. Проверьте доступность исходных файлов.")
    try:
        timeline.SetName(timeline_name)
    except Exception:
        pass
    try:
        project.SetCurrentTimeline(timeline)
    except Exception:
        pass
    return {"timeline": timeline_name, "xmlPath": str(xml_path)}
