"""Stub: anomaly prioritization based on deviation magnitude.

Assigns priority levels: HIGH (>5 sigma), MEDIUM (>3 sigma), LOW (else).
"""

from __future__ import annotations

from reck.events import AnomalyEvent, Priority


class Prioritizer:
    """Assign priority to anomaly events based on sigma deviation."""

    def prioritize(self, anomaly: AnomalyEvent) -> AnomalyEvent:
        """Set priority on the anomaly and return it."""
        if anomaly.deviation_sigma > 5.0:
            anomaly.priority = Priority.HIGH
        elif anomaly.deviation_sigma > 3.0:
            anomaly.priority = Priority.MEDIUM
        else:
            anomaly.priority = Priority.LOW
        return anomaly
