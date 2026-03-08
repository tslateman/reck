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
    ) -> None:
        """Append an escalation record as a JSON line."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "anomaly": asdict(anomaly),
            "proposal": asdict(proposal) if proposal else None,
            "constraint": asdict(constraint) if constraint else None,
        }
        path = self._data_dir / "escalations.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(record, default=default_serializer) + "\n")
