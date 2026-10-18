"""Validated local overlay templates and the common final FFmpeg composition.

Templates are data, never FFmpeg expressions. Only bounded numbers and a checked
colour enter the filtergraph; filenames are separate subprocess arguments.
"""
from __future__ import annotations

import math
import random
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

LAYOUTS = {"16:9": (1920, 1080), "9:16": (1080, 1920)}
# Layer count is governed by available rendering resources, not a product cap.
# Bound repeated *reactivations* so a tiny interval cannot expand the schedule
# without limit; the first/static activation of every layer is exempt.
MAX_REPEATED_ACTIVATIONS = 512
MAX_SECONDS = 604800


def _number(value, name: str, low: float, high: float, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Наложения: {name} должно быть числом")  # noqa: TRY004 -- public JSON validation contract
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"Наложения: недопустимое {name}") from error
    if not math.isfinite(result) or not low <= result <= high or (positive and result <= 0):
        raise ValueError(f"Наложения: {name} вне допустимого диапазона {low}–{high}")
    return result


def _text(value, name: str, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(c in value for c in "\0\r\n"):
        raise ValueError(f"Наложения: недопустимое {name}")
    return value


def _local_path(value) -> str:
    path = _text(value, "path", 32767).strip()
    # URL/protocol inputs can make FFmpeg access the network or other devices.
    # A Windows drive letter is the only permitted colon prefix.
    if path.startswith(("//", "\\\\")) or (re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path) and not re.match(r"^[a-zA-Z]:[\\/]", path)):
        raise ValueError("Наложения: нужен локальный файл, URL и сетевые пути не поддерживаются")
    return path


def _normalize_library_sources(rows) -> list[dict]:
    if not isinstance(rows, list):
        raise ValueError("Наложения: librarySources должен быть массивом")  # noqa: TRY004 -- public JSON validation contract
    result, ids = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Наложения: источник должен быть объектом")  # noqa: TRY004 -- public JSON validation contract
        identifier = _text(row.get("id", ""), "source.id", 128).strip()
        if not identifier or identifier in ids:
            raise ValueError("Наложения: id источников должны быть непустыми и уникальными")
        ids.add(identifier)
        root = _local_path(row.get("root", ""))
        if not root:
            raise ValueError("Наложения: выберите локальную папку источника")
        enabled = row.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("Наложения: source.enabled должно быть true/false")  # noqa: TRY004 -- public JSON validation contract
        mode, kind = row.get("mode", "random"), row.get("kind", "all")
        if mode not in ("random", "all") or kind not in ("image", "video", "all"):
            raise ValueError("Наложения: недопустимый режим или тип источника")
        result.append({"id": identifier, "name": _text(row.get("name", identifier), "source.name", 256),
                       "root": root, "enabled": enabled, "mode": mode, "kind": kind})
    return result


def _selection_group(row: dict, sources: dict[str, dict]) -> tuple[str, str] | None:
    """Permanent members are exempt; source IDs and manual groups cannot collide."""
    group = row.get("randomGroup", "")
    source_id = row.get("librarySourceId", "")
    if source_id:
        return ("source", source_id) if group and sources[source_id]["mode"] == "random" else None
    return ("manual", group) if group else None


def _source_active(row: dict, sources: dict[str, dict]) -> bool:
    identifier = row.get("librarySourceId", "")
    if not identifier:
        return True
    source = sources[identifier]
    return source["enabled"] and source["kind"] in ("all", row["kind"])


