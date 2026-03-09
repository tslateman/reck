"""Causal graph manager for Tier 2 reasoning.

Maintains a directed graph of signal dependencies using NetworkX.
Supports loading topology from YAML and persisting the graph state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx
import yaml


class CausalGraph:
    """Manages the causal graph of production signals."""

    def __init__(self, data_path: Path = Path("data/graph.json")) -> None:
        self._data_path = data_path
        self._graph = nx.DiGraph()

    def load_topology(self, yaml_path: Path) -> None:
        """Seed the graph from a YAML topology file."""
        if not yaml_path.exists():
            return

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not data or "topology" not in data:
            return

        for entry in data["topology"]:
            target = entry["signal"]
            dependencies = entry.get("depends_on", [])

            # Ensure nodes exist
            self._graph.add_node(target, type="signal")

            for dep in dependencies:
                self._graph.add_node(dep, type="signal")
                # Edge: dep -> target (dep causes target)
                self._graph.add_edge(dep, target, weight=1.0, confidence=1.0, origin="topology")

    def save_state(self) -> None:
        """Persist the current graph state to JSON."""
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph)
        with open(self._data_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_state(self) -> None:
        """Load the graph state from JSON."""
        if not self._data_path.exists():
            return
        with open(self._data_path) as f:
            data = json.load(f)
        self._graph = nx.node_link_graph(data)

    def get_neighbors(self, signal: str, depth: int = 1) -> list[str]:
        """Return upstream causal neighbors (potential causes)."""
        if signal not in self._graph:
            return []

        # predecessors are the nodes with an edge leading to 'signal'
        return list(self._graph.predecessors(signal))

    def add_discovery_edge(self, source: str, target: str, confidence: float) -> None:
        """Add or update an edge discovered by Tier 2."""
        self._graph.add_node(source, type="signal")
        self._graph.add_node(target, type="signal")
        self._graph.add_edge(source, target, weight=1.0, confidence=confidence, origin="discovery")

    @property
    def nodes(self) -> list[str]:
        return list(self._graph.nodes)

    @property
    def edges(self) -> list[tuple[str, str, dict[str, Any]]]:
        return list(self._graph.edges(data=True))
