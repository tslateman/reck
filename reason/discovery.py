"""Causal discovery engine for Plan 006 Phase 2.

Uses the PC algorithm from causal-learn to discover directed edges
between signals from observational data.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd
from causallearn.search.ConstraintBased.PC import pc

if TYPE_CHECKING:
    from reason.graph import CausalGraph

logger = logging.getLogger(__name__)


class DiscoveryEngine:
    """Discovers causal edges from signal history."""

    def __init__(self, graph: CausalGraph) -> None:
        self._graph = graph

    def run_pc(self, df: pd.DataFrame, alpha: float = 0.05) -> list[tuple[str, str, float]]:
        """Run PC algorithm on DataFrame. Returns list of (source, target, confidence)."""
        if df.empty or len(df.columns) < 2:
            return []

        # causal-learn PC implementation
        # PC requires numeric matrix
        data = df.to_numpy()
        nodes = list(df.columns)

        # Use Fisher-Z test for conditional independence
        # Note: requires Gaussian distribution assumption for valid results
        try:
            cg = pc(data, alpha, "fisherz", node_names=nodes, show_progress=False)
            logger.debug("PC GeneralGraph: %s", cg.G)
        except Exception as e:
            logger.error("PC algorithm failed: %s", e)
            return []

        found_edges: list[tuple[str, str, float]] = []

        # In causal-learn GeneralGraph, edges are accessed via get_graph_edges()
        try:
            cl_edges = cg.G.get_graph_edges()
            logger.debug("PC found %d edges", len(cl_edges))
        except Exception as e:
            logger.debug("Failed to get edges from GeneralGraph: %s", e)
            cl_edges = []

        if not cl_edges:
            # Fallback: Pearson correlation for Phase 2 stability
            corr_matrix = df.corr().abs()
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    val = float(corr_matrix.iloc[i, j])
                    if val > 0.8:
                        # Correlation is undirected, add both directions for Phase 3 refutation
                        found_edges.append((nodes[i], nodes[j], val))
                        found_edges.append((nodes[j], nodes[i], val))
            return found_edges

        for edge in cl_edges:
            node1 = edge.get_node1().get_name()
            node2 = edge.get_node2().get_name()

            # causal-learn endpoints: DASH, ARROW, CIRCLE
            ep1 = edge.get_endpoint1().name
            ep2 = edge.get_endpoint2().name

            if ep1 == "DASH" and ep2 == "ARROW":
                # node1 -> node2
                found_edges.append((node1, node2, 1.0 - alpha))
            elif ep1 == "ARROW" and ep2 == "DASH":
                # node2 -> node1
                found_edges.append((node2, node1, 1.0 - alpha))
            else:
                # Undirected (DASH-DASH) or other (CIRCLE)
                found_edges.append((node1, node2, (1.0 - alpha) * 0.5))
                found_edges.append((node2, node1, (1.0 - alpha) * 0.5))

        return found_edges

    def apply_discoveries(self, discovered_edges: list[tuple[str, str, float]]) -> None:
        """Update the causal graph with discovered edges."""
        for src, target, conf in discovered_edges:
            self._graph.add_discovery_edge(src, target, conf)
        self._graph.save_state()
