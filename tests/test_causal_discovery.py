"""Tests for Plan 006 Phase 2: causal discovery.

Verifies that the PC algorithm can identify directed edges
from synthetic observational data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from reason.discovery import DiscoveryEngine
from reason.graph import CausalGraph


def test_pc_discovery_basic() -> None:
    """PC algorithm identifies A -> B from correlated data."""
    # Generate A -> B
    # A is random noise
    # B is A * 2 + noise
    np.random.seed(42)
    n = 500
    a = np.random.normal(0, 1, n)
    b = a * 2.0 + np.random.normal(0, 0.1, n)

    df = pd.DataFrame({"A": a, "B": b})

    graph = CausalGraph()
    engine = DiscoveryEngine(graph)

    edges = engine.run_pc(df, alpha=0.01)

    # Should find connection between A and B
    # Directionality can be ambiguous (undirected), but the edge should exist.
    sources = {e[0] for e in edges}
    targets = {e[1] for e in edges}
    assert "A" in sources or "B" in sources
    assert "A" in targets or "B" in targets
    assert len(edges) > 0


def test_pc_discovery_no_correlation() -> None:
    """PC algorithm finds no edges between independent noise."""
    np.random.seed(42)
    n = 200
    a = np.random.normal(0, 1, n)
    b = np.random.normal(0, 1, n)

    df = pd.DataFrame({"A": a, "B": b})

    graph = CausalGraph()
    engine = DiscoveryEngine(graph)

    edges = engine.run_pc(df)
    assert len(edges) == 0
