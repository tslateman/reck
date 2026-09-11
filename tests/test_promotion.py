"""Tests for Plan 005 Phase 3: rule promotion pipeline.

Covers candidate identification and promotion to YAML rules.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
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


_RACER_SCRIPT = """
import sys, time
from pathlib import Path

from rules.promotion import RulePromoter

start_id, step, count, db_path, rules_path, start_at = sys.argv[1:7]
promoter = RulePromoter(db_path=Path(db_path))
while time.time() < float(start_at):
    time.sleep(0.001)
for i in range(int(count)):
    promoter.promote(int(start_id) + i * int(step), Path(rules_path))
"""


def test_concurrent_promote_preserves_all_rules(tmp_path: Path) -> None:
    """Two concurrent promote() calls against the same rules_path must not lose
    updates or corrupt the YAML file (regression test for rule-promoter-yaml-race)."""
    db_path = tmp_path / "patterns.db"
    memory = PatternMemory(db_path=db_path)

    n_candidates = 20
    for i in range(n_candidates):
        anomaly = AnomalyEvent(
            source=f"press-{i}",
            value=120.0,
            baseline_mean=100.0,
            baseline_stddev=5.0,
            deviation_sigma=4.0,
            context=EventContext(recipe="R1"),
        )
        memory.record_occurrence(anomaly)
        memory.record_outcome(anomaly, success=True)

    rules_path = tmp_path / "rules.yaml"
    racer_script = tmp_path / "racer.py"
    racer_script.write_text(_RACER_SCRIPT)

    repo_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    start_at = time.time() + 1.0
    procs = [
        subprocess.Popen(
            [
                sys.executable,
                str(racer_script),
                str(start_id),
                "2",
                str(n_candidates // 2),
                str(db_path),
                str(rules_path),
                str(start_at),
            ],
            env=env,
        )
        for start_id in (1, 2)
    ]
    for proc in procs:
        assert proc.wait(timeout=30) == 0

    with open(rules_path) as f:
        data = yaml.safe_load(f)

    assert len(data["rules"]) == n_candidates
