"""Non-blocking gRPC client for the Rust watch stub.

Forwards raw SignalEvents to the Rust hot-path stub. Failures are swallowed --
the Rust binary may not be running, and that must never block the Python loop.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))

logger = logging.getLogger(__name__)

_TIMEOUT_S = 0.1  # gRPC call budget; never block the hot path


class WatchClient:
    """Fire-and-forget gRPC client to the Rust watch stub."""

    def __init__(self, host: str = "localhost", port: int = 50051) -> None:
        try:
            import grpc
            import reck_pb2_grpc

            self._channel = grpc.insecure_channel(f"{host}:{port}")
            self._stub = reck_pb2_grpc.WatchServiceStub(self._channel)
            self._available = True
        except ImportError:
            logger.debug("grpcio not available; WatchClient disabled")
            self._available = False

    def forward(self, source: str, value: float, unit: str = "") -> bool:
        """Forward a raw signal to Rust. Returns True if accepted."""
        if not self._available:
            return False
        try:
            import reck_pb2

            event = reck_pb2.SignalEvent(source=source, value=value, unit=unit)
            ack = self._stub.ForwardSignal(event, timeout=_TIMEOUT_S)
            return bool(ack.accepted)
        except Exception as exc:
            logger.debug("WatchClient.forward failed: %s", exc)
            return False

    def close(self) -> None:
        if self._available:
            self._channel.close()
