"""Tests for BaselineStore.prune_history time-based pruning."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

pd = pytest.importorskip("pandas")

from memory.baselines import BaselineStore  # noqa: E402


@pytest.fixture()
def store(tmp_path):
    """Create a BaselineStore backed by a temporary database."""
    db_path = tmp_path / "baselines.db"
    s = BaselineStore(db_path=db_path)
    yield s
    s.close()


def _insert_signal(conn: sqlite3.Connection, source: str, value: float, ts: datetime) -> None:
    conn.execute(
        "INSERT INTO signal_history (source, value, timestamp) VALUES (?, ?, ?)",
        (source, value, ts.isoformat()),
    )


def _insert_anomaly(conn: sqlite3.Connection, source: str, value: float, ts: datetime) -> None:
    conn.execute(
        "INSERT INTO anomalies (source, value, deviation_sigma, priority, timestamp) VALUES (?, ?, ?, ?, ?)",
        (source, value, 3.0, "HIGH", ts.isoformat()),
    )


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608


class TestPruneHistory:
    def test_prunes_old_keeps_recent(self, store: BaselineStore) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=10)
        recent = now - timedelta(days=3)

        conn = store._conn  # noqa: SLF001

        # Insert old and recent records in both tables
        _insert_signal(conn, "temp", 100.0, old)
        _insert_signal(conn, "temp", 101.0, old)
        _insert_signal(conn, "temp", 102.0, recent)
        _insert_anomaly(conn, "temp", 100.0, old)
        _insert_anomaly(conn, "temp", 102.0, recent)
        conn.commit()

        assert _count(conn, "signal_history") == 3
        assert _count(conn, "anomalies") == 2

        deleted = store.prune_history(days=7)

        assert deleted == 3  # 2 old signals + 1 old anomaly
        assert _count(conn, "signal_history") == 1
        assert _count(conn, "anomalies") == 1

    def test_returns_zero_when_nothing_to_prune(self, store: BaselineStore) -> None:
        now = datetime.now(timezone.utc)
        recent = now - timedelta(days=1)

        conn = store._conn  # noqa: SLF001
        _insert_signal(conn, "pressure", 50.0, recent)
        conn.commit()

        deleted = store.prune_history(days=7)

        assert deleted == 0
        assert _count(conn, "signal_history") == 1
