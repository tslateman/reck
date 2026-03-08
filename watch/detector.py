"""Stub: anomaly detection via rolling-window statistical analysis.

Maintains a rolling window per signal source. Flags a value as anomalous
when it exceeds mean + 3*stddev. Clears the window on gaps > 60s.

Uses Welford's online algorithm for O(1) mean/stddev updates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reck.events import AnomalyEvent, SignalEvent


@dataclass
class _WindowState:
    """Per-source rolling window with Welford's online statistics."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def push(self, value: float) -> None:
        """Add a value using Welford's algorithm."""
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2

    @property
    def stddev(self) -> float:
        if self.count < 2:
            return 0.0
        return math.sqrt(self.m2 / self.count)

    def clear(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0


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
            self._windows[source] = _WindowState()

        state = self._windows[source]

        # Clear window on gap > 60s
        gap = (event.timestamp - state.last_seen).total_seconds()
        if gap > 60.0:
            state.clear()

        state.last_seen = event.timestamp

        # Need minimum samples before detecting
        if state.count < self._min_samples:
            state.push(event.value)
            return None

        # Check against current stats before updating
        stddev = state.stddev
        if stddev == 0:
            state.push(event.value)
            return None

        deviation = abs(event.value - state.mean) / stddev

        # Update window (cap at window_size by resetting periodically)
        if state.count >= self._window_size:
            # Decay: halve the window to prevent unbounded growth
            state.count //= 2
            state.m2 /= 2
        state.push(event.value)

        if deviation > 3.0:
            return AnomalyEvent(
                source=source,
                value=event.value,
                baseline_mean=round(state.mean, 4),
                baseline_stddev=round(stddev, 4),
                deviation_sigma=round(deviation, 2),
                timestamp=event.timestamp,
                context=event.context,
            )

        return None
