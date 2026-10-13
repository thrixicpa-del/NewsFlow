from __future__ import annotations

import errno
import hashlib
import json
import ntpath
import os
import shutil
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .security import protect, unprotect

_SETTINGS_WRITE_LOCK = threading.RLock()
_TEST_MODE_ENV = "NEWSFLOW_TEST_MODE"
_TEST_ROOT_ENV = "NEWSFLOW_TEST_ROOT"
_PRODUCTION_LOCALAPPDATA_ENV = "NEWSFLOW_PRODUCTION_LOCALAPPDATA"
SETTINGS_SCHEMA_VERSION = 4
_GPU_TIMELINE_AVAILABLE: bool | None = None


def _probe_gpu_timeline_available() -> bool:
    """Probe bundled FFmpeg once without making GPU an import-time requirement."""
    try:
        from .timeline import gpu_timeline_capability
        return bool(gpu_timeline_capability().get("available"))
    except (OSError, RuntimeError, ImportError):
        return False


def gpu_timeline_available() -> bool:
    """Return the per-process NVENC capability without repeatedly spawning FFmpeg."""
    global _GPU_TIMELINE_AVAILABLE
    if _GPU_TIMELINE_AVAILABLE is None:
        _GPU_TIMELINE_AVAILABLE = _probe_gpu_timeline_available()
    return _GPU_TIMELINE_AVAILABLE


def default_montage_renderer() -> str:
    """Choose the fast GPU route for a newly created profile only when usable."""
    return "gpu-timeline" if gpu_timeline_available() else "ffmpeg"


class TestStorageIsolationError(RuntimeError):
    """A test attempted to use persistent NewsFlow storage without a sandbox."""


