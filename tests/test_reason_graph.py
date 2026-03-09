"""Tests for Plan 006 Phase 1: causal graph foundation.

Covers topology seeding, serialization, and neighbor lookup.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reason.graph import CausalGraph


@pytest.fixture
def topology_file(tmp_path: Path) -> Path:
    path = tmp_path / "topology.yaml"
    data = {
        "topology": [
            {"signal": "temp", "depends_on": ["heater", "ambient"]},
            {"signal": "pressure", "depends_on": ["temp", "screw_speed"]},
        ]
    }
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def test_topology_seeding(topology_file: Path) -> None:
    """Graph is seeded correctly from YAML."""
    graph = CausalGraph()
    graph.load_topology(topology_file)

    assert "temp" in graph.nodes
    assert "heater" in graph.nodes

    neighbors = graph.get_neighbors("temp")
    assert set(neighbors) == {"heater", "ambient"}


def test_graph_persistence(topology_file: Path, tmp_path: Path) -> None:
    """Graph state is saved and loaded correctly from JSON."""
    data_path = tmp_path / "graph.json"
    graph1 = CausalGraph(data_path=data_path)
    graph1.load_topology(topology_file)
    graph1.save_state()

    assert data_path.exists()

    graph2 = CausalGraph(data_path=data_path)
    graph2.load_state()

    assert set(graph2.nodes) == set(graph1.nodes)
    assert set(graph2.get_neighbors("temp")) == {"heater", "ambient"}


def test_discovery_edge_addition() -> None:
    """Tier 2 can add newly discovered edges to the graph."""
    graph = CausalGraph()
    graph.add_discovery_edge("new_cause", "temp", confidence=0.8)

    assert "new_cause" in graph.get_neighbors("temp")
    # Verify metadata
    _, _, data = [e for e in graph.edges if e[0] == "new_cause" and e[1] == "temp"][0]
    assert data["origin"] == "discovery"
    assert data["confidence"] == 0.8
