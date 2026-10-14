"""Opt-in retrieval benchmark; synthetic vectors, no visual-quality claim."""
import hashlib
import json
import os
import statistics
import tempfile
import time
import tracemalloc
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from scriptor.ai_index import ClipIndex


class TextVectors:
    def query_embed(self, values):
        for value in [values] if isinstance(values, str) else values:
            seed = int.from_bytes(hashlib.sha256(value.encode()).digest()[:4], "little")
            yield np.random.default_rng(seed).normal(size=512).astype(np.float32)


@unittest.skipUnless(os.environ.get("NEWSFLOW_FOOTAGE_BENCHMARK"), "opt-in synthetic performance run")
class FootageRetrievalBenchmark(unittest.TestCase):
    def test_fixed_workloads(self):
        rows = []
        for count in (1000, 10000, 20000):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                index = ClipIndex(root / "index.sqlite3", embedder_factory=lambda: (object(), TextVectors()))
                index.allowed_roots = [str(root)]
                rng = np.random.default_rng(1702)
                vectors = rng.normal(size=(count, 512)).astype(np.float32)
                vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
                paths = [str(root / f"clip_{i:05}.mp4") for i in range(count)]
                with index._connect() as connection:
                    connection.executemany(
                        "INSERT INTO clips(path,name,size,mtime_ns,embedding,tags,duration) VALUES(?,?,0,0,?,?,6)",
                        [(path, Path(path).name, vector.tobytes(), '["diplomatic-negotiations"]')
                         for path, vector in zip(paths, vectors)],
                    )
                for batch in (12, 72):
                    # Distinct queries, equal dimensions/seed/workload in BASE and AFTER.
                    queries = [f"diplomatic negotiations press meeting {i}" for i in range(batch)]
                    samples = {key: [] for key in ("cold", "warm", "after_usage", "corpus")}
                    tracemalloc.start()
                    index._search_corpus()
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    for _ in range(5):
                        index._invalidate_search_cache()
                        # Filesystem/decode excluded explicitly: this profiles retrieval only.
                        with (patch("pathlib.Path.is_file", return_value=True),
                              patch.object(ClipIndex, "_signature", return_value=(0, 0))):
                            start = time.perf_counter()
                            index._search_corpus()
                            samples["corpus"].append((time.perf_counter() - start) * 1000)
                            for phase in ("cold", "warm", "after_usage"):
                                if phase == "after_usage":
                                    index.mark_used(paths[:32])
                                start = time.perf_counter()
                                results = index.search_many(queries, limit=32)
                                samples[phase].append((time.perf_counter() - start) * 1000)
                                self.assertEqual(len(results), batch)
                    rows.append({
                        "records": count, "queries": batch, "repeats": 5,
                        "python_peak_mib": round(peak / 2**20, 2),
                        "ms": {key: {"median": round(statistics.median(values), 2),
                                     "min": round(min(values), 2), "max": round(max(values), 2)}
                               for key, values in samples.items()},
                    })
        output = Path(os.environ["NEWSFLOW_FOOTAGE_BENCHMARK"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "kind": "synthetic-retrieval-only", "dimensions": 512, "selected_roots": "one allowed root containing all records",
            "memory": "tracemalloc corpus allocation peak; disabled during timed search",
            "filesystem": "mocked existence; no video decode", "rows": rows,
            "cold": "corpus prepared, text cache may be cold on first repeat",
            "warm": "same process/corpus/text vectors", "usage": "32 usage updates before search",
        }, indent=2), encoding="utf-8")
