from __future__ import annotations

import heapq
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .footage import VIDEO_EXTENSIONS, FootageItem, tokenize

IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"
EMBEDDING_DIM = 512

# One-time semantic pass used by the Footage screen's "Улучшить ИИ-индекс"
# action. It uses already stored CLIP vectors: no source video is decoded
# again and no external API tokens are spent.
SEMANTIC_TAG_QUERIES: tuple[tuple[str, str], ...] = (
    # Distinct military labels are deliberately narrower than a generic
    # "war" tag.  They let the montage choose a relevant action for a
    # frontline, offensive, armour or strike report without substituting a
    # Kremlin office or a decorative soldier portrait.
    ("frontline-combat", "real frontline battlefield trenches infantry soldiers in combat zone"),
    ("offensive-advance", "soldiers advancing military offensive infantry moving through battlefield"),
    ("soldiers-patrol", "soldiers patrol checkpoint infantry military unit walking"),
    ("military-vehicles", "tanks armored vehicles armored personnel carrier military convoy"),
    ("artillery-fire", "artillery firing howitzer rocket launcher military position"),
    ("missile-air-defense", "missile launcher air defense radar military rocket system"),
    ("missile-strike", "missile launch rocket strike explosion smoke military attack"),
    ("military-drone", "military drone UAV reconnaissance drone battlefield operator"),
    ("military-logistics", "military trucks supplies ammunition convoy soldiers logistics"),
    ("war-action", "battle strike shelling explosion combat damaged battlefield"),
    ("emergency-aftermath", "firefighters emergency workers smoke fire ruined buildings rescue"),
    ("civilian-evacuation", "evacuation civilians refugees people carrying bags emergency transport"),
    ("protest-crowd", "large street protest crowd people with placards flags banners rally"),
    ("workers-strike", "workers labor strike picket line factory gate protest banners"),
    ("public-unrest-police", "street unrest crowd police barriers emergency vehicles demonstration"),
    ("migrant-border", "migrants border crossing checkpoint fence border guards people with luggage"),
    ("refugee-transport", "refugee evacuation buses families luggage humanitarian aid"),
    ("political-office", "Kremlin government office politician press conference meeting room"),
    ("russia-government-moscow", "Moscow Kremlin Russian government officials meeting press conference"),
    ("iran-government-tehran", "Tehran Iran government officials Iranian flags political meeting"),
    ("armenia-government-yerevan", "Yerevan Armenia government officials Armenian flags political meeting"),
    ("azerbaijan-government-baku", "Baku Azerbaijan government officials Azerbaijani flags political meeting"),
    ("us-government-washington", "Washington DC White House United States government officials press briefing"),
    ("ukraine-government-kyiv", "Kyiv Ukraine government officials parliament presidential administration"),
    ("eu-institutions", "Brussels European Union parliament commission flags government meeting"),
    ("nato-alliance", "NATO headquarters alliance flags military officials Brussels meeting"),
    ("cybersecurity-network", "cyber security operations computer networks servers monitoring screens data center"),
    ("economic-sanctions", "economic sanctions finance banking trade restrictions government business markets"),
    ("negotiations", "diplomatic negotiations leaders conference table journalists cameras"),
    ("diplomatic-negotiations", "diplomatic negotiations summit leaders conference table"),
    ("parliament-government", "parliament government chamber government building political podium"),
    ("press-conference", "politician press conference podium microphones journalists cameras"),
    ("oil-tanker-port", "oil tanker cargo ship port cranes Persian Gulf sea"),
    ("oil-pipeline-refinery", "oil refinery pipeline fuel tanks energy industrial complex"),
    ("port-logistics", "seaport cargo cranes containers dock workers cargo ship logistics"),
    ("energy-infrastructure", "oil refinery power plant damaged energy infrastructure industrial facility"),
    ("markets-trading", "stock market trading screens money finance exchange business charts"),
    ("factory-industry", "industrial factory manufacturing assembly line machinery workers"),
    ("cargo-warehouse", "warehouse cargo containers forklifts trucks logistics distribution center"),
    ("aviation-airport", "airport runway passenger aircraft airplane terminal aviation"),
    ("rail-metro", "railway train metro subway station public transport passengers"),
    ("city-urban", "city streets skyline traffic buildings generic urban documentary b roll"),
    ("agriculture-farming", "potato harvest farming tractor combine wheat field agricultural workers"),
    ("healthcare-hospital", "hospital doctors nurses ambulance healthcare medical emergency room"),
    ("weather-disaster", "flood storm hurricane wildfire natural disaster extreme weather damage"),
    ("technology-datacenter", "data center servers semiconductor chips technology manufacturing computers"),
    ("documentary-neutral", "safe neutral documentary context everyday people buildings landscape b roll"),
)
SEMANTIC_TAG_LABELS = frozenset(label for label, _query in SEMANTIC_TAG_QUERIES)
SEMANTIC_INDEX_VERSION = 7

SCREEN_TEXT_CLASSIFIER_VERSION = 5
# Restore the NewsFlow 2.1.136 contract: ordinary Cyrillic/Russian lettering is
# allowed. Montage blocks prominent English/Latin lettering and, separately,
# full-screen title/interstitial slates in any language.
_SCREEN_TEXT_ENGLISH_QUERIES = (
    "readable English or Latin alphabet typography over natural video footage: captions subtitles lower third headline ticker labels or text overlay",
    "large prominent single English or Latin alphabet word or short phrase used as a title graphic banner centered overlay or lower third over video footage",
    "sign billboard poster computer screen or document where readable English or Latin alphabet writing is a dominant visible element",
)
_SCREEN_TEXT_INTERSTITIAL_QUERIES = (
    "full screen title card interstitial educational slate bumper graphic with large centered text or branding",
    "full screen program title explainer slate logo bumper presentation slide instead of natural video footage",
    "full screen Russian or Ukrainian Cyrillic title card educational interstitial slate with large centered text",
)
_SCREEN_TEXT_POSITIVE_QUERIES = (
    *_SCREEN_TEXT_ENGLISH_QUERIES,
    *_SCREEN_TEXT_INTERSTITIAL_QUERIES,
)
_SCREEN_TEXT_NEGATIVE_QUERIES = (
    "natural documentary video frame without readable English or Latin alphabet captions; Cyrillic writing may be present",
    "natural news b roll with people buildings vehicles and no readable English overlay or full screen title card",
    "clean studio presenter interview or press conference shot with no readable English Latin alphabet overlay lower third headline or title graphic",
    "real world footage with Russian or Ukrainian Cyrillic writing but no readable English Latin alphabet overlay",
)
_SCREEN_TEXT_SAFE_MARGIN = 0.015
_SCREEN_TEXT_OBVIOUS_MARGIN = 0.060
SCREEN_ELIGIBILITY_SAFE = "SAFE"
SCREEN_ELIGIBILITY_UNCERTAIN = "UNCERTAIN"
SCREEN_ELIGIBILITY_BLOCKED = "BLOCKED"


