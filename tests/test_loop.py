"""Integration tests for the full detection-to-action loop.

Tests run without MQTT by driving signals directly through the component chain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from act.executor import ActionExecutor
from breaker.circuit import CircuitBreaker
from escalate.handler import EscalationHandler
from gate.arbiter import GateKeeper
from guard.checker import ConstraintChecker
from ledger.archive import DecisionArchive
from memory.baselines import BaselineStore
from reck.events import (
    ActionLifecycle,
    ActionProposal,
    AnomalyEvent,
    ConstraintResult,
    DecisionRecord,
    GateDecision,
    Priority,
    SignalEvent,
    Verdict,
)
from rules.engine import RuleEngine
from triage.prioritizer import Prioritizer
from watch.detector import AnomalyDetector

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def baselines(tmp_path: Path) -> BaselineStore:
    return BaselineStore(db_path=tmp_path / "baselines.db")


@pytest.fixture
def archive(tmp_path: Path) -> DecisionArchive:
    return DecisionArchive(data_dir=tmp_path)


@pytest.fixture
def escalation(tmp_path: Path) -> EscalationHandler:
    return EscalationHandler(data_dir=tmp_path)


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine(PROJECT_ROOT / "rules" / "example.yaml")


@pytest.fixture
def checker() -> ConstraintChecker:
    return ConstraintChecker(PROJECT_ROOT / "guard" / "constraints.yaml")


# --- Test 1: Full chain happy path ---


def test_full_chain_anomaly_detected_and_fixed(
    baselines: BaselineStore,
    archive: DecisionArchive,
    engine: RuleEngine,
    checker: ConstraintChecker,
) -> None:
    """Signal enters, anomaly detected, rule matches, guard passes, gate approves."""
    detector = AnomalyDetector(min_samples=5)
    prioritizer = Prioritizer()
    gatekeeper = GateKeeper()

    now = datetime.now(timezone.utc)

    # Seed baseline with normal values
    for i in range(20):
        event = SignalEvent(
            source="site1/area1/line1/cell1/extruder/temperature",
            value=200.0 + (i % 3) * 0.1,  # tight cluster around 200
            unit="C",
            timestamp=now,
        )
        baselines.update_baseline(event.source, event.value)
        detector.detect(event)

    # Inject anomalous value
    anomaly_signal = SignalEvent(
        source="site1/area1/line1/cell1/extruder/temperature",
        value=220.0,  # way above baseline
        unit="C",
        timestamp=now,
    )
    anomaly = detector.detect(anomaly_signal)
    assert anomaly is not None, "Detector should flag 220C as anomalous"
    assert anomaly.deviation_sigma > 3.0

    # Triage
    anomaly = prioritizer.prioritize(anomaly)
    assert anomaly.priority in (Priority.MEDIUM, Priority.HIGH)

    # Record anomaly
    baselines.record_anomaly(anomaly)

    # Rules
    proposal = engine.match(anomaly)
    assert proposal is not None, "Rule 'extruder_temp_high' should match"
    assert proposal.rule_name == "extruder_temp_high"
    assert proposal.delta == -5.0

    # Guard
    constraint = checker.validate(proposal)
    assert constraint.verdict == Verdict.PASS

    # Seed precedent so gate approves
    seed_record = DecisionRecord(
        action_id="seed",
        anomaly=anomaly,
        proposal=proposal,
        constraint_check=constraint,
        gate_decision=GateDecision.GO,
        outcome=ActionLifecycle.CONFIRMED,
        action_chain_id="seed-chain",
    )
    archive.record(seed_record)

    from dataclasses import asdict

    assert "gear" in asdict(seed_record)

    has_precedent = archive.check_precedent(proposal.source, proposal.rule_name)
    assert has_precedent

    gate_decision, _reason = gatekeeper.decide(
        proposal,
        constraint,
        has_precedent,
        rule_confidence=0.90,
    )
    assert gate_decision == GateDecision.GO


# --- Test 2: Constraint violation ---


def test_guard_rejects_out_of_bounds(checker: ConstraintChecker) -> None:
    """Guard rejects a proposal that would push temperature below minimum."""
    proposal = ActionProposal(
        source="site1/area1/line1/cell1/extruder/temperature",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-50.0,
        previous_value=170.0,
        proposed_value=120.0,  # below min 160
        rule_name="test_rule",
        confidence=0.9,
    )
    result = checker.validate(proposal)
    assert result.verdict == Verdict.FAIL
    assert "below minimum" in result.reason


def test_gate_blocks_on_guard_failure(checker: ConstraintChecker) -> None:
    """Gate returns NO_GO when guard fails."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="test",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-50.0,
        previous_value=170.0,
        proposed_value=120.0,
        rule_name="test",
        confidence=0.9,
    )
    constraint = checker.validate(proposal)
    decision, _reason = gatekeeper.decide(proposal, constraint, has_precedent=True)
    assert decision == GateDecision.NO_GO


# --- Test 3: First-time fix escalation ---


