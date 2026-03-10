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
from typing import Any, cast

import grpc
import pytest

grpc_available = True
try:
    import grpc
except ImportError:
    grpc_available = False

if not grpc_available:
    pytest.skip("grpc not available", allow_module_level=True)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROTO_DIR = PROJECT_ROOT / "proto"
BINARY = PROJECT_ROOT / "reck-core" / "target" / "debug" / "reck-core"

sys.path.insert(0, str(PROTO_DIR))

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def watch_stub_process():
    """Start the Rust watch stub and yield. Terminate on cleanup."""
    if not BINARY.exists():
        pytest.skip(f"Rust binary not found at {BINARY}. Run: just build-core")

    port = int(os.environ.get("WATCH_PORT", "50051"))
    proc = subprocess.Popen(
        [str(BINARY)],
        env={
            **os.environ,
            "WATCH_PORT": str(port),
            "CONSTRAINTS_PATH": str(PROJECT_ROOT / "guard" / "constraints.yaml"),
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for server to be ready (up to 10s)
    time.sleep(2.0)  # Give it a head start
    deadline = time.monotonic() + 10.0
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
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


def test_guard_validation(watch_stub_process):
    """GuardService returns PASS for a valid proposal."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="act_123",
        source="temp",
        target="site1/area1/line1/cell1/extruder/temperature",
        proposed_value=210.0,
        delta=10.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)
    assert response.action_id == "act_123"
    # Verdict 1 is PASS
    assert response.verdict == 1


def test_act_execution(watch_stub_process):
    """ActService returns success=True for a valid proposal."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.ActServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="act_456",
        source="temp",
        target="site1/area1/line1/cell1/extruder/temperature",
        proposed_value=210.0,
        delta=10.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ExecuteAction(proposal)
    assert response.success is True


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


# ---------------------------------------------------------------------------
# GuardService contract tests
# ---------------------------------------------------------------------------

TARGET_TEMP_SP = "site1/area1/line1/cell1/extruder/temperature_sp"

# Constraint values from guard/constraints.yaml:
#   temperature_sp: min=160.0, max=230.0, rate_of_change=10.0


def test_guard_pass_valid_proposal(watch_stub_process):
    """GuardService returns PASS for a proposal within constraints."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="guard_pass_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=200.0,
        delta=5.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)
    assert response.action_id == "guard_pass_001"
    assert response.verdict == 1  # Verdict.PASS


def test_guard_fail_below_minimum(watch_stub_process):
    """GuardService returns FAIL when proposed_value < min."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="guard_fail_min_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=150.0,  # below min=160.0
        delta=5.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)
    assert response.action_id == "guard_fail_min_001"
    assert response.verdict == 2  # Verdict.FAIL


def test_guard_fail_above_maximum(watch_stub_process):
    """GuardService returns FAIL when proposed_value > max."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="guard_fail_max_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=240.0,  # above max=230.0
        delta=5.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)
    assert response.action_id == "guard_fail_max_001"
    assert response.verdict == 2  # Verdict.FAIL


def test_guard_fail_rate_of_change(watch_stub_process):
    """GuardService returns FAIL when |delta| exceeds rate_of_change."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="guard_fail_roc_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=200.0,  # within range
        delta=15.0,  # exceeds rate_of_change=10.0
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)
    assert response.action_id == "guard_fail_roc_001"
    assert response.verdict == 2  # Verdict.FAIL