def _is_same_or_descendant(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is the parent itself or lives beneath it."""
    return path == parent or parent in path.parents


def _is_test_runner_process() -> bool:
    """Detect an actual test runner without treating imported test modules as test mode."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True

    original = [str(value).casefold().strip() for value in getattr(sys, "orig_argv", [])]
    for index, value in enumerate(original[:-1]):
        if value == "-m" and original[index + 1] in {"unittest", "pytest"}:
            return True

    argv0 = str(sys.argv[0] if sys.argv else "").replace("\\", "/").casefold().strip()
    basename = Path(argv0).name
    return (
        argv0.endswith((" -m unittest", "/unittest/__main__.py", "/pytest/__main__.py"))
        or basename in {"pytest", "pytest.exe", "py.test", "py.test.exe"}
    )


def _test_storage_root() -> Path | None:
    """Return the required isolated root for a test process, never production.

    Unit tests commonly exercise real persistence code. Requiring an explicit
    root makes an accidental direct test-runner invocation fail before it can
    create or rewrite `%LOCALAPPDATA%/NewsFlow` or the default media folders.
    Importing unittest/pytest inside a normal packaged runtime is not itself
    evidence that the runtime is a test.
    """
    under_test = (os.environ.get(_TEST_MODE_ENV) == "1" or _is_test_runner_process())
    if not under_test:
        return None
    value = str(os.environ.get(_TEST_ROOT_ENV, "")).strip()
    if not value:
        raise TestStorageIsolationError(
            "Тестовый runtime требует отдельный NEWSFLOW_TEST_ROOT; "
            "production storage использовать запрещено."
        )
    root = Path(value).expanduser().resolve()
    production_local_appdata = Path(os.environ.get(
        _PRODUCTION_LOCALAPPDATA_ENV, os.environ.get("LOCALAPPDATA", Path.home())
    )).expanduser().resolve()
    production_storage = production_local_appdata / "NewsFlow"
    if (root == production_local_appdata
            or _is_same_or_descendant(root, production_storage)):
        raise TestStorageIsolationError(
            "NEWSFLOW_TEST_ROOT указывает на production NewsFlow storage; тест остановлен."
        )
    return root


class SettingsFileCorruptError(RuntimeError):
    """A persisted settings file cannot be safely read or replaced.

    Treating a read failure as an empty dictionary allows a later ordinary save
    to erase recoverable user state.  Callers must surface this condition and
    preserve the original file for explicit recovery instead.
    """

    def __init__(self, path: Path):
        super().__init__(f"Настройки NewsFlow повреждены и не были изменены: {path}")
        self.path = path


class SettingsFileReadError(RuntimeError):
    """An inaccessible file is not evidence of malformed persisted JSON."""

    def __init__(self, path: Path):
        super().__init__(f"Не удалось прочитать настройки NewsFlow; данные не изменены: {path}")
        self.path = path


def _read_settings_text(path: Path, *, missing_under_lock: bool = False) -> str:
    """Retry bounded Windows sharing/delete-pending races, never JSON errors.

    Readers do not hold the writer lock while opening the atomic replacement.
    Windows can briefly deny access or hide the destination during that rename.
    Persistent failures must surface without returning an empty/default state.
    """
    for attempt in range(20):
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeError as error:
            raise SettingsFileCorruptError(path) from error
        except OSError as error:
            # Only the holder of the writer lock can establish a genuinely
            # absent initial profile. A retained lock file is not live work.
            if (missing_under_lock and isinstance(error, FileNotFoundError)
                    and attempt == 19 and not path.is_file()):
                return "{}"
            retryable = (
                isinstance(error, (PermissionError, FileNotFoundError))
                or error.errno in {errno.EACCES, errno.EPERM, errno.ENOENT, errno.EBUSY}
                or getattr(error, "winerror", None) in {5, 32, 33}
            )
            if not retryable or attempt == 19:
                raise SettingsFileReadError(path) from error
            time.sleep(0.05)
    raise AssertionError("settings read retry exhausted")


class SettingsSchemaVersionError(RuntimeError):
    """A settings file belongs to a newer runtime and must not be downgraded."""

    def __init__(self, path: Path, found: int):
        super().__init__(
            f"Настройки NewsFlow новее текущего runtime ({found} > {SETTINGS_SCHEMA_VERSION}) "
            f"и не были изменены: {path}"
        )
        self.path = path
        self.found = found


@contextmanager
def _exclusive_settings_write(path: Path, timeout: float = 12.0):
    """Serialize settings writes across Electron bridge processes.

    NewsFlow starts a short bridge process for UI actions while a long montage
    worker writes visible progress in parallel.  On Windows, two simultaneous
    ``Path.replace`` calls can otherwise produce WinError 5/32.  The lock file
    is tiny, remains outside the JSON data and is released even after an error.
    """
    with _SETTINGS_WRITE_LOCK:
        lock_path = path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # A byte-range lock makes reading an already locked first byte
            # fail on Windows.  Initialise once, then only request the lock.
            with lock_path.open("xb") as initializer:
                initializer.write(b"0")
                initializer.flush()
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
                            raise TimeoutError("Не удалось дождаться сохранения настроек NewsFlow")
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
                        if os.name == "nt":
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass


def app_data_root() -> Path:
    test_root = _test_storage_root()
    if test_root is not None:
        local_appdata = Path(os.environ.get("LOCALAPPDATA", test_root)).expanduser().resolve()
        production_local_appdata = Path(os.environ.get(
            _PRODUCTION_LOCALAPPDATA_ENV, Path.home()
        )).expanduser().resolve()
        production_storage = production_local_appdata / "NewsFlow"
        if (local_appdata == production_local_appdata
                or _is_same_or_descendant(local_appdata / "NewsFlow", production_storage)):
            raise TestStorageIsolationError(
                "Тестовый runtime пытается использовать production LOCALAPPDATA; тест остановлен."
            )
        root = local_appdata / "NewsFlow"
    else:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NewsFlow"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_output_folder() -> Path:
    return storyflow_documents_root() / "Новости"


def storyflow_documents_root() -> Path:
    """Return the shared writable media root for NewsFlow.

    Generated video, downloads and caches can become very large.  Keep them
    off the system disk by default, while retaining a safe fallback for PCs
    without a D: drive.  Individual locations remain editable in Settings.
    """
    test_root = _test_storage_root()
    if test_root is not None:
        root = test_root / "Media"
    else:
        data_drive = Path("D:/")
        root = data_drive / "NewsFlow Studio" if data_drive.exists() else Path.home() / "Documents" / "NewsFlow Studio"
    root.mkdir(parents=True, exist_ok=True)
    return root


NEWS_TOPICS = [
    "Иран — Ормузский пролив",
    "Украина — удар РФ по военным заводам",
    "Россия-Украина — тупик переговоров",
    "Азербайджан-Россия — нормализация отношений",
    "Европа — энергетический кризис",
    "Продовольственный кризис — помидорная война",
    "Россия — удар по складу Wildberries в Волгограде",
    "Трамп-Путин — контакты и угрозы",
    "Трамп-Зеленский — давление и переговоры",
    "Украина — удары по морской инфраструктуре Одессы",
    "Россия — депортации и диаспоры",
    "НАТО — реакция на эскалацию",
    "ЕС-Россия — новые санкции",
    "Иран — кризис на Ормузе (нефть и танкеры)",
    "Израиль-Ливан — удары вопреки перемирию",
    "Армения-Азербайджан — мирный процесс и Карабах",
    "Армения-Россия — охлаждение и разворот Пашиняна",
]



def _storage_path_text(path: Path) -> str:
    """Serialize drive-letter paths with Windows separators on every host."""
    value = str(path)
    return ntpath.normpath(value) if ntpath.splitdrive(value)[0] else value

def migrate_standard_folder(value: str | None, old_leaf: str, new_leaf: str) -> str:
    old_path = Path.home() / "Documents" / "Scriptor" / old_leaf
    old_newsflow_path = Path.home() / "Documents" / "NewsFlow Studio" / new_leaf
    if not value or Path(value) in {old_path, old_newsflow_path}:
        return _storage_path_text(storyflow_documents_root() / new_leaf)
    return migrate_newsflow_storage(value, new_leaf)


def migrate_newsflow_storage(value: str | None, leaf: str) -> str:
    """Move only the old *default* NewsFlow root to D: in settings.

    The function does not move or delete files.  It merely makes future
    downloads and renders use D:, while custom folders chosen by the editor
    remain exactly as they were.
    """
    destination = storyflow_documents_root() / leaf
    if not value:
        return _storage_path_text(destination)
    source = Path(value)
    # Snapshot runs and generic Windows Temp directories are disposable.
    # Keeping either in persisted settings sends later desktop work into a
    # folder that Windows or a cleanup tool can remove without warning.
    temp_roots = [Path(os.environ[key]) for key in ("TEMP", "TMP") if os.environ.get(key)]
    is_temp_path = any(
        source == root or root in source.parents
        for root in temp_roots
        if root.is_absolute()
    )
    if is_temp_path or any(part.casefold().startswith("newsflow-snapshot-") for part in source.parts):
        return _storage_path_text(destination)
    legacy_root = Path.home() / "Documents" / "NewsFlow Studio"
    try:
        relative = source.relative_to(legacy_root)
    except ValueError:
        return str(source)
    return _storage_path_text(storyflow_documents_root() / relative)


def sessions_root() -> Path:
    root = app_data_root() / "ChromeSessions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_media_styles() -> list[dict]:
    styles = [
        ("Кинематографичный", "Киносвет, выразительная композиция, глубина кадра, плёночная цветокоррекция"),
        ("Документальный", "Правдоподобная документальная съёмка, естественный свет, реалистичные детали"),
        ("Историческая реконструкция", "Достоверная эпоха, аутентичная одежда и архитектура, музейная точность"),
        ("Мифологический эпос", "Монументальные боги и герои, мистический свет, древние символы, эпический масштаб"),
        ("Тёмное фэнтези", "Мрачная атмосфера, драматичные тени, древние руины, тревожная палитра"),
        ("Светлое фэнтези", "Волшебное сияние, воздушная атмосфера, насыщенные цвета, сказочная детализация"),
        ("Научная фантастика", "Футуристические технологии, масштабные пространства, холодный свет, реалистичный sci-fi"),
        ("Киберпанк", "Неон, дождь, ночной мегаполис, голограммы, контрастные пурпурно-синие цвета"),
        ("Ретрофутуризм", "Представление прошлого о будущем, аналоговые панели, винтажные формы и цвета"),
        ("Нуар", "Чёрно-белая палитра, жёсткий боковой свет, дым, глубокие тени, детективная атмосфера"),
        ("Хоррор", "Тревожная композиция, приглушённые цвета, неизвестная угроза, реалистичный кинематографичный ужас"),
        ("Мистический", "Туман, тайные знаки, мягкое сверхъестественное свечение, загадочная атмосфера"),
        ("Археологический", "Древние артефакты, раскопки, пыльный солнечный свет, научная достоверность"),
        ("Космический", "Глубокий космос, туманности, планеты, реалистичное освещение и огромный масштаб"),
        ("Природный National Geographic", "Живая природа, телеобъектив, естественный свет, высокая детализация"),
        ("Макросъёмка", "Экстремально крупный план, микродетали, малая глубина резкости, мягкий свет"),
        ("Минимализм", "Один главный объект, чистый фон, много свободного пространства, лаконичная палитра"),
        ("Рекламный премиум", "Студийный свет, безупречные материалы, дорогая композиция, коммерческое качество"),
        ("Редакционная фотография", "Современная журнальная эстетика, выразительная постановка, естественная фактура"),
        ("Живописный реализм", "Реалистичная цифровая живопись, заметные мазки, богатый свет и цвет"),
        ("Масляная живопись", "Классическая масляная техника, фактурные мазки, музейная палитра"),
        ("Акварель", "Прозрачные слои краски, мягкие края, бумажная фактура, воздушные цвета"),
        ("Графический роман", "Выразительный контур, драматичные панели, контрастная авторская раскраска"),
        ("Аниме", "Качественная аниме-иллюстрация, выразительные персонажи, чистые линии, кинематографичный фон"),
        ("3D-анимация", "Стилизованный объёмный мир, мягкие материалы, выразительный свет, анимационная пластика"),
        ("Изометрия", "Изометрическая проекция, аккуратная геометрия, миниатюрная детализация, чистый фон"),
        ("Винтаж 1960-х", "Фотоплёнка 1960-х, зерно, выцветшая палитра, достоверная одежда и реквизит"),
        ("VHS 1990-х", "Аналоговый видеошум, мягкая резкость, цветовые сдвиги, дата на записи"),
        ("Сюрреализм", "Невозможные сочетания объектов, символизм, сновидческое пространство, точные детали"),
        ("Инфографический", "Понятная визуальная иерархия, чистая композиция, наглядные объекты, без текста"),
    ]
    return [{"mode": mode, "name": name, "style": description}
            for mode in ("image", "video") for name, description in styles]


@dataclass
class ChromeSession:
    label: str
    profile_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    active: bool = True
    limit_status: str = "available"
    usage: dict[str, bool] = field(default_factory=lambda: {
        "ideas": True, "scenarios": True, "covers": True, "seo": True,
    })

    @property
    def profile_dir(self) -> Path:
        return sessions_root() / self.profile_id


@dataclass
class FastGenKey:
    label: str
    secret: str
    active: bool = True


@dataclass
class OpenAIKey:
    label: str
    secret: str
    active: bool = True


@dataclass
class SecretVoicerKey:
    label: str
    secret: str
    active: bool = True
    streams: int = 1
    balance: str = "—"
    balance_status: str = "not_checked"


@dataclass
class LumeanKey:
    """A local, DPAPI-protected Lumean credential and its safe UI metadata."""
    label: str
    secret: str
    active: bool = True
    streams: int = 1
    balance: str = "—"
    balance_status: str = "not_checked"


@dataclass
class VoiceGenKey:
    label: str
    secret: str
    active: bool = True
    streams: int = 1
    balance: str = "—"
    balance_status: str = "not_checked"


@dataclass
class WProjectKey:
    """DPAPI-protected W-Voice credential with safe capacity metadata."""
    label: str
    secret: str
    active: bool = True
    streams: int = 1
    balance: str = "—"
    balance_status: str = "not_checked"


@dataclass
class Settings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    chrome_sessions: list[ChromeSession] = field(default_factory=list)
    # Operator notes are stored separately from encrypted secrets, so a key
    # can be recognised without ever exposing it in the UI or in logs.
    api_key_notes: dict[str, str] = field(default_factory=dict)
    output_folder: str = field(default_factory=lambda: str(default_output_folder()))
    idea_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Идеи"))
    footage_folders: list[str] = field(default_factory=list)
    footage_download_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Футажи из интернета"))
    cutter_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Нарезки"))
    cutter_sources: list[str] = field(default_factory=list)
    mixer_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Вариации футажей"))
    montage_project_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Проекты монтажа"))
    montage_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Готовые ролики"))
    montage_aspect_ratio: str = "16:9"
    # New profiles prefer the explicit GPU timeline route when bundled FFmpeg
    # exposes NVENC.  The established FFmpeg proxy route remains a deliberate
    # manual fallback; Remotion remains an explicit composition choice.
    montage_renderer: str = field(default_factory=default_montage_renderer)
    montage_renderer_explicit: bool = False
    montage_remotion_frame_concurrency: int = 2
    # FCPXML is a lightweight editable copy of the same montage plan, not an
    # additional MP4 render. Automatic Resolve import remains opt-in.
    montage_export_davinci_xml: bool = True
    montage_davinci_auto_import: bool = False
    # The composition is still editable as a .newsflow/.remotion.json plan;
    # these fields only control how Remotion presents scene boundaries.
    montage_transition_style: str = "crossfade"
    montage_transition_frames: int = 7
    montage_auto_web: bool = True
    montage_auto_youtube: bool = False
    # Short external-only news cuts may deliberately skip the local library.
    montage_external_only: bool = False
    # The narration gives the planner the best semantic context. It can be
    # switched off for fast title+MP3 assembly when a text file is unavailable.
    montage_use_script_text: bool = True
    # Screen-text classification is persisted inside the footage index. The
    # legacy setting name is retained, but readable text in any language plus
    # full-screen title/interstitial cards are excluded from Montage.
    montage_exclude_english_text: bool = True
    # Optional text agent turns narration into concrete visual scene queries.
    # It falls back to the local deterministic planner without consuming API
    # tokens when disabled or when the API is unavailable.
    montage_scene_planner: str = "local"
    montage_match_threshold: float = 0.22
    # Fast visual loop: only the first N percent of a narration receives
    # unique footage matching. The selected sources are then rotated at every
    # following speech beat; this preserves timing while avoiding a full
    # expensive library search for a long voiceover.
    montage_fast_reuse_enabled: bool = False
    montage_unique_footage_percent: int = 100
    # Optional one-based scenario ranges.  When the list is empty the fast
    # mode applies to every selected topic; once ranges exist it applies only
    # to those rows, each with its own unique-footage percentage.
    montage_fast_reuse_ranges: list[dict] = field(default_factory=list)
    montage_intro_enabled: bool = False
    montage_intro_folder: str = ""
    montage_intro_duration: float = 6.0
    montage_overlay_enabled: bool = False
    montage_overlay_folder: str = ""
    # The video queue is persistent: a restart never loses a prepared plan or
    # a completed MP4.  These limits are intentionally separate because
    # semantic planning, network download/cutting and FFmpeg rendering stress
    # completely different parts of the computer.
    montage_planning_workers: int = 4
    montage_download_workers: int = 2
    montage_render_workers: int = 2
    montage_queue_paused: bool = False
    montage_task_statuses: dict[str, dict] = field(default_factory=dict)
    # Keep recent selections between runs. A re-render first tries unused
    # footage so the same topic does not turn into the same visual loop.
    montage_recent_clip_paths: list[str] = field(default_factory=list)
    # Publication is a separate persistent final-production queue.  The
    # records are plain metadata only; OAuth refresh tokens are stored by the
    # publisher in DPAPI-protected local token files, never in these lists.
    youtube_publication_jobs: list[dict] = field(default_factory=list)
    youtube_publication_presets: list[dict] = field(default_factory=list)
    youtube_publication_activity: list[dict] = field(default_factory=list)
    # Publication V2 keeps its stable production-item registry and immutable
    # upload intent separate from legacy queue rows.  These fields never hold
    # OAuth credentials.
    youtube_publication_items: dict[str, dict] = field(default_factory=dict)
    youtube_publication_snapshots: dict[str, dict] = field(default_factory=dict)
    youtube_publication_executions: dict[str, dict] = field(default_factory=dict)
    youtube_publication_receipts: dict[str, dict] = field(default_factory=dict)
    youtube_publication_migration_version: int = 0
    youtube_channel_publication_rules: dict[str, dict] = field(default_factory=dict)
    youtube_publication_v2_rule_presets: list[dict] = field(default_factory=list)
    youtube_publication_plan_versions: list[dict] = field(default_factory=list)
    youtube_publication_assignments: dict[str, dict] = field(default_factory=dict)
    youtube_publication_queue_paused: bool = False
    # The allocation constructor is intentionally distinct from the time-grid
    # presets: it keeps channel quotas, duration ranges and manual locks.
    youtube_publication_allocation_profiles: list[dict] = field(default_factory=list)
    youtube_publication_allocation_presets: list[dict] = field(default_factory=list)
    youtube_publication_allocation_updated_at: str = ""
    # Per-channel Studio automation policies and idempotent task state.  They
    # deliberately contain no browser cookies or OAuth secrets: each channel
    # continues to use its own persistent Chrome profile and protected token.
    youtube_engagement_policies: list[dict] = field(default_factory=list)
    youtube_engagement_tasks: list[dict] = field(default_factory=list)
    # Operator-controlled. There is intentionally no product-side upper cap:
    # the scheduler uses the value as the upload worker count and records API
    # throttling/errors instead of silently reducing it.
    youtube_publication_upload_concurrency: int = 2
    # Compact local series used by the Analytics charts. OAuth tokens are not
    # stored here; each point records only measured data and its source time.
    youtube_analytics_metric_points: list[dict] = field(default_factory=list)
    # Normalized per-video rows returned by YouTube Analytics. They contain
    # no OAuth credentials and let the desktop join a published videoId back
    # to its NewsFlow scenario, SEO package and cover.
    youtube_analytics_video_metrics: list[dict] = field(default_factory=list)
    youtube_analytics_updated_at: str = ""
    analytics_channels: list[dict] = field(default_factory=list)
    # Public, channel-scoped research queues and summaries. OAuth credentials
    # remain exclusively in the protected mapping below.
    channel_research: dict[str, dict] = field(default_factory=dict)
    google_oauth_client_file: str = ""
    # Public HTTPS endpoint of the Cloudflare OAuth handoff. OAuth secrets and
    # refresh tokens are deliberately never stored in this field.
    youtube_oauth_service_url: str = ""
    # Maps a local channel profile ID to a serialized Google credential. The
    # whole mapping is DPAPI-protected when settings are written.
    youtube_oauth_tokens: dict[str, str] = field(default_factory=dict)
    # OAuth handoff capabilities are short-lived credentials too. Persist them
    # with DPAPI so a callback can be collected after the desktop restarts.
    youtube_oauth_pending_handoffs: dict[str, dict] = field(default_factory=dict)
    # A separate project key is used only for public YouTube Data API search
    # and video statistics. It is DPAPI-protected on the local Windows account.
    youtube_api_key: str = ""
    youtube_api_enabled: bool = True
    # Obsidian stays local: the path is a normal Markdown vault, while the MCP
    # endpoint is optional and only used after the user enables a local server.
    obsidian_vault_path: str = ""
    obsidian_mcp_url: str = ""
    obsidian_mcp_token: str = ""
    obsidian_sync_enabled: bool = False
    voicer_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Озвучки"))
    secret_voicer_keys: list[SecretVoicerKey] = field(default_factory=list)
    lumean_api_keys: list[LumeanKey] = field(default_factory=list)
    voicegen_api_keys: list[VoiceGenKey] = field(default_factory=list)
    wproject_api_keys: list[WProjectKey] = field(default_factory=list)
    # The catalogue is a non-secret convenience cache. It is refreshed only
    # by an explicit operator action, never during an audio render.
    lumean_voice_cache: list[dict] = field(default_factory=list)
    lumean_model_cache: list[str] = field(default_factory=list)
    voicegen_voice_cache: list[dict] = field(default_factory=list)
    voicegen_preset_cache: list[dict] = field(default_factory=list)
    voicegen_engine_cache: list[str] = field(default_factory=list)
    voicegen_profile_cache: dict = field(default_factory=dict)
    wproject_voice_cache: list[dict] = field(default_factory=list)
    wproject_profile_cache: dict = field(default_factory=dict)
    wproject_usage_cache: dict = field(default_factory=dict)
    # The browser provider uses its own Chrome profile.  It never copies cookies,
    # passwords or Telegram credentials from the user's regular Chrome profile.
    voice_browser_profile_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    voice_provider: str = "chrome"
    voice_api_fallback: bool = True
    # The persistent Secret Voicer tab is normally the source of truth for
    # the selected voice; a user can choose it directly in authenticated Chrome.
    voice_use_chrome_selected_voice: bool = True
    # This flag is stored separately so the Electron pause button can stop the
    # next queued voice task without losing the already running browser task.
    voice_queue_paused: bool = False
    # Stable range orchestration is independent from a provider.  The legacy
    # voice provider field remains the default for profiles created by older
    # project versions, while every new TTS job stores its resolved profile.
    voice_default_profile_id: str = ""
    voice_ranges: list[dict] = field(default_factory=list)
    # Named, local presets let the operator switch a complete allocation of
    # voices and scenario ranges without re-entering every number.
    voice_range_presets: list[dict] = field(default_factory=list)
    voice_key_failover: bool = True
    voice_queue_concurrency: int = 20
    # Frozen batch order and per-item job snapshots survive a UI sort, restart
    # or a later edit to the current range editor.
    voice_tts_batches: list[dict] = field(default_factory=list)
    voice_active_tts_batch_id: str = ""
    voice_tts_jobs: dict[str, dict] = field(default_factory=dict)
    voice_scenario_outputs: dict[str, str] = field(default_factory=dict)
    # Saved after every synthesis step so a separate UI process can show live
    # progress and recover a queue after a restart.
    voice_task_statuses: dict[str, dict] = field(default_factory=dict)
    # Last folder-import audit. It contains only paths and matching outcomes,
    # never audio bytes or credentials, so the UI can survive a reload.
    voice_import_summary: dict = field(default_factory=dict)
    pipeline_target_count: int = 300
    pipeline_montage_outputs: list[str] = field(default_factory=list)
    video_result_packages: dict[str, str] = field(default_factory=dict)
    # Batch Results is a separate operator hand-off. It never changes the
    # Publication per-video package registry above.
    results_output_folder: str = ""
    results_last_export_folder: str = ""
    voice_profiles: list[dict] = field(default_factory=lambda: [{
        "name": "Новости", "voice_id": "", "stability": 0.30, "style": 0.50,
    }])
    template: str = (
        "Напиши точный новостной сценарий на тему «{title}». "
        "Отделяй подтверждённые факты от оценок и не выдумывай детали. "
        "Верни только готовый текст для диктора без заголовков, Markdown, списков и пояснений."
    )
    # Global Python-owned script-length contract. Per-range settings override it.
    scenario_target_chars: int = 0
    scenario_allowed_min: int = 0
    scenario_allowed_max: int = 0
    # Direct browser-authenticated ChatGPT topic scenario route.  This is
    # intentionally separate from the current Planner/Writer template and
    # carries no provider credentials.
    browser_topic_scenarios: dict = field(default_factory=dict)
    idea_topics: list[str] = field(default_factory=lambda: list(NEWS_TOPICS))
    # Agent proposals are deliberately separate from the user's permanent
    # direction library. They become favourites only after explicit approval.
    idea_suggested_topics: list[str] = field(default_factory=list)
    # Public channels used only as editorial references for title patterns.
    # They are intentionally separate from analytics channels and credentials.
    idea_reference_channels: list[dict] = field(default_factory=list)
    idea_reference_analysis: list[dict] = field(default_factory=list)
    idea_reference_rules: str = (
        "Создавай энергичные, конкретные новостные заголовки без копирования исходника. "
        "Не выдумывай факты, цитаты, потери, преступления или обвинения; не используй оскорбления, "
        "унижение стран, народов и политиков. Сильный заголовок строится на проверяемом событии, "
        "конфликте интересов, последствии или вопросе, а не на травле."
    )
    idea_plan: list[dict] = field(default_factory=list)
    # Last research batch is preserved separately from the global topic grid so
    # the editor can approve YouTube suggestions before deriving vectors.
    youtube_suggested_topics: list[str] = field(default_factory=list)
    idea_results: list[str] = field(default_factory=list)
    # Maps every generated title back to its source direction.  It lets the
    # result screen regenerate a rejected item without touching other vectors.
    idea_result_sources: dict[str, str] = field(default_factory=dict)
    # Publication-safe title provenance.  The persistent memory prevents the
    # next batch from recycling the same opening or semantic construction.
    idea_title_metadata: dict[str, dict] = field(default_factory=dict)
    idea_title_memory: list[dict] = field(default_factory=list)
    # Structured Ideas Engine records. Legacy title arrays remain above for
    # compatibility with projects created before production items existed.
    idea_raw_signals: list[dict] = field(default_factory=list)
    idea_events: list[dict] = field(default_factory=list)
    idea_directions: list[dict] = field(default_factory=list)
    idea_production_items: list[dict] = field(default_factory=list)
    idea_deleted_production_ids: list[str] = field(default_factory=list)
    # Script deletions use the source ProductionItem identity.  The legacy
    # title tombstone below remains only for scripts that predate that ID.
    deleted_scenario_production_ids: list[str] = field(default_factory=list)
    # Monotonic durable authority for a confirmed full-production reset.  A
    # worker can keep an older Settings object for minutes, so its later save
    # must never revive a release that a newer reset removed.
    production_reset_generation: int = 0
    idea_rejected_items: list[dict] = field(default_factory=list)
    idea_portfolio_summary: dict = field(default_factory=dict)
    idea_scenario_context: dict[str, dict] = field(default_factory=dict)
    # The release plan normally follows the shared production target.  It can
    # be detached when a smaller idea batch is intentionally needed.
    idea_target_count: int = 300
    idea_target_follows_pipeline: bool = True
    idea_route_presets: list[dict] = field(default_factory=list)
    cover_route_presets: list[dict] = field(default_factory=list)
    idea_include_custom: bool = False
    idea_custom_text: str = ""
    auto_montage_enabled: bool = False
    # The Electron control centre stores the enabled automatic stages here.
    # Ideas deliberately stay outside this list: they are always approved by
    # the user before the rest of the production chain can begin.
    auto_pipeline_stages: dict[str, bool] = field(default_factory=lambda: {
        "scenarios": True,
        "covers": True,
        "seo": True,
        "voice": True,
        "montage": True,
        "package": True,
    })
    idea_prompts: list[dict] = field(default_factory=lambda: [
        {"name": "Новостные углы", "topic": NEWS_TOPICS[0],
         "prompt": (
             "Предложи разные актуальные углы подачи новости. Не выдумывай события, даты, цитаты и цифры; "
             "формулировки должны быть конкретными, нейтральными и пригодными для последующей проверки фактов."
         )},
    ])
    idea_chat_bindings: list[dict] = field(default_factory=list)
    seo_chat_bindings: list[dict] = field(default_factory=list)
    cover_chat_bindings: list[dict] = field(default_factory=list)
    media_chat_bindings: list[dict] = field(default_factory=list)
    media_styles: list[dict] = field(default_factory=default_media_styles)
    scenario_templates: list[dict] = field(default_factory=list)
    range_templates: list[dict] = field(default_factory=list)
    cover_api_keys: list[FastGenKey] = field(default_factory=list)
    openai_api_keys: list[OpenAIKey] = field(default_factory=list)
    # One shared model is used by every active API key and every text stage:
    # ideas, scripts, cover phrases/prompts, SEO and tags.  Mini keeps batch
    # news production affordable while retaining structured JSON reliability.
    openai_model: str = "gpt-5.4-mini"
    cover_operation: str = "flower_image_generate"
    cover_aspect_ratio: str = "16:9"
    cover_variant_count: int = 1
    # The text executor is deliberately separate from FastGen.  It creates a
    # visual brief; FastGen only renders the approved/generated prompt.
    cover_prompt_provider: str = "agent"
    # The visual brief is optional.  When it is disabled, the cover agent uses
    # only the topic, selected text and the built-in news-thumbnail rules.
    cover_use_custom_prompt: bool = False
    cover_use_script_context: bool = True
    cover_prompt_variant_count: int = 2
    cover_headline_provider: str = "agent"
    cover_text_mode: str = "overlay"
    # Both supported routes are fully rendered by FastGen.  The second route
    # may send one selected portrait as a remote reference; it never composites
    # a local face onto the returned image.
    cover_build_mode: str = "fastgen-full"
    # One-based inclusive scenario ranges may override the default route.
    # Ranges are validated as non-overlapping before persistence so a batch
    # can never silently pick an arbitrary mode for the same topic.
    cover_build_mode_ranges: list[dict] = field(default_factory=list)
    # The red outer frame is invariant. This flag controls only whether
    # FastGen may vary the contrasting headline/panel colour pair.
    cover_allow_varied_text_palette: bool = False
    cover_headline_template: str = (
        "Придумай короткую фразу для текста на YouTube-обложке по теме «{title}». "
        "1–5 слов, конкретно, интригующе, без ложных фактов и без повторения полного заголовка."
    )
    cover_subheadline_template: str = (
        "Придумай короткий подзаголовок для YouTube-обложки по теме «{title}». "
        "3–7 слов: уточни главный смысл, не повторяй основной заголовок, без ложных фактов, капса и знаков-восклицаний."
    )
    # Separate from visual-cover presets: these are only the two text prompts
    # used to create the main headline and the supporting line.
    cover_headline_presets: list[dict] = field(default_factory=list)
    # When disabled, headline/subheadline generation follows only the user's
    # prompt plus topic safeguards — exactly as it worked before structures.
    cover_text_use_structure: bool = True
    cover_text_avoid_repeats: bool = True
    cover_headlines_paused: bool = False
    cover_subheadlines_paused: bool = False
    cover_prompt_ranges: list[dict] = field(default_factory=list)
    cover_prompt_presets: list[dict] = field(default_factory=list)
    # References can define one channel-wide visual language, be assigned to
    # arbitrary scenario ranges, or be deliberately disabled.  Keep this
    # separate from prompt ranges: one is visual input, the other is text.
    cover_reference_mode: str = "all"
    cover_reference_paths: list[str] = field(default_factory=list)
    cover_reference_ranges: list[dict] = field(default_factory=list)
    # Prompt-writing references are kept separately from FastGen render
    # references so a channel can teach the AI one visual language while the
    # image provider receives a different, explicitly selected pack.
    cover_ai_reference_mode: str = "off"
    cover_ai_reference_paths: list[str] = field(default_factory=list)
    cover_ai_reference_ranges: list[dict] = field(default_factory=list)
    # The prompt agent can study a reference without automatically sending it
    # to FastGen. This explicit switch makes the extra API input a user choice.
    cover_ai_reference_to_fastgen: bool = False
    # Explicit visual guidance for final FastGen renders.  This is distinct
    # from the older channel/agent reference packs: it is off by default and
    # never changes the current ProductionItem's factual scene.
    cover_fastgen_use_references: bool = False
    cover_fastgen_reference_paths: list[str] = field(default_factory=list)
    cover_fastgen_reference_mode_style: bool = False
    cover_fastgen_reference_mode_composition: bool = False
    cover_fastgen_reference_mode_mood_lighting: bool = False
    cover_fastgen_reference_mode_auto: bool = False
    # Opt-in scene treatment for newly generated visual briefs. It never
    # mutates an approved prompt or starts FastGen rendering.
    cover_scene_intensity_mode: bool = False
    cover_tabloid_mode: bool = False
    # A local portrait library is separate from generic visual references.  Its
    # folder/file names are matched against the topic before a person is ever
    # sent to FastGen, preventing a random face from leaking into a cover.
    cover_face_library_folder: str = ""
    # Prepared transparent copies are kept outside the source-photo library by
    # default.  The user may choose any separate destination folder.
    cover_face_prepared_folder: str = ""
    cover_face_library_enabled: bool = False
    cover_face_remove_background: bool = False
    cover_face_layout_memory: dict[str, dict] = field(default_factory=dict)
    # Overlay is deterministic and keeps Cyrillic cover words readable.  It is
    # deliberately separate from FastGen's optional text rendering.
    cover_auto_overlay_text: bool = True
    cover_auto_text_color: bool = True
    cover_generation_paused: bool = False
    # Optional local guard for a provider plan such as 100 generated images
    # per rolling hour. Zero means rely exclusively on FastGen's live API.
    cover_rate_limit_per_hour: int = 0
    cover_rate_auto_resume: bool = False
    cover_rate_usage_events: list[dict] = field(default_factory=list)
    # Empty means every active key; otherwise only these visible key labels
    # may be used for the current cover queue.
    cover_selected_key_labels: list[str] = field(default_factory=list)
    cover_seed: str = ""
    cover_upscale: bool = False
    cover_quality: str = ""
    cover_resolution: str = ""
    fastgen_capabilities_cache: dict[str, list[dict]] = field(default_factory=lambda: {"image": [], "video": []})
    fastgen_usage_cache: dict = field(default_factory=dict)
    cover_queue: list[dict] = field(default_factory=list)
    # Explicitly removed rows must win over stale detached workers that still
    # carry an older full queue snapshot in memory.
    cover_queue_tombstones: list[str] = field(default_factory=list)
    # Session v1 stores only title/index pairs. Keep deleted script identities
    # separately so an older session.backup.json cannot revive them.
    deleted_scenario_titles: list[str] = field(default_factory=list)
    cover_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Обложки"))
    cover_prompt_template: str = (
        "Visual-only 16:9 YouTube news thumbnail for «{title}». Build one instantly readable scene: "
        "a dominant, topic-relevant person or object in the foreground; one concrete visual evidence or symbol; "
        "and a cinematic panoramic background that clearly explains where and what is happening. "
        "Use plausible documentary details and real human activity when the event calls for it: people and emergency responders "
        "at a safe distance for explosions or disasters; soldiers, equipment, logistics or a command setting for military news; "
        "a crowd, speakers, journalists or a negotiation room for protests, meetings and statements; ports, tankers, terminals, "
        "factories or market screens for energy and economic news. Never invent a specific strike, casualty, leader, flag or event "
        "that is not supported by the title or context. Use strong foreground/background separation, dramatic but realistic light, "
        "red/orange danger accents against deep blue/black, and clean negative space on one side for external typography. "
        "No words, letters, logos, watermarks, collages, unrelated politicians, or invented events. "
        "Context: {excerpt}"
    )
    media_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "Медиа"))
    seo_output_folder: str = field(default_factory=lambda: str(storyflow_documents_root() / "SEO"))
    # Unlike the original Tkinter screen, the desktop shell must be able to
    # restore the manual hand-off queue after a restart.
    seo_queue: list[dict] = field(default_factory=list)
    seo_prompt_template: str = (
        "Для темы «{title}» создай привлекательный SEO-заголовок, SEO-описание с естественным призывом посмотреть "
        "ролик и 3–5 хештегов. Контекст: {excerpt}. Верни только JSON: "
        "{\"title\": \"...\", \"description\": \"один готовый текст без заголовков и подписей\", "
        "\"hashtags\": [\"#...\"]}. Не пиши внутри description слова «SEO-описание», "
        "«Хештеги», «Призыв», «Теги» и не используй Markdown-блоки."
    )
    tags_prompt_template: str = (
        "Для темы «{title}» подготовь 15 релевантных YouTube-тегов. Контекст сценария: {excerpt}. "
        "Верни только JSON: {\"tags\": [\"...\"]}. Не добавляй пояснения, заголовки или Markdown."
    )
    seo_provider: str = "agent"
    tags_provider: str = "agent"
    hashtag_batch_size: int = 5
    tag_char_limit: int = 500
    seo_use_script_context: bool = False
    seo_call_to_action: str = ""
    # A permanent contact/branding block placed before every generated SEO text.
    seo_description_prefix: str = ""
    # Reusable opening text for generated descriptions. The first enabled
    # one-based range wins, so an operator can deliberately layer presets.
    seo_description_prefix_ranges: list[dict] = field(default_factory=list)
    seo_description_prefix_presets: list[dict] = field(default_factory=list)
    prompt_ranges: list[dict] = field(default_factory=lambda: [
        {"start": 1, "end": 5, "prompt": ""},
        {"start": 6, "end": 10, "prompt": ""},
    ])
    scenario_provider: str = "agent"

    @property
    def active_sessions(self) -> list[ChromeSession]:
        return [item for item in self.chrome_sessions if item.active]


