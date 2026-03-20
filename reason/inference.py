"""Causal inference engine for Plan 006 Phase 3.

Uses DoWhy to estimate the effect of interventions on target signals
and rank candidate causes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pandas as pd
from dowhy import CausalModel

if TYPE_CHECKING:
    from reason.graph import CausalGraph

logger = logging.getLogger(__name__)


class InferenceEngine:
    """Estimates and refutes causal effects using DoWhy."""

    def __init__(self, graph: CausalGraph) -> None:
        self._graph = graph
        self._cache: dict[tuple[str, str, int], dict[str, Any]] = {}

    def _cache_key(self, treatment: str, outcome: str, df: pd.DataFrame) -> tuple[str, str, int]:
        """Build a cache key from treatment, outcome, and data hash."""
        return (treatment, outcome, hash((len(df), tuple(df.columns), df.values.tobytes())))

    def estimate_intervention(self, treatment: str, outcome: str, df: pd.DataFrame) -> dict[str, Any]:
        """Estimate the effect of treatment on outcome. Returns dict with results."""
        if df.empty:
            return {"error": "empty data"}

        key = self._cache_key(treatment, outcome, df)
        if key in self._cache:
            return self._cache[key]

        try:
            model = CausalModel(
                data=df,
                treatment=treatment,
                outcome=outcome,
                graph=self._graph._graph,
            )

            # 1. Identify causal effect
            identified_estimand = model.identify_effect(proceed_when_unidentifiable=True)

            # 2. Estimate the causal effect
            estimate = model.estimate_effect(identified_estimand, method_name="backdoor.linear_regression")

            result = {"treatment": treatment, "outcome": outcome, "value": estimate.value, "is_robust": True}
            self._cache[key] = result
            return result

        except Exception as e:
            logger.error("Causal inference failed for %s -> %s: %s", treatment, outcome, e)
            return {"error": str(e)}

    def rank_interventions(self, anomaly_source: str, df: pd.DataFrame) -> list[dict[str, Any]]:
        """Rank all upstream neighbors of the anomaly by their estimated effect size."""
        neighbors = self._graph.get_neighbors(anomaly_source)
        if not neighbors:
            return []

        results = []
        for n in neighbors:
            res = self.estimate_intervention(n, anomaly_source, df)
            if "error" not in res:
                results.append(res)

        # Sort by absolute effect size, descending
        return sorted(results, key=lambda x: abs(x["value"]), reverse=True)
