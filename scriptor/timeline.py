from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from xml.sax.saxutils import quoteattr

_ENCODER_CACHE: dict[str, list[str]] = {}
_PROXY_LOCK_GUARD = threading.RLock()
_PROXY_LOCKS: dict[str, threading.Lock] = {}


def _replace_with_retry(source: Path, target: Path, timeout: float = 20.0) -> None:
    """Atomically publish a rendered file, tolerating short Windows locks.

    Windows Media Player, Explorer preview and antivirus can retain a just
    rendered MP4 for a moment.  A direct ``os.replace`` then raises WinError
    32 and used to fail an otherwise completed montage.  The source remains a
    uniquely named ``.partial`` file, so retrying is safe and never overwrites
    another worker's output.
    """
    deadline = time.monotonic() + max(0.1, timeout)
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            os.replace(source, target)
            return
        except PermissionError as error:
            last_error = error
            time.sleep(0.2)
    raise RuntimeError(
        f"Не удалось сохранить MP4: файл занят другой программой: {target.name}. "
        "Закройте предпросмотр/плеер и повторите задачу."
    ) from last_error


@contextmanager
def _proxy_lock(path: Path, timeout: float = 180.0):
    """Lock one normalised proxy across threads *and* bridge processes.

    A render queue runs inside a long-lived worker, but manual commands arrive
    through short-lived Electron bridge processes.  A Python ``threading.Lock``
    alone therefore cannot protect the same proxy MP4 from two commands.  The
    tiny sidecar lock uses the operating-system file lock; it is automatically
    released when a crashed process closes its handle and the sidecar itself is
    harmless to keep for the next task.
    """
    key = str(path.resolve()).casefold()
    with _PROXY_LOCK_GUARD:
        thread_lock = _PROXY_LOCKS.setdefault(key, threading.Lock())
    with thread_lock:
        lock_path = path.with_name(f".{path.name}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Initialise exactly once.  Do not read/write the byte after
            # another process has locked it: Windows then reports access
            # denied before ``msvcrt.locking`` has a chance to wait.
            with lock_path.open("xb") as initializer:
                initializer.write(b"0")
                initializer.flush()
        except FileExistsError:
            pass
        with lock_path.open("r+b") as handle:
            acquired = False
            deadline = time.monotonic() + max(1.0, timeout)
            if os.name == "nt":
                import msvcrt
                while not acquired:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(
                                f"Не удалось дождаться подготовки футажа: {path.name}"
                            )
                        time.sleep(0.10)
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


@dataclass
class TimelineClip:
    path: str
    narration: str
    visual_query_en: str
    duration: float = 3.0
    source_start: float = 0.0
    score: float = 0.0
    source: str = "local"
    fallback_level: str = "STRICT_MATCH"
    source_family: str = ""
    reused: bool = False
    position_bucket: str = ""
    position_rotation_penalty: float = 0.0
    position_rotation_reason: str = ""
    strict_rejection_reason: str = ""
    voice_segment_id: int = 0
    voice_segment_ids: list[int] = field(default_factory=list)
    narration_start: float = 0.0
    narration_end: float = 0.0
    minimum_source_duration: float = 0.0
    visual_beat_index: int = 0
    visual_beat_count: int = 0


@dataclass
class TimelineProject:
    title: str
    aspect_ratio: str = "16:9"
    clips: list[TimelineClip] = field(default_factory=list)
    voiceover_path: str = ""
    output_path: str = ""
    davinci_xml_path: str = ""
    intro_path: str = ""
    intro_duration: float = 0.0
    overlay_path: str = ""
    transition_style: str = "crossfade"
    transition_frames: int = 7
    selection_summary: dict = field(default_factory=dict)
    preparation_metrics_ms: dict = field(default_factory=dict)
    voice_map_provenance: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.intro_duration + sum(item.duration for item in self.clips)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["clips"] = [TimelineClip(**item) for item in data.get("clips", [])]
        return cls(**data)


def split_narration(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    sentences = re.split(r"(?<=[.!?…])\s+", compact)
    result = []
    for sentence in sentences:
        words = sentence.split()
        while len(words) > 20:
            result.append(" ".join(words[:16]))
            words = words[16:]
        if words:
            result.append(" ".join(words))
    return result


VISUAL_TERMS = {
    # These are deliberately concrete, observable associations.  They give the
    # free local planner useful CLIP queries when a paid scene agent is off.
    "иран": "Iran Tehran Iranian flag", "тегеран": "Tehran Iran city government",
    "ормуз": "Strait of Hormuz oil tankers Persian Gulf", "танкер": "oil tanker cargo ship port",
    "нефт": "oil tanker refinery oil terminal", "украин": "Ukraine Ukrainian flag Kyiv",
    # "Russia" alone must not become a Kremlin office.  Kremlin/Putin are a
    # specific political visual and are requested only when the narration
    # actually names them.
    "росси": "Russia current events", "москв": "Moscow Russia government city",
    "кремл": "Kremlin Moscow government", "вашингтон": "Washington DC White House US government officials",
    "сша": "United States Washington DC government officials", "америк": "United States government Washington DC",
    "киев": "Kyiv Ukraine government city", "брюссел": "Brussels European Union institutions",
    "евросоюз": "European Union parliament commission Brussels flags",
    "путин": "Vladimir Putin press conference", "трамп": "Donald Trump press conference",
    "зеленск": "Volodymyr Zelensky Ukraine", "нато": "NATO headquarters flags military alliance officials",
    "альянс": "NATO military alliance headquarters officials flags",
    "европ": "Europe European Parliament Brussels institutions",
    "санкц": "economic sanctions finance banking trade restrictions markets",
    "эконом": "economy finance business markets industry", "рынк": "financial markets trading screens business",
    "банк": "banking finance money business", "торгов": "trade cargo logistics markets business",
    "гибрид": "cybersecurity network operations military command Europe",
    "кибер": "cybersecurity operations computer networks servers monitoring",
    "хакер": "cybersecurity computer network operations monitoring screens",
    "одесс": "Odesa port Black Sea", "порт": "seaport cargo cranes ships", "кораб": "ship navy cargo vessel",
    "завод": "industrial factory workers", "переговор": "diplomatic negotiations leaders journalists cameras",
    "саммит": "political summit leaders journalists", "армени": "Armenia Yerevan",
    "азербайдж": "Azerbaijan Baku", "израил": "Israel military border", "ливан": "Lebanon Beirut",
    "энерг": "energy infrastructure power plant", "склад": "warehouse fire emergency workers",
    # Military reports must request the visible action, not the abstract word
    # "war".  This separates an offensive/frontline from a Kremlin office or
    # an unrelated politician shot in a large mixed footage library.
    "наступлен": "frontline battlefield soldiers advancing infantry armored vehicles",
    "фронт": "frontline trenches soldiers battlefield military action",
    "окоп": "frontline trenches soldiers battlefield", "солдат": "soldiers infantry patrol frontline",
    "войск": "troops soldiers military convoy frontline", "арм": "army soldiers military vehicles",
    "танк": "tanks armored vehicles military convoy", "бронетех": "armored vehicles military convoy",
    "артилл": "artillery firing military position battlefield", "ракет": "missile launcher air defense military",
    "обстрел": "artillery shelling explosion damaged buildings", "дрон": "military drone battlefield soldiers",
    "военн": "soldiers military vehicles", "удар": "explosion aftermath firefighters damaged buildings",
    "разруш": "war damaged buildings firefighters rescue workers",
    "митинг": "protest crowd placards flags street rally", "протест": "protest crowd placards flags street rally",
    "демонстр": "protest crowd demonstration banners street", "пикет": "picket line workers protest banners",
    "забастов": "workers labor strike picket line factory gate", "беспоряд": "street unrest crowd police barriers",
    "мигрант": "migrants border crossing checkpoint fence luggage", "границ": "border checkpoint guards fence",
    "депортац": "migrants border guards transport checkpoint", "бежен": "refugees evacuation buses families luggage",
    "эвакуац": "civilian evacuation emergency transport families luggage", "фермер": "farmers tractors protest",
    "картош": "potato harvest farm tractor agricultural field", "урож": "harvest farming combine wheat field",
    "сельхоз": "agriculture farm tractor combine field workers", "пшениц": "wheat harvest grain field combine",
    "зерн": "grain harvest agricultural storage wheat field", "комбайн": "farm combine harvester agricultural field",
}


GENERIC_VISUAL_QUERY = "international news, documentary footage"


def fallback_visual_query(text: str) -> str:
    lowered = text.casefold()
    terms = [english for stem, english in VISUAL_TERMS.items() if stem in lowered]
    return ", ".join(dict.fromkeys(terms)) or GENERIC_VISUAL_QUERY


def fallback_scene_plan(narration: str, topic: str = "") -> list[dict]:
    """Build deterministic scenes while retaining the overall news topic.

    Later sentences often use pronouns such as "это" or "он" and contain no
    country, subject or location on their own.  Searching only those words
    used to let an unrelated war clip outrank footage from the actual story.
    The title is therefore appended as stable visual context to every local
    scene query; it does not change the narration or invent an event.
    """
    plan = []
    topic_query = fallback_visual_query(topic) if topic else ""
    for sentence in split_narration(narration):
        word_count = len(sentence.split())
        duration = min(6.0, max(2.5, word_count / 2.7))
        sentence_query = fallback_visual_query(sentence)
        if sentence_query == GENERIC_VISUAL_QUERY and topic_query != GENERIC_VISUAL_QUERY:
            sentence_query = ""
        query = ", ".join(dict.fromkeys(filter(None, (topic_query, sentence_query))))
        plan.append({"narration": sentence, "visual_query_en": query,
                     "duration": round(duration, 2)})
    return plan


def title_only_scene_plan(topic: str, duration: float) -> list[dict]:
    """Create a quick visual plan when the user intentionally skips TXT.

    The MP3 remains the timing authority.  We make 3–6 second scenes using
    only the title's visual context; this is faster but intentionally less
    precise than the normal narration-aware planner.
    """
    total = max(1.0, float(duration or 0.0))
    count = max(1, math.ceil(total / 4.5))
    query = fallback_visual_query(topic)
    base = total / count
    return [{"narration": topic, "visual_query_en": query, "duration": round(base, 2)} for _ in range(count)]


def fit_scene_plan_to_voice_duration(scenes: list[dict], voice_duration: float,
                                     max_clip_duration: float = 6.0) -> list[dict]:
    """Fit visuals to narration using full source-length beats.

    NewsFlow footage is normally cut to about six seconds. Every normal beat
    therefore remains six seconds; only the final beat receives the residual
    tail required to align video and narration exactly.
    """
    usable = [dict(scene) for scene in scenes if isinstance(scene, dict)]
    target = max(0.0, float(voice_duration or 0.0))
    ceiling = max(0.5, float(max_clip_duration or 5.8))
    current = sum(max(0.0, float(scene.get("duration", 0.0) or 0.0)) for scene in usable)
    if not usable or current <= 0.0 or target <= 0.0:
        return usable

    # Spread the authored queries over the narration proportionally, but never
    # spread a small residual over every source clip (the old 6→4→3 trimming).
    source_edges = []
    cursor = 0.0
    for scene in usable:
        cursor += max(0.0, float(scene.get("duration", 0.0) or 0.0)) / current * target
        source_edges.append(cursor)
    full_count = int(target // ceiling)
    remainder = round(target - full_count * ceiling, 3)
    durations = [round(ceiling, 3)] * full_count
    if remainder > 0.02:
        durations.append(remainder)
    if not durations:
        durations = [round(target, 3)]
    result: list[dict] = []
    elapsed = 0.0
    source_index = 0
    for duration in durations:
        midpoint = elapsed + duration / 2
        while source_index < len(source_edges) - 1 and midpoint > source_edges[source_index]:
            source_index += 1
        scene = dict(usable[source_index])
        scene["duration"] = duration
        result.append(scene)
        elapsed += duration
    return result


def parse_agent_scene_plan(value: str) -> list[dict]:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", value, re.DOTALL | re.IGNORECASE)
    payload = fenced.group(1) if fenced else value
    start, end = payload.find("["), payload.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("Агент не вернул JSON-массив сцен")
    data = json.loads(payload[start:end + 1])
    result = []
    for item in data:
        narration = str(item.get("narration", "")).strip()
        visual = str(item.get("visual_query_en", "")).strip()
        if not narration or not visual:
            continue
        duration = min(6.0, max(1.5, float(item.get("duration", 3.0))))
        result.append({"narration": narration, "visual_query_en": visual, "duration": duration})
    if not result:
        raise ValueError("В плане нет пригодных сцен")
    return result


def agent_plan_prompt(title: str, narration: str) -> str:
    return (
        "Ты планировщик видеоряда для новостного ролика. Разбей дикторский текст на короткие сцены. "
        "Для каждой сцены создай конкретный запрос НА АНГЛИЙСКОМ к визуальной CLIP-медиатеке. "
        "Запрос должен описывать видимые объекты, людей, места и действия, а не абстрактный смысл. "
        "Для удара указывай последствия, спасателей, повреждённую инфраструктуру или военных; для переговоров — "
        "конкретных участников только если они названы, стол переговоров и журналистов; для протеста — толпу и плакаты. "
        "Сцены про бой, удар, фронт, войска, эвакуацию или разрушения НЕ заменяй кадром Кремля, кабинетом, "
        "переговорами или политиком, если это прямо не сказано в соответствующей реплике. "
        "Не добавляй в кадр несвязанного политика и не придумывай событие. "
        "Одна сцена длится 2–6 секунд. Не добавляй факты и не меняй текст диктора. "
        "Верни только JSON-массив объектов: "
        "[{\"narration\":\"...\",\"visual_query_en\":\"...\",\"duration\":3.5}].\n"
        f"ТЕМА: {title}\nДИКТОРСКИЙ ТЕКСТ:\n{narration}"
    )


def ffmpeg_executable() -> str:
    roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])),
             Path(__file__).resolve().parents[1]]
    for root in roots:
        candidate = root / "assets" / "ffmpeg.exe"
        if candidate.exists():
            return str(candidate)
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("FFmpeg не найден в сборке") from exc


