"""Anomaly pattern memory for Plan 005 Phase 2.

Stores anomaly signatures and outcome history to answer
"have we seen this before?" and "did it work last time?".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from reck.events import AnomalyEvent


@dataclass(frozen=True)
class AnomalySignature:
    """Distinct signature for an anomaly pattern."""

    source: str
    deviation_type: str  # e.g., "high", "low"
    magnitude_bucket: int  # e.g., 3, 5, 10 (sigma floor)
    recipe: str = ""

    def __post_init__(self) -> None:
        """Bucket the deviation magnitude."""
        # magnitude_bucket is expected to be an int (e.g. floor(sigma))
        pass


class PatternMemory:
    """SQLite-backed memory for anomaly signatures and fix history."""

    def __init__(self, db_path: Path = Path("data/patterns.db")) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS anomaly_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                deviation_type TEXT NOT NULL,
                magnitude_bucket INTEGER NOT NULL,
                recipe TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                occurrence_count INTEGER DEFAULT 1,
                fix_success_count INTEGER DEFAULT 0,
                fix_failure_count INTEGER DEFAULT 0,
                UNIQUE(source, deviation_type, magnitude_bucket, recipe)
            )"""
        )
        self._conn.commit()

    def _get_signature(self, anomaly: AnomalyEvent) -> AnomalySignature:
        """Extract a signature from an AnomalyEvent."""
        dev_type = "high" if anomaly.value > anomaly.baseline_mean else "low"
        # Bucket by sigma (floor)
        mag = int(anomaly.deviation_sigma)
        return AnomalySignature(
            source=anomaly.source,
            deviation_type=dev_type,
            magnitude_bucket=mag,
            recipe=anomaly.context.recipe,
        )

    def record_occurrence(self, anomaly: AnomalyEvent) -> bool:
        """Record an occurrence of an anomaly pattern. Returns True if new."""
        sig = self._get_signature(anomaly)
        now = datetime.now(timezone.utc).isoformat()

        # Check if it exists
        exists = (
            self._conn.execute(
                """SELECT 1 FROM anomaly_patterns
               WHERE source = ? AND deviation_type = ?
               AND magnitude_bucket = ? AND recipe = ?""",
                (sig.source, sig.deviation_type, sig.magnitude_bucket, sig.recipe),
            ).fetchone()
            is not None
        )

        self._conn.execute(
            """INSERT INTO anomaly_patterns
               (source, deviation_type, magnitude_bucket, recipe, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(source, deviation_type, magnitude_bucket, recipe) DO UPDATE SET
               occurrence_count = occurrence_count + 1,
               last_seen = excluded.last_seen""",
            (
                sig.source,
                sig.deviation_type,
                sig.magnitude_bucket,
                sig.recipe,
                now,
                now,
            ),
        )
        self._conn.commit()
        return not exists

    def record_outcome(self, anomaly: AnomalyEvent, success: bool) -> None:
        """Update the fix success/failure count for a pattern."""
        sig = self._get_signature(anomaly)
        if success:
            self._conn.execute(
                """UPDATE anomaly_patterns
                   SET fix_success_count = fix_success_count + 1
                   WHERE source = ? AND deviation_type = ?
                   AND magnitude_bucket = ? AND recipe = ?""",
                (sig.source, sig.deviation_type, sig.magnitude_bucket, sig.recipe),
            )
        else:
            self._conn.execute(
                """UPDATE anomaly_patterns
                   SET fix_failure_count = fix_failure_count + 1
                   WHERE source = ? AND deviation_type = ?
                   AND magnitude_bucket = ? AND recipe = ?""",
                (sig.source, sig.deviation_type, sig.magnitude_bucket, sig.recipe),
            )
        self._conn.commit()

    def lookup(self, anomaly: AnomalyEvent) -> dict | None:
        """Return history for a matching signature."""
        sig = self._get_signature(anomaly)
        row = self._conn.execute(
            """SELECT occurrence_count, fix_success_count, fix_failure_count, last_seen
               FROM anomaly_patterns
               WHERE source = ? AND deviation_type = ?
               AND magnitude_bucket = ? AND recipe = ?""",
            (sig.source, sig.deviation_type, sig.magnitude_bucket, sig.recipe),
        ).fetchone()

        if row:
            return {
                "count": row[0],
                "success_rate": row[1] / (row[1] + row[2]) if (row[1] + row[2]) > 0 else 0.0,
                "last_seen": row[3],
            }
        return None

    def get_all_patterns(self) -> list[dict]:
        """Return all known patterns for CLI display."""
        rows = self._conn.execute(
            """SELECT source, deviation_type, magnitude_bucket, recipe,
                      occurrence_count, fix_success_count, fix_failure_count, last_seen
               FROM anomaly_patterns
               ORDER BY occurrence_count DESC"""
        ).fetchall()
        return [
            {
                "source": r[0],
                "type": r[1],
                "mag": r[2],
                "recipe": r[3],
                "count": r[4],
                "successes": r[5],
                "failures": r[6],
                "last_seen": r[7],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
