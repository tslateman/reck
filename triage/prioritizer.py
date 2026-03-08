"""Stub: anomaly prioritization based on deviation magnitude.

Assigns priority levels: HIGH (>5 sigma), MEDIUM (>3 sigma), LOW (else).
"""

from __future__ import annotations

from dataclasses import replace

from reck.events import AnomalyEvent, Priority


class Prioritizer:
    """Assign priority to anomaly events based on sigma deviation and history."""

    def prioritize(self, anomaly: AnomalyEvent, pattern_history: dict | None = None) -> AnomalyEvent:
        """Return a copy of the anomaly with priority set."""
        # Base priority on magnitude
        if anomaly.deviation_sigma > 10.0:
            priority = Priority.HIGH
        elif anomaly.deviation_sigma > 5.0:
            priority = Priority.MEDIUM
        else:
            priority = Priority.LOW

        if pattern_history:
            count = pattern_history["count"]
            success_rate = pattern_history["success_rate"]

            # Novelty: if seen < 3 times, keep or raise priority
            if count < 3:
                pass  # Keep magnitude-based priority

            # Habituation: if seen often (>10 times) and fixed successfully (>90%)
            elif count > 10 and success_rate > 0.9:
                # Lower priority (e.g. HIGH -> MEDIUM -> LOW)
                if priority == Priority.HIGH:
                    priority = Priority.MEDIUM
                else:
                    priority = Priority.LOW

            # Alarm: if seen often (>5 times) but fixes keep failing (<30%)
            elif count > 5 and success_rate < 0.3:
                priority = Priority.HIGH

        return replace(anomaly, priority=priority)
