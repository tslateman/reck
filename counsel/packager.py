"""Context packager for Tier 3 reasoning.

Assembles signal history, causal graph excerpts, and Tier 2 hypotheses
into a structured CounselRequest for the ecosystem.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from google.protobuf.timestamp_pb2 import Timestamp

from proto.reck_pb2 import (
    AnomalyEvent as ProtoAnomalyEvent,
)
from proto.reck_pb2 import (
    CausalHypothesis,
    CausalLink,
    CounselRequest,
    EventContext,
    SignalSample,
)

if TYPE_CHECKING:
    from memory.baselines import BaselineStore
    from reason.graph import CausalGraph
    from reck.events import AnomalyEvent

logger = logging.getLogger(__name__)


class ContextPackager:
    """Assembles rich diagnostic context for Tier 3 reasoning."""

    def __init__(self, baselines: BaselineStore, graph: CausalGraph) -> None:
        self._baselines = baselines
        self._graph = graph

    def package(
        self,
        anomaly: AnomalyEvent,
        action_id: str,
        hypotheses: list[dict[str, Any]] | None = None,
    ) -> CounselRequest:
        """Assemble all Tier 1 and Tier 2 context into a CounselRequest."""

        # 1. Convert anomaly event to proto
        proto_ts = Timestamp()
        proto_ts.FromDatetime(anomaly.timestamp)

        proto_anomaly = ProtoAnomalyEvent(
            source=anomaly.source,
            timestamp=proto_ts,
            value=anomaly.value,
            baseline_mean=anomaly.baseline_mean,
            baseline_stddev=anomaly.baseline_stddev,
            deviation_sigma=anomaly.deviation_sigma,
            priority=cast(Any, anomaly.priority.value),
            context=EventContext(
                recipe=anomaly.context.recipe,
                batch=anomaly.context.batch,
                operator_shift=anomaly.context.operator_shift,
            ),
        )

        # 2. Extract Causal Graph neighborhood
        proto_graph: list[CausalLink] = []
        neighbors = self._graph.get_neighbors(anomaly.source)
        # Add edges for these neighbors
        for n in neighbors:
            # Look for the edge in our internal graph
            for src, target, data in self._graph.edges:
                if src == n and target == anomaly.source:
                    proto_graph.append(
                        CausalLink(
                            source=src,
                            target=target,
                            confidence=data.get("confidence", 1.0),
                            origin=data.get("origin", "unknown"),
                        )
                    )

        # 3. Extract Signal History
        # We want history for the target and its direct causal neighbors
        nodes_to_fetch = [anomaly.source] + neighbors
        df = self._baselines.get_history(nodes_to_fetch, last_n=100)

        proto_history: list[SignalSample] = []
        if not df.empty:
            for ts, row in df.iterrows():
                # pandas iterrows with DatetimeIndex gives ts as Timestamp
                p_ts = Timestamp()
                p_ts.FromDatetime(ts.to_pydatetime())  # type: ignore

                for source in nodes_to_fetch:
                    if source in row:
                        val = row[source]
                        proto_history.append(
                            SignalSample(
                                source=source,
                                timestamp=p_ts,
                                value=cast(float, val),
                            )
                        )

        # 4. Format Tier 2 Hypotheses
        proto_hypotheses: list[CausalHypothesis] = []
        if hypotheses:
            for h in hypotheses:
                proto_hypotheses.append(
                    CausalHypothesis(
                        treatment=h.get("treatment", "unknown"),
                        estimated_effect=h.get("value", 0.0),
                        is_robust=h.get("is_robust", False),
                    )
                )

        return CounselRequest(
            action_id=action_id,
            anomaly=proto_anomaly,
            history=proto_history,
            graph=proto_graph,
            hypotheses=proto_hypotheses,
        )
