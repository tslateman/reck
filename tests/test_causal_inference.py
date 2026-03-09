"""Tests for Plan 006 Phase 3: causal inference & estimation.

Verifies that InferenceEngine can estimate effect sizes and rank
interventions using DoWhy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from reason.graph import CausalGraph
from reason.inference import InferenceEngine


def test_effect_estimation() -> None:
    """InferenceEngine estimates correct effect size for linear dependency."""
    # Generate A -> B with effect size 2.0
    np.random.seed(42)
    n = 500
    a = np.random.normal(10, 1, n)
    b = a * 2.0 + np.random.normal(0, 0.1, n)
    df = pd.DataFrame({"A": a, "B": b})

    graph = CausalGraph()
    graph.add_discovery_edge("A", "B", confidence=1.0)

    engine = InferenceEngine(graph)
    res = engine.estimate_intervention("A", "B", df)

    assert "error" not in res
    # Should be close to 2.0
    assert 1.9 < res["value"] < 2.1


def test_intervention_ranking() -> None:
    """InferenceEngine ranks multiple causes by absolute effect size."""
    # A -> C (effect 2.0)
    # B -> C (effect 0.5)
    np.random.seed(42)
    n = 500
    a = np.random.normal(10, 1, n)
    b = np.random.normal(10, 1, n)
    c = a * 2.0 + b * 0.5 + np.random.normal(0, 0.1, n)
    df = pd.DataFrame({"A": a, "B": b, "C": c})

    graph = CausalGraph()
    graph.add_discovery_edge("A", "C", confidence=1.0)
    graph.add_discovery_edge("B", "C", confidence=1.0)

    engine = InferenceEngine(graph)
    ranking = engine.rank_interventions("C", df)

    assert len(ranking) == 2
    # A should be first (larger absolute effect)
    assert ranking[0]["treatment"] == "A"
    assert ranking[1]["treatment"] == "B"