def test_guard_verdict_field_structure(watch_stub_process):
    """ConstraintResult has action_id, verdict, violated_constraint, reason."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="guard_struct_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=150.0,  # triggers FAIL to populate all fields
        delta=5.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    response = stub.ValidateProposal(proposal)

    # All four fields must be present on a FAIL result
    assert hasattr(response, "action_id")
    assert hasattr(response, "verdict")
    assert hasattr(response, "violated_constraint")
    assert hasattr(response, "reason")
    assert response.action_id == "guard_struct_001"
    assert response.verdict == 2  # Verdict.FAIL
    assert response.violated_constraint != ""
    assert response.reason != ""


# ---------------------------------------------------------------------------
# ActService contract tests
# ---------------------------------------------------------------------------


def test_act_execute_action_structure(watch_stub_process):
    """ExecuteAction returns ActionAck with success and error fields, or raises RpcError when broker is down."""
    import reck_pb2
    import reck_pb2_grpc

    from reck.events import ActionLifecycle

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.ActServiceStub(channel)

    proposal = reck_pb2.ActionProposal(
        action_id="act_exec_001",
        source="test",
        target=TARGET_TEMP_SP,
        proposed_value=200.0,
        delta=5.0,
        lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
    )
    try:
        response = stub.ExecuteAction(proposal)
        # Broker connected: assert structure
        assert hasattr(response, "success")
        assert hasattr(response, "error")
        assert isinstance(response.success, bool)
        assert isinstance(response.error, str)
    except grpc.RpcError as exc:
        # Broker down: service returns UNAVAILABLE -- acceptable outcome
        assert exc.code() == grpc.StatusCode.UNAVAILABLE, f"Expected UNAVAILABLE when broker is down, got {exc.code()}"


def test_act_revert_action_structure(watch_stub_process):
    """RevertAction returns ActionAck with success and error fields, or raises RpcError when broker is down."""
    import reck_pb2
    import reck_pb2_grpc

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.ActServiceStub(channel)

    revert_req = reck_pb2.RevertRequest(
        target=TARGET_TEMP_SP,
        original_value=195.0,
    )
    try:
        response = stub.RevertAction(revert_req)
        # Broker connected: assert structure
        assert hasattr(response, "success")
        assert hasattr(response, "error")
        assert isinstance(response.success, bool)
        assert isinstance(response.error, str)
    except grpc.RpcError as exc:
        # Broker down: service returns UNAVAILABLE -- acceptable outcome
        assert exc.code() == grpc.StatusCode.UNAVAILABLE, f"Expected UNAVAILABLE when broker is down, got {exc.code()}"


def test_act_revert_restores_original_value(watch_stub_process):
    """RevertRequest carries original_value; service accepts it without a gRPC-level error (UNAVAILABLE is acceptable)."""
    import reck_pb2
    import reck_pb2_grpc

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.ActServiceStub(channel)

    revert_req = reck_pb2.RevertRequest(
        target=TARGET_TEMP_SP,
        original_value=185.0,
    )
    try:
        response = stub.RevertAction(revert_req)
        assert response.success is True
    except grpc.RpcError as exc:
        # UNAVAILABLE means broker is down but the RPC itself was handled correctly
        assert exc.code() == grpc.StatusCode.UNAVAILABLE, f"Expected UNAVAILABLE when broker is down, got {exc.code()}"


# ---------------------------------------------------------------------------
# Shadow-mode divergence detection test
# ---------------------------------------------------------------------------


def test_guard_verdict_matches_python_checker(watch_stub_process):
    """Rust GuardService verdict must match Python ConstraintChecker on the same proposal."""
    import reck_pb2
    import reck_pb2_grpc

    from guard.checker import ConstraintChecker
    from reck.events import ActionLifecycle
    from reck.events import ActionProposal as PyActionProposal

    _, port, channel = watch_stub_process
    stub = reck_pb2_grpc.GuardServiceStub(channel)

    constraints_path = PROJECT_ROOT / "guard" / "constraints.yaml"
    checker = ConstraintChecker(constraints_path)

    # Test proposals: (proposed_value, delta, description)
    cases = [
        (200.0, 5.0, "valid within range"),
        (150.0, 5.0, "below minimum"),
        (240.0, 5.0, "above maximum"),
        (200.0, 15.0, "rate-of-change exceeded"),
    ]

    for proposed_value, delta, description in cases:
        action_id = f"shadow_{description.replace(' ', '_')}"

        # Python checker
        py_proposal = PyActionProposal(
            action_id=action_id,
            source="shadow-test",
            target=TARGET_TEMP_SP,
            delta=delta,
            previous_value=195.0,
            proposed_value=proposed_value,
            rule_name="shadow_test",
            confidence=1.0,
        )
        py_result = checker.validate(py_proposal)

        # Rust GuardService
        proto_proposal = reck_pb2.ActionProposal(
            action_id=action_id,
            source="shadow-test",
            target=TARGET_TEMP_SP,
            proposed_value=proposed_value,
            delta=delta,
            lifecycle=cast(Any, int(ActionLifecycle.PROPOSED.value)),
        )
        rust_result = stub.ValidateProposal(proto_proposal)

        # Proto verdict integers: PASS=1, FAIL=2, ESCALATE=3
        # Python Verdict enum: PASS=1, FAIL=2, ESCALATE=3 (auto() starts at 1)
        py_verdict_int = py_result.verdict.value
        rust_verdict_int = rust_result.verdict

        assert py_verdict_int == rust_verdict_int, (
            f"Shadow divergence on '{description}': "
            f"Python={py_result.verdict.name} ({py_verdict_int}), "
            f"Rust verdict={rust_verdict_int}. "
            f"Proposal: target={TARGET_TEMP_SP}, proposed_value={proposed_value}, delta={delta}"
        )
