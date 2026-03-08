"""Stub: cascade protection circuit breaker.

Tracks whether recent actions on a production line caused new
anomalies. Trips after three consecutive bad outcomes, preventing
further autonomous action until reset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _Outcome:
    action_chain_id: str
    caused_new_anomaly: bool


class CircuitBreaker:
    """Per-line circuit breaker that trips on consecutive failures."""

    def __init__(self) -> None:
        self._history: dict[str, list[_Outcome]] = {}

    def record_outcome(
        self,
        line: str,
        action_chain_id: str,
        caused_new_anomaly: bool,
    ) -> None:
        """Append an outcome for a production line."""
        self._history.setdefault(line, []).append(_Outcome(action_chain_id, caused_new_anomaly))

    def tripped(self, line: str) -> bool:
        """True if the last 3 consecutive outcomes all caused new anomalies."""
        history = self._history.get(line, [])
        if len(history) < 3:
            return False
        return all(o.caused_new_anomaly for o in history[-3:])

    def reset(self, line: str) -> None:
        """Clear history for a production line."""
        self._history.pop(line, None)