def _run(command: list[str], process_observer: Callable[[int | None], None] | None = None):
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", creationflags=flags)
    if process_observer:
        process_observer(process.pid)
    try:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=2.0)
                break
            except subprocess.TimeoutExpired:
                # FFmpeg can legitimately spend minutes normalising a long
                # source. Refresh the owning queue row while its process is
                # demonstrably alive so watchdog/restart logic never treats it
                # as a silent stuck render.
                if process_observer:
                    process_observer(process.pid)
    finally:
        if process_observer:
            process_observer(None)
    if process.returncode:
        message = (stderr or stdout or "FFmpeg завершился с ошибкой")[-3000:]
        if "No space left on device" in message or "error code: -28" in message:
            raise RuntimeError(
                "Недостаточно места для временного MP4. NewsFlow собирает временные файлы "
                "в D:\\NewsFlow Studio\\Временный рендер; освободите место на D: и повторите задачу."
            )
        raise RuntimeError(message)


def video_encoder_args(ffmpeg: str) -> list[str]:
    if ffmpeg in _ENCODER_CACHE:
        return list(_ENCODER_CACHE[ffmpeg])
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags, check=False)
    if "h264_nvenc" in (result.stdout or ""):
        args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "0"]
    else:
        args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
    _ENCODER_CACHE[ffmpeg] = args
    return list(args)


