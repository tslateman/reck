"""Stub: baseline storage using SQLite and Welford's online algorithm.

Maintains incremental mean/stddev per signal source. Records anomaly
events and checks for precedent.
"""

from __future__ import annotations

import math
import sqlite3
from pathlib import Path

from reck.events import AnomalyEvent

DB_DIR = Path("data")
DB_PATH = DB_DIR / "baselines.db"


class BaselineStore:
    """SQLite-backed baseline statistics and anomaly history."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._create_tables()

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                source TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                mean REAL NOT NULL DEFAULT 0.0,
                m2 REAL NOT NULL DEFAULT 0.0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS anomalies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                value REAL NOT NULL,
                deviation_sigma REAL NOT NULL,
                priority TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def update_baseline(self, source: str, value: float) -> None:
        """Update running stats for source using Welford's algorithm."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT count, mean, m2 FROM baselines WHERE source = ?",
            (source,),
        )
        row = cur.fetchone()

        if row is None:
            count, mean, m2 = 0, 0.0, 0.0
        else:
            count, mean, m2 = row

        count += 1
        delta = value - mean
        mean += delta / count
        delta2 = value - mean
        m2 += delta * delta2

        cur.execute(
            """
            INSERT INTO baselines (source, count, mean, m2)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                count = excluded.count,
                mean = excluded.mean,
                m2 = excluded.m2
            """,
            (source, count, mean, m2),
        )
        self._conn.commit()

    def get_baseline(self, source: str) -> tuple[float, float] | None:
        """Return (mean, stddev) for source, or None if no data."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT count, mean, m2 FROM baselines WHERE source = ?",
            (source,),
        )
        row = cur.fetchone()
        if row is None or row[0] < 2:
            return None

        count, mean, m2 = row
        variance = m2 / count
        return (mean, math.sqrt(variance))

    def record_anomaly(self, event: AnomalyEvent) -> None:
        """Record an anomaly event for precedent tracking."""
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO anomalies (source, value, deviation_sigma, priority, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.source,
                event.value,
                event.deviation_sigma,
                event.priority.name,
                event.timestamp.isoformat(),
            ),
        )
        self._conn.commit()

    def check_precedent(self, source: str) -> int:
        """Return count of past anomalies for source."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM anomalies WHERE source = ?",
            (source,),
        )
        return cur.fetchone()[0]

    def close(self) -> None:
        self._conn.close()