def config_path() -> Path:
    return app_data_root() / "settings.json"


def seal_current_runtime_storage() -> bool:
    """Advance only the runtime schema fence, never rewrite user state.

    A previous bridge can understand the same JSON shape while still selecting
    obsolete cover rows.  The schema fence makes that executable stop before
    any write.  This explicit operation deliberately works on raw JSON rather
    than ``Settings`` so it preserves unknown fields, encrypted values and
    every user record byte-for-byte in meaning; only ``schema_version`` moves
    forward.
    """
    path = config_path()
    if not path.is_file():
        raise FileNotFoundError(f"Нет canonical settings для runtime seal: {path}")
    with _exclusive_settings_write(path):
        try:
            raw = _read_settings_text(path)
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError) as error:
            raise SettingsFileCorruptError(path) from error
        if not isinstance(data, dict):
            raise SettingsFileCorruptError(path)
        try:
            stored_version = max(0, int(data.get("schema_version", 0) or 0))
        except (TypeError, ValueError) as error:
            raise SettingsFileCorruptError(path) from error
        if stored_version > SETTINGS_SCHEMA_VERSION:
            raise SettingsSchemaVersionError(path, stored_version)
        if stored_version == SETTINGS_SCHEMA_VERSION:
            return False
        data["schema_version"] = SETTINGS_SCHEMA_VERSION
        _archive_pre_write_settings(path, raw)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, path)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
    return True