def probe_media_duration(path: Path) -> float:
    ffmpeg = ffmpeg_executable()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags, check=False)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
    if not match:
        raise ValueError("Не удалось определить длительность озвучки")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def probe_video_duration(path: Path) -> float:
    """Return duration only when the file is readable and contains video."""
    ffmpeg = ffmpeg_executable()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags, check=False)
    details = result.stderr or ""
    if not re.search(r"\bVideo:\s", details):
        raise ValueError("В файле нет читаемого видеопотока")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    if not match:
        raise ValueError("Не удалось определить длительность видео")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0.05:
        raise ValueError("Видео имеет нулевую длительность")
    return duration


def validate_rendered_montage(path: Path, *, expected_duration: float) -> float:
    """Validate the final published MP4 before a queue can mark it READY.

    Recovery may use a cheap ISO-BMFF header check for a large historical
    batch, but a *new* render must have readable video and audio and cover the
    planned narration.  This deliberately runs once per completed render,
    never once per dashboard row.
    """
    ffmpeg = ffmpeg_executable()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", creationflags=flags, check=False)
    details = result.stderr or ""
    if not re.search(r"\bVideo:\s", details):
        raise ValueError("В итоговом MP4 нет читаемого видеопотока")
    if not re.search(r"\bAudio:\s", details):
        raise ValueError("В итоговом MP4 нет аудиопотока")
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    if not match:
        raise ValueError("Не удалось определить длительность итогового MP4")
    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    if duration <= 0.05:
        raise ValueError("Итоговый MP4 имеет нулевую длительность")
    if duration + 0.15 < max(0.0, float(expected_duration)):
        raise ValueError(
            f"Итоговый MP4 короче озвучки: {duration:.2f} сек. вместо {expected_duration:.2f} сек."
        )
    return duration


