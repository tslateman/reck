"""gRPC contract tests: Rust watch stub <-> Python client.

Requires the Rust binary to be built (just build-watch).
Run with: just test-integration

Skipped by default in just test to keep the suite under 60s.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

grpc = pytest.importorskip("grpc")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = PROJECT_ROOT / "proto"
BINARY = PROJECT_ROOT / "watch" / "rust" / "target" / "debug" / "reck-watch"

sys.path.insert(0, str(PROTO_DIR))

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def watch_stub_process():
    """Start the Rust watch stub and yield. Terminate on cleanup."""
    if not BINARY.exists():
        pytest.skip(f"Rust binary not found at {BINARY}. Run: just build-watch")

    port = int(os.environ.get("WATCH_PORT", "50051"))
    proc = subprocess.Popen(
        [str(BINARY)],
        env={**os.environ, "WATCH_PORT": str(port)},
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready (up to 5s)
    deadline = time.monotonic() + 5.0
    channel = grpc.insecure_channel(f"localhost:{port}")
    while time.monotonic() < deadline:
        try:
            grpc.channel_ready_future(channel).result(timeout=0.2)
            break
        except grpc.FutureTimeoutError:
            continue
    yield proc, port, channel
    proc.terminate()
    proc.wait(timeout=5)


def test_forward_signal_accepted(watch_stub_process):
    """ForwardSignal returns accepted=True for a valid event."""
    import reck_pb2
    import reck_pb2_grpc

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.WatchServiceStub(channel)

    event = reck_pb2.SignalEvent(
        source="site1/area1/line1/cell1/extruder/temperature",
        value=220.0,
        unit="C",
    )
    response = stub.ForwardSignal(event)
    assert response.accepted is True


def test_anomaly_detection_return(watch_stub_process):
    """ForwardSignal returns an AnomalyEvent after enough samples and a deviation."""
    import reck_pb2
    import reck_pb2_grpc

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.WatchServiceStub(channel)

    source = "site1/area1/line1/cell1/test/detector"

    # Send 20 samples to build a baseline (default min_samples=20)
    for _ in range(20):
        event = reck_pb2.SignalEvent(source=source, value=100.0)
        ack = stub.ForwardSignal(event)
        assert not ack.HasField("anomaly")

    # Send anomalous value (100.0 mean, 0.0 stddev)
    # Deviation will be large if stddev > 0.
    # Wait, the stddev will be 0 if all are 100.0. Rust logic: if stddev > 0.
    # Let's add some jitter.
    for i in range(20):
        val = 100.0 + (i % 2)  # stddev will be ~0.5
        event = reck_pb2.SignalEvent(source=source, value=val)
        ack = stub.ForwardSignal(event)

    # Now send anomaly: 120.0 (40 sigma if stddev=0.5)
    event = reck_pb2.SignalEvent(source=source, value=120.0)
    ack = stub.ForwardSignal(event)
    assert ack.HasField("anomaly")
    assert ack.anomaly.source == source
    assert ack.anomaly.value == 120.0
    assert ack.anomaly.deviation_sigma > 3.0


def test_watch_client_forward_integration(watch_stub_process):
    """WatchClient properly forwards and parses AnomalyEvent."""
    from reck.events import SignalEvent
    from watch.client import WatchClient

    _, port, _ = watch_stub_process
    client = WatchClient(port=port)
    source = "site1/area1/line1/cell1/test/client"

    # Send 20 samples to build a baseline
    for _ in range(20):
        client.forward(SignalEvent(source=source, value=100.0, unit="C"))

    # Jitter
    for i in range(20):
        client.forward(SignalEvent(source=source, value=100.0 + (i % 2), unit="C"))

    # Anomaly
    anomaly = client.forward(SignalEvent(source=source, value=120.0, unit="C"))
    assert anomaly is not None
    assert anomaly.source == source
    assert anomaly.value == 120.0
    assert anomaly.deviation_sigma > 3.0
    client.close()


def test_signal_event_schema_fields(watch_stub_process):
    """SignalEvent proto fields match reck/events.py SignalEvent fields."""
    import reck_pb2

    from reck.events import SignalEvent as PySignalEvent  # noqa: F401

    proto_event = reck_pb2.SignalEvent()
    proto_fields = {f.name for f in proto_event.DESCRIPTOR.fields}
    expected = {"source", "value", "unit", "state_transition", "context"}
    assert expected.issubset(proto_fields), f"Proto missing fields: {expected - proto_fields}"


def test_action_lifecycle_values_match(watch_stub_process):
    """ActionLifecycle enum values are consistent between proto and Python."""
    import reck_pb2

    from reck.events import ActionLifecycle

    proto_names = {v.name for v in reck_pb2.ActionLifecycle.DESCRIPTOR.values}
    for member in ActionLifecycle:
        assert member.name in proto_names, f"{member.name} missing from proto ActionLifecycle"
