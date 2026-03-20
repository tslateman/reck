"""Non-blocking gRPC client for the Rust watch stub.

Forwards raw SignalEvents to the Rust hot-path stub. Failures never block the
Python loop, but every failure is logged at WARNING with a structured payload
so autonomous agents can detect and act on persistent degradation.
"""

from __future__ import annotations

import logging
import sys
from datetime import timezone
from pathlib import Path

from reck.events import AnomalyEvent, SignalEvent

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
            logger.debug(
                "watch.client disabled",
                extra={"reason": "grpcio not installed", "error_code": "GRPC_UNAVAILABLE"},
            )
            self._available = False

    def forward(self, event: SignalEvent) -> AnomalyEvent | None:
        """Forward a raw signal to Rust. Returns AnomalyEvent if anomalous."""
        if not self._available:
            return None
        try:
            import google.protobuf.timestamp_pb2
            import reck_pb2

            ts = google.protobuf.timestamp_pb2.Timestamp()
            ts.FromDatetime(event.timestamp)

            ctx = reck_pb2.EventContext(
                recipe=event.context.recipe,
                batch=event.context.batch,
                operator_shift=event.context.operator_shift,
            )

            proto_event = reck_pb2.SignalEvent(
                source=event.source,
                value=event.value,
                unit=event.unit,
                timestamp=ts,
                context=ctx,
            )
            ack = self._stub.ForwardSignal(proto_event, timeout=_TIMEOUT_S)

            if not ack.HasField("anomaly"):
                return None

            # Convert proto AnomalyEvent to our internal dataclass
            from reck.events import EventContext, Priority

            p = ack.anomaly
            return AnomalyEvent(
                source=p.source,
                value=p.value,
                baseline_mean=p.baseline_mean,
                baseline_stddev=p.baseline_stddev,
                deviation_sigma=p.deviation_sigma,
                priority=Priority(p.priority) if p.priority else Priority.LOW,
                timestamp=p.timestamp.ToDatetime().replace(tzinfo=timezone.utc),
                context=EventContext(
                    recipe=p.context.recipe,
                    batch=p.context.batch,
                    operator_shift=p.context.operator_shift,
                ),
            )
        except Exception as exc:
            logger.warning(
                "watch.client.forward failed",
                extra={
                    "source": event.source,
                    "error": str(exc),
                    "error_code": "GRPC_FORWARD_FAILED",
                },
            )
            return None

    def close(self) -> None:
        if self._available:
            self._channel.close()