def test_first_time_fix_escalates(
    archive: DecisionArchive,
    checker: ConstraintChecker,
) -> None:
    """Gate escalates when no precedent exists for the source+rule combo."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="site1/area1/line1/cell1/extruder/temperature",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-5.0,
        previous_value=220.0,
        proposed_value=215.0,
        rule_name="extruder_temp_high",
        confidence=0.95,
    )
    constraint = checker.validate(proposal)
    has_precedent = archive.check_precedent(proposal.source, proposal.rule_name)
    assert not has_precedent

    decision, reason = gatekeeper.decide(proposal, constraint, has_precedent)
    assert decision == GateDecision.ESCALATE
    assert "first-time" in reason


# --- Test 4: Cascade circuit breaker ---


def test_cascade_trips_breaker() -> None:
    """Three consecutive fixes causing new anomalies trips the breaker."""
    breaker = CircuitBreaker()
    line = "site1/area1/line1"

    assert not breaker.tripped(line)

    breaker.record_outcome(line, "chain-1", caused_new_anomaly=True)
    assert not breaker.tripped(line)

    breaker.record_outcome(line, "chain-2", caused_new_anomaly=True)
    assert not breaker.tripped(line)

    breaker.record_outcome(line, "chain-3", caused_new_anomaly=True)
    assert breaker.tripped(line)

    # Reset clears
    breaker.reset(line)
    assert not breaker.tripped(line)


# --- Test 5: Ledger records and queries ---


def test_ledger_records_and_queries(archive: DecisionArchive) -> None:
    """Ledger records decisions and retrieves them."""
    anomaly = AnomalyEvent(
        source="test/signal",
        value=100.0,
        baseline_mean=50.0,
        baseline_stddev=5.0,
        deviation_sigma=10.0,
    )
    proposal = ActionProposal(
        source="test/signal",
        target="test/signal_sp",
        delta=-5.0,
        previous_value=100.0,
        proposed_value=95.0,
        rule_name="test_rule",
        confidence=0.9,
    )
    constraint = ConstraintResult(action_id=proposal.action_id, verdict=Verdict.PASS)
    record = DecisionRecord(
        action_id=proposal.action_id,
        anomaly=anomaly,
        proposal=proposal,
        constraint_check=constraint,
        gate_decision=GateDecision.GO,
        outcome=ActionLifecycle.CONFIRMED,
        action_chain_id=proposal.action_chain_id,
    )
    archive.record(record)

    results = archive.query(last_n=5)
    assert len(results) == 1
    assert results[0]["proposal"]["rule_name"] == "test_rule"
    assert results[0]["outcome"] == "CONFIRMED"


# --- Test 6: Rollback on executor ---


def test_executor_stores_snapshot_and_reverts() -> None:
    """Executor stores previous value and can revert."""
    executor = ActionExecutor()
    published: list[tuple[str, float]] = []

    def mock_publish(topic: str, value: float) -> None:
        published.append((topic, value))

    proposal = ActionProposal(
        source="test",
        target="test/temp_sp",
        delta=-5.0,
        previous_value=200.0,
        proposed_value=195.0,
        rule_name="test",
        confidence=0.9,
    )

    executor.execute(proposal, mock_publish)
    assert published[-1] == ("test/temp_sp/cmd", 195.0)
    assert proposal.action_id in executor.snapshots

    executor.revert(proposal.action_id, mock_publish)
    assert published[-1] == ("test/temp_sp/cmd", 200.0)


# --- Test 7: Gear flows through decision chain ---


def test_gear_flows_through_chain(
    tmp_path: Path,
    archive: DecisionArchive,
) -> None:
    """Gear flows through the decision chain: high confidence -> high gear -> GO."""
    from dataclasses import asdict

    from reck.gear import Gear, select_gear
    from rules.confidence import RuleConfidence

    gatekeeper = GateKeeper()

    # Seed confidence with 12 successes: Beta(13,1) mean = 0.93 -> 4th gear
    confidence = RuleConfidence(db_path=tmp_path / "confidence.db")
    for _ in range(12):
        confidence.update("proven_rule", success=True)
    rule_conf = confidence.get("proven_rule")
    assert rule_conf > 0.85, f"Expected >0.85, got {rule_conf}"

    gear = select_gear(rule_conf)
    assert gear == Gear.FOURTH

    proposal = ActionProposal(
        source="site1/area1/line1/cell1/extruder/temperature",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-5.0,
        previous_value=220.0,
        proposed_value=215.0,
        rule_name="proven_rule",
        confidence=rule_conf,
    )
    constraint = ConstraintResult(action_id=proposal.action_id, verdict=Verdict.PASS)

    # Seed precedent
    seed = DecisionRecord(
        action_id="seed",
        anomaly=AnomalyEvent(
            source="site1/area1/line1/cell1/extruder/temperature",
            value=220.0,
            baseline_mean=200.0,
            baseline_stddev=2.0,
            deviation_sigma=10.0,
        ),
        proposal=proposal,
        constraint_check=constraint,
        gate_decision=GateDecision.GO,
        outcome=ActionLifecycle.CONFIRMED,
        action_chain_id="seed-chain",
    )
    archive.record(seed)
    has_precedent = archive.check_precedent(proposal.source, proposal.rule_name)

    decision, reason = gatekeeper.decide(
        proposal,
        constraint,
        has_precedent,
        rule_confidence=rule_conf,
        gear=gear,
    )
    assert decision == GateDecision.GO
    assert "4th gear" in reason

    # Verify gear stamps on record
    record = DecisionRecord(
        action_id=proposal.action_id,
        anomaly=seed.anomaly,
        proposal=proposal,
        constraint_check=constraint,
        gate_decision=decision,
        outcome=ActionLifecycle.CONFIRMED,
        gear=gear.value,
        confidence_at_decision=rule_conf,
    )
    d = asdict(record)
    assert d["gear"] == 4
    assert d["confidence_at_decision"] > 0.85

    confidence.close()
