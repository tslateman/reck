"""Tests for Plan 005 Phase 3: rule promotion pipeline.

Covers candidate identification and promotion to YAML rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from memory.patterns import PatternMemory
from reck.events import AnomalyEvent, EventContext
from rules.promotion import RulePromoter


@pytest.fixture
def promoter(tmp_path: Path) -> RulePromoter:
    return RulePromoter(db_path=tmp_path / "patterns.db")


@pytest.fixture
def memory(tmp_path: Path) -> PatternMemory:
    return PatternMemory(db_path=tmp_path / "patterns.db")


def test_candidate_identification(memory: PatternMemory, promoter: RulePromoter) -> None:
    """Patterns meeting criteria are identified as candidates."""
    anomaly = AnomalyEvent(
        source="test/signal",
        value=120.0,
        baseline_mean=100.0,
        baseline_stddev=5.0,
        deviation_sigma=4.0,
        context=EventContext(recipe="R1"),
    )

    # 10 occurrences, all successful
    for _ in range(10):
        memory.record_occurrence(anomaly)
        memory.record_outcome(anomaly, success=True)

    candidates = promoter.get_candidates(min_occurrences=10, min_success_rate=0.8)
    assert len(candidates) == 1
    assert candidates[0].source == "test/signal"
    assert candidates[0].occurrence_count == 10
    assert candidates[0].success_rate == 1.0


def test_rule_promotion(promoter: RulePromoter, memory: PatternMemory, tmp_path: Path) -> None:
    """Promote a candidate and verify YAML output."""
    anomaly = AnomalyEvent(
        source="test/signal",
        value=120.0,
        baseline_mean=100.0,
        baseline_stddev=5.0,
        deviation_sigma=4.0,
        context=EventContext(recipe="R1"),
    )
    memory.record_occurrence(anomaly)
    memory.record_outcome(anomaly, success=True)

    # Get the ID (should be 1)
    # PatternMemory.get_all_patterns doesn't return ID currently in the dict.
    # Let's just use 1 as it's the first.

    rules_path = tmp_path / "rules.yaml"
    name = promoter.promote(candidate_id=1, rules_path=rules_path)

    assert "test_signal_high_4" in name
    assert rules_path.exists()

    with open(rules_path) as f:
        data = yaml.safe_load(f)

    rule = data["rules"][0]
    assert rule["name"] == name
    assert rule["source"] == "test/signal"
    assert rule["action"]["target"] == "test/signal_sp"
    assert rule["meta"]["pattern_id"] == 1
