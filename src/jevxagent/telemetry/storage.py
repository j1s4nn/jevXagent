"""Persistent telemetry store (SQLite).

Storage is fully separated from routing logic. All aggregation happens in
metrics.py; this module only persists and retrieves records.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterator

from ..config import Settings
from .events import DecisionRecord, RequestRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    event_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    request_id TEXT,
    model TEXT,
    operation TEXT,
    stream INTEGER,
    route TEXT,
    status INTEGER,
    total_ms REAL,
    claude_ms REAL,
    jev_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_input_tokens INTEGER,
    cache_creation_input_tokens INTEGER,
    thinking_tokens INTEGER,
    error TEXT,
    summary TEXT,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    request_id TEXT,
    decision_type TEXT,
    route TEXT,
    routing_status TEXT,
    fallback INTEGER,
    confidence REAL,
    status TEXT,
    jev_ms REAL,
    claude_ms REAL,
    jev_input_tokens INTEGER,
    jev_output_tokens INTEGER,
    claude_input_tokens INTEGER,
    claude_output_tokens INTEGER,
    error TEXT,
    meta TEXT
);
CREATE TABLE IF NOT EXISTS benchmarks (
    run_id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    mode TEXT,
    item TEXT,
    decision_type TEXT,
    route TEXT,
    latency_ms REAL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    fallback INTEGER,
    decision TEXT,
    reference TEXT,
    agreement INTEGER,
    status TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests (ts);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions (ts);
CREATE INDEX IF NOT EXISTS idx_benchmarks_ts ON benchmarks (ts);
"""


class TelemetryStore:
    def __init__(self, settings: Settings, path: Path | None = None) -> None:
        settings.ensure_data_dir()
        self._path = path or settings.db_path()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record_request(self, record: RequestRecord) -> None:
        row = record.to_row()
        row["meta"] = json.dumps(row["meta"], ensure_ascii=False, default=str)
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO requests ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            self._conn.commit()

    def record_decision(self, record: DecisionRecord) -> None:
        row = record.to_row()
        row["meta"] = json.dumps(row["meta"], ensure_ascii=False, default=str)
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO decisions ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            self._conn.commit()

    def record_benchmark(self, row: dict) -> None:
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        with self._lock:
            self._conn.execute(
                f"INSERT OR REPLACE INTO benchmarks ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
            self._conn.commit()

    def fetch_requests(self, since_ts: float | None = None, until_ts: float | None = None) -> list[dict]:
        query = "SELECT * FROM requests"
        conditions, params = [], []
        if since_ts is not None:
            conditions.append("ts >= ?")
            params.append(since_ts)
        if until_ts is not None:
            conditions.append("ts < ?")
            params.append(until_ts)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY ts ASC"
        return self._fetch(query, params)

    def fetch_decisions(self, since_ts: float | None = None, until_ts: float | None = None) -> list[dict]:
        query = "SELECT * FROM decisions"
        conditions, params = [], []
        if since_ts is not None:
            conditions.append("ts >= ?")
            params.append(since_ts)
        if until_ts is not None:
            conditions.append("ts < ?")
            params.append(until_ts)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY ts ASC"
        return self._fetch(query, params)

    def fetch_benchmarks(self, since_ts: float | None = None) -> list[dict]:
        query = "SELECT * FROM benchmarks"
        params: list = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " ORDER BY ts ASC"
        return self._fetch(query, params)

    def _fetch(self, query: str, params: list) -> list[dict]:
        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
            names = [description[0] for description in cursor.description]
        out = []
        for row in rows:
            item = dict(zip(names, row))
            for key in ("meta",):
                raw = item.get(key)
                item[key] = json.loads(raw) if raw else {}
            out.append(item)
        return out

    def reset(self) -> int:
        """Delete all telemetry data. Returns number of rows removed."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT (SELECT COUNT(*) FROM requests) + "
                "(SELECT COUNT(*) FROM decisions) + "
                "(SELECT COUNT(*) FROM benchmarks)"
            )
            count = cursor.fetchone()[0] or 0
            self._conn.execute("DELETE FROM requests")
            self._conn.execute("DELETE FROM decisions")
            self._conn.execute("DELETE FROM benchmarks")
            self._conn.commit()
        return count