def required_video_duration(voice_duration: float, intro_duration: float = 0.0) -> float:
    """Minimum visual duration required to preserve delayed voiceover."""
    return max(0.0, float(voice_duration)) + max(0.0, float(intro_duration))


def _remaining_source_duration(source_duration: float, source_start: float) -> float:
    """Return playable source duration left after a clip-specific start offset."""
    return max(0.0, float(source_duration) - max(0.0, float(source_start)))


def align_timeline_to_audio(
    project: TimelineProject,
    required_duration: float,
    candidates: list[TimelineClip],
    *,
    duration_probe: Callable[[Path], float] = probe_media_duration,
    tolerance: float = 0.05,
    allow_terminal_reuse: bool = False,
) -> list[TimelineClip]:
    """Make the visual timeline cover the narration without looping footage.

    Each valid source is kept at its real duration.  A trim is allowed only on
    the final source that crosses the required duration.  When the saved plan
    is short, candidates are appended one by one; an exhausted candidate pool
    is a recoverable planning error rather than a request to clone a frame.
    """
    target = max(0.0, float(required_duration))
    if target <= tolerance:
        project.clips = []
        return []

    def source_duration(clip: TimelineClip) -> float:
        value = float(duration_probe(Path(clip.path)))
        if value <= tolerance:
            raise ValueError(f"Футаж имеет нулевую длительность: {clip.path}")
        return value

    normalized: list[TimelineClip] = []
    total = 0.0
    for clip in project.clips:
        if total >= target - tolerance:
            break
        available = _remaining_source_duration(source_duration(clip), clip.source_start)
        remaining = max(0.0, target - total)
        contribution = min(available, remaining)
        normalized.append(replace(clip, duration=contribution))
        total += contribution
        if contribution < available - tolerance:
            project.clips = normalized
            return []

    added: list[TimelineClip] = []
    used_paths = {str(Path(clip.path)).casefold() for clip in normalized}
    terminal_reuse_used = False
    for candidate in candidates:
        if total >= target - tolerance:
            break
        candidate_key = str(Path(candidate.path)).casefold()
        if candidate_key in used_paths:
            # This is intentionally limited to one final real-footage reuse.
            # It is used only after the Montage selector has exhausted unique
            # candidates, so a short residual never creates an audio gap or
            # a cloned frozen frame.
            if not allow_terminal_reuse or terminal_reuse_used:
                continue
            terminal_reuse_used = True
        try:
            available = _remaining_source_duration(source_duration(candidate), candidate.source_start)
        except (OSError, ValueError):
            continue
        remaining = max(0.0, target - total)
        contribution = min(available, remaining)
        appended = replace(candidate, duration=contribution)
        normalized.append(appended)
        added.append(appended)
        used_paths.add(candidate_key)
        total += contribution
        if contribution < available - tolerance:
            break

    if target - total > tolerance:
        raise ValueError(
            "Не удалось подобрать достаточное число валидных футажей "
            f"для завершения таймлайна (не хватает {target - total:.2f} сек.)"
        )
    project.clips = normalized
    return added


def _writable_render_folder(folder: Path, minimum_free_bytes: int = 512 * 1024 * 1024) -> Path:
    """Return a usable render folder without silently filling the system disk."""
    folder.mkdir(parents=True, exist_ok=True)
    # A directory can be writable but still be on a nearly-full system disk.
    # Rendering writes concatenated intermediate MP4s, so reserve a modest
    # workspace before FFmpeg starts a long job and produces an opaque -28.
    if shutil.disk_usage(folder).free < minimum_free_bytes:
        raise OSError(f"Недостаточно свободного места для временного рендера: {folder}")
    probe = folder / f".write-probe-{os.getpid()}-{threading.get_ident()}"
    try:
        with probe.open("xb") as handle:
            handle.write(b"0")
    finally:
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
    return folder


def render_workspace_root() -> Path:
    """Store all disposable montage files on D: by default, not on C:/Temp."""
    preferred = Path(os.environ.get("NEWSFLOW_RENDER_TEMP_ROOT", r"D:\NewsFlow Studio\Временный рендер"))
    try:
        return _writable_render_folder(preferred)
    except OSError:
        # Keep a functional fallback for computers without a D: drive, but do
        # not choose it when D: is available. The raised message retains the
        # failing folder for a useful task status should every location fail.
        try:
            return _writable_render_folder(Path(tempfile.gettempdir()) / "NewsFlow" / "Временный рендер")
        except OSError as fallback_error:
            raise RuntimeError(
                "Недостаточно места для временного рендера. Освободите место на D: "
                "или задайте NEWSFLOW_RENDER_TEMP_ROOT на другой диск."
            ) from fallback_error


