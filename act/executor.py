"""Stub: action executor that publishes setpoints and supports rollback.

Writes proposed values to MQTT topics and stores previous values
for reversion. Operates at ISA-95 Level 2.5 -- setpoints only,
never PLC logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from reck.events import ActionLifecycle, ActionProposal


@dataclass
class _Snapshot:
    target: str
    previous_value: float


class ActionExecutor:
    """Executes action proposals by publishing setpoints via MQTT."""

    def __init__(self) -> None:
        self.snapshots: dict[str, _Snapshot] = {}

    def execute(
        self,
        proposal: ActionProposal,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Publish proposed setpoint and store previous value for rollback."""
        self.snapshots[proposal.action_id] = _Snapshot(
            target=proposal.target,
            previous_value=proposal.previous_value,
        )
        mqtt_publish(f"{proposal.target}/cmd", proposal.proposed_value)
        proposal.lifecycle = ActionLifecycle.EXECUTING

    def revert(
        self,
        action_id: str,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Revert to stored previous value on the original target topic."""
        snapshot = self.snapshots.pop(action_id)
        mqtt_publish(f"{snapshot.target}/cmd", snapshot.previous_value)
