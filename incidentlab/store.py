import json
import sqlite3
import threading
import time
from pathlib import Path

from incidentlab.models import Span


class Store:
    """Small, bounded WAL store. Each process owns its connection and lock."""

    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS spans (
                    trace_id TEXT NOT NULL, span_id TEXT NOT NULL, service TEXT NOT NULL,
                    start_ns INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(trace_id, span_id)
                );
                CREATE INDEX IF NOT EXISTS spans_time ON spans(start_ns);
                CREATE INDEX IF NOT EXISTS spans_trace ON spans(trace_id);
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS baselines (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL
                );
            """)
        self._last_prune = 0.0

    def insert(self, spans: list[Span]):
        with self.lock, self.db:
            self.db.executemany(
                "INSERT OR IGNORE INTO spans VALUES(?,?,?,?,?)",
                [(s.trace_id, s.span_id, s.service, s.start_ns, s.model_dump_json()) for s in spans],
            )
            if time.monotonic() - self._last_prune > 30:
                # Retention is bounded by both age and row count.
                cutoff = int((time.time() - 86400) * 1e9)
                self.db.execute("DELETE FROM spans WHERE start_ns < ?", (cutoff,))
                self.db.execute("""DELETE FROM spans WHERE rowid IN (
                    SELECT rowid FROM spans ORDER BY start_ns DESC LIMIT -1 OFFSET 100000
                )""")
                self._last_prune = time.monotonic()

    def window(self, start: float, end: float, limit: int = 20000) -> list[Span]:
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM spans WHERE start_ns >= ? AND start_ns < ? ORDER BY start_ns DESC LIMIT ?",
                (int(start * 1e9), int(end * 1e9), limit),
            ).fetchall()
        return [Span.model_validate_json(r[0]) for r in rows]

    def trace(self, trace_id: str) -> list[Span]:
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM spans WHERE trace_id = ? ORDER BY start_ns", (trace_id,)
            ).fetchall()
        return [Span.model_validate_json(r[0]) for r in rows]

    def save_incident(self, incident: dict):
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO incidents VALUES(?,?,?)",
                (incident["id"], incident["created_at"], json.dumps(incident)),
            )
            self.db.execute("""DELETE FROM incidents WHERE id IN (
                SELECT id FROM incidents ORDER BY created DESC LIMIT -1 OFFSET 200
            )""")

    def incidents(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT payload FROM incidents ORDER BY created DESC LIMIT 200").fetchall()
        return [json.loads(r[0]) for r in rows]

    def save_baseline(self, baseline: dict):
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO baselines VALUES(?,?,?)",
                (baseline["id"], baseline["created_at"], json.dumps(baseline)),
            )
            self.db.execute("""DELETE FROM baselines WHERE id IN (
                SELECT id FROM baselines ORDER BY created DESC LIMIT -1 OFFSET 10
            )""")

    def baselines(self) -> list[dict]:
        with self.lock:
            rows = self.db.execute("SELECT payload FROM baselines ORDER BY created DESC LIMIT 10").fetchall()
        return [json.loads(r[0]) for r in rows]

    def close(self):
        self.db.close()