def _apply_idea_production_tombstones(settings: Settings) -> None:
    """Project an interrupted delete consistently without writing during load.

    A Topic delete is recorded by durable production-item ID.  A stale worker
    can still leave the old item in settings.json beside that tombstone.  Hide
    it, and the legacy title projections that could recreate it, as soon as
    settings are loaded; a later explicit save then compacts the persisted
    state.  This keeps a read-only status snapshot from reviving deleted work.
    """
    deleted_ids = {str(value).strip() for value in settings.idea_deleted_production_ids if str(value).strip()}
    if not deleted_ids:
        return
    deleted_titles = {
        str(item.get("title", "")).strip()
        for item in settings.idea_production_items
        if isinstance(item, dict) and str(item.get("id", "")).strip() in deleted_ids
        and str(item.get("title", "")).strip()
    }
    settings.idea_production_items = [
        item for item in settings.idea_production_items
        if not isinstance(item, dict) or str(item.get("id", "")).strip() not in deleted_ids
    ]
    if not deleted_titles:
        return
    settings.idea_results = [title for title in settings.idea_results if str(title).strip() not in deleted_titles]
    settings.idea_result_sources = {
        title: source for title, source in settings.idea_result_sources.items()
        if str(title).strip() not in deleted_titles
    }
    settings.idea_title_metadata = {
        title: metadata for title, metadata in settings.idea_title_metadata.items()
        if str(title).strip() not in deleted_titles
    }
    settings.idea_scenario_context = {
        title: context for title, context in settings.idea_scenario_context.items()
        if str(title).strip() not in deleted_titles
    }


