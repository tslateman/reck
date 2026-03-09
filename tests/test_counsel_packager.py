"""Tests for Plan 007 Phase 1: context packaging.

Verifies that ContextPackager correctly assembles Signal history,
Causal Graph excerpts, and Tier 2 hypotheses.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from counsel.packager import ContextPackager
from memory.baselines import BaselineStore
from reason.graph import CausalGraph
from reck.events import AnomalyEvent, EventContext, Priority


@pytest.fixture
def baselines(tmp_path: Path) -> BaselineStore:
    return BaselineStore(db_path=tmp_path / "baselines.db")


@pytest.fixture
def graph(tmp_path: Path) -> CausalGraph:
    return CausalGraph(data_path=tmp_path / "graph.json")


def test_package_counsel_request(baselines: BaselineStore, graph: CausalGraph) -> None:
    """Packager assembles a full CounselRequest with history and causal context."""
    # 1. Setup Causal Graph
    graph.add_discovery_edge("heater", "temp", confidence=0.9)

    # 2. Setup History
    # Record some values
    baselines.update_baseline("heater", 50.0)
    baselines.update_baseline("temp", 100.0)
    baselines.update_baseline("heater", 55.0)
    baselines.update_baseline("temp", 110.0)

    # 3. Create Anomaly
    anomaly = AnomalyEvent(
        source="temp",
        value=150.0,
        baseline_mean=100.0,
        baseline_stddev=5.0,
        deviation_sigma=10.0,
        priority=Priority.HIGH,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
        context=EventContext(recipe="R1"),
    )

    # 4. Mock Hypotheses
    hypotheses = [{"treatment": "heater", "value": 2.5, "is_robust": True}]

    # 5. Package
    packager = ContextPackager(baselines, graph)
    request = packager.package(anomaly, "act_123", hypotheses)

    # 6. Verify
    assert request.action_id == "act_123"
    assert request.anomaly.source == "temp"
    assert request.anomaly.value == 150.0

    # Causal Graph
    assert len(request.graph) == 1
    assert request.graph[0].source == "heater"
    assert request.graph[0].target == "temp"
    assert request.graph[0].confidence == 0.9

    # Hypotheses
    assert len(request.hypotheses) == 1
    assert request.hypotheses[0].treatment == "heater"
    assert request.hypotheses[0].estimated_effect == 2.5
    assert request.hypotheses[0].is_robust is True

    # History
    # Should have samples for both temp and heater
    sources_in_history = {s.source for s in request.history}
    assert "temp" in sources_in_history
    assert "heater" in sources_in_history
    assert len(request.history) >= 4
