"""Tests for Plan 009 Phase 2: TimescaleDB sink.

Verifies that TimescaleSink correctly handles schema initialization
and data sinking by mocking psycopg2.
"""

from __future__ import annotations

from unittest.mock import ANY, MagicMock, patch

from reck.infra.timescale import TimescaleSink


def test_timescale_sink_initializes_schema() -> None:
    """Sink should connect and create tables if not exists."""

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        sink = TimescaleSink()
        success = sink.connect()

        assert success is True
        assert mock_connect.called

        # Verify signal table and hypertable creation
        calls = [call[0][0] for call in mock_cur.execute.call_args_list]
        assert any("CREATE TABLE IF NOT EXISTS signals" in c for c in calls)
        assert any("create_hypertable('signals'" in c for c in calls)
        assert any("CREATE TABLE IF NOT EXISTS decisions" in c for c in calls)


def test_timescale_sink_signal() -> None:
    """Sink should execute INSERT for signals."""

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        sink = TimescaleSink()
        sink.connect()
        sink.sink_signal("test/source", 42.0, "C")

        # Verify insert call
        mock_cur.execute.assert_any_call(
            "INSERT INTO signals (timestamp, source, value, unit) VALUES (%s, %s, %s, %s)", ANY
        )


def test_timescale_sink_decision() -> None:
    """Sink should execute INSERT for decisions, extracting nested fields."""

    with patch("psycopg2.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        sink = TimescaleSink()
        sink.connect()

        record = {
            "timestamp": "2026-03-09T12:00:00Z",
            "action_id": "act_123",
            "proposal": {"source": "temp", "rule_name": "high_temp", "proposed_value": 200.0},
            "outcome": "CONFIRMED",
        }
        sink.sink_decision(record)

        # Verify insert call
        mock_cur.execute.assert_any_call(
            """INSERT INTO decisions (timestamp, action_id, source, rule_name, proposed_value, outcome, payload)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (action_id) DO NOTHING""",
            ANY,
        )
