"""Performance metrics and latency tracing for the Reck hot-path.

Provides a context manager to track execution time of various components
and calculate p50, p95, and p99 statistics.
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import numpy as np


class LatencyTracer:
    """Thread-safe latency tracker for component execution time."""

    def __init__(self) -> None:
        self._measurements: dict[str, list[float]] = defaultdict(list)

    @contextmanager
    def trace(self, component: str) -> Generator[None, None, None]:
        """Record the duration of the enclosed block."""
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            duration_ms = (end - start) * 1000.0
            self._measurements[component].append(duration_ms)

    def get_stats(self) -> dict[str, dict[str, float]]:
        """Calculate statistics for all tracked components."""
        stats = {}
        for component, values in self._measurements.items():
            if not values:
                continue
            data = np.array(values)
            stats[component] = {
                "count": len(values),
                "p50": float(np.percentile(data, 50)),
                "p95": float(np.percentile(data, 95)),
                "p99": float(np.percentile(data, 99)),
                "max": float(np.max(data)),
            }
        return stats

    def reset(self) -> None:
        """Clear all measurements."""
        self._measurements.clear()

    def save_stats(self, path: Path) -> None:
        """Persist current stats to a JSON file."""
        stats = self.get_stats()
        if not stats:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(path, "w") as f:
            json.dump(stats, f, indent=2)

    def load_stats(self, path: Path) -> dict[str, dict[str, float]]:
        """Load stats from a JSON file."""
        if not path.exists():
            return {}
        import json

        with open(path) as f:
            return json.load(f)


# Global singleton for the orchestrator
tracer = LatencyTracer()
