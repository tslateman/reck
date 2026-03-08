"""Safety invariant tests: boundary conditions that must hold unconditionally.

If AI rewrites surrounding code, these tests catch violations of the
guard -> gate safety path. Properties are parametric and cover edge cases
that the happy-path tests do not exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from breaker.circuit import CircuitBreaker
from gate.arbiter import GateKeeper
from guard.checker import ConstraintChecker
from reck.events import (
    ActionProposal,
    ConstraintResult,
    GateDecision,
    Verdict,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def checker() -> ConstraintChecker:
    return ConstraintChecker(PROJECT_ROOT / "guard" / "constraints.yaml")


# --- Guard: value bounds ---


@pytest.mark.parametrize("proposed", [0.0, 100.0, 159.9, -999.0])
def test_guard_always_rejects_below_min(checker: ConstraintChecker, proposed: float) -> None:
    """Guard rejects any value below the temperature_sp minimum of 160."""
    proposal = ActionProposal(
        source="s",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-1.0,
        previous_value=165.0,
        proposed_value=proposed,
        rule_name="r",
        confidence=0.9,
    )
    assert checker.validate(proposal).verdict == Verdict.FAIL


@pytest.mark.parametrize("proposed", [230.1, 500.0, 1e6])
def test_guard_always_rejects_above_max(checker: ConstraintChecker, proposed: float) -> None:
    """Guard rejects any value above the temperature_sp maximum of 230."""
    proposal = ActionProposal(
        source="s",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=1.0,
        previous_value=225.0,
        proposed_value=proposed,
        rule_name="r",
        confidence=0.9,
    )
    assert checker.validate(proposal).verdict == Verdict.FAIL


# --- Gate: guard failure is unbypassable ---


def test_gate_never_go_when_guard_fails(checker: ConstraintChecker) -> None:
    """Gate never produces GO when guard verdict is FAIL."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="s",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-50.0,
        previous_value=170.0,
        proposed_value=120.0,
        rule_name="r",
        confidence=0.9,
    )
    constraint = checker.validate(proposal)
    assert constraint.verdict == Verdict.FAIL
    decision, _ = gatekeeper.decide(proposal, constraint, has_precedent=True, rule_confidence=1.0)
    assert decision != GateDecision.GO


# --- Gate: precedent required ---


def test_gate_never_go_without_precedent() -> None:
    """Gate never produces GO for a first-time fix (no precedent)."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="s",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-5.0,
        previous_value=220.0,
        proposed_value=215.0,
        rule_name="r",
        confidence=0.9,
    )
    constraint = ConstraintResult(action_id=proposal.action_id, verdict=Verdict.PASS)
    decision, _ = gatekeeper.decide(proposal, constraint, has_precedent=False, rule_confidence=1.0)
    assert decision != GateDecision.GO


# --- Gate: confidence threshold is enforced ---


@pytest.mark.parametrize("confidence", [0.0, 0.1, 0.29])
def test_gate_never_go_below_confidence_threshold(confidence: float) -> None:
    """Gate never produces GO when confidence is below the 0.3 threshold."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="s",
        target="site1/area1/line1/cell1/extruder/temperature_sp",
        delta=-5.0,
        previous_value=220.0,
        proposed_value=215.0,
        rule_name="r",
        confidence=confidence,
    )
    constraint = ConstraintResult(action_id=proposal.action_id, verdict=Verdict.PASS)
    decision, _ = gatekeeper.decide(proposal, constraint, has_precedent=True, rule_confidence=confidence)
    assert decision != GateDecision.GO


# --- Breaker: trip boundary ---


def test_breaker_trips_at_exactly_3_not_2() -> None:
    """Circuit breaker trips after 3 consecutive failures, not 2."""
    breaker = CircuitBreaker()
    line = "test/line"
    for i in range(2):
        breaker.record_outcome(line, f"chain-{i}", caused_new_anomaly=True)
        assert not breaker.tripped(line), f"Tripped early after {i + 1} failures"
    breaker.record_outcome(line, "chain-2", caused_new_anomaly=True)
    assert breaker.tripped(line)
