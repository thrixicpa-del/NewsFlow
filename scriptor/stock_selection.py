"""Select media for existing voice scenes; never creates or re-times scenes."""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from collections import Counter
from contextlib import closing, nullcontext
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path

from .footage import FootageItem
from .stock_history import StockUsageHistory
from .stock_media import prepare_stock_media, source_is_hd
from .stock_sources import StockSourceError

STOCK_PROVIDERS = {"pexels", "pixabay", "coverr", "wikimedia", "commons", "nasa"}
_SYNONYMS = {
    "cargo": ("freight",), "train": ("railway", "rail transport"),
    "warehouse": ("logistics depot", "distribution center"),
    "truck": ("road freight", "lorry"), "port": ("seaport", "harbor"),
    "factory": ("manufacturing plant",), "protest": ("demonstration", "rally"),
    "meeting": ("negotiations", "conference"), "hospital": ("medical center",),
}


def stock_query_variants(scene: dict, ladder: dict, topic: str = "") -> list[str]:
    """Extend the existing planner clauses with finite, deduplicated synonyms."""
    original = str(scene.get("visual_query_en") or topic).strip()
    synonyms = []
    for word, alternatives in _SYNONYMS.items():
        if re.search(rf"\b{word}\b", original, re.IGNORECASE):
            synonyms.extend(re.sub(rf"\b{word}\b", synonym, original, flags=re.IGNORECASE) for synonym in alternatives)
    # The scenario topic is context, never permission to replace a scene with
    # generic unrelated news. The original query remains the CLIP/safety gate.
    contextual = [f"{original} {topic}"] if topic and original and len(topic) < 160 else []
    groups = [synonyms, ladder.get('RELAXED_SEMANTIC', []), ladder.get('CATEGORY_MATCH', []),
              ladder.get('SAFE_CONTEXT', []), contextual]
    # Interleave aliases and context without dropping the planner clauses.
    # Expansion is finite; selection stops as soon as an eligible batch wins.
    queries = [original, *ladder.get('STRICT_MATCH', [])]
    queries.extend(value for row in zip_longest(*groups) for value in row if value)
    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def local_family(item: FootageItem) -> str:
    from .ai_index import source_family_identity_text
    return source_family_identity_text(item.path, item.source_url)


@dataclass
class StockChoice:
    item: FootageItem
    duration: float
    score: float
    family: str
    source_start: float = 0.0
    level: str = "STRICT_MATCH"
    provenance: dict | None = None
    reused: bool = False
    position_bucket: str = ""
    context_query: str = ""
    context_score: float = 0.0
    visual_features: object | None = field(default=None, repr=False, compare=False)


@dataclass
class StockReplacementItem(FootageItem):
    source_family: str = ""
    stock_provenance: dict = field(default_factory=dict)
    selection_score: float = 0.0


