"""Tests for Plan 005 Phase 1: confidence tracking and learning loop.

Covers Bayesian confidence updates, gate escalation on low confidence,
time-based decay, and post-action monitoring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gate.arbiter import GateKeeper
from monitor.watcher import ActionMonitor, MonitorResult
from reck.events import (
    ActionLifecycle,
    ActionProposal,
    ConstraintResult,
    GateDecision,
    Verdict,
)
from rules.confidence import RuleConfidence


@pytest.fixture
def confidence(tmp_path: Path) -> RuleConfidence:
    return RuleConfidence(db_path=tmp_path / "confidence.db")


# --- Test 1: Fresh confidence returns prior ---


def test_confidence_starts_at_prior(confidence: RuleConfidence) -> None:
    """Unknown rule returns the 0.5 prior."""
    assert confidence.get("never_seen_rule") == 0.5


# --- Test 2: Successes raise confidence ---


def test_confidence_increases_on_success(confidence: RuleConfidence) -> None:
    """Five consecutive successes raise confidence above the 0.5 prior."""
    rule = "good_rule"
    for _ in range(5):
        confidence.update(rule, success=True)
    assert confidence.get(rule) > 0.5


# --- Test 3: Failures drop confidence below gate threshold ---


def test_confidence_drops_below_threshold_on_failures(
    confidence: RuleConfidence,
) -> None:
    """Three consecutive failures lower confidence below 0.3.

    Starting from alpha=1, beta=1 (the insert default):
      3 failures -> alpha=1, beta=4 -> confidence = 1/5 = 0.2
    """
    rule = "bad_rule"
    for _ in range(3):
        confidence.update(rule, success=False)
    assert confidence.get(rule) < 0.3


# --- Test 4: Gate escalates on low confidence ---


def test_gate_escalates_on_low_confidence() -> None:
    """Gate returns ESCALATE with 'low confidence' when rule_confidence < 0.3."""
    gatekeeper = GateKeeper()
    proposal = ActionProposal(
        source="test/signal",
        target="test/signal_sp",
        delta=-5.0,
        previous_value=200.0,
        proposed_value=195.0,
        rule_name="shaky_rule",
        confidence=0.2,
    )
    constraint = ConstraintResult(
        action_id=proposal.action_id,
        verdict=Verdict.PASS,
    )
    decision, reason = gatekeeper.decide(proposal, constraint, has_precedent=True, rule_confidence=0.2)
    assert decision == GateDecision.ESCALATE
    assert "low confidence" in reason


# --- Test 5: Decay moves confidence toward 0.5 ---


def test_confidence_decay(confidence: RuleConfidence) -> None:
    """Decay pulls a high-confidence rule back toward the 0.5 prior."""
    rule = "decaying_rule"
    # Build up confidence: 10 successes -> alpha=11, beta=1 -> ~0.917
    for _ in range(10):
        confidence.update(rule, success=True)
    before = confidence.get(rule)
    assert before > 0.8

    # Decay with 30 days (one half-life)
    after = confidence.decay(rule, days_since_last_fire=30)
    assert after < before
    # Should move toward 0.5 but not reach it
    assert after > 0.5


# --- Test 6: Monitor captures KPI fields ---


@pytest.mark.asyncio
async def test_monitor_result_captures_kpi() -> None:
    """ActionMonitor returns MonitorResult with kpi_before, kpi_after, duration_s."""
    monitor = ActionMonitor()
    proposal = ActionProposal(
        source="test/signal",
        target="test/signal_sp",
        delta=-5.0,
        previous_value=200.0,
        proposed_value=195.0,
        rule_name="test_rule",
        confidence=0.9,
        rollback_window_s=2,
    )
    result = await monitor.monitor(
        proposal,
        get_current_value=lambda: 196.0,
        rollback_window_s=2,
    )
    assert isinstance(result, MonitorResult)
    assert result.kpi_before == 196.0
    assert result.kpi_after == 196.0
    assert result.duration_s == 2
    assert result.outcome == ActionLifecycle.CONFIRMED