def _protected_json_dict(data: dict, key: str) -> dict[str, str]:
    """Read a DPAPI-protected JSON mapping without making settings fail-open."""

    try:
        decoded = json.loads(unprotect(str(data.get(key, ""))) or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {str(item_key): str(item_value) for item_key, item_value in decoded.items()
            if str(item_key).strip() and str(item_value).strip()}


def _protected_json_object_dict(data: dict, key: str) -> dict[str, dict]:
    try:
        decoded = json.loads(unprotect(str(data.get(key, ""))) or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {str(item_key): dict(item_value) for item_key, item_value in decoded.items()
            if str(item_key).strip() and isinstance(item_value, dict)}


_AUTH_LIBRARY_FIELDS = (
    "analytics_channels",
    "chrome_sessions",
    "youtube_oauth_tokens_protected",
    "youtube_oauth_pending_handoffs_protected",
    "youtube_api_key_protected",
    "google_oauth_client_file",
    "youtube_oauth_service_url",
    "youtube_channel_publication_rules",
)


def _auth_library_value_present(data: dict, field_name: str) -> bool:
    """Return whether a protected auth field contains usable state.

    An encrypted representation of ``{}`` is deliberately treated as empty.
    Several old desktop versions wrote exactly that placeholder and otherwise
    made a newer shared NewsFlow library look as though it were authenticated.
    """
    value = data.get(field_name)
    if field_name == "youtube_oauth_tokens_protected":
        return bool(_protected_json_dict(data, field_name))
    if field_name == "youtube_oauth_pending_handoffs_protected":
        return bool(_protected_json_object_dict(data, field_name))
    if field_name == "youtube_api_key_protected":
        return bool(unprotect(str(value or "")).strip())
    if field_name in {"analytics_channels", "chrome_sessions"}:
        return isinstance(value, list) and bool(value)
    if field_name == "youtube_channel_publication_rules":
        return isinstance(value, dict) and bool(value)
    return bool(str(value or "").strip())


def recover_missing_auth_and_channels(data: dict, candidates: list[dict]) -> tuple[dict, bool]:
    """Fill only absent auth/channel state from the most complete library copy.

    This is intentionally a one-way, non-destructive migration: current
    populated state always wins, while ideas, scripts, SEO, cover jobs and
    montage data are outside this helper's write set.
    """
    recovered = dict(data) if isinstance(data, dict) else {}
    valid_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    if not valid_candidates:
        return recovered, False

    def completeness(candidate: dict) -> tuple[int, int, int, int]:
        return (
            len(_protected_json_dict(candidate, "youtube_oauth_tokens_protected")),
            len(candidate.get("analytics_channels", [])) if isinstance(candidate.get("analytics_channels"), list) else 0,
            len(_protected_json_object_dict(candidate, "youtube_oauth_pending_handoffs_protected")),
            sum(1 for field_name in _AUTH_LIBRARY_FIELDS if _auth_library_value_present(candidate, field_name)),
        )

    source = max(valid_candidates, key=completeness)
    changed = False
    for field_name in _AUTH_LIBRARY_FIELDS:
        if (not _auth_library_value_present(recovered, field_name)
                and _auth_library_value_present(source, field_name)):
            recovered[field_name] = source[field_name]
            changed = True
    return recovered, changed


def _newsflow_auth_library_candidates() -> list[dict]:
    """Read only NewsFlow's own small backup snapshots, never media folders."""
    backup_root = storyflow_documents_root() / "Backups"
    if not backup_root.is_dir():
        return []
    candidates: list[dict] = []
    try:
        paths = sorted(backup_root.glob("*/settings.json"), key=lambda item: item.stat().st_mtime,
                       reverse=True)
    except OSError:
        return []
    for candidate_path in paths:
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(candidate, dict):
            candidates.append(candidate)
    return candidates


def load_settings() -> Settings:
    path = config_path()
    try:
        if not path.exists():
            with _exclusive_settings_write(path):
                data = json.loads(_read_settings_text(path, missing_under_lock=True))
        else:
            data = json.loads(_read_settings_text(path))
    except (ValueError, json.JSONDecodeError) as error:
        raise SettingsFileCorruptError(path) from error
    if not isinstance(data, dict):
        raise SettingsFileCorruptError(path)
    try:
        try:
            stored_schema_version = max(0, int(data.get("schema_version", 0) or 0))
        except (TypeError, ValueError) as error:
            raise SettingsFileCorruptError(path) from error
        if stored_schema_version > SETTINGS_SCHEMA_VERSION:
            raise SettingsSchemaVersionError(path, stored_schema_version)
        # The active runtime reads only its canonical NewsFlow settings file.
        # Legacy Scriptor state and backup snapshots are recovery inputs, not
        # runtime fallbacks: loading them here let an old profile silently
        # change a newer build.  An operator migration must be explicit.
        cover_keys = [FastGenKey(item.get("label", "FastGen ключ"),
                                 unprotect(item.get("secret_protected", "")),
                                 bool(item.get("active", True)))
                      for item in data.get("cover_api_keys", [])]
        legacy_cover_secret = unprotect(data.get("cover_api_key_protected", ""))
        if legacy_cover_secret and not cover_keys:
            cover_keys.append(FastGenKey("Основной ключ", legacy_cover_secret, True))
        openai_keys = [OpenAIKey(item.get("label", "OpenAI ключ"),
                                 unprotect(item.get("secret_protected", "")),
                                 bool(item.get("active", True)))
                      for item in data.get("openai_api_keys", [])]
        voicer_keys = [SecretVoicerKey(item.get("label", "Secret Voicer ключ"),
                                       unprotect(item.get("secret_protected", "")),
                                       bool(item.get("active", True)),
                                       max(1, min(20, int(item.get("streams", 1)))),
                                       str(item.get("balance", "—")),
                                       str(item.get("balance_status", "not_checked")))
                       for item in data.get("secret_voicer_keys", [])]
        lumean_keys = [LumeanKey(item.get("label", "Lumean ключ"),
                                 unprotect(item.get("secret_protected", "")),
                                 bool(item.get("active", True)),
                                 max(1, min(100, int(item.get("streams", 1)))),
                                 str(item.get("balance", "—")),
                                 str(item.get("balance_status", "not_checked")))
                       for item in data.get("lumean_api_keys", [])]
        voicegen_keys = [VoiceGenKey(item.get("label", "VoiceGen ключ"),
                                     unprotect(item.get("secret_protected", "")),
                                     bool(item.get("active", True)),
                                     max(1, min(100, int(item.get("streams", 1)))),
                                     str(item.get("balance", "—")),
                                     str(item.get("balance_status", "not_checked")))
                         for item in data.get("voicegen_api_keys", [])]
        wproject_keys = [WProjectKey(item.get("label", "WProject ключ"),
                                     unprotect(item.get("secret_protected", "")),
                                     bool(item.get("active", True)),
                                     max(1, min(100, int(item.get("streams", 1)))),
                                     str(item.get("balance", "—")),
                                     str(item.get("balance_status", "not_checked")))
                         for item in data.get("wproject_api_keys", [])]
        sessions = [ChromeSession(
            label=item.get("label", "Chrome-сессия"),
            profile_id=item.get("profile_id") or uuid.uuid4().hex,
            active=bool(item.get("active", True)),
            limit_status=item.get("limit_status", "available"),
            usage=item.get("usage") or {"ideas": True, "scenarios": True, "covers": True, "seo": True},
        ) for item in data.get("chrome_sessions", [])]
        pipeline_target = max(1, int(data.get("pipeline_target_count", 300)))
        # Settings created before the linking switch had two unrelated defaults
        # (300 and 100).  On first update, make the release plan follow the
        # production target so that the dashboard is internally consistent.
        follows_pipeline = bool(data.get("idea_target_follows_pipeline", True))
        idea_target = (pipeline_target if follows_pipeline
                       else max(1, int(data.get("idea_target_count", 100))))
        saved_renderer_value = data.get("montage_renderer")
        saved_montage_renderer = (
            default_montage_renderer()
            if saved_renderer_value is None
            else str(saved_renderer_value).casefold()
        )
        montage_renderer_explicit = bool(data.get("montage_renderer_explicit", False))
        # Earlier builds wrote ``remotion`` merely because it was the default.
        # The absence of the explicit marker means this was never an operator
        # choice, so route it to the current FAST NEWS default. A deliberate
        # Remotion selection is preserved exactly.
        if saved_montage_renderer not in {"remotion", "ffmpeg", "gpu-timeline"}:
            saved_montage_renderer = default_montage_renderer()
        if saved_montage_renderer == "remotion" and "montage_renderer_explicit" not in data:
            saved_montage_renderer = "ffmpeg"
        settings = Settings(
            schema_version=SETTINGS_SCHEMA_VERSION,
            chrome_sessions=sessions,
            api_key_notes=data.get("api_key_notes", {}),
            output_folder=migrate_standard_folder(data.get("output_folder"), "Исходники", "Сценарии"),
            idea_output_folder=migrate_standard_folder(data.get("idea_output_folder"), "Идеи", "Идеи"),
            footage_folders=data.get("footage_folders", []),
            footage_download_folder=migrate_newsflow_storage(data.get("footage_download_folder"), "Футажи из интернета"),
            cutter_output_folder=migrate_standard_folder(data.get("cutter_output_folder"), "Нарезки", "Нарезки"),
            cutter_sources=data.get("cutter_sources", []),
            mixer_output_folder=migrate_standard_folder(data.get("mixer_output_folder"), "Вариации футажей", "Вариации футажей"),
            montage_project_folder=migrate_newsflow_storage(data.get("montage_project_folder"), "Проекты монтажа"),
            montage_output_folder=migrate_newsflow_storage(data.get("montage_output_folder"), "Готовые ролики"),
            montage_aspect_ratio=data.get("montage_aspect_ratio", "16:9"),
            montage_renderer=saved_montage_renderer,
            montage_renderer_explicit=montage_renderer_explicit,
            montage_remotion_frame_concurrency=max(1, int(data.get("montage_remotion_frame_concurrency", 2))),
            montage_export_davinci_xml=bool(data.get("montage_export_davinci_xml", True)),
            montage_davinci_auto_import=bool(data.get("montage_davinci_auto_import", False)),
            montage_transition_style=(data.get("montage_transition_style", "crossfade")
                                      if data.get("montage_transition_style", "crossfade") in {"crossfade", "dip-black", "cut", "slide-left"}
                                      else "crossfade"),
            montage_transition_frames=max(0, min(30, int(data.get("montage_transition_frames", 7)))),
            montage_auto_web=bool(data.get("montage_auto_web", True)),
            # Automatic YouTube clip downloads are intentionally retired from
            # montage: only the explicit research/download screen may use a
            # user-approved source. Keeping old saved ``true`` values here
            # would make upgraded projects silently behave differently.
            montage_auto_youtube=False,
            montage_external_only=bool(data.get("montage_external_only", False)),
            montage_use_script_text=bool(data.get("montage_use_script_text", True)),
            # Core Montage policy: English/Latin on-screen text is never accepted.
            # Ignore stale legacy false values from older settings files.
            montage_exclude_english_text=True,
            montage_scene_planner=(data.get("montage_scene_planner", "local")
                                   if data.get("montage_scene_planner", "local") in {"local", "agent"} else "local"),
            montage_match_threshold=float(data.get("montage_match_threshold", 0.22)),
            montage_fast_reuse_enabled=bool(data.get("montage_fast_reuse_enabled", False)),
            montage_unique_footage_percent=max(5, min(100, int(data.get("montage_unique_footage_percent", 100)))),
            montage_fast_reuse_ranges=[item for item in data.get("montage_fast_reuse_ranges", []) if isinstance(item, dict)],
            montage_intro_enabled=bool(data.get("montage_intro_enabled", False)),
            montage_intro_folder=data.get("montage_intro_folder", ""),
            montage_intro_duration=float(data.get("montage_intro_duration", 6.0)),
            montage_overlay_enabled=bool(data.get("montage_overlay_enabled", False)),
            montage_overlay_folder=data.get("montage_overlay_folder", ""),
            montage_planning_workers=max(1, int(data.get("montage_planning_workers", 4))),
            montage_download_workers=max(1, int(data.get("montage_download_workers", 2))),
            montage_render_workers=max(1, int(data.get("montage_render_workers", 2))),
            montage_queue_paused=bool(data.get("montage_queue_paused", False)),
            montage_task_statuses=data.get("montage_task_statuses", {}),
            montage_recent_clip_paths=data.get("montage_recent_clip_paths", []),
            youtube_publication_jobs=[item for item in data.get("youtube_publication_jobs", []) if isinstance(item, dict)],
            youtube_publication_presets=[item for item in data.get("youtube_publication_presets", []) if isinstance(item, dict)],
            youtube_publication_activity=[item for item in data.get("youtube_publication_activity", []) if isinstance(item, dict)][-5000:],
            youtube_publication_items={str(key): dict(value) for key, value in data.get("youtube_publication_items", {}).items()
                                      if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_snapshots={str(key): dict(value) for key, value in data.get("youtube_publication_snapshots", {}).items()
                                          if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_executions={str(key): dict(value) for key, value in data.get("youtube_publication_executions", {}).items()
                                            if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_receipts={str(key): dict(value) for key, value in data.get("youtube_publication_receipts", {}).items()
                                          if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_migration_version=max(0, int(data.get("youtube_publication_migration_version", 0))),
            youtube_channel_publication_rules={str(key): dict(value) for key, value in data.get("youtube_channel_publication_rules", {}).items()
                                               if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_v2_rule_presets=[dict(item) for item in data.get("youtube_publication_v2_rule_presets", [])
                                                 if isinstance(item, dict)][-100:],
            youtube_publication_plan_versions=[dict(item) for item in data.get("youtube_publication_plan_versions", [])
                                               if isinstance(item, dict)][-50:],
            youtube_publication_assignments={str(key): dict(value) for key, value in data.get("youtube_publication_assignments", {}).items()
                                             if isinstance(key, str) and isinstance(value, dict)},
            youtube_publication_queue_paused=bool(data.get("youtube_publication_queue_paused", False)),
            youtube_publication_allocation_profiles=[item for item in data.get("youtube_publication_allocation_profiles", []) if isinstance(item, dict)],
            youtube_publication_allocation_presets=[item for item in data.get("youtube_publication_allocation_presets", []) if isinstance(item, dict)],
            youtube_publication_allocation_updated_at=str(data.get("youtube_publication_allocation_updated_at", "")),
            youtube_engagement_policies=[item for item in data.get("youtube_engagement_policies", []) if isinstance(item, dict)],
            youtube_engagement_tasks=[item for item in data.get("youtube_engagement_tasks", []) if isinstance(item, dict)][-10000:],
            youtube_publication_upload_concurrency=max(1, int(data.get("youtube_publication_upload_concurrency", 2))),
            youtube_analytics_metric_points=[item for item in data.get("youtube_analytics_metric_points", []) if isinstance(item, dict)][-20000:],
            youtube_analytics_video_metrics=[item for item in data.get("youtube_analytics_video_metrics", []) if isinstance(item, dict)][-10000:],
            youtube_analytics_updated_at=str(data.get("youtube_analytics_updated_at", "")),
            analytics_channels=data.get("analytics_channels", []),
            channel_research={str(key): dict(value) for key, value in data.get("channel_research", {}).items()
                              if isinstance(key, str) and isinstance(value, dict)},
            google_oauth_client_file=data.get("google_oauth_client_file", ""),
            youtube_oauth_service_url=data.get("youtube_oauth_service_url", ""),
            youtube_oauth_tokens=_protected_json_dict(data, "youtube_oauth_tokens_protected"),
            youtube_oauth_pending_handoffs=_protected_json_object_dict(data, "youtube_oauth_pending_handoffs_protected"),
            youtube_api_key=unprotect(data.get("youtube_api_key_protected", "")),
            youtube_api_enabled=bool(data.get("youtube_api_enabled", True)),
            obsidian_vault_path=data.get("obsidian_vault_path", ""),
            obsidian_mcp_url=data.get("obsidian_mcp_url", ""),
            obsidian_mcp_token=unprotect(data.get("obsidian_mcp_token_protected", "")),
            obsidian_sync_enabled=bool(data.get("obsidian_sync_enabled", False)),
            voicer_output_folder=migrate_newsflow_storage(data.get("voicer_output_folder"), "Озвучки"),
            secret_voicer_keys=voicer_keys,
            lumean_api_keys=lumean_keys,
            voicegen_api_keys=voicegen_keys,
            wproject_api_keys=wproject_keys,
            lumean_voice_cache=[item for item in data.get("lumean_voice_cache", []) if isinstance(item, dict)],
            lumean_model_cache=[str(item) for item in data.get("lumean_model_cache", []) if str(item).strip()],
            voicegen_voice_cache=[item for item in data.get("voicegen_voice_cache", []) if isinstance(item, dict)],
            voicegen_preset_cache=[item for item in data.get("voicegen_preset_cache", []) if isinstance(item, dict)],
            voicegen_engine_cache=[str(item) for item in data.get("voicegen_engine_cache", []) if str(item).strip()],
            voicegen_profile_cache=data.get("voicegen_profile_cache", {}) if isinstance(data.get("voicegen_profile_cache", {}), dict) else {},
            wproject_voice_cache=[item for item in data.get("wproject_voice_cache", []) if isinstance(item, dict)],
            wproject_profile_cache=data.get("wproject_profile_cache", {}) if isinstance(data.get("wproject_profile_cache", {}), dict) else {},
            wproject_usage_cache=data.get("wproject_usage_cache", {}) if isinstance(data.get("wproject_usage_cache", {}), dict) else {},
            voice_browser_profile_id=data.get("voice_browser_profile_id") or uuid.uuid4().hex,
            voice_provider=data.get("voice_provider", "chrome"),
            voice_api_fallback=bool(data.get("voice_api_fallback", True)),
            voice_use_chrome_selected_voice=bool(data.get("voice_use_chrome_selected_voice", True)),
            voice_queue_paused=bool(data.get("voice_queue_paused", False)),
            voice_default_profile_id=str(data.get("voice_default_profile_id", "") or ""),
            voice_ranges=data.get("voice_ranges", []),
            voice_range_presets=[item for item in data.get("voice_range_presets", []) if isinstance(item, dict)],
            voice_key_failover=bool(data.get("voice_key_failover", True)),
            voice_queue_concurrency=max(1, min(100, int(data.get("voice_queue_concurrency", 20) or 20))),
            voice_tts_batches=[item for item in data.get("voice_tts_batches", []) if isinstance(item, dict)][-30:],
            voice_active_tts_batch_id=str(data.get("voice_active_tts_batch_id", "") or ""),
            voice_tts_jobs={str(key): dict(value) for key, value in data.get("voice_tts_jobs", {}).items()
                            if isinstance(value, dict)},
            voice_scenario_outputs=data.get("voice_scenario_outputs", {}),
            voice_task_statuses=data.get("voice_task_statuses", {}),
            voice_import_summary=data.get("voice_import_summary", {}) if isinstance(data.get("voice_import_summary", {}), dict) else {},
            pipeline_target_count=pipeline_target,
            pipeline_montage_outputs=data.get("pipeline_montage_outputs", []),
            video_result_packages=data.get("video_result_packages", {}),
            results_output_folder=str(data.get("results_output_folder", "") or ""),
            results_last_export_folder=str(data.get("results_last_export_folder", "") or ""),
            voice_profiles=data.get("voice_profiles") or Settings().voice_profiles,
            template=data.get("template") or Settings().template,
            scenario_target_chars=max(0, int(data.get("scenario_target_chars", 0) or 0)),
            scenario_allowed_min=max(0, int(data.get("scenario_allowed_min", 0) or 0)),
            scenario_allowed_max=max(0, int(data.get("scenario_allowed_max", 0) or 0)),
            browser_topic_scenarios=(dict(data.get("browser_topic_scenarios", {}))
                                     if isinstance(data.get("browser_topic_scenarios", {}), dict) else {}),
            idea_topics=data.get("idea_topics", Settings().idea_topics),
            idea_suggested_topics=data.get("idea_suggested_topics", []),
            idea_reference_channels=[item for item in data.get("idea_reference_channels", []) if isinstance(item, dict)],
            idea_reference_analysis=[item for item in data.get("idea_reference_analysis", []) if isinstance(item, dict)],
            idea_reference_rules=data.get("idea_reference_rules", Settings().idea_reference_rules),
            idea_plan=data.get("idea_plan", []),
            youtube_suggested_topics=data.get("youtube_suggested_topics", []),
            idea_results=data.get("idea_results", []),
            idea_result_sources=data.get("idea_result_sources", {}),
            idea_title_metadata=data.get("idea_title_metadata", {}),
            idea_title_memory=data.get("idea_title_memory", []),
            idea_raw_signals=data.get("idea_raw_signals", []),
            idea_events=data.get("idea_events", []),
            idea_directions=data.get("idea_directions", []),
            idea_production_items=data.get("idea_production_items", []),
            idea_deleted_production_ids=[str(value).strip() for value in data.get("idea_deleted_production_ids", []) if str(value).strip()][-10000:],
            deleted_scenario_production_ids=[str(value).strip() for value in data.get("deleted_scenario_production_ids", []) if str(value).strip()][-10000:],
            production_reset_generation=max(0, int(data.get("production_reset_generation", 0) or 0)),
            idea_rejected_items=data.get("idea_rejected_items", []),
            idea_portfolio_summary=data.get("idea_portfolio_summary", {}),
            idea_scenario_context=data.get("idea_scenario_context", {}),
            idea_target_count=idea_target,
            idea_target_follows_pipeline=follows_pipeline,
            idea_route_presets=data.get("idea_route_presets", []),
            cover_route_presets=data.get("cover_route_presets", []),
            idea_include_custom=bool(data.get("idea_include_custom", False)),
            idea_custom_text=data.get("idea_custom_text", ""),
            auto_montage_enabled=bool(data.get("auto_montage_enabled", False)),
            auto_pipeline_stages={
                name: bool((data.get("auto_pipeline_stages") or {}).get(name, enabled))
                for name, enabled in Settings().auto_pipeline_stages.items()
            },
            idea_prompts=data.get("idea_prompts", Settings().idea_prompts),
            idea_chat_bindings=data.get("idea_chat_bindings", []),
            seo_chat_bindings=data.get("seo_chat_bindings", []),
            cover_chat_bindings=data.get("cover_chat_bindings", []),
            media_chat_bindings=data.get("media_chat_bindings", []),
            media_styles=data.get("media_styles") or Settings().media_styles,
            scenario_templates=data.get("scenario_templates", []),
            range_templates=data.get("range_templates", []),
            cover_api_keys=cover_keys,
            openai_api_keys=openai_keys,
            openai_model=data.get("openai_model", "gpt-5.4-mini"),
            cover_operation=data.get("cover_operation", "flower_image_generate"),
            cover_aspect_ratio=data.get("cover_aspect_ratio", "16:9"),
            cover_variant_count=max(1, min(10, int(data.get("cover_variant_count", 1)))),
            cover_prompt_provider=data.get("cover_prompt_provider", "agent") if data.get("cover_prompt_provider", "agent") in {"agent", "openai"} else "agent",
            cover_use_custom_prompt=bool(data.get("cover_use_custom_prompt", False)),
            cover_use_script_context=bool(data.get("cover_use_script_context", True)),
            # Up to ten visual approaches per topic; one remains a valid fast workflow.
            cover_prompt_variant_count=max(1, min(10, int(data.get("cover_prompt_variant_count", 2) or 2))),
            cover_headline_provider=data.get("cover_headline_provider", "agent") if data.get("cover_headline_provider", "agent") in {"agent", "openai"} else "agent",
            cover_text_mode=data.get("cover_text_mode", "overlay") if data.get("cover_text_mode", "overlay") in {"overlay", "fastgen"} else "overlay",
            # Retired local-composite routes retain the closest intent after
            # migration: FastGen receives the already selected portrait.
            cover_build_mode=("fastgen-full"
                              if str(data.get("cover_build_mode", "fastgen-full")) == "fastgen-full"
                              else "fastgen-full-my-face"),
            cover_build_mode_ranges=[item for item in data.get("cover_build_mode_ranges", [])
                                     if isinstance(item, dict)],
            cover_allow_varied_text_palette=bool(data.get("cover_allow_varied_text_palette", False)),
            cover_headline_template=data.get("cover_headline_template") or Settings().cover_headline_template,
            cover_subheadline_template=data.get("cover_subheadline_template") or Settings().cover_subheadline_template,
            cover_headline_presets=data.get("cover_headline_presets", []),
            cover_text_use_structure=bool(data.get("cover_text_use_structure", True)),
            cover_text_avoid_repeats=bool(data.get("cover_text_avoid_repeats", True)),
            cover_headlines_paused=bool(data.get("cover_headlines_paused", False)),
            cover_subheadlines_paused=bool(data.get("cover_subheadlines_paused", False)),
            cover_prompt_ranges=data.get("cover_prompt_ranges", []),
            cover_prompt_presets=data.get("cover_prompt_presets", []),
            cover_reference_mode=(str(data.get("cover_reference_mode", "all")).casefold()
                                  if str(data.get("cover_reference_mode", "all")).casefold() in {"all", "ranges", "off"} else "all"),
            cover_reference_paths=[str(value) for value in data.get("cover_reference_paths", []) if str(value).strip()],
            cover_reference_ranges=[item for item in data.get("cover_reference_ranges", []) if isinstance(item, dict)],
            cover_ai_reference_mode=(str(data.get("cover_ai_reference_mode", "off")).casefold()
                                     if str(data.get("cover_ai_reference_mode", "off")).casefold() in {"all", "ranges", "off"} else "off"),
            cover_ai_reference_paths=[str(value) for value in data.get("cover_ai_reference_paths", []) if str(value).strip()],
            cover_ai_reference_ranges=[item for item in data.get("cover_ai_reference_ranges", []) if isinstance(item, dict)],
            cover_ai_reference_to_fastgen=bool(data.get("cover_ai_reference_to_fastgen", False)),
            cover_fastgen_use_references=bool(data.get("cover_fastgen_use_references", False)),
            # Keep unavailable paths. The Covers UI must tell the operator
            # about a missing selected file instead of silently losing it.
            cover_fastgen_reference_paths=[str(value) for value in data.get("cover_fastgen_reference_paths", []) if str(value).strip()],
            cover_fastgen_reference_mode_style=bool(data.get("cover_fastgen_reference_mode_style", False)),
            cover_fastgen_reference_mode_composition=bool(data.get("cover_fastgen_reference_mode_composition", False)),
            cover_fastgen_reference_mode_mood_lighting=bool(data.get("cover_fastgen_reference_mode_mood_lighting", False)),
            cover_fastgen_reference_mode_auto=bool(data.get("cover_fastgen_reference_mode_auto", False)),
            cover_scene_intensity_mode=bool(data.get("cover_scene_intensity_mode", False)),
            cover_tabloid_mode=bool(data.get("cover_tabloid_mode", False)),
            cover_face_library_folder=str(data.get("cover_face_library_folder", "") or ""),
            cover_face_prepared_folder=str(data.get("cover_face_prepared_folder", "") or ""),
            cover_face_library_enabled=bool(data.get("cover_face_library_enabled", False)),
            cover_face_remove_background=bool(data.get("cover_face_remove_background", False)),
            cover_face_layout_memory=(data.get("cover_face_layout_memory", {})
                                      if isinstance(data.get("cover_face_layout_memory", {}), dict) else {}),
            cover_auto_overlay_text=bool(data.get("cover_auto_overlay_text", True)),
            cover_auto_text_color=bool(data.get("cover_auto_text_color", True)),
            cover_generation_paused=bool(data.get("cover_generation_paused", False)),
            cover_rate_limit_per_hour=max(0, int(data.get("cover_rate_limit_per_hour", 0) or 0)),
            cover_rate_auto_resume=bool(data.get("cover_rate_auto_resume", False)),
            cover_rate_usage_events=[item for item in data.get("cover_rate_usage_events", []) if isinstance(item, dict)][-10000:],
            cover_selected_key_labels=[str(item).strip() for item in data.get("cover_selected_key_labels", []) if str(item).strip()],
            cover_seed=str(data.get("cover_seed", "") or ""),
            cover_upscale=bool(data.get("cover_upscale", False)),
            cover_quality=str(data.get("cover_quality", "") or ""),
            cover_resolution=str(data.get("cover_resolution", "") or ""),
            fastgen_capabilities_cache=data.get("fastgen_capabilities_cache") or {"image": [], "video": []},
            fastgen_usage_cache=data.get("fastgen_usage_cache") or {},
            cover_queue=data.get("cover_queue", []),
            cover_queue_tombstones=[str(value).strip() for value in data.get("cover_queue_tombstones", [])
                                     if str(value).strip()][-10000:],
            deleted_scenario_titles=[" ".join(str(value).split()).casefold()
                                     for value in data.get("deleted_scenario_titles", []) if str(value).strip()][-10000:],
            cover_output_folder=migrate_standard_folder(data.get("cover_output_folder"), "Обложки", "Обложки"),
            cover_prompt_template=str(data.get("cover_prompt_template", "")),
            media_output_folder=migrate_standard_folder(data.get("media_output_folder"), "Медиа", "Медиа"),
            seo_output_folder=migrate_standard_folder(data.get("seo_output_folder"), "SEO", "SEO"),
            seo_queue=data.get("seo_queue", []),
            seo_prompt_template=data.get("seo_prompt_template") or Settings().seo_prompt_template,
            tags_prompt_template=data.get("tags_prompt_template") or Settings().tags_prompt_template,
            seo_provider=data.get("seo_provider", "agent") if data.get("seo_provider", "agent") in {"agent", "openai"} else "agent",
            tags_provider=data.get("tags_provider", "agent") if data.get("tags_provider", "agent") in {"agent", "openai"} else "agent",
            hashtag_batch_size=max(1, min(30, int(data.get("hashtag_batch_size", 5) or 5))),
            tag_char_limit=max(50, min(5000, int(data.get("tag_char_limit", 500) or 500))),
            seo_use_script_context=bool(data.get("seo_use_script_context", False)),
            seo_call_to_action=str(data.get("seo_call_to_action") or Settings().seo_call_to_action)[:1000],
            seo_description_prefix=str(data.get("seo_description_prefix") or "")[:4000],
            seo_description_prefix_ranges=[item for item in data.get("seo_description_prefix_ranges", []) if isinstance(item, dict)],
            seo_description_prefix_presets=[item for item in data.get("seo_description_prefix_presets", []) if isinstance(item, dict)],
            prompt_ranges=data.get("prompt_ranges") or Settings().prompt_ranges,
            scenario_provider=data.get("scenario_provider", "agent") if data.get("scenario_provider", "agent") in {"agent", "openai"} else "agent",
        )
        _apply_idea_production_tombstones(settings)
        # Old builds stored a profile list and a positional ``profile`` index
        # in ranges. Upgrade once in memory; the next ordinary save persists
        # stable IDs without touching audio mappings or media files.
        from .tts_ranges import migrate_voice_range_settings
        (settings.voice_profiles, settings.voice_ranges,
         settings.voice_default_profile_id, _changed) = migrate_voice_range_settings(
            settings.voice_profiles, settings.voice_ranges, settings.voice_default_profile_id,
        )
        # Memory-only baseline: an old worker must not resurrect a replaced key.
        settings._observed_api_keys = {
            name: data.get(name, []) for name in _API_KEY_FIELDS
        }
        settings._observed_youtube_key = data.get("youtube_api_key_protected", "")
        settings._observed_cover_key_labels = list(settings.cover_selected_key_labels)
        _remember_montage_reuse_preferences(settings)
        return settings
    except (SettingsFileCorruptError, SettingsSchemaVersionError):
        raise
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return Settings()


def _montage_status_order(item: object) -> tuple[str, int, int]:
    """Order persisted queue updates from different NewsFlowCore processes.

    Long-running cover and montage commands each own a Settings instance.  A
    whole-file save from an unrelated worker must retain the newest progress
    written by the montage worker instead of restoring its stale snapshot.
    """
    if not isinstance(item, dict):
        return ("", -1, -1)
    status_rank = {
        "В очереди": 0, "Планирование": 1, "Планирование сцен": 2,
        "Подбор футажей": 3, "Внешний поиск": 4,
        "Нарезка внешнего футажа": 5, "Ожидает рендер": 6,
        "Рендер": 7, "Готово": 8,
    }.get(str(item.get("status", "")), 0)
    try:
        progress = int(item.get("progress", -1))
    except (TypeError, ValueError):
        progress = -1
    return (str(item.get("updatedAt", "")), progress, status_rank)


def _merge_montage_task_statuses(persisted: object, incoming: object) -> dict[str, dict]:
    """Keep the newest per-task montage status during an unrelated save."""
    merged = {str(key): dict(value) for key, value in (persisted or {}).items()
              if isinstance(value, dict)} if isinstance(persisted, dict) else {}
    if not isinstance(incoming, dict):
        return merged
    for key, value in incoming.items():
        if not isinstance(value, dict):
            continue
        key = str(key)
        if key not in merged or _montage_status_order(value) >= _montage_status_order(merged[key]):
            merged[key] = dict(value)
    return merged


def _api_key_record_identity(record: dict, position: int) -> str:
    """Identify encrypted key rows without exposing a secret in the JSON file."""
    protected = str(record.get("secret_protected", "") or "")
    try:
        secret = unprotect(protected).strip()
    except (OSError, ValueError):
        secret = ""
    if secret:
        return f"secret:{secret}"
    label = " ".join(str(record.get("label", "")).split()).casefold()
    return f"fallback:{label}:{protected or position}"


_API_KEY_FIELDS = ("cover_api_keys", "openai_api_keys", "secret_voicer_keys",
                   "lumean_api_keys", "voicegen_api_keys", "wproject_api_keys")


_MONTAGE_REUSE_PREFERENCES = (
    "montage_fast_reuse_enabled", "montage_unique_footage_percent", "montage_fast_reuse_ranges",
)


def _remember_montage_reuse_preferences(settings: Settings) -> None:
    # Copy nested ranges: an in-place operator edit must differ from its baseline.
    settings._observed_montage_reuse = {
        name: deepcopy(getattr(settings, name)) for name in _MONTAGE_REUSE_PREFERENCES
    }


def _merge_api_key_records(persisted: object, incoming: object, observed: object = None) -> list[dict]:
    """Keep newly saved API keys when an older worker writes its snapshot."""
    disk_rows = [dict(item) for item in (persisted or []) if isinstance(item, dict)] \
        if isinstance(persisted, list) else []
    memory_rows = [dict(item) for item in (incoming or []) if isinstance(item, dict)] \
        if isinstance(incoming, list) else []
    if isinstance(observed, list):
        # Rows are append-only; rotation preserves positions even for duplicate
        # secrets. Compare each loaded row, not a set of secret identities.
        for index, item in enumerate(memory_rows):
            if index >= len(observed) or index >= len(disk_rows) or not isinstance(observed[index], dict):
                continue
            baseline = observed[index]
            disk = disk_rows[index]
            same_loaded_secret = _api_key_record_identity(item, index) == _api_key_record_identity(baseline, index)
            disk_changed = (_api_key_record_identity(disk, index) != _api_key_record_identity(baseline, index)
                            or disk.get("label") != baseline.get("label"))
            if same_loaded_secret and disk_changed:
                memory_rows[index] = disk
    if not disk_rows:
        return memory_rows
    if not memory_rows:
        return disk_rows
    known = {_api_key_record_identity(item, position) for position, item in enumerate(memory_rows)}
    merged = list(memory_rows)
    for position, item in enumerate(disk_rows):
        identity = _api_key_record_identity(item, position)
        if identity not in known:
            merged.append(item)
            known.add(identity)
    return merged


def _cover_queue_key(item: dict, position: int) -> str:
    """Stable identity for a cover row while two workers save in parallel."""
    identity = str(item.get("production_item_id") or item.get("productionItemId") or "").strip()
    if identity:
        return f"production:{identity}"
    return _legacy_cover_queue_key(item, position)


def _legacy_cover_queue_key(item: dict, position: int) -> str:
    scenario_index = item.get("scenario_index")
    if scenario_index not in (None, ""):
        return f"scenario:{scenario_index}"
    title = " ".join(str(item.get("title", "")).split()).casefold()
    return f"title:{title}" if title else f"position:{position}"


def _cover_status_order(item: dict) -> tuple[str, int, int]:
    """Newer progress wins; a valid completed file always beats stale work."""
    status_rank = {
        "Ожидает": 1, "Подготовка запросов": 2, "Подготовка варианта": 3,
        "FastGen генерирует": 4, "Повторная попытка": 5, "Переписываем промпт": 6,
        "Ошибка FastGen": 7, "Готово": 9,
    }.get(str(item.get("status", "")), 0)
    try:
        progress = int(item.get("progress", -1))
    except (TypeError, ValueError):
        progress = -1
    return (str(item.get("updatedAt", "")), progress, status_rank)


def _merge_cover_queue(persisted: object, incoming: object, *, tombstones: set[str] | None = None) -> list[dict]:
    """Do not let montage progress saves erase active FastGen row updates.

    Electron starts the montage queue as a detached core process, while cover
    generation runs through another bridge process.  Both own a Settings
    snapshot.  Merge each known row by its scenario identity instead of
    replacing the entire cover queue from a stale snapshot.
    """
    removed = tombstones or set()
    disk_rows = [dict(item) for item in (persisted or []) if isinstance(item, dict)] \
        if isinstance(persisted, list) else []
    memory_rows = [dict(item) for item in (incoming or []) if isinstance(item, dict)] \
        if isinstance(incoming, list) else []
    disk_rows = [item for position, item in enumerate(disk_rows)
                 if _cover_queue_key(item, position) not in removed]
    memory_rows = [item for position, item in enumerate(memory_rows)
                   if _cover_queue_key(item, position) not in removed]
    if not disk_rows:
        return memory_rows
    if not memory_rows:
        return disk_rows
    disk_by_key = {_cover_queue_key(item, position): item for position, item in enumerate(disk_rows)}
    incoming_by_key = {_cover_queue_key(item, position): item for position, item in enumerate(memory_rows)}
    merged: list[dict] = []
    for position, current in enumerate(memory_rows):
        key = _cover_queue_key(current, position)
        saved = disk_by_key.get(key)
        if saved is not None and _cover_status_order(saved) > _cover_status_order(current):
            merged.append(saved)
        else:
            merged.append(current)
    # A concurrently added cover must not disappear merely because an older
    # montage process never saw that row.
    for position, saved in enumerate(disk_rows):
        key = _cover_queue_key(saved, position)
        if key not in incoming_by_key:
            merged.append(saved)
    return merged


_RELEASE_STATE_FIELDS = (
    "idea_plan", "youtube_suggested_topics", "idea_title_memory", "idea_raw_signals", "idea_events",
    "idea_rejected_items", "idea_portfolio_summary", "idea_suggested_topics",
    "idea_results", "idea_result_sources", "idea_title_metadata", "idea_scenario_context",
    "idea_production_items", "voice_scenario_outputs", "voice_task_statuses", "voice_tts_jobs",
    "voice_tts_batches", "voice_active_tts_batch_id", "voice_import_summary",
    "pipeline_montage_outputs", "video_result_packages", "montage_task_statuses", "seo_queue",
    "youtube_publication_jobs", "youtube_publication_items", "youtube_publication_snapshots",
    "youtube_publication_executions", "youtube_publication_receipts", "youtube_publication_assignments",
    "youtube_publication_activity", "youtube_publication_plan_versions", "youtube_engagement_tasks",
    "results_last_export_folder", "cover_queue",
)


def allow_empty_release_state(settings: Settings, *field_names: str) -> None:
    """Mark an explicit, user-confirmed destructive action for one save only.

    Detached workers own stale ``Settings`` instances.  Empty collections from
    such a worker are not evidence that a user asked to erase a release.
    Explicit removal commands opt in to empty writes through this transient
    marker, which is deliberately never written to settings.json.
    """
    allowed = set(getattr(settings, "_allowed_empty_release_fields", set()))
    allowed.update(name for name in field_names if name in _RELEASE_STATE_FIELDS)
    settings._allowed_empty_release_fields = allowed


def _has_release_state(value: object) -> bool:
    return bool(value) if isinstance(value, (dict, list, tuple, set)) else value is not None


def _preserve_release_state(persisted: object, incoming: object, *, allow_empty: bool) -> object:
    """Reject an unexplained empty overwrite from a stale background worker."""
    if not allow_empty and not _has_release_state(incoming) and _has_release_state(persisted):
        return persisted
    return incoming


def _archive_pre_write_settings(path: Path, raw_on_disk: str) -> None:
    """Keep one independent, atomically-written rollback point before a save.

    The archive lives beside the shared settings file rather than inside any
    portable build or temporary extraction directory, so upgrading an EXE
    cannot replace it.  It intentionally stores the original raw JSON: a
    failed migration can therefore be reversed without reserializing secrets
    or losing unknown fields from a newer build.
    """
    if not raw_on_disk:
        return
    archive_dir = path.parent / "state-backups"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / "settings-last-known-good.json"
    temporary = archive.with_name(f".{archive.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(raw_on_disk, encoding="utf-8")
        deadline = time.monotonic() + 8.0
        while True:
            try:
                os.replace(temporary, archive)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.10)
    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass



def reconcile_voice_outputs(updates: list[dict]) -> dict:
    """Atomically attach validated MP3s without serializing unrelated settings.

    Each update is a compare-and-swap against the latest settings.json under
    the same cross-process lock used by normal saves. Only voice_tts_jobs,
    voice_scenario_outputs and voice_task_statuses may change.
    """
    clean_updates = [dict(item) for item in updates if isinstance(item, dict)]
    result = {"applied_indices": [], "blocked": 0, "skipped": 0, "skip_reasons": {}}
    if not clean_updates:
        return result

    def skip(reason: str) -> None:
        result["skipped"] += 1
        reasons = result["skip_reasons"]
        reasons[reason] = int(reasons.get(reason, 0) or 0) + 1

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_settings_write(path):
        if not path.is_file():
            result["skipped"] = len(clean_updates)
            result["skip_reasons"] = {"SETTINGS_MISSING": len(clean_updates)}
            return result
        try:
            raw_on_disk = _read_settings_text(path)
            data = json.loads(raw_on_disk)
        except (ValueError, json.JSONDecodeError) as error:
            raise SettingsFileCorruptError(path) from error
        if not isinstance(data, dict):
            raise SettingsFileCorruptError(path)

        voice_jobs = {
            str(key): dict(value)
            for key, value in dict(data.get("voice_tts_jobs") or {}).items()
            if isinstance(value, dict)
        }
        voice_outputs = dict(data.get("voice_scenario_outputs") or {})
        voice_statuses = dict(data.get("voice_task_statuses") or {})
        deleted_ids = {
            str(value).strip()
            for field_name in ("idea_deleted_production_ids", "deleted_scenario_production_ids")
            for value in (data.get(field_name) if isinstance(data.get(field_name), list) else [])
            if str(value).strip()
        }
        active_count = sum(
            1 for item in voice_jobs.values()
            if str(item.get("state", "")).casefold() in {"running", "retrying"}
        )
        if active_count:
            result["blocked"] = active_count
            return result

        for update in clean_updates:
            production_item_id = str(update.get("production_item_id", "")).strip()
            current = voice_jobs.get(production_item_id)
            if not production_item_id or not isinstance(current, dict):
                skip("JOB_MISSING")
                continue
            if production_item_id in deleted_ids:
                skip("PRODUCTION_ITEM_DELETED")
                continue
            expected_deleted_ids_hash = str(update.get("deleted_ids_hash", "")).strip()
            if expected_deleted_ids_hash:
                current_deleted_ids_hash = hashlib.sha256(
                    "\0".join(sorted(deleted_ids)).encode("utf-8")
                ).hexdigest()
                if current_deleted_ids_hash != expected_deleted_ids_hash:
                    skip("TOMBSTONES_CHANGED")
                    continue
            expected_job_id = str(update.get("expected_job_id", "")).strip()
            if not expected_job_id or str(current.get("id", "")).strip() != expected_job_id:
                skip("JOB_CHANGED")
                continue
            try:
                scenario_index = int(update.get("scenario_index"))
                current_index = int(current.get("scenario_index"))
            except (TypeError, ValueError):
                skip("INDEX_INVALID")
                continue
            output_key = str(update.get("output_key", "")).strip()
            expected_key = str(scenario_index + 1)
            current_script_hash = str(
                current.get("script_hash") or current.get("script_revision") or ""
            ).strip()
            expected_script_hash = str(update.get("script_hash", "")).strip()
            if (scenario_index < 0 or current_index != scenario_index
                    or output_key != expected_key
                    or str(current.get("production_item_id", "")).strip() != production_item_id
                    or not expected_script_hash
                    or current_script_hash != expected_script_hash):
                skip("IDENTITY_CHANGED")
                continue
            existing_output = Path(str(voice_outputs.get(output_key, "")))
            if existing_output.is_file():
                skip("OUTPUT_ALREADY_READY")
                continue

            candidate = Path(str(update.get("output_path", "")))
            if not candidate.is_file() or candidate.suffix.casefold() != ".mp3":
                skip("CANDIDATE_MISSING")
                continue
            try:
                candidate_stat = candidate.stat()
                expected_size = int(update.get("file_size"))
                expected_mtime_ns = int(update.get("file_mtime_ns"))
                duration = float(update.get("duration_seconds"))
            except (OSError, TypeError, ValueError):
                skip("CANDIDATE_METADATA_INVALID")
                continue
            if (candidate_stat.st_size != expected_size
                    or candidate_stat.st_mtime_ns != expected_mtime_ns
                    or duration <= 0.05):
                skip("FILE_CHANGED")
                continue

            validated_at = str(update.get("validated_at", "")).strip()
            restored = dict(current)
            restored.update({
                "state": "ready",
                "output_path": str(candidate),
                "artifact": {
                    "path": str(candidate),
                    "duration_seconds": duration,
                    "validated_at": validated_at,
                },
            })
            restored.pop("error", None)
            restored.pop("retry_count", None)
            restored.pop("next_retry_after_seconds", None)
            for field_name in list(restored):
                if (field_name.startswith("wproject_")
                        and field_name.endswith(("_error", "_next_retry_seconds"))):
                    restored.pop(field_name, None)
            voice_jobs[production_item_id] = restored
            voice_outputs[output_key] = str(candidate)
            voice_statuses[output_key] = {
                "label": "Готово: восстановлено",
                "progress": 100,
                "updatedAt": time.strftime("%H:%M:%S"),
                "durationSeconds": duration,
                "artifactPath": str(candidate),
                "jobSnapshotId": str(restored.get("id", "")),
            }
            result["applied_indices"].append(scenario_index)

        if not result["applied_indices"]:
            return result

        data["voice_tts_jobs"] = voice_jobs
        data["voice_scenario_outputs"] = voice_outputs
        data["voice_task_statuses"] = voice_statuses
        _archive_pre_write_settings(path, raw_on_disk)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            deadline = time.monotonic() + 8.0
            while True:
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.10)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass
    return result


def save_settings(settings: Settings):
    data = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "api_key_notes": settings.api_key_notes,
        "output_folder": settings.output_folder,
        "idea_output_folder": settings.idea_output_folder,
        "footage_folders": settings.footage_folders,
        "footage_download_folder": settings.footage_download_folder,
        "cutter_output_folder": settings.cutter_output_folder,
        "cutter_sources": settings.cutter_sources,
        "mixer_output_folder": settings.mixer_output_folder,
        "montage_project_folder": settings.montage_project_folder,
        "montage_output_folder": settings.montage_output_folder,
        "montage_aspect_ratio": settings.montage_aspect_ratio,
        "montage_renderer": settings.montage_renderer,
        "montage_renderer_explicit": settings.montage_renderer_explicit,
        "montage_remotion_frame_concurrency": settings.montage_remotion_frame_concurrency,
        "montage_export_davinci_xml": settings.montage_export_davinci_xml,
        "montage_davinci_auto_import": settings.montage_davinci_auto_import,
        "montage_transition_style": settings.montage_transition_style,
        "montage_transition_frames": settings.montage_transition_frames,
        "montage_auto_web": settings.montage_auto_web,
        "montage_auto_youtube": settings.montage_auto_youtube,
        "montage_external_only": settings.montage_external_only,
        "montage_use_script_text": settings.montage_use_script_text,
        "montage_exclude_english_text": settings.montage_exclude_english_text,
        "montage_scene_planner": settings.montage_scene_planner,
        "montage_match_threshold": settings.montage_match_threshold,
        "montage_fast_reuse_enabled": settings.montage_fast_reuse_enabled,
        "montage_unique_footage_percent": settings.montage_unique_footage_percent,
        "montage_fast_reuse_ranges": settings.montage_fast_reuse_ranges,
        "montage_intro_enabled": settings.montage_intro_enabled,
        "montage_intro_folder": settings.montage_intro_folder,
        "montage_intro_duration": settings.montage_intro_duration,
        "montage_overlay_enabled": settings.montage_overlay_enabled,
        "montage_overlay_folder": settings.montage_overlay_folder,
        "montage_planning_workers": settings.montage_planning_workers,
        "montage_download_workers": settings.montage_download_workers,
        "montage_render_workers": settings.montage_render_workers,
        "montage_queue_paused": settings.montage_queue_paused,
        "montage_task_statuses": settings.montage_task_statuses,
        "montage_recent_clip_paths": settings.montage_recent_clip_paths[-3000:],
        "youtube_publication_jobs": settings.youtube_publication_jobs,
        "youtube_publication_presets": settings.youtube_publication_presets,
        "youtube_publication_activity": settings.youtube_publication_activity[-5000:],
        "youtube_publication_items": settings.youtube_publication_items,
        "youtube_publication_snapshots": settings.youtube_publication_snapshots,
        "youtube_publication_executions": settings.youtube_publication_executions,
        "youtube_publication_receipts": settings.youtube_publication_receipts,
        "youtube_publication_migration_version": settings.youtube_publication_migration_version,
        "youtube_channel_publication_rules": settings.youtube_channel_publication_rules,
        "youtube_publication_v2_rule_presets": settings.youtube_publication_v2_rule_presets[-100:],
        "youtube_publication_plan_versions": settings.youtube_publication_plan_versions[-50:],
        "youtube_publication_assignments": settings.youtube_publication_assignments,
        "youtube_publication_queue_paused": settings.youtube_publication_queue_paused,
        "youtube_publication_allocation_profiles": settings.youtube_publication_allocation_profiles,
        "youtube_publication_allocation_presets": settings.youtube_publication_allocation_presets,
        "youtube_publication_allocation_updated_at": settings.youtube_publication_allocation_updated_at,
        "youtube_engagement_policies": settings.youtube_engagement_policies,
        "youtube_engagement_tasks": settings.youtube_engagement_tasks[-10000:],
        "youtube_publication_upload_concurrency": settings.youtube_publication_upload_concurrency,
        "youtube_analytics_metric_points": settings.youtube_analytics_metric_points[-20000:],
        "youtube_analytics_video_metrics": settings.youtube_analytics_video_metrics[-10000:],
        "youtube_analytics_updated_at": settings.youtube_analytics_updated_at,
        "analytics_channels": settings.analytics_channels,
        "channel_research": settings.channel_research,
        "google_oauth_client_file": settings.google_oauth_client_file,
        "youtube_oauth_service_url": settings.youtube_oauth_service_url,
        "youtube_oauth_tokens_protected": protect(json.dumps(settings.youtube_oauth_tokens, ensure_ascii=False)),
        "youtube_oauth_pending_handoffs_protected": protect(json.dumps(settings.youtube_oauth_pending_handoffs, ensure_ascii=False)),
        "youtube_api_key_protected": protect(settings.youtube_api_key),
        "youtube_api_enabled": settings.youtube_api_enabled,
        "obsidian_vault_path": settings.obsidian_vault_path,
        "obsidian_mcp_url": settings.obsidian_mcp_url,
        "obsidian_mcp_token_protected": protect(settings.obsidian_mcp_token),
        "obsidian_sync_enabled": settings.obsidian_sync_enabled,
        "voicer_output_folder": settings.voicer_output_folder,
        "secret_voicer_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active,
                                 "streams": item.streams, "balance": item.balance,
                                 "balance_status": item.balance_status}
                               for item in settings.secret_voicer_keys],
        "lumean_api_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active,
                             "streams": item.streams, "balance": item.balance,
                             "balance_status": item.balance_status}
                            for item in settings.lumean_api_keys],
        "lumean_voice_cache": settings.lumean_voice_cache,
        "lumean_model_cache": settings.lumean_model_cache,
        "voicegen_api_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active,
                               "streams": item.streams, "balance": item.balance,
                               "balance_status": item.balance_status}
                              for item in settings.voicegen_api_keys],
        "voicegen_voice_cache": settings.voicegen_voice_cache,
        "voicegen_preset_cache": settings.voicegen_preset_cache,
        "voicegen_engine_cache": settings.voicegen_engine_cache,
        "voicegen_profile_cache": settings.voicegen_profile_cache,
        "wproject_api_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active,
                               "streams": item.streams, "balance": item.balance,
                               "balance_status": item.balance_status}
                              for item in settings.wproject_api_keys],
        "wproject_voice_cache": settings.wproject_voice_cache,
        "wproject_profile_cache": settings.wproject_profile_cache,
        "wproject_usage_cache": settings.wproject_usage_cache,
        "voice_browser_profile_id": settings.voice_browser_profile_id,
        "voice_provider": settings.voice_provider,
        "voice_api_fallback": settings.voice_api_fallback,
        "voice_use_chrome_selected_voice": settings.voice_use_chrome_selected_voice,
        "voice_queue_paused": settings.voice_queue_paused,
        "voice_default_profile_id": settings.voice_default_profile_id,
        "voice_ranges": settings.voice_ranges,
        "voice_range_presets": settings.voice_range_presets,
        "voice_key_failover": settings.voice_key_failover,
        "voice_queue_concurrency": settings.voice_queue_concurrency,
        "voice_tts_batches": settings.voice_tts_batches[-30:],
        "voice_active_tts_batch_id": settings.voice_active_tts_batch_id,
        "voice_tts_jobs": settings.voice_tts_jobs,
        "voice_scenario_outputs": settings.voice_scenario_outputs,
        "voice_task_statuses": settings.voice_task_statuses,
        "voice_import_summary": settings.voice_import_summary,
        "pipeline_target_count": settings.pipeline_target_count,
        "pipeline_montage_outputs": settings.pipeline_montage_outputs,
        "video_result_packages": settings.video_result_packages,
        "results_output_folder": settings.results_output_folder,
        "results_last_export_folder": settings.results_last_export_folder,
        "voice_profiles": settings.voice_profiles,
        "template": settings.template,
        "scenario_target_chars": settings.scenario_target_chars,
        "scenario_allowed_min": settings.scenario_allowed_min,
        "scenario_allowed_max": settings.scenario_allowed_max,
        "browser_topic_scenarios": settings.browser_topic_scenarios,
        "idea_topics": settings.idea_topics,
        "idea_suggested_topics": settings.idea_suggested_topics,
        "idea_reference_channels": settings.idea_reference_channels,
        "idea_reference_analysis": settings.idea_reference_analysis,
        "idea_reference_rules": settings.idea_reference_rules,
        "idea_plan": settings.idea_plan,
        "youtube_suggested_topics": settings.youtube_suggested_topics,
        "idea_results": settings.idea_results,
        "idea_result_sources": settings.idea_result_sources,
        "idea_title_metadata": settings.idea_title_metadata,
        "idea_title_memory": settings.idea_title_memory,
        "idea_raw_signals": settings.idea_raw_signals,
        "idea_events": settings.idea_events,
        "idea_directions": settings.idea_directions,
        "idea_production_items": settings.idea_production_items,
        "idea_deleted_production_ids": settings.idea_deleted_production_ids[-10000:],
        "deleted_scenario_production_ids": settings.deleted_scenario_production_ids[-10000:],
        "production_reset_generation": settings.production_reset_generation,
        "idea_rejected_items": settings.idea_rejected_items,
        "idea_portfolio_summary": settings.idea_portfolio_summary,
        "idea_scenario_context": settings.idea_scenario_context,
        "idea_target_count": settings.idea_target_count,
        # A manually chosen differing amount is, by definition, detached.
        "idea_target_follows_pipeline": bool(settings.idea_target_follows_pipeline
                                              and settings.idea_target_count == settings.pipeline_target_count),
        "idea_route_presets": settings.idea_route_presets,
        "cover_route_presets": settings.cover_route_presets,
        "idea_include_custom": settings.idea_include_custom,
        "idea_custom_text": settings.idea_custom_text,
        "auto_montage_enabled": settings.auto_montage_enabled,
        "auto_pipeline_stages": settings.auto_pipeline_stages,
        "idea_prompts": settings.idea_prompts,
        "idea_chat_bindings": settings.idea_chat_bindings,
        "seo_chat_bindings": settings.seo_chat_bindings,
        "cover_chat_bindings": settings.cover_chat_bindings,
        "media_chat_bindings": settings.media_chat_bindings,
        "media_styles": settings.media_styles,
        "scenario_templates": settings.scenario_templates,
        "range_templates": settings.range_templates,
        "cover_api_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active}
                           for item in settings.cover_api_keys],
        "openai_api_keys": [{"label": item.label, "secret_protected": protect(item.secret), "active": item.active}
                            for item in settings.openai_api_keys],
        "openai_model": settings.openai_model,
        "cover_operation": settings.cover_operation,
        "cover_aspect_ratio": settings.cover_aspect_ratio,
        "cover_variant_count": settings.cover_variant_count,
        "cover_prompt_provider": settings.cover_prompt_provider,
        "cover_use_custom_prompt": settings.cover_use_custom_prompt,
        "cover_use_script_context": settings.cover_use_script_context,
        "cover_prompt_variant_count": settings.cover_prompt_variant_count,
        "cover_headline_provider": settings.cover_headline_provider,
        "cover_text_mode": settings.cover_text_mode,
        "cover_build_mode": settings.cover_build_mode,
        "cover_build_mode_ranges": settings.cover_build_mode_ranges,
        "cover_allow_varied_text_palette": settings.cover_allow_varied_text_palette,
        "cover_headline_template": settings.cover_headline_template,
        "cover_subheadline_template": settings.cover_subheadline_template,
        "cover_headline_presets": settings.cover_headline_presets,
        "cover_text_use_structure": settings.cover_text_use_structure,
        "cover_text_avoid_repeats": settings.cover_text_avoid_repeats,
        "cover_headlines_paused": settings.cover_headlines_paused,
        "cover_subheadlines_paused": settings.cover_subheadlines_paused,
        "cover_prompt_ranges": settings.cover_prompt_ranges,
        "cover_prompt_presets": settings.cover_prompt_presets,
        "cover_reference_mode": settings.cover_reference_mode,
        "cover_reference_paths": settings.cover_reference_paths,
        "cover_reference_ranges": settings.cover_reference_ranges,
        "cover_ai_reference_mode": settings.cover_ai_reference_mode,
        "cover_ai_reference_paths": settings.cover_ai_reference_paths,
        "cover_ai_reference_ranges": settings.cover_ai_reference_ranges,
        "cover_ai_reference_to_fastgen": settings.cover_ai_reference_to_fastgen,
        "cover_fastgen_use_references": settings.cover_fastgen_use_references,
        "cover_fastgen_reference_paths": settings.cover_fastgen_reference_paths,
        "cover_fastgen_reference_mode_style": settings.cover_fastgen_reference_mode_style,
        "cover_fastgen_reference_mode_composition": settings.cover_fastgen_reference_mode_composition,
        "cover_fastgen_reference_mode_mood_lighting": settings.cover_fastgen_reference_mode_mood_lighting,
        "cover_fastgen_reference_mode_auto": settings.cover_fastgen_reference_mode_auto,
        "cover_scene_intensity_mode": settings.cover_scene_intensity_mode,
        "cover_tabloid_mode": settings.cover_tabloid_mode,
        "cover_face_library_folder": settings.cover_face_library_folder,
        "cover_face_prepared_folder": settings.cover_face_prepared_folder,
        "cover_face_library_enabled": settings.cover_face_library_enabled,
        "cover_face_remove_background": settings.cover_face_remove_background,
        "cover_face_layout_memory": settings.cover_face_layout_memory,
        "cover_auto_overlay_text": settings.cover_auto_overlay_text,
        "cover_auto_text_color": settings.cover_auto_text_color,
        "cover_generation_paused": settings.cover_generation_paused,
        "cover_rate_limit_per_hour": settings.cover_rate_limit_per_hour,
        "cover_rate_auto_resume": settings.cover_rate_auto_resume,
        "cover_rate_usage_events": settings.cover_rate_usage_events,
        "cover_selected_key_labels": settings.cover_selected_key_labels,
        "cover_seed": settings.cover_seed,
        "cover_upscale": settings.cover_upscale,
        "cover_quality": settings.cover_quality,
        "cover_resolution": settings.cover_resolution,
        "fastgen_capabilities_cache": settings.fastgen_capabilities_cache,
        "fastgen_usage_cache": settings.fastgen_usage_cache,
        "cover_queue": settings.cover_queue,
        "cover_queue_tombstones": settings.cover_queue_tombstones,
        "deleted_scenario_titles": settings.deleted_scenario_titles[-10000:],
        "cover_output_folder": settings.cover_output_folder,
        "cover_prompt_template": settings.cover_prompt_template,
        "media_output_folder": settings.media_output_folder,
        "seo_output_folder": settings.seo_output_folder,
        "seo_queue": settings.seo_queue,
        "seo_prompt_template": settings.seo_prompt_template,
        "tags_prompt_template": settings.tags_prompt_template,
        "seo_provider": settings.seo_provider,
        "tags_provider": settings.tags_provider,
        "hashtag_batch_size": settings.hashtag_batch_size,
        "tag_char_limit": settings.tag_char_limit,
        "seo_use_script_context": settings.seo_use_script_context,
        "seo_call_to_action": settings.seo_call_to_action,
        "seo_description_prefix": settings.seo_description_prefix,
        "seo_description_prefix_ranges": settings.seo_description_prefix_ranges,
        "seo_description_prefix_presets": settings.seo_description_prefix_presets,
        "prompt_ranges": settings.prompt_ranges,
        "scenario_provider": settings.scenario_provider,
        "chrome_sessions": [
            {"label": item.label, "profile_id": item.profile_id, "active": item.active,
             "limit_status": item.limit_status, "usage": item.usage}
            for item in settings.chrome_sessions
        ],
    }
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_settings_write(path):
        try:
            raw_on_disk = _read_settings_text(path, missing_under_lock=True)
            on_disk = json.loads(raw_on_disk)
        except (ValueError, json.JSONDecodeError) as error:
            raise SettingsFileCorruptError(path) from error
        if not isinstance(on_disk, dict):
            raise SettingsFileCorruptError(path)
        replacement = getattr(settings, "_api_key_replacement", None)
        if replacement:
            # A credential edit is a narrow mutation, not a stale whole-profile
            # save. Start from the current locked disk snapshot so concurrent
            # settings changes and other credential selections survive.
            data = dict(on_disk)
        observed_reuse = getattr(settings, "_observed_montage_reuse", {})
        edited_reuse = getattr(settings, "_edited_montage_reuse", set())
        for name in _MONTAGE_REUSE_PREFERENCES:
            # A progress/project/queue save does not own unchanged preferences.
            # Resolve against the latest disk snapshot while holding the lock,
            # not a pre-lock read that another process can immediately supersede.
            # Credential replacement already uses only the current disk
            # snapshot, which may legitimately omit these optional fields.
            if (not replacement and name in observed_reuse and name not in edited_reuse
                    and getattr(settings, name) == observed_reuse[name]):
                data[name] = on_disk.get(name, data[name])
        disk_generation = max(0, int(on_disk.get("production_reset_generation", 0) or 0))
        incoming_generation = max(0, int(data.get("production_reset_generation", 0) or 0))
        stale_release_snapshot = incoming_generation < disk_generation
        data["production_reset_generation"] = max(disk_generation, incoming_generation)
        allowed_empty_fields = set(getattr(settings, "_allowed_empty_release_fields", set()))
        data["montage_task_statuses"] = (
            dict(on_disk.get("montage_task_statuses") or {})
            if stale_release_snapshot
            else (dict(data.get("montage_task_statuses") or {})
                  if "montage_task_statuses" in allowed_empty_fields
                  else _merge_montage_task_statuses(
                      on_disk.get("montage_task_statuses"), data.get("montage_task_statuses"),
                  ))
        )
        for key_name in _RELEASE_STATE_FIELDS:
            if key_name == "montage_task_statuses":
                continue
            if stale_release_snapshot:
                data[key_name] = on_disk.get(key_name, data.get(key_name))
            else:
                data[key_name] = _preserve_release_state(
                    on_disk.get(key_name), data.get(key_name),
                    allow_empty=key_name in allowed_empty_fields,
                )
        for key_name in _API_KEY_FIELDS:
            if replacement and replacement["field"] == key_name:
                rows = [dict(row) for row in on_disk.get(key_name, [])]
                index = replacement["index"]
                if not 0 <= index < len(rows):
                    raise ValueError("Ключ изменён. Обновите список и откройте его заново.")
                old_secret = unprotect(rows[index].get("secret_protected", ""))
                old_label = str(rows[index].get("label", ""))
                revision = hashlib.sha256(f"{old_secret}\0{old_label}".encode()).hexdigest()
                if revision != replacement["revision"]:
                    raise ValueError("Ключ изменён. Обновите список и откройте его заново.")
                rows[index]["secret_protected"] = protect(replacement["secret"])
                rows[index]["label"] = replacement["label"]
                data[key_name] = rows
                if key_name == "cover_api_keys":
                    selected = list(on_disk.get("cover_selected_key_labels", []))
                    if old_label in selected:
                        still_used = any(row.get("label") == old_label for row in rows)
                        data["cover_selected_key_labels"] = list(dict.fromkeys([
                            *[value for value in selected if value != old_label or still_used],
                            replacement["label"],
                        ]))
            else:
                data[key_name] = _merge_api_key_records(
                    on_disk.get(key_name), data.get(key_name),
                    getattr(settings, "_observed_api_keys", {}).get(key_name),
                )
        if replacement and replacement["field"] == "youtube_api_key_protected":
            old_secret = unprotect(on_disk.get("youtube_api_key_protected", ""))
            revision = hashlib.sha256(f"{old_secret}\0YouTube Data API".encode()).hexdigest()
            if revision != replacement["revision"]:
                raise ValueError("Ключ изменён. Обновите список и откройте его заново.")
            data["youtube_api_key_protected"] = protect(replacement["secret"])
            data["youtube_api_enabled"] = on_disk.get("youtube_api_enabled", True)
        elif hasattr(settings, "_observed_youtube_key"):
            observed = unprotect(settings._observed_youtube_key)
            disk_secret = unprotect(on_disk.get("youtube_api_key_protected", ""))
            if settings.youtube_api_key == observed and disk_secret != observed:
                data["youtube_api_key_protected"] = on_disk.get("youtube_api_key_protected", "")
                data["youtube_api_enabled"] = on_disk.get("youtube_api_enabled", True)
        if (not replacement and hasattr(settings, "_observed_cover_key_labels")
                and settings.cover_selected_key_labels == settings._observed_cover_key_labels):
            data["cover_selected_key_labels"] = on_disk.get("cover_selected_key_labels", [])
        tombstones = {
            str(value).strip()
            for value in [*(on_disk.get("cover_queue_tombstones") or []), *(data.get("cover_queue_tombstones") or [])]
            if str(value).strip()
        }
        data["cover_queue_tombstones"] = sorted(tombstones)[-10000:]
        # A cover queue is normally merged so an independent worker cannot
        # erase it with a stale empty Settings instance.  The explicit
        # confirmed release reset is the sole exception: preserving its old
        # rows would make the UI appear to delete nothing and could revive the
        # prior session through emergency backup recovery.
        if "cover_queue" in allowed_empty_fields:
            data["cover_queue"] = list(data.get("cover_queue") or [])
        else:
            data["cover_queue"] = _merge_cover_queue(
                on_disk.get("cover_queue"), data.get("cover_queue"), tombstones=tombstones,
            )
        deleted_production_ids = {
            str(value).strip() for value in [
                *(on_disk.get("idea_deleted_production_ids") or []),
                *(data.get("idea_deleted_production_ids") or []),
            ] if str(value).strip()
        }
        data["idea_deleted_production_ids"] = sorted(deleted_production_ids)[-10000:]
        data["idea_production_items"] = [
            item for item in data.get("idea_production_items", [])
            if not isinstance(item, dict) or str(item.get("id", "")).strip() not in deleted_production_ids
        ]
        deleted_scenario_titles = {
            " ".join(str(value).split()).casefold() for value in [
                *(on_disk.get("deleted_scenario_titles") or []),
                *(data.get("deleted_scenario_titles") or []),
            ] if str(value).strip()
        }
        data["deleted_scenario_titles"] = sorted(deleted_scenario_titles)[-10000:]
        deleted_scenario_production_ids = {
            str(value).strip() for value in [
                *(on_disk.get("deleted_scenario_production_ids") or []),
                *(data.get("deleted_scenario_production_ids") or []),
            ] if str(value).strip()
        }
        data["deleted_scenario_production_ids"] = sorted(deleted_scenario_production_ids)[-10000:]
        _archive_pre_write_settings(path, raw_on_disk)
        # A unique temporary name prevents a status-poll bridge call from
        # colliding with the long montage worker's old ``settings.tmp`` file.
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            deadline = time.monotonic() + 8.0
            while True:
                try:
                    os.replace(temporary, path)
                    # Remember the object's inputs, not the merged disk values:
                    # a running preparation must keep its captured parameters,
                    # and repeated progress saves must still count as unchanged.
                    _remember_montage_reuse_preferences(settings)
                    settings._edited_montage_reuse = set()
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.10)
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass


def delete_session_profile(session: ChromeSession):
    profile = session.profile_dir.resolve()
    root = sessions_root().resolve()
    if profile.parent != root:
        raise ValueError("Некорректная папка профиля Chrome")
    if profile.exists():
        shutil.rmtree(profile)