def proxy_cache_root() -> Path:
    try:
        return _writable_render_folder(render_workspace_root() / "RenderProxy")
    except (OSError, RuntimeError):
        # A custom temp root may be unavailable. Keep the historical cache as
        # a last resort, but its free-space check prevents another hidden C:
        # exhaustion.
        from .config import app_data_root
        return _writable_render_folder(app_data_root() / "RenderProxy")


def _proxy_key(clip: TimelineClip, width: int, height: int) -> str:
    source = Path(clip.path)
    stat = source.stat()
    value = (f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{clip.source_start:.3f}|"
             f"{clip.duration:.3f}|{width}x{height}|30fps|crf20|proxy-v3-loop-short-source")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _remotion_runner() -> tuple[str, str] | None:
    """Return Electron-in-Node and the bundled Remotion adapter when available.

    The portable application supplies these two paths through Electron.  Keeping
    the legacy FFmpeg path below makes developer diagnostics and old projects
    usable, while new NewsFlow builds render the actual final timeline through
    Remotion.
    """
    node = os.environ.get("NEWSFLOW_REMOTION_NODE", "").strip()
    runner = os.environ.get("NEWSFLOW_REMOTION_RUNNER", "").strip()
    # ``runner`` lives inside Electron's app.asar in a packaged build, so it
    # cannot be checked with Python's Path.exists(). Electron itself resolves
    # that virtual path when launched in Node mode.
    if node and runner and Path(node).exists():
        return node, runner
    return None


def _remotion_memory_error(message: str) -> bool:
    """Whether Chromium stopped because render parallelism exhausted resources."""
    text = str(message or "").casefold()
    markers = (
        "ran out of memory", "out of memory", "datacloneerror",
        "could not take a screenshot", "timed out evaluating page function",
        "waiting for the page to render", "err_memory",
    )
    return any(marker in text for marker in markers)


def _render_project_remotion(project: TimelineProject, output: Path,
                             progress: Callable[[int, int, str], None] | None = None,
                             frame_concurrency: int = 1,
                             parallel_jobs: int = 1) -> Path:
    configured = _remotion_runner()
    if configured is None:
        raise RuntimeError("Remotion не найден в этой сборке NewsFlow")
    node, runner = configured
    if not project.clips:
        raise ValueError("Таймлайн пуст")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = output.with_name(f".{output.stem}.{os.getpid()}.remotion.json")
    partial = output.with_name(f"{output.stem}.{os.getpid()}.partial.mp4")
    manifest.write_text(json.dumps(remotion_payload(project), ensure_ascii=False), encoding="utf-8")
    total = 100
    # Frame and job parallelism are explicit user settings.  Do not quietly
    # downgrade them: a powerful workstation may deliberately use every slot.
    requested_frames = max(1, int(frame_concurrency or 1))
    active_jobs = max(1, int(parallel_jobs or 1))
    env = {
        **os.environ,
        "ELECTRON_RUN_AS_NODE": "1",
        "NEWSFLOW_REMOTION_FRAME_CONCURRENCY": str(requested_frames),
        "NEWSFLOW_REMOTION_PARALLEL_JOBS": str(active_jobs),
        "NEWSFLOW_REMOTION_TIMEOUT_MS": "180000",
    }
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    def run_once(workers: int) -> str:
        current_command = [node, runner, str(manifest), str(partial), str(workers), str(active_jobs)]
        current_env = {**env, "NEWSFLOW_REMOTION_FRAME_CONCURRENCY": str(workers)}
        process = subprocess.Popen(current_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding="utf-8", errors="replace", env=current_env, creationflags=flags)
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "newsflow-remotion":
                continue
            percent = max(1, min(100, int(event.get("progress") or 1)))
            if progress:
                progress(percent, total, str(event.get("stage") or "Remotion"))
        stderr = process.stderr.read() if process.stderr else ""
        code = process.wait()
        if code != 0:
            return stderr or "Remotion завершился с ошибкой"
        return ""

    try:
        error = run_once(requested_frames)
        if error:
            if _remotion_memory_error(error):
                raise RuntimeError(
                    "Remotion: Chrome не хватило памяти. Уменьшите заданные вами "
                    "«Видео одновременно» или «Кадров параллельно» и повторите задачу."
                )
            message = error[-3000:]
            raise RuntimeError(f"Remotion: {message}")
        if not partial.exists() or partial.stat().st_size < 1024:
            raise RuntimeError("Remotion не создал итоговый MP4")
        _replace_with_retry(partial, output)
        project.output_path = str(output)
        if progress:
            progress(total, total, "MP4 Remotion готов")
        return output
    finally:
        try:
            manifest.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
        except OSError:
            pass