# A montage batch creates several ClipIndex instances (one per worker).  The
# actual footage vectors, however, are the same SQLite rows for every worker.
# Keeping that immutable snapshot in process memory avoids reading and
# decoding tens of thousands of vectors once *per scene* and once *per job*.
_SHARED_MODELS: dict[str, tuple[object, object]] = {}
_SHARED_MODELS_LOCK = threading.RLock()
_TEXT_EMBED_LOCK = threading.RLock()
_SEARCH_CORPORA: dict[str, _SearchCorpus] = {}
_SEARCH_CORPORA_LOCK = threading.RLock()


@dataclass(frozen=True)
class _SearchCorpus:
    """Decoded, read-only representation of the active rows in an index."""

    fingerprint: tuple[tuple[int, int], ...]
    items: tuple[FootageItem, ...]
    vectors: object
    path_keys: tuple[str, ...]
    durations: tuple[float, ...]
    widths: tuple[int, ...]
    heights: tuple[int, ...]
    semantic_confidences: tuple[float, ...]
    source_families: tuple[str, ...]
    used_counts: object
    ratings: object


@dataclass
class IndexProgress:
    total: int
    processed: int
    indexed: int
    skipped: int
    failed: int
    current: str = ""
    stage: str = "scan"
    removed: int = 0


@dataclass(frozen=True)
class ClipMetadata:
    path: str
    size: int
    mtime_ns: int
    duration: float
    width: int
    height: int
    fps: float
    source_family: str
    english_text: int
    semantic_scores: dict[str, float]


@dataclass
class SearchHit:
    item: FootageItem
    score: float
    duration: float = 6.0
    width: int = 0
    height: int = 0
    semantic_confidence: float = 0.0
    source_family: str = ""


