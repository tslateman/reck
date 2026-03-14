"""Tests for Plan 005 Phase 2: anomaly pattern memory.

Covers signature generation, similarity lookup, triage enrichment,
and gate enrichment using pattern history.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gate.arbiter import GateKeeper
from memory.patterns import PatternMemory
from reck.events import (
    ActionProposal,
    AnomalyEvent,
    ConstraintResult,
    EventContext,
    GateDecision,
    Priority,
    Verdict,
)
from triage.prioritizer import Prioritizer


@pytest.fixture
def memory(tmp_path: Path) -> PatternMemory:
    return PatternMemory(db_path=tmp_path / "patterns.db")


@pytest.fixture
def anomaly() -> AnomalyEvent:
    return AnomalyEvent(
        source="test/signal",
        value=120.0,
        baseline_mean=100.0,
        baseline_stddev=5.0,
        deviation_sigma=4.0,
        context=EventContext(recipe="R1"),
    )


def test_record_and_lookup(memory: PatternMemory, anomaly: AnomalyEvent) -> None:
    """Record multiple occurrences and verify history."""
    # First occurrence
    is_new = memory.record_occurrence(anomaly)
    assert is_new is True

    # Second occurrence
    is_new = memory.record_occurrence(anomaly)
    assert is_new is False

    history = memory.lookup(anomaly)
    assert history is not None
    assert history["count"] == 2
    assert history["success_rate"] == 0.0


def test_outcome_tracking(memory: PatternMemory, anomaly: AnomalyEvent) -> None:
    """Update outcomes and verify success rate."""
    memory.record_occurrence(anomaly)
    memory.record_outcome(anomaly, success=True)
    memory.record_outcome(anomaly, success=False)

    history = memory.lookup(anomaly)
    assert history is not None
    assert history["count"] == 1
    assert history["success_rate"] == 0.5


def test_triage_habituation(anomaly: AnomalyEvent) -> None:
    """Triage lowers priority for frequently successful patterns."""
    prioritizer = Prioritizer()

    # Base case: 4.0 sigma -> LOW (per new thresholds: HIGH > 10, MEDIUM > 5)
    # Wait, 4.0 is LOW. Let's make it 6.0 for MEDIUM.
    anomaly_med = AnomalyEvent(
        source="test/signal",
        value=130.0,
        baseline_mean=100.0,
        baseline_stddev=5.0,
        deviation_sigma=6.0,
        context=EventContext(recipe="R1"),
    )

    # Without history
    res1 = prioritizer.prioritize(anomaly_med)
    assert res1.priority == Priority.MEDIUM

    # With high-success history
    history = {"count": 15, "success_rate": 0.95}
    res2 = prioritizer.prioritize(anomaly_med, pattern_history=history)
    assert res2.priority == Priority.LOW


def test_gate_pattern_approval(anomaly: AnomalyEvent) -> None:
    """Gate allows first-time fix if the pattern is known and successful."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source=anomaly.source,
        target="test/sp",
        delta=-5.0,
        previous_value=120.0,
        proposed_value=115.0,
        rule_name="test_rule",
        confidence=0.9,
    )
    constraint = ConstraintResult(action_id=proposal.action_id, verdict=Verdict.PASS)

    # Case A: Novel anomaly (count < 2) -> ESCALATE
    history_novel = {"count": 1, "success_rate": 0.0}
    decision, reason = gatekeeper.decide(
        proposal,
        constraint,
        has_precedent=False,
        rule_confidence=0.9,
        pattern_history=history_novel,
    )
    assert decision == GateDecision.ESCALATE
    assert "novel" in reason

    # Case B: Known high-success pattern, with precedent -> GO via gear model
    history_known = {"count": 10, "success_rate": 0.9}
    decision, reason = gatekeeper.decide(
        proposal,
        constraint,
        has_precedent=True,
        rule_confidence=0.9,
        pattern_history=history_known,
    )
    assert decision == GateDecision.GO
    assert "4th gear" in reason