class StockSceneSelector:
    def __init__(self, *, mode, service, index, cache_root, threshold, trim,
                 aspect_ratio, semantic_ok, source_allowed, duration_probe, checkpoint, download_semaphore=None, use_library=True,
                 hd_only=False, local_window=None, download_queue=None):
        if mode not in {"local", "hybrid", "stock"}:
            raise ValueError("Неподдерживаемый режим источников")
        self.mode, self.service, self.index = mode, service, index
        self.root = Path(cache_root)
        self.threshold = max(.01, float(threshold))
        self.trim, self.aspect_ratio = trim, aspect_ratio
        self.semantic_ok, self.source_allowed = semantic_ok, source_allowed
        self.local_window = local_window
        self.duration_probe, self.checkpoint = duration_probe, checkpoint
        self.download_semaphore = download_semaphore
        self.download_queue = download_queue or getattr(download_semaphore, 'stock_download_queue', None)
        self.use_library = bool(use_library)
        self.hd_only = bool(hd_only)
        self._hd_sources: dict[tuple[str, str], bool] = {}
        self.pool: list[StockChoice] = []
        self.plan_uses = Counter()
        self.last_family = ""
        self.position_bucket = ""
        self.history = StockUsageHistory(self.root)

    def record_project_usage(self, project_key, clips):
        self.history.record(project_key, clips)

    def reject_unclaimed(self, family):
        # Selection is provisional until the batch reservation succeeds. A
        # rejected source must not become this project's safe-reuse footage.
        self.pool = [choice for choice in self.pool if choice.family != family]
        self.plan_uses.pop(family, None)
        self.last_family = self.pool[-1].family if self.pool else ""

    def _remember_choice(self, choice):
        choice.position_bucket = self.position_bucket
        self.plan_uses[choice.family] += 1
        self.last_family = choice.family
        return choice

    def exclude_project_clips(self, clips):
        """Seed repair with retained stock windows, never the full library."""
        extractor = getattr(type(self.index), 'stock_visual_features', None)
        if not callable(extractor):
            return
        for clip in clips:
            self.checkpoint()
            if not clip.stock_provenance or not Path(clip.path).is_file():
                continue
            try:
                available = self.duration_probe(Path(clip.path)) - clip.source_start
                if not math.isfinite(available) or available + .01 < clip.duration:
                    continue  # Other failed/short slots are not retained edits.
                window = prepare_stock_media(Path(clip.path), self.root, duration=clip.duration,
                    trim=True, kind='video', aspect_ratio=self.aspect_ratio, source_start=clip.source_start)
            except (OSError, ValueError, RuntimeError, StockSourceError):
                continue
            features = extractor(self.index, window)
            self._visual_duplicate(features, set())  # Validate before retaining.
            self.pool.append(StockChoice(FootageItem(clip.path, '', clip.source), clip.duration,
                clip.score, clip.source_family, provenance=clip.stock_provenance, visual_features=features))

    def _visual_duplicate(self, features, used):
        """Match near-identical views, not merely a shared subject/category.

        Only accepted windows of this project participate. Rejected batch
        claims leave the pool; deliberate SAFE_REUSE is handled separately.
        """
        if features is None:
            return False  # Legacy index adapters have no image feature API.
        import numpy as np

        mean, frames = np.asarray(features.mean), np.asarray(features.frames)
        if (mean.ndim != 1 or frames.ndim != 2 or not len(frames)
                or frames.shape[1] != len(mean) or not np.isfinite(mean).all()
                or not np.isfinite(frames).all()):
            raise ValueError('Недостоверные признаки визуальной уникальности')
        for choice in self.pool:
            previous = choice.visual_features
            if choice.family not in used or previous is None:
                continue
            if float(np.dot(mean, previous.mean)) < .95:
                continue
            similarities = frames @ np.asarray(previous.frames).T
            # Two-way coverage excludes an isolated common intro/logo frame.
            if ((similarities.max(axis=1) >= .94).mean() >= 2 / 3
                    and (similarities.max(axis=0) >= .94).mean() >= 2 / 3):
                return True
        return False

    def _score(self, path: Path, query: str) -> float:
        # Content keys survive restarts and do not accept a differently named
        # or overwritten file's cached verdict. Model identity is part of key.
        from .ai_index import IMAGE_MODEL, TEXT_MODEL
        model = f"{IMAGE_MODEL}|{TEXT_MODEL}|frames-v1|{type(self.index).__module__}.{type(self.index).__qualname__}"
        identity = hashlib.sha256(f"{_digest(path)}|{query}|{model}|stock-score-v2-ad-frames".encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.root / "visual-verdicts.sqlite3", timeout=30)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS scores (id TEXT PRIMARY KEY, score REAL NOT NULL)")
            row = db.execute("SELECT score FROM scores WHERE id=?", (identity,)).fetchone()
            if row:
                return float(row[0])
        # Dynamic test/legacy adapters may manufacture missing attributes.
        # Use the stock guard only when the concrete index declares it.
        stock_scorer = getattr(type(self.index), "score_stock_file", None)
        score = float(stock_scorer(self.index, path, query) if callable(stock_scorer)
                      else self.index.score_file(path, query))
        if not math.isfinite(score):
            raise ValueError("CLIP не вернул достоверную оценку")
        with closing(sqlite3.connect(self.root / "visual-verdicts.sqlite3", timeout=30)) as db, db:
            db.execute("INSERT OR REPLACE INTO scores VALUES (?,?)", (identity, score))
        return score

    def _local(self, scene, hits, used, *, strict=False, allow_reuse=False, history_families=(),
               guard_query=None, score_query=None):
        levels = ("STRICT_MATCH",) if strict else ("STRICT_MATCH", "RELAXED_SEMANTIC", "CATEGORY_MATCH", "SAFE_CONTEXT")
        candidates = []
        for level in levels:
            for hit in hits.get(level, []):
                item = hit.item
                if item.source in STOCK_PROVIDERS or not Path(item.path).is_file():
                    continue
                family = local_family(item)
                if family in used and not allow_reuse:
                    continue
                # No below-threshold/random continuity escape for the new modes.
                if ((score_query is None and hit.score < self.threshold)
                        or not self.source_allowed(item)):
                    continue
                query = guard_query if guard_query is not None else scene["visual_query_en"]
                start = self.local_window(query, item, float(scene["duration"])) if self.local_window else 0.0
                if start is None or (not self.local_window and not self.semantic_ok(query, item)):
                    continue
                try:
                    score = float(hit.score) if score_query is None else self._score(Path(item.path), score_query)
                except InterruptedError:
                    raise
                except (OSError, ValueError, RuntimeError):
                    continue
                if score < self.threshold:
                    continue
                duration = self.duration_probe(Path(item.path))
                if duration - start + .01 < max(float(scene["duration"]), float(scene.get("minimum_footage_duration", 0))):
                    continue
                candidates.append(StockChoice(item, duration, score, family, source_start=start,
                                              level=level, reused=family in used))
        return self._best(candidates, history_families)

    def _best(self, choices, history_families=()):
        if not choices:
            return None
        counts, windows = self.history.snapshot(choice.family for choice in choices)
        positions = self.history.position_snapshot((choice.family for choice in choices), self.position_bucket)
        recent = set(history_families)
        def rank(choice):
            uses, last = counts.get(choice.family, (0, 0))
            position_uses, position_last = positions.get(choice.family, (0, 0))
            provenance = choice.provenance or {}
            start = float(provenance.get('originalStart', choice.source_start))
            end = start + float(provenance.get('selectedDuration', choice.duration))
            window_uses, window_last = windows.get((choice.family, round(start*1000), round(end*1000)), (0, 0))
            return (not choice.reused, choice.family not in recent, choice.family != self.last_family,
                    -self.plan_uses[choice.family], -uses, -position_uses, -position_last, -last, -window_uses, -window_last, choice.score)
        return max(choices, key=rank)

    def _search_batches(self, query, kind):
        # Discovery responses already contain/cache up to 40 items. Widen only
        # after the initial candidates are exhausted; short/failed results stop
        # here, so an unavailable provider is not hammered repeatedly.
        for limit in (10, 20, 40):
            self.checkpoint()
            found = self._timed('search', self.service.search, query, kind=kind, limit=limit)
            yield found
            if len(found) < limit:
                break

    def _timed(self, phase, function, *args, **kwargs):
        if self.download_queue:
            return self.download_queue.call(phase, function, *args, **kwargs)
        return function(*args, **kwargs)

    def _stock(self, scene, queries, used, *, kind, cached_only=False, history_families=(), broad_only=False,
               guard_query=None):
        if not self.service.enabled:
            return None
        seen = set()
        needed = max(float(scene["duration"]), float(scene.get("minimum_footage_duration", 0)))
        visual_query = scene["visual_query_en"]
        original_query = visual_query if guard_query is None else guard_query
        def batches():
            # Exhaust relevant downloaded candidates across the full synonym
            # ladder before any provider call. Allowed-source and visual gates
            # still apply; disabling library reuse does not delete originals.
            if self.use_library:
                # The caller exhausts lexical video/image matches before a
                # generic-title library scan. Empty queries stay cache-only.
                for query in dict.fromkeys([""] if broad_only else queries):
                    self.checkpoint()
                    cached_batches = getattr(self.service, "cached_batches", None)
                    if cached_batches is not None:
                        yield from cached_batches(query, kind=kind)
                    else:
                        yield self.service.cached(query, kind=kind)
            if not cached_only:
                for query in queries:
                    yield from self._search_batches(query, kind)

        for candidates in batches():
            choices = []
            eligible = []
            for candidate in candidates:
                self.checkpoint()
                if candidate.provider not in self.service.enabled or candidate.kind != kind:
                    continue
                identity = (candidate.provider, candidate.asset_id)
                if identity in seen:
                    continue
                seen.add(identity)
                metadata = FootageItem("", candidate.title, candidate.provider, candidate.source_url, candidate.license, list(candidate.tags))
                if not self.semantic_ok(original_query, metadata):
                    continue
                eligible.append(candidate)
            # Queue only this finite, semantically eligible batch. Selection
            # still consumes it in the original order and applies every gate.
            prefetched = {}
            next_prefetch = 0
            def refill(eligible=eligible, prefetched=prefetched):
                nonlocal next_prefetch
                if not self.download_queue:
                    return
                while next_prefetch < len(eligible):
                    self.checkpoint()
                    future = self.download_queue.submit(self.service, eligible[next_prefetch], block=False)
                    if future is None:
                        break
                    prefetched[next_prefetch] = future
                    next_prefetch += 1
            refill()
            for candidate_index, candidate in enumerate(eligible):
                self.checkpoint()
                try:
                    if self.download_queue:
                        refill()
                        future = prefetched.pop(candidate_index, None)
                        if future is None:
                            future = self.download_queue.submit(self.service, candidate)
                            next_prefetch = max(next_prefetch, candidate_index + 1)
                        try:
                            source = self.download_queue.result(future, self.checkpoint)
                        finally:
                            refill()
                    else:
                        with self.download_semaphore or nullcontext():
                            source = self.service.fetch(candidate)
                    family = f"stock-sha256::{_digest(source)}"
                    if family in used:
                        continue
                    if self.hd_only:
                        hd_key = (family, kind)
                        if hd_key not in self._hd_sources:
                            self._hd_sources[hd_key] = self._timed('validation', source_is_hd, source, kind)
                        if not self._hd_sources[hd_key]:
                            continue
                    length = needed if kind == "image" else self.duration_probe(source)
                    if length + .01 < needed:
                        continue
                    starts = [0.0] if kind == "image" else list(dict.fromkeys((0.0, max(0.0, (length-needed)/2), max(0.0, length-needed))))
                    for start in starts:
                        self.checkpoint()
                        try:
                            window = self._timed('validation', prepare_stock_media, source, self.root, duration=needed, trim=True,
                                kind=kind, aspect_ratio=self.aspect_ratio, source_start=start)
                            score = self._timed('validation', self._score, window, visual_query)
                            checked = FootageItem(str(window), candidate.title, candidate.provider, candidate.source_url,
                                                  candidate.license, list(candidate.tags))
                            if score < self.threshold or not self.source_allowed(checked):
                                continue
                            # The concrete index exposes real, cached CLIP
                            # frame features. Do not trust dynamically invented
                            # capabilities on legacy/test adapters.
                            extractor = getattr(type(self.index), 'stock_visual_features', None)
                            features = extractor(self.index, window) if callable(extractor) else None
                            if self._visual_duplicate(features, used):
                                continue
                            path = window if self.trim or kind == "image" else source
                            metadata = {**candidate.to_dict(), "kind": kind, "originalSha256": family.split("::", 1)[1],
                                        "clipScore": score, "originalPath": str(source), "originalStart": start,
                                        "originalHdVerified": self.hd_only,
                                        "selectedDuration": needed}
                            item = FootageItem(str(path), candidate.title, candidate.provider, candidate.source_url,
                                               candidate.license, list(candidate.tags))
                            choices.append(StockChoice(item, self.duration_probe(path), score, family,
                                source_start=0.0 if path == window else start, level="EXTERNAL_FALLBACK", provenance=metadata,
                                visual_features=features))
                        except InterruptedError:
                            raise
                        except (OSError, ValueError, RuntimeError, StockSourceError):
                            # A damaged/unpreparable interval says nothing
                            # about the remaining windows of this original.
                            continue
                except InterruptedError:
                    raise
                except (OSError, ValueError, RuntimeError, StockSourceError):
                    continue
            best = self._best(choices, history_families)
            if best:
                return best
        return None

    def select_context(self, scene, local_hits, queries, *, used_families, history_families=(), position_bucket=None):
        """Explicit thematic fallback; the original scene still owns hard guards."""
        if position_bucket is not None:
            self.position_bucket = position_bucket
        self.checkpoint()
        queries = list(dict.fromkeys(query.strip() for query in queries if isinstance(query, str) and query.strip()))
        original_query = scene["visual_query_en"]

        def remember(choice, query):
            choice.level = "THEMATIC_CONTEXT"
            choice.context_query, choice.context_score = query, choice.score
            if choice.provenance is not None:
                choice.provenance = {**choice.provenance, "contextQuery": query, "contextScore": choice.score}
                choice.provenance.pop("clipScore", None)
            self.pool.append(choice)
            return self._remember_choice(choice)

        if self.mode != "stock":
            for query in queries:
                self.checkpoint()
                choice = self._local(scene, local_hits, used_families, history_families=history_families,
                    guard_query=original_query, score_query=query)
                if choice is not None:
                    return remember(choice, query)
        if self.mode == "local":
            return None
        # All allowed cached kinds/queries precede the first provider request.
        if self.use_library:
            for broad_only in (False, True):
                for kind in ("video", "image"):
                    for query in queries:
                        choice = self._stock({**scene, "visual_query_en": query}, [query], used_families,
                            kind=kind, cached_only=True, history_families=history_families,
                            broad_only=broad_only, guard_query=original_query)
                        if choice is not None:
                            return remember(choice, query)
        for kind in ("video", "image"):
            for query in queries:
                for excluded in (used_families | set(history_families), used_families) if history_families else (used_families,):
                    choice = self._stock({**scene, "visual_query_en": query}, [query], excluded,
                        kind=kind, history_families=history_families, guard_query=original_query)
                    if choice is not None:
                        return remember(choice, query)
        return None

    def select(self, scene, local_hits, queries, *, used_families, allow_reuse=False, history_families=(), position_bucket=None):
        if position_bucket is not None:
            self.position_bucket = position_bucket
        self.checkpoint()
        # After the existing percentage's pool boundary, reuse only an already
        # accepted semantically suitable window. Never let slider override CLIP.
        if allow_reuse:
            pooled = []
            for choice in self.pool:
                if choice.family not in used_families or choice.duration-choice.source_start + .01 < float(scene["duration"]):
                    continue
                if not choice.provenance and self.local_window:
                    if self.local_window(scene["visual_query_en"], choice.item, float(scene["duration"]),
                                         choice.source_start) is None:
                        continue
                elif not self.semantic_ok(scene["visual_query_en"], choice.item):
                    continue
                try:
                    needed = max(float(scene["duration"]), float(scene.get("minimum_footage_duration", 0)))
                    window = prepare_stock_media(Path(choice.item.path), self.root, duration=needed,
                        trim=True, kind="video", aspect_ratio=self.aspect_ratio, source_start=choice.source_start)
                    checked_item = FootageItem(str(window), choice.item.name, choice.item.source,
                        choice.item.source_url, choice.item.license, choice.item.tags)
                    score = self._score(window, scene["visual_query_en"])
                    if score >= self.threshold and self.source_allowed(checked_item):
                        pooled.append(StockChoice(**{**vars(choice), "reused": True, "score": score, "level": "SAFE_REUSE"}))
                except InterruptedError:
                    raise
                except (OSError, ValueError, RuntimeError):
                    continue
            choice = self._best(pooled)
            if choice:
                return self._remember_choice(choice)
        choice = None
        if self.mode != "stock":
            choice = self._local(scene, local_hits, used_families, strict=self.mode == "hybrid", history_families=history_families)
        if choice is None and self.mode != "local" and self.use_library:
            for broad_only in (False, True):
                for kind in ("video", "image"):
                    choice = self._stock(scene, queries, used_families, kind=kind,
                        cached_only=True, history_families=history_families, broad_only=broad_only)
                    if choice is not None:
                        break
                if choice is not None:
                    break
        if choice is None and self.mode != "local":
            # History is a preference across videos, never a bypass of this
            # video's uniqueness. Try fresh families before recent ones.
            choice = self._stock(scene, queries, used_families | set(history_families), kind="video")
            if choice is None and history_families:
                choice = self._stock(scene, queries, used_families, kind="video")
        if choice is None and self.mode == "hybrid":
            choice = self._local(scene, local_hits, used_families, history_families=history_families)
        if choice is None and self.mode != "local":
            choice = self._stock(scene, queries, used_families, kind="image")
        if choice is None and allow_reuse and self.mode != "stock":
            choice = self._local(scene, local_hits, used_families, allow_reuse=True, history_families=history_families)
        if choice:
            if not choice.reused:
                self.pool.append(choice)
            return self._remember_choice(choice)
        return None