def normalize_overlay_template(template, *, check_files: bool = False) -> dict:
    """Return an independent canonical v1 template; never read media by default.

    Loading settings must remain possible after an asset was moved. Saving new
    choices and rendering explicitly request ``check_files=True`` instead.
    """
    if template is None or template == {}:
        template = {"version": 1, "layouts": {}}
    if not isinstance(template, dict) or type(template.get("version", 1)) is not int or template.get("version", 1) != 1:
        raise ValueError("Наложения: поддерживается только версия 1")
    layouts = template.get("layouts", {})
    if not isinstance(layouts, dict) or any(key not in LAYOUTS for key in layouts):
        raise ValueError("Наложения: недопустимый формат layouts")
    result = {"version": 1, "layouts": {}}
    library_root = _local_path(template.get("libraryRoot", ""))
    if library_root:
        result["libraryRoot"] = library_root
    library_sources = _normalize_library_sources(template.get("librarySources", []))
    sources = {source["id"]: source for source in library_sources}
    if library_sources:
        result["librarySources"] = library_sources
    for layout, (width, height) in LAYOUTS.items():
        rows = layouts.get(layout, [])
        if not isinstance(rows, list):
            raise ValueError("Наложения: список слоёв должен быть массивом")  # noqa: TRY004 -- public JSON validation contract
        normalized, ids = [], set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("Наложения: слой должен быть объектом")  # noqa: TRY004 -- public JSON validation contract
            item = {
                "id": _text(row.get("id", f"overlay-{index + 1}"), "id", 128),
                "name": _text(row.get("name", f"Слой {index + 1}"), "name", 256),
                "path": _local_path(row.get("path", "")),
                "kind": row.get("kind", "image"),
                "mode": row.get("mode", "once"),
            }
            group = _text(row.get("randomGroup", ""), "randomGroup", 128).strip()
            if group:
                item["randomGroup"] = group
            source_id = _text(row.get("librarySourceId", ""), "librarySourceId", 128).strip()
            if source_id:
                if source_id not in sources:
                    raise ValueError(f"Наложения: источник «{source_id}» не найден")
                item["librarySourceId"] = source_id
            if not item["id"] or item["id"] in ids:
                raise ValueError("Наложения: id слоёв должны быть непустыми и уникальными")
            ids.add(item["id"])
            if item["kind"] not in ("image", "video") or item["mode"] not in ("once", "repeat", "end", "until-end"):
                raise ValueError("Наложения: недопустимый тип или режим слоя")
            for name, default in (("enabled", True), ("keepAspect", True), ("chromaEnabled", False), ("audioEnabled", False)):
                value = row.get(name, default)
                if not isinstance(value, bool):
                    raise ValueError(f"Наложения: {name} должно быть true/false")  # noqa: TRY004 -- public JSON validation contract
                item[name] = value
            for name, default, low, high, positive in (
                ("x", 0, -16384, 16384, False), ("y", 0, -16384, 16384, False),
                ("width", width, 1, 16384, False), ("height", height, 1, 16384, False),
                ("opacity", 1, 0, 1, False), ("start", 0, 0, MAX_SECONDS, False),
                ("duration", 5, 0, MAX_SECONDS, True), ("repeatEvery", 30, 0, MAX_SECONDS, True),
                ("endOffset", 5, 0, MAX_SECONDS, False), ("chromaSimilarity", .12, .01, 1, False),
                ("chromaBlend", .08, 0, 1, False),
            ):
                item[name] = _number(row.get(name, default), name, low, high, positive=positive)
            color = row.get("chromaColor", "#00FF00")
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Наложения: chromaColor должен быть #RRGGBB")
            item["chromaColor"] = color.upper()
            source_enabled = _source_active(item, sources)
            if check_files and item["enabled"] and source_enabled and not Path(item["path"]).is_file():
                raise ValueError(f"Наложение «{item['name']}»: файл не найден: {item['path'] or '(пустой путь)'}")
            if item["path"] and item["kind"] == "image" and Path(item["path"]).suffix.lower() not in (".png", ".jpg", ".jpeg"):
                raise ValueError("Наложения: изображения должны быть PNG или JPG")
            normalized.append(item)
        result["layouts"][layout] = normalized
    return result


