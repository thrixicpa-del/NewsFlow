"""Selection history beside the existing stock cache; originals stay immutable.

This additive, versioned database is independent from the original/cache schema.
Older runtimes ignore it. Receipts make publication retries idempotent; SQLite
transactions protect counters across threads/processes. It records accepted
plans, not an assertion that those plans have already rendered successfully.
"""
import hashlib
import json
import math
import sqlite3
import time
from contextlib import closing
from pathlib import Path


class StockUsageHistory:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'selection-usage.sqlite3'
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('Неподдерживаемая версия истории подбора стоков')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS families (
                    family TEXT PRIMARY KEY, uses INTEGER NOT NULL, last_used INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS windows (
                    family TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
                    uses INTEGER NOT NULL, last_used INTEGER NOT NULL,
                    PRIMARY KEY(family,start_ms,end_ms));
                CREATE TABLE IF NOT EXISTS positions (
                    family TEXT NOT NULL, bucket TEXT NOT NULL,
                    uses INTEGER NOT NULL, last_used INTEGER NOT NULL,
                    PRIMARY KEY(family,bucket));
                CREATE TABLE IF NOT EXISTS receipts (event TEXT PRIMARY KEY);
                PRAGMA user_version=1;
            ''')

    def snapshot(self, families):
        keys = list(dict.fromkeys(families))
        counts, windows = {}, {}
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            for offset in range(0, len(keys), 900):
                batch = keys[offset:offset+900]
                placeholders = ','.join('?' for _ in batch)
                for family, uses, last in db.execute(f'SELECT family,uses,last_used FROM families WHERE family IN ({placeholders})', batch):
                    counts[family] = (uses, last)
                for family, start, end, uses, last in db.execute(
                        f'SELECT family,start_ms,end_ms,uses,last_used FROM windows WHERE family IN ({placeholders})', batch):
                    windows[(family, start, end)] = (uses, last)
        return counts, windows

    def position_snapshot(self, families, bucket):
        keys = list(dict.fromkeys(families))
        result = {}
        if not bucket:
            return result
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            for offset in range(0, len(keys), 900):
                batch = keys[offset:offset+900]
                placeholders = ','.join('?' for _ in batch)
                for family, uses, last in db.execute(
                        f'SELECT family,uses,last_used FROM positions WHERE bucket=? AND family IN ({placeholders})',
                        [bucket, *batch]):
                    result[family] = (uses, last)
        return result

    def record(self, project_key: str, clips):
        records = set()
        for clip in clips:
            if getattr(clip, 'continuity', {}).get('mode') in {'freeze', 'background'}:
                # A held frame does not consume more seconds of its original.
                continue
            if not clip.source_family:
                continue
            start = float((clip.stock_provenance or {}).get('originalStart', clip.source_start))
            duration = float(clip.duration)
            if not math.isfinite(start) or not math.isfinite(duration) or start < 0 or duration <= 0:
                raise ValueError('Некорректный интервал в истории подбора')
            records.add((clip.source_family, round(start*1000), round((start+duration)*1000), clip.position_bucket))
        if not records:
            return
        event = hashlib.sha256(json.dumps([str(project_key), sorted(records)], ensure_ascii=False).encode()).hexdigest()
        stamp = time.time_ns()
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('INSERT OR IGNORE INTO receipts VALUES (?)', (event,)).rowcount:
                return
            for family in sorted({record[0] for record in records}):
                db.execute('''INSERT INTO families VALUES (?,1,?) ON CONFLICT(family)
                    DO UPDATE SET uses=uses+1,last_used=excluded.last_used''', (family, stamp))
            for family, bucket in sorted({(record[0], record[3]) for record in records if record[3]}):
                db.execute('''INSERT INTO positions VALUES (?,?,1,?) ON CONFLICT(family,bucket)
                    DO UPDATE SET uses=uses+1,last_used=excluded.last_used''', (family, bucket, stamp))
            for family, start, end in sorted({record[:3] for record in records}):
                db.execute('''INSERT INTO windows VALUES (?,?,?,1,?) ON CONFLICT(family,start_ms,end_ms)
                    DO UPDATE SET uses=uses+1,last_used=excluded.last_used''', (family, start, end, stamp))
