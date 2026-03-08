"""Stub: anomaly prioritization based on deviation magnitude.

Assigns priority levels: HIGH (>5 sigma), MEDIUM (>3 sigma), LOW (else).
"""

from __future__ import annotations

from dataclasses import replace

from reck.events import AnomalyEvent, Priority


class Prioritizer:
    """Assign priority to anomaly events based on sigma deviation."""

    def prioritize(self, anomaly: AnomalyEvent) -> AnomalyEvent:
        """Return a copy of the anomaly with priority set."""
        if anomaly.deviation_sigma > 5.0:
            priority = Priority.HIGH
        elif anomaly.deviation_sigma > 3.0:
            priority = Priority.MEDIUM
        else:
            priority = Priority.LOW
        return replace(anomaly, priority=priority)
