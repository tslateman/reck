"""Stub: escalation handler that logs decisions requiring human review.

Writes structured escalation records to data/escalations.jsonl.
Each record captures the anomaly, the proposed action (if any),
constraint results, and the reason for escalation.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from reck.events import ActionProposal, AnomalyEvent, ConstraintResult
from reck.lore import emit_escalation, notify_cmux
from reck.serialize import default_serializer


class EscalationHandler:
    """Writes escalation records to a JSONL file for human review."""

    def __init__(self, data_dir: Path = Path("data")) -> None:
        self._data_dir = data_dir

    def escalate(
        self,
        anomaly: AnomalyEvent,
        proposal: ActionProposal | None,
        constraint: ConstraintResult | None,
        reason: str,
        causal_hypotheses: list[dict] | None = None,
        counsel_narrative: str = "",
        diagnostic_intent: str = "",
    ) -> None:
        """Append an escalation record as a JSON line."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "anomaly": asdict(anomaly),
            "proposal": asdict(proposal) if proposal else None,
            "constraint": asdict(constraint) if constraint else None,
            "causal_hypotheses": causal_hypotheses,
            "counsel_narrative": counsel_narrative,
            "diagnostic_intent": diagnostic_intent,
        }
        path = self._data_dir / "escalations.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(record, default=default_serializer) + "\n")
        emit_escalation(
            source=anomaly.source,
            reason=reason,
            rule_name=proposal.rule_name if proposal else "",
        )
        notify_cmux("Reck: escalation", f"{reason} on {anomaly.source}")
