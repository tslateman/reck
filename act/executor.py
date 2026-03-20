"""Stub: action executor that publishes setpoints and supports rollback.

Writes proposed values to MQTT topics and stores previous values
for reversion. Operates at ISA-95 Level 2.5 -- setpoints only,
never PLC logic.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

import grpc

# Add proto directory to path for generated stubs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))

from reck.events import ActionLifecycle, ActionProposal

logger = logging.getLogger(__name__)

_TIMEOUT_S = 0.5  # gRPC budget for actuation


class ActClient:
    """Non-blocking gRPC client for the Rust Act service."""

    def __init__(self, port: int = 50051) -> None:
        try:
            import reck_pb2_grpc

            self._channel = grpc.insecure_channel(f"localhost:{port}")
            self._stub = reck_pb2_grpc.ActServiceStub(self._channel)
            self._available = True
        except ImportError:
            logger.debug("grpcio not available; ActClient disabled")
            self._available = False

    def execute(self, proposal: ActionProposal) -> bool:
        """Forward execute request to Rust."""
        if not self._available:
            return False

        try:
            import reck_pb2

            proto_proposal = reck_pb2.ActionProposal(
                action_id=proposal.action_id,
                source=proposal.source,
                target=proposal.target,
                delta=proposal.delta,
                previous_value=proposal.previous_value,
                proposed_value=proposal.proposed_value,
                rule_name=proposal.rule_name,
                confidence=proposal.confidence,
                lifecycle=cast(Any, int(proposal.lifecycle.value)),
                action_chain_id=proposal.action_chain_id,
                rollback_window_s=proposal.rollback_window_s,
            )

            res = self._stub.ExecuteAction(proto_proposal, timeout=_TIMEOUT_S)
            return res.success
        except Exception as exc:
            logger.warning(
                "act.client.execute_failed",
                extra={
                    "error": str(exc),
                    "error_code": "GRPC_ACT_FAILED",
                    "action_id": proposal.action_id,
                },
            )
            return False

    def revert(self, target: str, original_value: float) -> bool:
        """Forward revert request to Rust."""
        if not self._available:
            return False

        try:
            import reck_pb2

            req = reck_pb2.RevertRequest(
                target=target,
                original_value=original_value,
            )

            res = self._stub.RevertAction(req, timeout=_TIMEOUT_S)
            return res.success
        except Exception as exc:
            logger.warning(
                "act.client.revert_failed",
                extra={
                    "error": str(exc),
                    "error_code": "GRPC_REVERT_FAILED",
                    "target": target,
                },
            )
            return False

    def close(self) -> None:
        if self._available:
            self._channel.close()


@dataclass
class _Snapshot:
    target: str
    previous_value: float


class ActionExecutor:
    """Executes action proposals by publishing setpoints via MQTT (coordinates with Rust)."""

    def __init__(
        self,
        act_client: ActClient | None = None,
        snapshot_db: Path = Path("data/snapshots.db"),
    ) -> None:
        self.snapshots: dict[str, _Snapshot] = {}
        self._client = act_client
        self._db = self._init_db(snapshot_db)

    @staticmethod
    def _init_db(path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS snapshots (
                action_id TEXT PRIMARY KEY,
                target TEXT NOT NULL,
                previous_value REAL NOT NULL
            )"""
        )
        conn.commit()
        return conn

    def _save_snapshot(self, action_id: str, snap: _Snapshot) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO snapshots (action_id, target, previous_value) VALUES (?, ?, ?)",
            (action_id, snap.target, snap.previous_value),
        )
        self._db.commit()

    def _load_snapshot(self, action_id: str) -> _Snapshot | None:
        row = self._db.execute(
            "SELECT target, previous_value FROM snapshots WHERE action_id = ?", (action_id,)
        ).fetchone()
        if row is None:
            return None
        return _Snapshot(target=row[0], previous_value=row[1])

    def _delete_snapshot(self, action_id: str) -> None:
        self._db.execute("DELETE FROM snapshots WHERE action_id = ?", (action_id,))
        self._db.commit()

    def execute(
        self,
        proposal: ActionProposal,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Publish proposed setpoint and store previous value for rollback."""
        snap = _Snapshot(target=proposal.target, previous_value=proposal.previous_value)
        self.snapshots[proposal.action_id] = snap
        self._save_snapshot(proposal.action_id, snap)

        success = False
        if self._client:
            success = self._client.execute(proposal)

        if not success:
            # Fallback to local MQTT stub
            mqtt_publish(f"{proposal.target}/cmd", proposal.proposed_value)

        proposal.lifecycle = ActionLifecycle.EXECUTING

    def revert(
        self,
        action_id: str,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Revert to stored previous value on the original target topic."""
        snapshot = self.snapshots.pop(action_id, None) or self._load_snapshot(action_id)
        if snapshot is None:
            logger.warning("act.revert.no_snapshot", extra={"action_id": action_id})
            return

        self._delete_snapshot(action_id)

        success = False
        if self._client:
            success = self._client.revert(snapshot.target, snapshot.previous_value)

        if not success:
            # Fallback to local MQTT stub
            mqtt_publish(f"{snapshot.target}/cmd", snapshot.previous_value)
