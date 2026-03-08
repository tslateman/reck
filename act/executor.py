"""Stub: action executor that publishes setpoints and supports rollback.

Writes proposed values to MQTT topics and stores previous values
for reversion. Operates at ISA-95 Level 2.5 -- setpoints only,
never PLC logic.
"""

from __future__ import annotations

from typing import Callable

from reck.events import ActionLifecycle, ActionProposal


class ActionExecutor:
    """Executes action proposals by publishing setpoints via MQTT."""

    def __init__(self) -> None:
        self.snapshots: dict[str, float] = {}

    def execute(
        self,
        proposal: ActionProposal,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Publish proposed setpoint and store previous value for rollback."""
        self.snapshots[proposal.action_id] = proposal.previous_value
        mqtt_publish(f"{proposal.target}/cmd", proposal.proposed_value)
        proposal.lifecycle = ActionLifecycle.EXECUTING

    def revert(
        self,
        action_id: str,
        mqtt_publish: Callable[[str, float], None],
    ) -> None:
        """Revert to stored previous value."""
        previous = self.snapshots.pop(action_id)
        # Caller must supply the original target; for now we derive
        # nothing -- the revert publishes via the same callback.
        mqtt_publish(action_id, previous)