def resolve_overlay_template(template, rng: random.Random | None = None) -> dict:
    """Snapshot one enabled candidate per group and layout before rendering.

    The global preset remains unchanged. Materialized rows keep their original
    stack position and complete per-file settings, including source metadata.
    Empty groups are permanent members. Each enabled random source selects one
    nonempty-group member; all-mode sources retain every checked member.
    Unattached manual groups remain independent. Members of disabled sources
    are omitted while source definitions remain available as snapshot metadata.
    Callers persist this result so retries and saved projects never reroll.
    """
    resolved = normalize_overlay_template(template)
    generator = rng if rng is not None else random.SystemRandom()
    sources = {source["id"]: source for source in resolved.get("librarySources", [])}
    for layout, rows in resolved["layouts"].items():
        groups: dict[tuple[str, str], list[int]] = {}
        for index, row in enumerate(rows):
            group = _selection_group(row, sources)
            source_enabled = _source_active(row, sources)
            if group and row["enabled"] and source_enabled:
                groups.setdefault(group, []).append(index)
        chosen = {generator.choice(indices) for indices in groups.values()}
        resolved["layouts"][layout] = [row for index, row in enumerate(rows)
            if (not row.get("librarySourceId") or (row["enabled"] and _source_active(row, sources)))
            and (_selection_group(row, sources) is None or index in chosen)]
    return resolved


def overlay_intervals(layer: dict, total_duration: float) -> list[tuple[float, float]]:
    """Visible half-open intervals, including the intro in the final clock."""
    total = _number(total_duration, "total_duration", 0, MAX_SECONDS)
    if not layer.get("enabled", True) or not total:
        return []
    mode = layer.get("mode", "once")
    start = _number(layer.get("start", 0), "start", 0, MAX_SECONDS)
    if mode == "until-end":
        return [(start, total)] if start < total else []
    duration = _number(layer.get("duration", 5), "duration", 0, MAX_SECONDS, positive=True)
    if mode == "end":
        start = total - _number(layer.get("endOffset", 5), "endOffset", 0, MAX_SECONDS)
    count, every = 1, 0.0
    if mode == "repeat":
        every = _number(layer.get("repeatEvery", 30), "repeatEvery", 0, MAX_SECONDS, positive=True)
        count = max(0, math.ceil((total - start) / every))
    elif mode not in ("once", "end"):
        raise ValueError("Наложения: недопустимый режим")
    if max(0, count - 1) > MAX_REPEATED_ACTIVATIONS:
        raise ValueError(f"Наложения: слишком много повторных включений (максимум {MAX_REPEATED_ACTIVATIONS} повторов)")
    result = []
    for index in range(count):
        begin = start + index * every
        end = min(total, begin + duration)
        begin = max(0.0, begin)
        if end > begin:
            result.append((begin, end))
    return result


def overlay_layers(template, aspect_ratio: str, *, legacy_path: str = "", total_duration: float = 0,
                   check_files: bool = False) -> list[dict]:
    """Read a materialized layout, reject unresolved pools, and migrate legacy.

    This preflight never randomly selects candidates or changes a saved choice.
    """
    value = normalize_overlay_template(template, check_files=False)
    sources = {source["id"]: source for source in value.get("librarySources", [])}
    rows = [dict(row) for row in value["layouts"].get(aspect_ratio, []) if row["enabled"]
            and _source_active(row, sources)]
    groups: set[tuple[str, str]] = set()
    for row in rows:
        group = _selection_group(row, sources)
        if group and group in groups:
            raise ValueError(f"Наложения: случайная группа «{group[1]}» не выбрана; подготовьте проект с выбранным вариантом")
        if group:
            groups.add(group)
    if legacy_path:
        path = _local_path(legacy_path)
        rows.insert(0, {"id": "legacy", "name": "Прежнее наложение", "enabled": True, "path": path,
                        "kind": "video", "x": 0, "y": 0, "width": LAYOUTS.get(aspect_ratio, LAYOUTS["16:9"])[0],
                        "height": 1080, "keepAspect": True, "opacity": 1, "start": 0,
                        "duration": total_duration or MAX_SECONDS, "mode": "once", "audioEnabled": False,
                        "chromaEnabled": True, "chromaColor": "#00FF00", "chromaSimilarity": .12,
                        "chromaBlend": .08, "_legacy": True})
    if check_files:
        for row in rows:
            if not Path(row["path"]).is_file():
                raise ValueError(f"Наложение «{row['name']}»: файл не найден: {row['path'] or '(пустой путь)'}")
    return rows


