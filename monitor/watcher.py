"""Stub: post-action monitor that watches KPIs after setpoint changes.

Polls a value source at 2-second intervals for the rollback window.
Returns CONFIRMED if the signal stabilizes or improves, REVERTED
if it degrades beyond the starting distance from the proposed value.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from reck.events import ActionLifecycle, ActionProposal


class ActionMonitor:
    """Watches a signal after action execution to confirm or revert."""

    async def monitor(
        self,
        proposal: ActionProposal,
        get_current_value: Callable[[], float],
        rollback_window_s: int = 60,
    ) -> ActionLifecycle:
        """Poll value source and decide CONFIRMED or REVERTED.

        Compares the distance between the current reading and the
        proposed value. If the final reading drifts further than the
        initial distance, the action is considered degraded.
        """
        initial = get_current_value()
        initial_distance = abs(initial - proposal.proposed_value)

        elapsed = 0
        latest = initial
        while elapsed < rollback_window_s:
            await asyncio.sleep(2)
            elapsed += 2
            latest = get_current_value()

        final_distance = abs(latest - proposal.proposed_value)
        if final_distance > initial_distance:
            return ActionLifecycle.REVERTED
        return ActionLifecycle.CONFIRMED
