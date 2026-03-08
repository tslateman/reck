"""Stub: anomaly detection via rolling-window statistical analysis.

Maintains a rolling window per signal source. Flags a value as anomalous
when it exceeds mean + 3*stddev. Clears the window on gaps > 60s.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reck.events import AnomalyEvent, SignalEvent


@dataclass
class _WindowState:
    """Per-source rolling window state."""

    values: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AnomalyDetector:
    """Detect anomalies using a rolling z-score threshold."""

    def __init__(self, window_size: int = 100, min_samples: int = 20) -> None:
        self._windows: dict[str, _WindowState] = {}
        self._window_size = window_size
        self._min_samples = min_samples

    def detect(self, event: SignalEvent) -> AnomalyEvent | None:
        """Check event against rolling baseline. Returns AnomalyEvent if anomalous."""
        source = event.source

        if source not in self._windows:
            self._windows[source] = _WindowState(values=deque(maxlen=self._window_size))

        state = self._windows[source]

        # Clear window on gap > 60s
        gap = (event.timestamp - state.last_seen).total_seconds()
        if gap > 60.0:
            state.values.clear()

        state.last_seen = event.timestamp

        # Need minimum samples before detecting
        if len(state.values) < self._min_samples:
            state.values.append(event.value)
            return None

        # Compute stats from current window (before adding new value)
        n = len(state.values)
        mean = sum(state.values) / n
        variance = sum((v - mean) ** 2 for v in state.values) / n
        stddev = math.sqrt(variance) if variance > 0 else 0.0

        # Add new value to window
        state.values.append(event.value)

        if stddev == 0:
            return None

        deviation = abs(event.value - mean) / stddev

        if deviation > 3.0:
            return AnomalyEvent(
                source=source,
                value=event.value,
                baseline_mean=round(mean, 4),
                baseline_stddev=round(stddev, 4),
                deviation_sigma=round(deviation, 2),
                timestamp=event.timestamp,
                context=event.context,
            )

        return None