def render_project(project: TimelineProject, output: Path, progress: Callable[[int, int, str], None] | None = None,
                   renderer: str = "ffmpeg", remotion_concurrency: int | None = None,
                   remotion_parallel_jobs: int = 1,
                   heartbeat: Callable[[int | None], None] | None = None):
    if not project.clips:
        raise ValueError("Таймлайн пуст")
    # FAST NEWS uses the direct, cached FFmpeg pipeline by default.  Remotion
    # remains an explicit composition choice; it must never become an implicit
    # fallback when a current caller omits the renderer argument.
    if renderer == "remotion":
        if _remotion_runner() is None:
            raise RuntimeError("Remotion не найден в этой сборке NewsFlow")
        return _render_project_remotion(
            project, output, progress,
            frame_concurrency=max(1, int(remotion_concurrency or 1)),
            parallel_jobs=max(1, int(remotion_parallel_jobs or 1)),
        )
    if renderer != "ffmpeg":
        raise ValueError(f"Неподдерживаемый рендерер монтажа: {renderer}")
    ffmpeg = ffmpeg_executable()
    def run_ffmpeg(command: list[str]) -> None:
        _run(command, process_observer=heartbeat)
    width, height = (1080, 1920) if project.aspect_ratio == "9:16" else (1920, 1080)
    output.parent.mkdir(parents=True, exist_ok=True)
    published_output = output
    # A forced retry must never truncate a valid MP4 before its replacement
    # succeeds.  FFmpeg writes a sibling partial, then Windows receives one
    # atomic publish operation after audio/video validation has passed.
    output = published_output.with_name(
        f"{published_output.stem}.{os.getpid()}.{threading.get_ident()}.partial{published_output.suffix}"
    )
    render_clips = list(project.clips)
    if project.intro_path and Path(project.intro_path).exists() and project.intro_duration > 0:
        render_clips.insert(0, TimelineClip(project.intro_path, "Заставка", "intro", project.intro_duration, source="intro"))
    # Encoders can round a 30fps proxy down by a few frames.  Borrow that
    # tiny technical margin from the *real final source* before rendering,
    # rather than cloning its final frame after concat.  ``-shortest`` then
    # ends exactly on the narration without frozen visual padding.
    voice_for_margin = Path(project.voiceover_path) if project.voiceover_path else None
    if voice_for_margin and voice_for_margin.is_file() and project.clips:
        try:
            target = required_video_duration(probe_media_duration(voice_for_margin), project.intro_duration)
            margin = 0.15
            current = sum(max(0.0, float(clip.duration)) for clip in render_clips)
            needed = target + margin - current
            tail_index = len(render_clips) - 1
            tail = render_clips[tail_index]
            available = _remaining_source_duration(
                probe_video_duration(Path(tail.path)), tail.source_start,
            )
            if needed > 0.0 and available + 0.01 >= tail.duration + needed:
                render_clips[tail_index] = replace(tail, duration=tail.duration + needed)
        except (OSError, RuntimeError, ValueError):
            # The strict source preflight in the queue will surface a real
            # problem.  Legacy manual FFmpeg rendering retains its clear
            # timeline-length validation below.
            pass
    total = len(render_clips) + 2
    temp_root = render_workspace_root()
    with tempfile.TemporaryDirectory(prefix="newsflow-render-", dir=temp_root) as temporary:
        work = Path(temporary)
        normalized = []
        cache_root = proxy_cache_root()
        # A custom/cache-root override (including portable tests) may point at
        # a directory that does not exist yet.  Creating it here also makes
        # proxy rendering resilient after a cleanup of AppData.
        cache_root.mkdir(parents=True, exist_ok=True)
        for index, clip in enumerate(render_clips, 1):
            source = Path(clip.path)
            if not source.exists():
                raise FileNotFoundError(f"Футаж не найден: {source}")
            target = cache_root / f"{_proxy_key(clip, width, height)}.mp4"
            # FFmpeg's ``-t 6.000`` at 30fps can encode only 179 frames
            # (5.97s). Across 44 ordinary clips that silently removed 1.3s
            # from a real NewsFlow video. Ask for one extra frame from the
            # source; the final audio mux still ends at the exact MP3 length.
            proxy_duration = max(0.1, clip.duration + (1.0 / 30.0) + 0.002)
            filter_value = (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},fps=30,format=yuv420p"
            )
            # Several videos can legitimately use the same 6-second local
            # footage.  Serialize only that exact proxy, not the entire render
            # queue, so two workers never write/rename the same partial MP4.
            with _proxy_lock(target):
                if not target.exists() or target.stat().st_size < 1024:
                    partial = target.with_name(
                        f"{target.stem}.{os.getpid()}.{threading.get_ident()}.partial.mp4"
                    )
                    try:
                        # A short *moving* source can safely repeat from its
                        # beginning.  This keeps the requested visual beat in
                        # motion instead of truncating the final narration.
                        # The selector still avoids this for normal queue
                        # planning; this is only the renderer's bounded
                        # fallback for an explicit clip already in a project.
                        available = _remaining_source_duration(probe_video_duration(source), clip.source_start)
                        loop_args = ["-stream_loop", "-1"] if available + 0.01 < proxy_duration else []
                        command = [ffmpeg, "-y", *loop_args, "-ss", f"{max(0.0, clip.source_start):.3f}",
                                   "-t", f"{proxy_duration:.3f}", "-i", str(source),
                                   "-vf", filter_value, "-an", *video_encoder_args(ffmpeg),
                                   "-movflags", "+faststart", str(partial)]
                        try:
                            run_ffmpeg(command)
                        except RuntimeError:
                            if "h264_nvenc" not in command:
                                raise
                            _ENCODER_CACHE[ffmpeg] = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
                            command = [ffmpeg, "-y", *loop_args, "-ss", f"{max(0.0, clip.source_start):.3f}",
                                       "-t", f"{proxy_duration:.3f}", "-i", str(source),
                                       "-vf", filter_value, "-an", *_ENCODER_CACHE[ffmpeg],
                                       "-movflags", "+faststart", str(partial)]
                            run_ffmpeg(command)
                        _replace_with_retry(partial, target, timeout=12.0)
                    finally:
                        try:
                            if partial.exists():
                                partial.unlink()
                        except OSError:
                            pass
            normalized.append(target)
            if progress:
                progress(index, total, source.name)
        concat_file = work / "concat.txt"
        concat_file.write_text("\n".join(f"file '{str(path).replace('\\', '/')}'" for path in normalized),
                               encoding="utf-8")
        silent = work / "silent.mp4"
        run_ffmpeg([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
              "-c", "copy", "-movflags", "+faststart", str(silent)])
        if progress:
            progress(len(render_clips) + 1, total, "Склейка")
        video_source = silent
        overlay = Path(project.overlay_path) if project.overlay_path else None
        if overlay and overlay.exists():
            composited = work / "with-overlay.mp4"
            filter_value = (
                f"[1:v]chromakey=0x00FF00:0.12:0.08,scale={width}:-2[overlay];"
                f"[0:v][overlay]overlay=(W-w)/2:H-h-24:shortest=1[outv]"
            )
            run_ffmpeg([ffmpeg, "-y", "-i", str(silent), "-stream_loop", "-1", "-i", str(overlay),
                  "-filter_complex", filter_value, "-map", "[outv]", "-an", *video_encoder_args(ffmpeg),
                  "-movflags", "+faststart", str(composited)])
            video_source = composited
        voiceover = Path(project.voiceover_path) if project.voiceover_path else None
        if voiceover and voiceover.exists():
            # The planner is required to cover the whole narration with real
            # clips.  Do not silently clone the last frame when that invariant
            # is broken: a visible frozen tail is worse than a retryable task
            # with an exact reason.
            voice_duration = probe_media_duration(voiceover)
            visual_duration = probe_media_duration(video_source)
            required_duration = required_video_duration(voice_duration, project.intro_duration)
            visual_gap = required_duration - visual_duration
            if visual_gap > 0.05:
                raise RuntimeError(
                    "Таймлайн футажей короче озвучки на "
                    f"{visual_gap:.1f} сек. Ролик не сохранён, "
                    "чтобы не получить зависший последний кадр. Нажмите «Переделать» — "
                    "NewsFlow подберёт дополнительные разные футажи."
                )
            # Keep the real sound of the initial news insert.  The narration
            # starts only after it; this avoids the old silent/truncated intro.
            intro = Path(project.intro_path) if project.intro_path else None
            if intro and intro.exists() and project.intro_duration > 0:
                delay = int(project.intro_duration * 1000)
                mix = (
                    f"[1:a]adelay={delay}:all=1[voice];"
                    f"[2:a]atrim=duration={project.intro_duration:.3f},asetpts=N/SR/TB[intro];"
                    "[intro][voice]amix=inputs=2:duration=longest:normalize=0[audio]"
                )
                run_ffmpeg([ffmpeg, "-y", "-i", str(video_source), "-i", str(voiceover), "-i", str(intro),
                      "-filter_complex", mix, "-map", "0:v:0", "-map", "[audio]", "-c:v", "copy",
                      "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output)])
            else:
                audio_filter = ["-af", f"adelay={int(project.intro_duration * 1000)}:all=1"] if project.intro_duration > 0 else []
                run_ffmpeg([ffmpeg, "-y", "-i", str(video_source), "-i", str(voiceover), "-map", "0:v:0",
                      "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                      *audio_filter, "-shortest", "-movflags", "+faststart", str(output)])
        else:
            shutil.copy2(video_source, output)
        if progress:
            progress(total, total, "Готово")
    _replace_with_retry(output, published_output)
    project.output_path = str(published_output)
    return published_output


def remotion_payload(project: TimelineProject, fps: int = 30) -> dict:
    """Portable data for the final Remotion composition stage."""
    sequences, frame = [], 0
    if project.intro_path and project.intro_duration > 0:
        duration = round(project.intro_duration * fps)
        sequences.append({"kind": "intro", "src": project.intro_path, "from": frame, "durationInFrames": duration})
        frame += duration
    for clip in project.clips:
        duration = max(1, round(clip.duration * fps))
        sequences.append({"kind": "footage", "src": clip.path, "from": frame, "durationInFrames": duration,
                          "sourceStart": clip.source_start, "narration": clip.narration})
        frame += duration
    # The canonical FFmpeg preflight rejects an insufficient footage plan
    # before it can render.  A saved Remotion manifest, however, must still
    # preserve every narration frame when it is opened/repaired later; its
    # `visualDurationInFrames` makes a short legacy plan explicit rather than
    # silently truncating the MP3.
    voice_frames = 0
    if project.voiceover_path and Path(project.voiceover_path).is_file():
        try:
            voice_frames = max(1, round(probe_media_duration(Path(project.voiceover_path)) * fps))
        except (OSError, ValueError, RuntimeError):
            voice_frames = 0
    required_frames = round(max(0.0, project.intro_duration) * fps) + voice_frames
    composition_frames = max(frame, required_frames)
    return {"schema": "newsflow-remotion/v1", "fps": fps, "aspectRatio": project.aspect_ratio,
            "durationInFrames": max(1, composition_frames), "visualDurationInFrames": frame, "sequences": sequences,
            "transitionStyle": project.transition_style,
            "transitionFrames": max(0, int(project.transition_frames)),
            "voiceover": {"src": project.voiceover_path, "from": round(project.intro_duration * fps)},
            "overlay": {"src": project.overlay_path, "chromaKey": "#00ff00", "position": "bottom"}}


def _fcpxml_time(seconds: float, fps: int = 30) -> str:
    """Encode a timeline value on an exact 30fps boundary for FCPXML."""
    frames = max(0, round(float(seconds) * fps))
    return "0s" if not frames else f"{frames}/{fps}s"


def _fcpxml_dimensions(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 1080, 1920
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1920, 1080


def _fcpxml_url(path: Path) -> str:
    # Path.as_uri() creates the Windows-compatible file:///D:/... spelling.
    return path.resolve().as_uri()


def export_fcpxml(project: TimelineProject, output: Path, fps: int = 30) -> Path:
    """Write an editable DaVinci Resolve FCPXML timeline for a NewsFlow plan.

    This is deliberately an export, not a third renderer: it references the
    selected original footage and MP3, so Resolve can open the exact sequence
    without duplicating or transcoding media.
    """
    if not project.clips:
        raise ValueError("Нельзя создать DaVinci XML: таймлайн пуст")
    width, height = _fcpxml_dimensions(project.aspect_ratio)
    output.parent.mkdir(parents=True, exist_ok=True)
    assets: list[str] = []
    asset_ids: dict[str, str] = {}

    def add_asset(path_text: str, has_video: bool, min_duration: float = 0.0) -> str | None:
        if not path_text:
            return None
        path = Path(path_text)
        if not path.is_file():
            return None
        key = str(path.resolve()).casefold()
        if key in asset_ids:
            return asset_ids[key]
        asset_id = f"r{len(asset_ids) + 2}"
        asset_ids[key] = asset_id
        try:
            duration = max(float(min_duration), probe_media_duration(path))
        except (OSError, ValueError, RuntimeError):
            duration = max(1.0, float(min_duration))
        media = ' hasVideo="1" format="r1"' if has_video else ' hasAudio="1" audioSources="1" audioChannels="2" audioRate="48000"'
        assets.append(
            f"    <asset id={quoteattr(asset_id)} name={quoteattr(path.name)} src={quoteattr(_fcpxml_url(path))} "
            f"start=\"0s\" duration={quoteattr(_fcpxml_time(duration, fps))}{media}/>"
        )
        return asset_id

    intro_id = add_asset(project.intro_path, True, project.intro_duration)
    video_rows: list[tuple[str, TimelineClip]] = []
    for clip in project.clips:
        asset_id = add_asset(clip.path, True, clip.source_start + clip.duration)
        if asset_id:
            video_rows.append((asset_id, clip))
    # The voice asset must retain its actual duration.  Using the duration of
    # the visual clips here would silently crop a longer MP3 after import into
    # Resolve, exactly when a user needs the XML as the editable source.
    voice_id = add_asset(project.voiceover_path, False, project.duration)
    if not video_rows and not intro_id:
        raise ValueError("Нельзя создать DaVinci XML: исходные футажи не найдены")

    spine: list[str] = []
    offset = 0.0
    if intro_id and project.intro_duration > 0:
        duration = project.intro_duration
        spine.append(
            f"          <asset-clip ref={quoteattr(intro_id)} name={quoteattr('Заставка')} "
            f"offset={quoteattr(_fcpxml_time(offset, fps))} start=\"0s\" duration={quoteattr(_fcpxml_time(duration, fps))}/>"
        )
        offset += duration
    for asset_id, clip in video_rows:
        duration = max(1 / fps, clip.duration)
        spine.append(
            f"          <asset-clip ref={quoteattr(asset_id)} name={quoteattr(Path(clip.path).stem)} "
            f"offset={quoteattr(_fcpxml_time(offset, fps))} start={quoteattr(_fcpxml_time(clip.source_start, fps))} "
            f"duration={quoteattr(_fcpxml_time(duration, fps))}/>"
        )
        offset += duration
    sequence_duration = offset
    if voice_id:
        try:
            voice_duration = max(1 / fps, probe_media_duration(Path(project.voiceover_path)))
        except (OSError, ValueError, RuntimeError):
            voice_duration = max(1 / fps, offset - project.intro_duration)
        sequence_duration = max(sequence_duration, project.intro_duration + voice_duration)
        spine.append(
            f"          <asset-clip ref={quoteattr(voice_id)} name={quoteattr('Озвучка')} lane=\"1\" "
            f"offset={quoteattr(_fcpxml_time(project.intro_duration, fps))} start=\"0s\" "
            f"duration={quoteattr(_fcpxml_time(voice_duration, fps))}/>"
        )
    xml = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE fcpxml>',
        '<fcpxml version="1.10">',
        '  <resources>',
        f'    <format id="r1" name="NewsFlow {width}x{height}p{fps}" frameDuration="1/{fps}s" width="{width}" height="{height}" colorSpace="1-1-1 (Rec. 709)"/>',
        *assets,
        '  </resources>',
        '  <library><event name="NewsFlow">',
        f'    <project name={quoteattr(project.title or output.stem)}>',
        f'      <sequence format="r1" duration={quoteattr(_fcpxml_time(sequence_duration, fps))} tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">',
        '        <spine>',
        *spine,
        '        </spine>',
        '      </sequence>',
        '    </project>',
        '  </event></library>',
        '</fcpxml>',
        '',
    ])
    output.write_text(xml, encoding="utf-8")
    project.davinci_xml_path = str(output)
    return output