def _has_audio(ffmpeg: str, source: Path) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    probe = subprocess.run([ffmpeg, "-hide_banner", "-protocol_whitelist", "file,pipe", "-i", str(source)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=flags, check=False)
    return bool(re.search(r"Stream #\d+:\d+[^\r\n]*Audio:", probe.stderr or ""))


def _n(value: float) -> str:
    return format(float(value), ".9f").rstrip("0").rstrip(".") or "0"


@lru_cache(maxsize=64)
def _filter_graph_option(ffmpeg: str) -> str:
    """Use the file-option syntax supported by this trusted FFmpeg executable.

    Generic option-file arguments arrived in FFmpeg 7; version 9 removed the
    older filter_complex_script option. Unrecognised development builds retain
    the universally supported inline form for reasonably short graphs only.
    """
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", creationflags=flags,
                             timeout=15, check=False)
    match = re.search(r"\bffmpeg version n?(\d+)\.", (version.stdout or "") + (version.stderr or ""))
    if match:
        return "-/filter_complex" if int(match.group(1)) >= 7 else "-filter_complex_script"
    return "-filter_complex"


def compose_overlays(source: Path, output: Path, template, aspect_ratio: str, *, total_duration: float,
                     ffmpeg: str, encoder_args: list[str], legacy_path: str = "", run=None) -> Path:
    """Composite the entire ordered stack in one pass; never shorten base audio.

    Every occurrence trims from source timestamp zero, then moves onto the final
    clock. ``eof_action=pass`` prevents a short insert freezing or cutting video.
    Input loops fill a requested occurrence, but a later occurrence starts fresh.
    The caller owns atomic publication of the completed temporary output.
    """
    total = _number(total_duration, "total_duration", 0, MAX_SECONDS, positive=True)
    rows = overlay_layers(template, aspect_ratio, legacy_path=legacy_path, total_duration=total, check_files=True)
    occurrences = [(row, overlay_intervals(row, total)) for row in rows]
    occurrences = [(row, times) for row, times in occurrences if times]
    reactivations = sum(max(0, len(times) - 1) for row, times in occurrences if row["mode"] == "repeat")
    if reactivations > MAX_REPEATED_ACTIVATIONS:
        raise ValueError(f"Наложения: максимум {MAX_REPEATED_ACTIVATIONS} повторных включений во всём ролике; увеличьте интервал повторов")
    command = [ffmpeg, "-y", "-protocol_whitelist", "file,pipe", "-i", str(source)]
    filters, audio = ["[0:v]setpts=PTS-STARTPTS,format=rgba[base]"], []
    main = "base"
    for input_index, (row, times) in enumerate(occurrences, 1):
        if row["kind"] == "image":
            command += ["-loop", "1", "-framerate", "30", "-protocol_whitelist", "file,pipe", "-i", row["path"]]
        else:
            command += ["-stream_loop", "-1", "-protocol_whitelist", "file,pipe", "-i", row["path"]]
        prefix = f"l{input_index}"
        incoming = f"{input_index}:v"
        if row["chromaEnabled"]:
            filters += [f"[{incoming}]format=rgba,split=2[{prefix}original][{prefix}keysrc]",
                        f"[{prefix}original]alphaextract[{prefix}originalpha]",
                        f"[{prefix}keysrc]format=yuva444p,chromakey=0x{row['chromaColor'][1:]}:{_n(row['chromaSimilarity'])}:{_n(row['chromaBlend'])},format=rgba,split=2[{prefix}keyed][{prefix}keyalpha]",
                        f"[{prefix}keyalpha]alphaextract[{prefix}mask]",
                        f"[{prefix}originalpha][{prefix}mask]blend=all_mode=multiply[{prefix}alpha]",
                        f"[{prefix}keyed][{prefix}alpha]alphamerge[{prefix}key]"]
            incoming = f"{prefix}key"
        if row.get("_legacy"):
            scale = f"scale={_n(row['width'])}:-2"
            x, y = "(W-w)/2", "H-h-24"
        else:
            scale = f"scale={round(row['width'])}:{round(row['height'])}"
            if row["keepAspect"]:
                scale += ":force_original_aspect_ratio=decrease"
            x, y = _n(row["x"]), _n(row["y"])
        labels = "".join(f"[{prefix}v{i}]" for i in range(len(times)))
        filters.append(f"[{incoming}]{scale},setsar=1,format=rgba,colorchannelmixer=aa={_n(row['opacity'])},split={len(times)}{labels}")
        audible = row["kind"] == "video" and row["audioEnabled"] and _has_audio(ffmpeg, Path(row["path"]))
        if audible:
            filters.append(f"[{input_index}:a]asplit={len(times)}" + "".join(f"[{prefix}a{i}]" for i in range(len(times))))
        for occurrence, (begin, end) in enumerate(times):
            label, composed = f"{prefix}trim{occurrence}", f"{prefix}out{occurrence}"
            filters += [f"[{prefix}v{occurrence}]trim=duration={_n(end-begin)},setpts=PTS-STARTPTS+{_n(begin)}/TB[{label}]",
                        f"[{main}][{label}]overlay=x={x}:y={y}:eof_action=pass:repeatlast=0:format=auto:enable='gte(t,{_n(begin)})*lt(t,{_n(end)})'[{composed}]"]
            main = composed
            if audible:
                tag = f"{prefix}audio{occurrence}"
                filters.append(f"[{prefix}a{occurrence}]atrim=duration={_n(end-begin)},asetpts=PTS-STARTPTS,adelay={round(begin*1000)}:all=1[{tag}]")
                audio.append(tag)
    filters.append(f"[{main}]format=yuv420p[outv]")
    base_audio = _has_audio(ffmpeg, source)
    if audio:
        if base_audio:
            filters.append("[0:a]asetpts=PTS-STARTPTS[baseaudio]")
            audio.insert(0, "baseaudio")
        filters.append("".join(f"[{tag}]" for tag in audio) + f"amix=inputs={len(audio)}:duration=longest:normalize=0,apad,atrim=duration={_n(total)}[outa]")
    # Keep large repeat graphs outside Windows' 32768-character process limit.
    # The unique script remains alive for FFmpeg and is removed on any failure.
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".newsflow-overlaygraph-", dir=output.parent) as temporary:
        script = Path(temporary) / "overlays.ffscript"
        graph = ";\n".join(filters)
        script.write_text(graph, encoding="utf-8")
        option = _filter_graph_option(ffmpeg)
        if option == "-filter_complex" and len(graph) > 24000:
            raise ValueError("Наложения: неизвестная версия FFmpeg не поддерживает большой граф; используйте FFmpeg 6 или новее")
        command += [option, graph if option == "-filter_complex" else str(script), "-map", "[outv]"]
        if audio:
            command += ["-map", "[outa]", "-c:a", "aac", "-b:a", "192k"]
        elif base_audio:
            command += ["-map", "0:a:0", "-c:a", "copy"]
        command += [*encoder_args, "-t", _n(total), "-movflags", "+faststart", str(output)]
        if sys.platform == "win32" and len(subprocess.list2cmdline(command)) > 30000:
            raise ValueError("Наложения: пути к файлам слишком длинные для Windows; сократите пути")
        if run is None:
            from .timeline import _run
            run = _run
        run(command)
    return output
