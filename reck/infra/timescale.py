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
from psycopg2.extras import execute_values

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
                "timescale.connect.failed",
                extra={"error": str(exc), "error_code": "TIMESCALE_CONNECTION_FAILED"}
            )
            self._connected = False
            return False

    def _initialize_schema(self) -> None:
        """Create hypertables and audit tables."""
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

    def sink_signal(self, source: str, value: float, unit: str = "") -> None:
        """Insert a single signal sample."""
        if not self._connected:
            return
        
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO signals (timestamp, source, value, unit) VALUES (%s, %s, %s, %s)",
                    (datetime.now(timezone.utc), source, value, unit)
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
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO decisions (timestamp, action_id, source, rule_name, proposed_value, outcome, payload)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (action_id) DO NOTHING""",
                    (
                        record.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        record.get("action_id", "unknown"),
                        proposal.get("source", "unknown"),
                        proposal.get("rule_name", "unknown"),
                        proposal.get("proposed_value"),
                        str(record.get("outcome", "unknown")),
                        json.dumps(record)
                    )
                )
        except Exception as exc:
            logger.warning(f"Failed to sink decision to Timescale: {exc}")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            logger.info("TimescaleDB connection closed")