def discover_video_paths(folders: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for raw in folders:
        folder = Path(raw).expanduser()
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.casefold() in VIDEO_EXTENSIONS:
                resolved = path.resolve()
                found[str(resolved).casefold()] = resolved
    return sorted(found.values(), key=lambda value: str(value).casefold())


def source_family_identity_text(path_text: str, source_url: str = "") -> str:
    """Return canonical family identity with pure string operations."""
    if source_url.strip():
        return f"url::{source_url.strip().casefold()}"
    candidate = str(path_text).replace("\\", "/").casefold()
    if "/" in candidate:
        parent, name = candidate.rsplit("/", 1)
        parent = parent or "/"
    else:
        parent, name = ".", candidate
    stem_base, separator, _suffix = name.rpartition(".")
    stem = stem_base if separator and stem_base else name
    trimmed_parent = parent.rstrip("/")
    parent_name = trimmed_parent.rsplit("/", 1)[-1] if trimmed_parent else "/"
    if parent_name.endswith("_slices"):
        return f"path::{parent}"
    if parent_name and re.fullmatch(rf"{re.escape(parent_name)}_\d{{4}}", stem):
        return f"path::{parent}"
    if re.fullmatch(r"clip_[a-z0-9]{6}_\d{3}", stem):
        return f"path::{parent}"
    stem = re.sub(r"(?:[_\-\s]+(?:clip|slice|cut|part|segment)[_\-\s]*\d+)$", "", stem)
    return f"path::{parent}::{stem}"


def source_family_identity(path: str | Path, source_url: str = "") -> str:
    """Return deterministic original-source identity without filesystem I/O."""
    return source_family_identity_text(str(path), source_url)


class ClipIndex:
    """SQLite-backed multimodal index designed for tens of thousands of short clips."""

    def __init__(self, db_path: Path, model_cache: Path | None = None, embedder_factory=None):
        self.db_path = Path(db_path)
        self.model_cache = Path(model_cache or self.db_path.parent / "models")
        self.embedder_factory = embedder_factory
        self._image_embedder = None
        self._text_embedder = None
        self._screen_text_state_cache: dict[tuple[str, bool], str] = {}
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _create_schema(self):
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    path TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    duration REAL NOT NULL DEFAULT 6,
                    width INTEGER NOT NULL DEFAULT 0,
                    height INTEGER NOT NULL DEFAULT 0,
                    fps REAL NOT NULL DEFAULT 0,
                    source_family TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'local',
                    source_url TEXT NOT NULL DEFAULT '',
                    license TEXT NOT NULL DEFAULT 'user-library',
                    tags TEXT NOT NULL DEFAULT '[]',
                    embedding BLOB,
                    model TEXT NOT NULL DEFAULT '',
                    indexed_at REAL NOT NULL DEFAULT 0,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    last_used REAL NOT NULL DEFAULT 0,
                    rating INTEGER NOT NULL DEFAULT 0,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    -- 0 = not checked, 1 = English lettering detected,
                    -- -1 = checked and safe. The value stays across restarts.
                    english_text INTEGER NOT NULL DEFAULT 0,
                    english_text_version INTEGER NOT NULL DEFAULT 0,
                    semantic_version INTEGER NOT NULL DEFAULT 0,
                    semantic_scores TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_clips_mtime ON clips(mtime_ns, size);
                CREATE INDEX IF NOT EXISTS idx_clips_source ON clips(source);
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(clips)")}
            if "rating" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
            if "disabled" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0")
            if "english_text" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN english_text INTEGER NOT NULL DEFAULT 0")
            if "english_text_version" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN english_text_version INTEGER NOT NULL DEFAULT 0")
            if "semantic_version" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN semantic_version INTEGER NOT NULL DEFAULT 0")
            if "fps" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN fps REAL NOT NULL DEFAULT 0")
            if "source_family" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN source_family TEXT NOT NULL DEFAULT ''")
            if "semantic_scores" not in columns:
                connection.execute("ALTER TABLE clips ADD COLUMN semantic_scores TEXT NOT NULL DEFAULT '{}'")

    def count(self, embedded_only: bool = False) -> int:
        where = " WHERE embedding IS NOT NULL" if embedded_only else ""
        with self._connect() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM clips{where}").fetchone()[0])

    def model_ready(self) -> bool:
        return self._image_embedder is not None and self._text_embedder is not None

    def _models(self):
        if self._image_embedder is None or self._text_embedder is None:
            if self.embedder_factory:
                self._image_embedder, self._text_embedder = self.embedder_factory()
            else:
                # Windowed PyInstaller builds have no stderr; tqdm would crash while models download.
                # The same CLIP model is used by the indexer and all montage
                # workers.  Constructing it for every worker is expensive and
                # can exhaust RAM/VRAM, so it is shared per model-cache path.
                cache = str(self.model_cache.resolve())
                with _SHARED_MODELS_LOCK:
                    shared = _SHARED_MODELS.get(cache)
                    if shared is None:
                        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
                        os.environ.setdefault("TQDM_DISABLE", "1")
                        from fastembed import ImageEmbedding, TextEmbedding
                        threads = max(4, min(16, (os.cpu_count() or 8) // 2))
                        shared = (
                            ImageEmbedding(IMAGE_MODEL, cache_dir=cache, threads=threads, cuda="auto"),
                            TextEmbedding(TEXT_MODEL, cache_dir=cache, threads=threads, cuda="auto"),
                        )
                        _SHARED_MODELS[cache] = shared
                self._image_embedder, self._text_embedder = shared
        return self._image_embedder, self._text_embedder

    def _cache_key(self) -> str:
        return str(self.db_path.resolve()).casefold()

    def _database_fingerprint(self) -> tuple[tuple[int, int], ...]:
        """Changes whenever SQLite commits data, including WAL transactions."""
        parts = (self.db_path, self.db_path.with_name(self.db_path.name + "-wal"))
        fingerprint = []
        for path in parts:
            try:
                stat = path.stat()
                fingerprint.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                fingerprint.append((0, 0))
        return tuple(fingerprint)

    def _invalidate_search_cache(self) -> None:
        self._screen_text_state_cache.clear()
        with _SEARCH_CORPORA_LOCK:
            _SEARCH_CORPORA.pop(self._cache_key(), None)

    def _search_corpus(self) -> _SearchCorpus:
        """Load active vectors once, then reuse them for all scene queries."""
        import numpy as np

        key = self._cache_key()
        fingerprint = self._database_fingerprint()
        with _SEARCH_CORPORA_LOCK:
            cached = _SEARCH_CORPORA.get(key)
            if cached and cached.fingerprint == fingerprint:
                return cached
            # Hold the lock while loading.  This intentionally lets the first
            # montage worker prepare the shared data, while the remaining
            # workers reuse it instead of issuing the same 15k-row query.
            with self._connect() as connection:
                rows = connection.execute(
                    """SELECT path,name,source,source_url,license,tags,embedding,duration,width,height,source_family,
                              semantic_scores,
                              used_count,rating FROM clips
                       WHERE embedding IS NOT NULL AND disabled=0
                         AND NOT (english_text=1 AND english_text_version>=?)"""
                    + " ORDER BY path",
                    (SCREEN_TEXT_CLASSIFIER_VERSION,),
                ).fetchall()
            items: list[FootageItem] = []
            vectors = []
            path_keys: list[str] = []
            durations: list[float] = []
            widths: list[int] = []
            heights: list[int] = []
            semantic_confidences: list[float] = []
            source_families: list[str] = []
            used_counts: list[int] = []
            ratings: list[int] = []
            vector_size = 0
            for row in rows:
                vector = np.frombuffer(row["embedding"], dtype=np.float32)
                if vector.size == 0:
                    continue
                if vector_size == 0:
                    vector_size = vector.size
                if vector.size != vector_size:
                    continue
                items.append(FootageItem(row["path"], row["name"], row["source"], row["source_url"],
                                         row["license"], json.loads(row["tags"] or "[]")))
                source_families.append(
                    row["source_family"] or source_family_identity(row["path"], row["source_url"])
                )
                vectors.append(vector)
                path_keys.append(row["path"].casefold())
                durations.append(float(row["duration"]))
                widths.append(int(row["width"]))
                heights.append(int(row["height"]))
                try:
                    stored_scores = json.loads(row["semantic_scores"] or "{}")
                    semantic_confidences.append(max((float(value) for value in stored_scores.values()), default=0.0))
                except (TypeError, ValueError):
                    semantic_confidences.append(0.0)
                used_counts.append(int(row["used_count"] or 0))
                ratings.append(int(row["rating"] or 0))
            matrix = np.vstack(vectors).astype(np.float32, copy=False) if vectors else np.empty((0, 0), dtype=np.float32)
            corpus = _SearchCorpus(
                fingerprint=fingerprint,
                items=tuple(items), vectors=matrix, path_keys=tuple(path_keys),
                durations=tuple(durations), widths=tuple(widths), heights=tuple(heights),
                semantic_confidences=tuple(semantic_confidences),
                source_families=tuple(source_families),
                used_counts=np.asarray(used_counts, dtype=np.float32),
                ratings=np.asarray(ratings, dtype=np.float32),
            )
            _SEARCH_CORPORA[key] = corpus
            return corpus

    def _query_vectors(self, queries: list[str]):
        """Embed several text queries together when the backend supports it."""
        import numpy as np

        _, text_model = self._models()
        if len(queries) == 1:
            with _TEXT_EMBED_LOCK:
                value = next(iter(text_model.query_embed(queries[0])))
            return np.asarray([self._normalize(value)], dtype=np.float32)
        try:
            with _TEXT_EMBED_LOCK:
                values = list(text_model.query_embed(queries))
            if len(values) == len(queries):
                return np.asarray([self._normalize(value) for value in values], dtype=np.float32)
        except (TypeError, ValueError):
            pass
        # Compatibility fallback for older FastEmbed adapters and test doubles.
        with _TEXT_EMBED_LOCK:
            return np.asarray([
                self._normalize(next(iter(text_model.query_embed(query)))) for query in queries
            ], dtype=np.float32)

    def _text_model_is_cached(self) -> bool:
        """Whether semantic search can start without a network download.

        Montage planning is an interactive action.  A ready footage index must
        not unexpectedly spend minutes downloading FastEmbed models merely to
        embed a query.  Indexing is the deliberate maintenance action that
        may populate this cache.  Test embedders are already in memory and do
        not need a filesystem model cache.
        """
        if self.embedder_factory is not None or self._text_embedder is not None:
            return True
        model_root = self.model_cache / "models--Qdrant--clip-ViT-B-32-text"
        try:
            return (model_root / "refs" / "main").is_file() and any(
                path.is_file() and path.stat().st_size > 1_000_000
                for path in (model_root / "blobs").glob("*")
            )
        except OSError:
            return False

    @staticmethod
    def _metadata_tokens(item: FootageItem) -> set[str]:
        return set(tokenize(" ".join((
            item.name,
            *(tag.replace("-", " ") for tag in item.tags),
            *Path(item.path).parts[-4:],
        ))))

    def _search_many_metadata(self, queries: list[str], corpus: _SearchCorpus,
                              limit: int, excluded: set[str],
                              existence_cache: dict[str, bool]) -> list[list[SearchHit]]:
        """Fast local fallback used only until the text model is available."""
        item_tokens = [self._metadata_tokens(item) for item in corpus.items]
        result: list[list[SearchHit]] = []
        take = max(1, int(limit))
        for query in queries:
            query_tokens = set(tokenize(query))
            def scores(wanted=query_tokens):
                for position, tokens in enumerate(item_tokens):
                    if corpus.path_keys[position] in excluded:
                        continue
                    overlap = len(wanted & tokens)
                    # Prefer specific name/tag matches, retain ratings and
                    # avoid repeated clips even while semantic mode is
                    # unavailable. Zero-overlap rows remain valid in a small
                    # library, but never justify sorting all 29k candidates.
                    score = (overlap * 1.0 + (overlap / max(1, len(wanted)))
                             - min(0.12, float(corpus.used_counts[position]) * 0.008)
                             + max(-0.12, min(0.12, float(corpus.ratings[position]) * 0.025)))
                    yield -score, corpus.path_keys[position], position
            candidate_count = min(len(corpus.items), max(32, take * 4))
            while True:
                ranked = heapq.nsmallest(candidate_count, scores())
                positions = self._valid_ranked_positions(
                    (position for _score, _path_key, position in ranked),
                    corpus, take, excluded, existence_cache,
                )
                if len(positions) >= take or candidate_count >= len(corpus.items):
                    break
                candidate_count = min(len(corpus.items), candidate_count * 2)
            score_by_position = {position: -negative_score
                                 for negative_score, _path_key, position in ranked}
            result.append([
                SearchHit(corpus.items[position], score_by_position[position], corpus.durations[position],
                          corpus.widths[position], corpus.heights[position],
                          corpus.semantic_confidences[position], corpus.source_families[position])
                for position in positions
            ])
        return result

    @staticmethod
    def _valid_ranked_positions(ranked_positions: Iterable[int], corpus: _SearchCorpus, limit: int,
                                excluded: set[str], existence_cache: dict[str, bool]) -> list[int]:
        """Validate only ranked candidates needed to fill top-K results."""
        valid: list[int] = []
        for position in ranked_positions:
            path_key = corpus.path_keys[position]
            if path_key in excluded:
                continue
            if path_key not in existence_cache:
                existence_cache[path_key] = Path(corpus.items[position].path).is_file()
            if not existence_cache[path_key]:
                continue
            valid.append(position)
            if len(valid) >= limit:
                break
        return valid

    @staticmethod
    def _signature(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns

    def _needs_index(self, connection, path: Path) -> bool:
        row = connection.execute(
            "SELECT size, mtime_ns, embedding, model FROM clips WHERE path = ?", (str(path),)
        ).fetchone()
        if row is None:
            return True
        size, mtime_ns = self._signature(path)
        return not (row["size"] == size and row["mtime_ns"] == mtime_ns
                    and row["embedding"] is not None and row["model"] == IMAGE_MODEL)

    @staticmethod
    def _sample_frames(path: Path, samples: int = 3):
        import cv2
        from PIL import Image
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise ValueError("Видео не открывается")
        frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        sample_count = max(1, int(samples))
        if sample_count <= 3:
            fractions = (0.15, 0.50, 0.85)[:sample_count]
        else:
            fractions = tuple(
                0.03 + (0.94 * index / max(1, sample_count - 1))
                for index in range(sample_count)
            )
        positions = [int(frame_count * value) for value in fractions]
        images = []
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, min(frame_count - 1, position))
            ok, frame = capture.read()
            if ok:
                images.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        capture.release()
        if not images:
            raise ValueError("Не удалось извлечь кадры")
        return images, frame_count / max(fps, 0.001), width, height, fps

    @staticmethod
    def _normalize(vector):
        import numpy as np
        value = np.asarray(vector, dtype=np.float32)
        norm = float(np.linalg.norm(value))
        return value / norm if norm else value

    def index_folders(self, folders: list[str], progress: Callable[[IndexProgress], None] | None = None,
                      cancel: threading.Event | None = None, batch_clips: int = 16) -> IndexProgress:
        import numpy as np
        paths = discover_video_paths(folders)
        state = IndexProgress(total=len(paths), processed=0, indexed=0, skipped=0, failed=0,
                              removed=self.remove_missing())
        if progress:
            progress(state)
        with self._connect() as connection:
            pending = [path for path in paths if self._needs_index(connection, path)]
        state.skipped = len(paths) - len(pending)
        state.processed = state.skipped
        if not pending:
            state.stage = "complete"
            if progress:
                progress(state)
            return state
        image_model, _ = self._models()
        screen_query_vectors = None
        if self.embedder_factory is None and self._text_model_is_cached():
            try:
                screen_query_vectors = self._query_vectors([
                    *_SCREEN_TEXT_POSITIVE_QUERIES, *_SCREEN_TEXT_NEGATIVE_QUERIES,
                ])
            except (OSError, RuntimeError, ValueError):
                screen_query_vectors = None
        for offset in range(0, len(pending), max(1, batch_clips)):
            if cancel and cancel.is_set():
                state.stage = "cancelled"
                break
            batch_paths = pending[offset:offset + batch_clips]
            flat_images, groups, metadata = [], [], []
            for path in batch_paths:
                state.current = path.name
                try:
                    sampled = self._sample_frames(path)
                    images, duration, width, height = sampled[:4]
                    fps = float(sampled[4]) if len(sampled) > 4 else 0.0
                    start = len(flat_images)
                    flat_images.extend(images)
                    groups.append((path, start, len(images)))
                    metadata.append((duration, width, height, fps))
                except Exception:  # noqa: BLE001 - one unreadable codec must not abort the batch
                    state.failed += 1
                    state.processed += 1
            if flat_images:
                embeddings = list(image_model.embed(flat_images, batch_size=min(32, len(flat_images))))
                rows = []
                for group_index, (path, start, length) in enumerate(groups):
                    frame_vectors = [
                        self._normalize(value) for value in embeddings[start:start + length]
                    ]
                    vector = self._normalize(np.mean(frame_vectors, axis=0))
                    obvious_text = (
                        self._screen_text_obvious_from_vectors(frame_vectors, screen_query_vectors)
                        if screen_query_vectors is not None else False
                    )
                    # Three indexing frames block only high-confidence text
                    # for free. Ambiguous/clean-looking clips remain unchecked
                    # until the strict five-frame selection gate verifies them.
                    indexed_english = 1 if obvious_text else 0
                    indexed_english_version = (
                        SCREEN_TEXT_CLASSIFIER_VERSION if indexed_english == 1 else 0
                    )
                    try:
                        size, mtime_ns = self._signature(path)
                    except OSError:
                        state.failed += 1
                        state.processed += 1
                        continue
                    duration, width, height, fps = metadata[group_index]
                    tags = sorted(tokenize(" ".join(path.parts[-4:])))
                    rows.append((
                        str(path), path.name, size, mtime_ns, duration, width, height, fps,
                        source_family_identity(path), json.dumps(tags, ensure_ascii=False),
                        vector.tobytes(), IMAGE_MODEL, time.time(),
                        indexed_english, indexed_english_version,
                    ))
                with self._lock, self._connect() as connection:
                    connection.executemany(
                        """
                        INSERT INTO clips(path,name,size,mtime_ns,duration,width,height,fps,source_family,
                                          tags,embedding,model,indexed_at,english_text,english_text_version)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(path) DO UPDATE SET name=excluded.name,size=excluded.size,
                        mtime_ns=excluded.mtime_ns,duration=excluded.duration,width=excluded.width,
                        height=excluded.height,fps=excluded.fps,
                        source_family=CASE WHEN clips.source_url<>'' THEN clips.source_family ELSE excluded.source_family END,
                        tags=excluded.tags,embedding=excluded.embedding,model=excluded.model,
                        indexed_at=excluded.indexed_at,english_text=excluded.english_text,
                        english_text_version=excluded.english_text_version,
                        semantic_version=0,semantic_scores='{}'
                        """, rows)
                self._invalidate_search_cache()
                state.indexed += len(rows)
                state.processed += len(rows)
            state.stage = "embedding"
            if progress:
                progress(state)
        if state.stage != "cancelled":
            state.stage = "complete"
        if progress:
            progress(state)
        return state

    def enrich_semantic_tags(self, progress: Callable[[IndexProgress], None] | None = None,
                              cancel: threading.Event | None = None, batch_clips: int = 384) -> IndexProgress:
        """Add conservative CLIP labels without reopening the source videos.

        Existing vectors are compared against a small fixed visual taxonomy.
        This is an explicit maintenance pass: ordinary indexing stays fast and
        processes only new or changed clips, while this can improve an already
        built library without repeatedly decoding 20,000 source files.
        """
        import numpy as np

        with self._connect() as connection:
            total = int(connection.execute(
                "SELECT COUNT(*) FROM clips WHERE embedding IS NOT NULL AND semantic_version < ?",
                (SEMANTIC_INDEX_VERSION,),
            ).fetchone()[0])
        state = IndexProgress(total=total, processed=0, indexed=0, skipped=0, failed=0, stage="semantic")
        if progress:
            progress(state)
        if not total:
            state.stage = "complete"
            if progress:
                progress(state)
            return state

        labels = [label for label, _query in SEMANTIC_TAG_QUERIES]
        queries = [query for _label, query in SEMANTIC_TAG_QUERIES]
        query_vectors = self._query_vectors(queries)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT path, tags, embedding FROM clips WHERE embedding IS NOT NULL AND semantic_version < ? ORDER BY path",
                (SEMANTIC_INDEX_VERSION,),
            ).fetchall()

        for offset in range(0, len(rows), max(1, int(batch_clips))):
            if cancel and cancel.is_set():
                state.stage = "cancelled"
                break
            batch = rows[offset:offset + max(1, int(batch_clips))]
            updates = []
            for row in batch:
                try:
                    vector = np.frombuffer(row["embedding"], dtype=np.float32)
                    if vector.size != query_vectors.shape[1]:
                        state.failed += 1
                        state.processed += 1
                        continue
                    scores = query_vectors @ vector
                    order = np.argsort(scores)[::-1]
                    # Labels remain advisory. They complement, but never
                    # overwrite, the user's folder and file-name metadata.
                    selected = [(labels[int(index)], float(scores[int(index)]))
                                for index in order[:3] if float(scores[int(index)]) >= 0.18]
                    semantic = [label for label, _score in selected]
                    confidence = {label: round(score, 6) for label, score in selected}
                    try:
                        tags = [str(value) for value in json.loads(row["tags"] or "[]") if value]
                    except (TypeError, ValueError):
                        tags = []
                    # Generated labels are versioned metadata, not user
                    # folder tags. Replace older generated labels so future
                    # ranking follows the current rule set without retaining
                    # stale or overly generic classifications.
                    tags = sorted(dict.fromkeys([
                        *(tag for tag in tags if tag not in SEMANTIC_TAG_LABELS), *semantic
                    ]))
                    updates.append((json.dumps(tags, ensure_ascii=False),
                                    json.dumps(confidence, ensure_ascii=False),
                                    SEMANTIC_INDEX_VERSION, row["path"]))
                    state.indexed += 1
                    state.processed += 1
                    state.current = Path(row["path"]).name
                except Exception:  # noqa: BLE001 - malformed persisted row is counted and isolated
                    state.failed += 1
                    state.processed += 1
            if updates:
                with self._lock, self._connect() as connection:
                    connection.executemany(
                        "UPDATE clips SET tags=?, semantic_scores=?, semantic_version=? WHERE path=?", updates
                    )
                self._invalidate_search_cache()
            if progress:
                progress(state)
        if state.stage != "cancelled":
            state.stage = "complete"
        if progress:
            progress(state)
        return state

    def semantic_status(self) -> dict[str, int]:
        """Return compact deep-index currency without reopening source media."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                       SUM(CASE WHEN embedding IS NOT NULL AND semantic_version=? THEN 1 ELSE 0 END) AS current,
                       SUM(CASE WHEN embedding IS NOT NULL AND semantic_version<>? THEN 1 ELSE 0 END) AS outdated
                     FROM clips""",
                (SEMANTIC_INDEX_VERSION, SEMANTIC_INDEX_VERSION),
            ).fetchone()
        return {
            "version": SEMANTIC_INDEX_VERSION,
            "current": int(row["current"] or 0),
            "outdated": int(row["outdated"] or 0),
        }

    def add_item(self, item: FootageItem):
        path = Path(item.path)
        size, mtime_ns = self._signature(path) if path.exists() else (0, 0)
        family = source_family_identity(path, item.source_url)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO clips(path,name,size,mtime_ns,source,source_url,license,tags,source_family)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET source=excluded.source,source_url=excluded.source_url,
                license=excluded.license,tags=excluded.tags,source_family=excluded.source_family
                """,
                (item.path, item.name, size, mtime_ns, item.source, item.source_url, item.license,
                 json.dumps(item.tags or [], ensure_ascii=False), family),
            )
        self._invalidate_search_cache()

    def all_items(self, limit: int | None = None, exclude_english_text: bool = False) -> list[FootageItem]:
        # 2.1.136 semantics: exclude only a current positive block. Stale and
        # UNCERTAIN rows remain searchable and can be verified lazily.
        text_filter = (" WHERE NOT (english_text=1 AND english_text_version>=?)"
                       if exclude_english_text else "")
        query = ("SELECT path,name,source,source_url,license,tags,source_family FROM clips"
                 + text_filter + " ORDER BY name")
        params = (SCREEN_TEXT_CLASSIFIER_VERSION,) if exclude_english_text else ()
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        current = [FootageItem(row["path"], row["name"], row["source"], row["source_url"], row["license"],
                               json.loads(row["tags"] or "[]"))
                   for row in rows if Path(row["path"]).is_file()]
        return current[:limit] if limit is not None else current

    def metadata(self, path: str | Path) -> ClipMetadata | None:
        """Expose persisted media/freshness identity for retrieval and QA."""
        with self._connect() as connection:
            row = connection.execute(
                """SELECT path,size,mtime_ns,duration,width,height,fps,source_family,english_text,
                            source_url,semantic_scores
                     FROM clips WHERE path=?""",
                (str(Path(path).resolve()),),
            ).fetchone()
        if row is None:
            return None
        try:
            semantic_scores = {str(key): float(value)
                               for key, value in json.loads(row["semantic_scores"] or "{}").items()}
        except (AttributeError, TypeError, ValueError):
            semantic_scores = {}
        return ClipMetadata(
            path=row["path"], size=int(row["size"]), mtime_ns=int(row["mtime_ns"]),
            duration=float(row["duration"]), width=int(row["width"]), height=int(row["height"]),
            fps=float(row["fps"]),
            source_family=row["source_family"] or source_family_identity(row["path"], row["source_url"]),
            english_text=int(row["english_text"]),
            semantic_scores=semantic_scores,
        )

    def cached_media_duration(self, path: str | Path) -> float | None:
        """Return validated indexed duration when the file identity is unchanged.

        Indexing opens and decodes the video already, so repeatedly spawning
        FFprobe for that same ``path + size + mtime`` during every montage is
        pure process-start overhead.  A changed or unindexed file deliberately
        returns ``None`` and continues through the stricter preflight path.
        """
        candidate = Path(path)
        try:
            size, mtime_ns = self._signature(candidate)
        except OSError:
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT size, mtime_ns, duration, embedding FROM clips WHERE path = ?", (str(candidate),)
            ).fetchone()
        if row is None or row["embedding"] is None:
            return None
        if int(row["size"]) != size or int(row["mtime_ns"]) != mtime_ns:
            return None
        duration = float(row["duration"] or 0.0)
        return duration if duration > 0.05 else None

    def search_many(self, visual_queries: Iterable[str], limit: int = 20,
                    exclude: set[str] | None = None) -> list[list[SearchHit]]:
        """Find footage for all scenes of one scenario in a single vector pass.

        The prior implementation fetched and decoded the full SQLite index for
        every scene.  A 7-minute news video can have 70+ scenes, so a library
        of 15k clips was decoded dozens of times.  Here a shared decoded
        corpus is multiplied by all text vectors at once.
        """
        import numpy as np
        queries = [str(query).strip() for query in visual_queries]
        if not queries:
            return []
        # A news narration commonly repeats the same visual context across
        # several adjacent beats.  Text embedding every duplicate query was
        # needlessly the slowest part of parallel planning: a 7-minute video
        # could submit the identical "frontline soldiers" prompt 20+ times.
        # Keep the caller's scene order in the return value, while embedding
        # and ranking each distinct prompt only once.
        unique_queries = list(dict.fromkeys(queries))
        excluded = {value.casefold() for value in (exclude or set())}
        corpus = self._search_corpus()
        if not corpus.items:
            return [[] for _ in queries]
        existence_cache: dict[str, bool] = {}
        if not self._text_model_is_cached():
            return self._search_many_metadata(queries, corpus, limit, excluded, existence_cache)
        query_vectors = self._query_vectors(unique_queries)
        if query_vectors.shape[1] != corpus.vectors.shape[1]:
            return [[] for _ in queries]
        scores = query_vectors @ corpus.vectors.T
        scores = scores - np.minimum(0.12, corpus.used_counts * 0.008) + np.clip(corpus.ratings * 0.025, -0.12, 0.12)
        # Keep vector similarity primary, then add a small bounded fusion
        # bonus from versioned semantic tags and path metadata. This improves
        # broad fallback without turning retrieval into brittle keywords.
        item_tokens = [self._metadata_tokens(item) for item in corpus.items]
        for query_index, query in enumerate(unique_queries):
            query_tokens = set(tokenize(query.replace("-", " ")))
            if not query_tokens:
                continue
            for item_index, tokens in enumerate(item_tokens):
                overlap = len(query_tokens & tokens)
                if overlap:
                    scores[query_index, item_index] += min(0.08, 0.025 * overlap)
        take = min(len(corpus.items), max(1, int(limit)))
        by_query: dict[str, list[SearchHit]] = {}
        for query, row_scores in zip(unique_queries, scores):
            candidate_count = min(len(corpus.items), max(32, take * 4))
            while True:
                if candidate_count >= len(corpus.items):
                    ordered = np.argsort(row_scores, kind="stable")[::-1]
                else:
                    partition = np.argpartition(row_scores, -candidate_count)[-candidate_count:]
                    ordered = partition[np.argsort(row_scores[partition], kind="stable")[::-1]]
                valid_positions = self._valid_ranked_positions(
                    (int(position) for position in ordered), corpus, take, excluded, existence_cache,
                )
                if len(valid_positions) >= take or candidate_count >= len(corpus.items):
                    break
                candidate_count = min(len(corpus.items), candidate_count * 2)
            hits = []
            for index in valid_positions:
                hits.append(SearchHit(corpus.items[index], float(row_scores[index]), corpus.durations[index],
                                      corpus.widths[index], corpus.heights[index],
                                      corpus.semantic_confidences[index], corpus.source_families[index]))
            by_query[query] = hits
        return [list(by_query[query]) for query in queries]

    def search(self, visual_query_en: str, limit: int = 20, exclude: set[str] | None = None) -> list[SearchHit]:
        return self.search_many([visual_query_en], limit=limit, exclude=exclude)[0]

    def score_file(self, path: str | Path, visual_query_en: str) -> float:
        """Score an unindexed preview clip against the same CLIP text space."""
        import numpy as np
        image_model, text_model = self._models()
        sampled = self._sample_frames(Path(path))
        images = sampled[0]
        image_vectors = list(image_model.embed(images, batch_size=len(images)))
        clip_vector = self._normalize(np.mean(image_vectors, axis=0))
        query_vector = self._normalize(next(iter(text_model.query_embed(visual_query_en))))
        return float(np.dot(clip_vector, query_vector))

    def mark_used(self, paths: Iterable[str]):
        now = time.time()
        with self._connect() as connection:
            connection.executemany(
                "UPDATE clips SET used_count=used_count+1,last_used=? WHERE path=?",
                [(now, path) for path in paths],
            )
        self._invalidate_search_cache()

    @staticmethod
    def _screen_text_scores(frame, query_vectors) -> tuple[float, float]:
        import numpy as np

        positive_count = len(_SCREEN_TEXT_POSITIVE_QUERIES)
        positive_vectors = query_vectors[:positive_count]
        negative_vectors = query_vectors[positive_count:]
        positive = max(float(np.dot(frame, vector)) for vector in positive_vectors)
        negative = max(float(np.dot(frame, vector)) for vector in negative_vectors)
        return positive, negative

    @classmethod
    def _screen_text_obvious_from_vectors(cls, frame_vectors, query_vectors) -> bool:
        """Cheap indexing gate: block only unmistakable English/title evidence."""
        return any(
            positive >= negative + _SCREEN_TEXT_OBVIOUS_MARGIN
            for positive, negative in (
                cls._screen_text_scores(frame, query_vectors) for frame in frame_vectors
            )
        )

    @classmethod
    def _screen_text_state_from_vectors(cls, frame_vectors, query_vectors) -> int:
        """Return 1=BLOCKED, -1=SAFE, 0=UNCERTAIN."""
        safe_frames = 0
        total = 0
        for frame in frame_vectors:
            total += 1
            positive, negative = cls._screen_text_scores(frame, query_vectors)
            if positive >= negative + _SCREEN_TEXT_OBVIOUS_MARGIN:
                return 1
            if negative >= positive + _SCREEN_TEXT_SAFE_MARGIN:
                safe_frames += 1
        if total and safe_frames == total:
            return -1
        return 0

    def _screen_text_state(self, path: Path, *, samples: int = 5) -> int:
        """Classify samples without turning ambiguity into a hard block."""
        if not self._text_model_is_cached():
            return 0
        images = self._sample_frames(path, samples=samples)[0]
        image_model, _text_model = self._models()
        frame_vectors = [
            self._normalize(value) for value in image_model.embed(images, batch_size=len(images))
        ]
        query_vectors = self._query_vectors([
            *_SCREEN_TEXT_POSITIVE_QUERIES, *_SCREEN_TEXT_NEGATIVE_QUERIES,
        ])
        return self._screen_text_state_from_vectors(frame_vectors, query_vectors)

    def screen_text_eligibility(self, path: str | Path, *, deep: bool = False) -> str:
        """Return SAFE, UNCERTAIN or BLOCKED for one ranked candidate."""
        candidate = Path(path)
        try:
            resolved = str(candidate.resolve())
        except OSError:
            resolved = str(candidate)
        cache_key = (resolved, bool(deep))
        cached = self._screen_text_state_cache.get(cache_key)
        if cached is not None:
            return cached
        with self._connect() as connection:
            row = connection.execute(
                "SELECT english_text,english_text_version FROM clips WHERE path=?", (resolved,)
            ).fetchone()
        if row is not None and int(row["english_text_version"] or 0) >= SCREEN_TEXT_CLASSIFIER_VERSION:
            persisted = int(row["english_text"])
            if persisted == 1:
                self._screen_text_state_cache[cache_key] = SCREEN_ELIGIBILITY_BLOCKED
                return SCREEN_ELIGIBILITY_BLOCKED
            # A shallow all-clear must not suppress a later deep inspection:
            # sparse lower-thirds and end cards can fall between five samples.
            if persisted == -1 and not deep:
                self._screen_text_state_cache[cache_key] = SCREEN_ELIGIBILITY_SAFE
                return SCREEN_ELIGIBILITY_SAFE
            if not deep:
                self._screen_text_state_cache[cache_key] = SCREEN_ELIGIBILITY_UNCERTAIN
                return SCREEN_ELIGIBILITY_UNCERTAIN
        try:
            state = self._screen_text_state(candidate, samples=11 if deep else 5)
        except (OSError, ValueError):
            state = 0
        if row is not None:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "UPDATE clips SET english_text=?,english_text_version=? WHERE path=?",
                    (state, SCREEN_TEXT_CLASSIFIER_VERSION, resolved),
                )
            if state == 1:
                self._invalidate_search_cache()
        eligibility = (
            SCREEN_ELIGIBILITY_BLOCKED if state == 1
            else SCREEN_ELIGIBILITY_SAFE if state == -1
            else SCREEN_ELIGIBILITY_UNCERTAIN
        )
        self._screen_text_state_cache[(resolved, bool(deep))] = eligibility
        # A BLOCKED verdict remains blocking at either sampling depth.  SAFE is
        # deliberately depth-specific so a deep request can inspect all frames.
        if state == 1:
            self._screen_text_state_cache[(resolved, not bool(deep))] = eligibility
        return eligibility

    def screen_text_safe(self, path: str | Path) -> bool:
        """Compatibility helper: deep-check ambiguity; reject only BLOCKED."""
        return self.screen_text_eligibility(path, deep=True) != SCREEN_ELIGIBILITY_BLOCKED

    def classify_english_screen_text(self) -> dict[str, int]:
        """Persist v4 English/interstitial SAFE/BLOCKED/UNCERTAIN states."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT path FROM clips
                   WHERE english_text_version < ? ORDER BY path""",
                (SCREEN_TEXT_CLASSIFIER_VERSION,),
            ).fetchall()
        if not rows:
            stats = self.screen_text_stats()
            return {"checked": 0, "blocked": stats["blocked"], "safe": stats["safe"],
                    "uncertain": stats["unchecked"]}
        if not self._text_model_is_cached():
            stats = self.screen_text_stats()
            return {"checked": 0, "blocked": stats["blocked"], "safe": stats["safe"],
                    "uncertain": stats["unchecked"]}
        blocked = safe = uncertain = checked = 0
        for row in rows:
            eligibility = self.screen_text_eligibility(row["path"], deep=True)
            checked += 1
            blocked += int(eligibility == SCREEN_ELIGIBILITY_BLOCKED)
            safe += int(eligibility == SCREEN_ELIGIBILITY_SAFE)
            uncertain += int(eligibility == SCREEN_ELIGIBILITY_UNCERTAIN)
        return {"checked": checked, "blocked": blocked, "safe": safe, "uncertain": uncertain}

    def screen_text_stats(self) -> dict[str, int]:
        """Count only current-v4 verdicts; stale v3 blocks become uncertain."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT english_text,english_text_version,COUNT(*) AS amount
                   FROM clips GROUP BY english_text,english_text_version"""
            ).fetchall()
        blocked = safe = unchecked = 0
        for row in rows:
            state = int(row["english_text"])
            version = int(row["english_text_version"] or 0)
            amount = int(row["amount"])
            if version < SCREEN_TEXT_CLASSIFIER_VERSION:
                unchecked += amount
            elif state == 1:
                blocked += amount
            elif state == -1:
                safe += amount
            else:
                unchecked += amount
        return {"blocked": blocked, "safe": safe, "unchecked": unchecked}

    def rate(self, path: str, value: int):
        with self._connect() as connection:
            if value <= -10:
                connection.execute("UPDATE clips SET disabled=1 WHERE path=?", (path,))
            else:
                exact_delta = value * 2 if value > 0 else value
                connection.execute(
                    "UPDATE clips SET rating=MAX(-5,MIN(5,rating+?)) WHERE path=?", (exact_delta, path))
                if value > 0:
                    row = connection.execute("SELECT embedding FROM clips WHERE path=?", (path,)).fetchone()
                    if row and row["embedding"]:
                        import numpy as np
                        reference = np.frombuffer(row["embedding"], dtype=np.float32)
                        candidates = connection.execute(
                            "SELECT path,embedding FROM clips WHERE path<>? AND embedding IS NOT NULL", (path,)).fetchall()
                        for candidate in candidates:
                            vector = np.frombuffer(candidate["embedding"], dtype=np.float32)
                            if vector.size == reference.size and float(np.dot(reference, vector)) >= 0.92:
                                connection.execute(
                                    "UPDATE clips SET rating=MIN(5,rating+1) WHERE path=?", (candidate["path"],))
        self._invalidate_search_cache()

    def remove_missing(self) -> int:
        with self._connect() as connection:
            rows = connection.execute("SELECT path FROM clips").fetchall()
            missing = []
            for row in rows:
                try:
                    Path(row["path"]).stat()
                except FileNotFoundError:
                    missing.append((row["path"],))
                except OSError:
                    # A temporarily unreadable drive/file is not proof that
                    # the user's source was deleted. Keep it for a later run.
                    continue
            connection.executemany("DELETE FROM clips WHERE path=?", missing)
        if missing:
            self._invalidate_search_cache()
        return len(missing)
