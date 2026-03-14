"""TimescaleDB Sink for Phase 2 of Plan 009.

Provides time-series persistence for signals and a durable audit log for decisions.
Uses TimescaleDB (PostgreSQL) hypertables for performance.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)

DB_DSN = "host=localhost dbname=reck user=reck password=password"


class TimescaleSink:
    """Persistence layer for signals and decisions in TimescaleDB."""

    def __init__(self, dsn: str = DB_DSN) -> None:
        self._dsn = dsn
        self._conn = None
        self._connected = False

    def connect(self) -> bool:
        """Establish connection and initialize schema."""
        try:
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = True
            self._initialize_schema()
            self._connected = True
            logger.info("Connected to TimescaleDB")
            return True
        except Exception as exc:
            logger.warning(
                "timescale.connect.failed", extra={"error": str(exc), "error_code": "TIMESCALE_CONNECTION_FAILED"}
            )
            self._connected = False
            return False

    def _initialize_schema(self) -> None:
        """Create hypertables and audit tables."""
        assert self._conn is not None
        with self._conn.cursor() as cur:
            # 1. Signals Hypertable
            cur.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    timestamp TIMESTAMPTZ NOT NULL,
                    source TEXT NOT NULL,
                    value DOUBLE PRECISION NOT NULL,
                    unit TEXT
                );
            """)
            # Convert to hypertable (TimescaleDB specific)
            cur.execute("""
                SELECT create_hypertable('signals', 'timestamp', if_not_exists => TRUE);
            """)

            # 2. Decisions Audit Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    timestamp TIMESTAMPTZ NOT NULL,
                    action_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    rule_name TEXT NOT NULL,
                    proposed_value DOUBLE PRECISION,
                    outcome TEXT NOT NULL,
                    payload JSONB
                );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(timestamp)")

            # 3. Operator Feedback Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS operator_feedback (
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    action_id TEXT PRIMARY KEY,
                    rating INTEGER NOT NULL, -- 1 for success, -1 for failure
                    comment TEXT,
                    processed BOOLEAN DEFAULT FALSE
                );
            """)

            # 4. Idempotent column additions for gear model (Plan 010)
            cur.execute("ALTER TABLE decisions ADD COLUMN IF NOT EXISTS gear INTEGER")
            cur.execute("ALTER TABLE decisions ADD COLUMN IF NOT EXISTS rule_confidence DOUBLE PRECISION")

            # 5. Gear Transitions Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS gear_transitions (
                    timestamp TIMESTAMPTZ NOT NULL,
                    rule_name TEXT NOT NULL,
                    gear_before INTEGER,
                    gear_after INTEGER NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL
                );
            """)

    def sink_signal(self, source: str, value: float, unit: str = "") -> None:
        """Insert a single signal sample."""
        if not self._connected:
            return

        try:
            assert self._conn is not None
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO signals (timestamp, source, value, unit) VALUES (%s, %s, %s, %s)",
                    (datetime.now(timezone.utc), source, value, unit),
                )
        except Exception as exc:
            logger.warning(f"Failed to sink signal to Timescale: {exc}")

    def sink_decision(self, record: dict[str, Any]) -> None:
        """Archive a full decision record."""
        if not self._connected:
            return

        try:
            # Extract key fields for flat columns, store rest in JSONB
            proposal = record.get("proposal", {})
            gear = record.get("gear")
            rule_confidence = record.get("confidence_at_decision")
            assert self._conn is not None
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO decisions
                       (timestamp, action_id, source, rule_name,
                        proposed_value, outcome, payload, gear, rule_confidence)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (action_id) DO UPDATE SET
                       gear = excluded.gear,
                       rule_confidence = excluded.rule_confidence""",
                    (
                        record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        record.get("action_id", "unknown"),
                        proposal.get("source", "unknown"),
                        proposal.get("rule_name", "unknown"),
                        proposal.get("proposed_value"),
                        str(record.get("outcome", "unknown")),
                        json.dumps(record),
                        gear,
                        rule_confidence,
                    ),
                )
        except Exception as exc:
            logger.warning(f"Failed to sink decision to Timescale: {exc}")

    def sink_gear_transition(
        self,
        rule_name: str,
        gear_before: int | None,
        gear_after: int,
        confidence: float,
    ) -> None:
        """Record a gear transition for a rule."""
        if not self._connected:
            return
        try:
            assert self._conn is not None
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO gear_transitions
                       (timestamp, rule_name, gear_before, gear_after, confidence)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (datetime.now(timezone.utc), rule_name, gear_before, gear_after, confidence),
                )
        except Exception as exc:
            logger.warning(f"Failed to sink gear transition: {exc}")

    def get_pending_feedback(self) -> list[dict[str, Any]]:
        """Retrieve all unprocessed operator feedback."""
        if not self._connected:
            return []

        try:
            assert self._conn is not None
            with self._conn.cursor() as cur:
                cur.execute(
                    """SELECT f.action_id, f.rating, d.rule_name
                       FROM operator_feedback f
                       JOIN decisions d ON f.action_id = d.action_id
                       WHERE f.processed = FALSE"""
                )
                rows = cur.fetchall()
                return [{"action_id": r[0], "rating": r[1], "rule_name": r[2]} for r in rows]
        except Exception as exc:
            logger.warning(f"Failed to fetch pending feedback: {exc}")
            return []

    def mark_feedback_processed(self, action_id: str) -> None:
        """Mark feedback as processed to avoid double-counting."""
        if not self._connected:
            return

        try:
            assert self._conn is not None
            with self._conn.cursor() as cur:
                cur.execute("UPDATE operator_feedback SET processed = TRUE WHERE action_id = %s", (action_id,))
        except Exception as exc:
            logger.warning(f"Failed to mark feedback as processed: {exc}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            logger.info("TimescaleDB connection closed")
