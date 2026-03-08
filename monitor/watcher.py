"""Stub: post-action monitor that watches KPIs after setpoint changes.

Polls a value source at 2-second intervals for the rollback window.
Returns CONFIRMED if the signal stabilizes or improves, REVERTED
if it degrades beyond the starting distance from the proposed value.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from reck.events import ActionLifecycle, ActionProposal


@dataclass
class MonitorResult:
    """Result of a post-action monitoring window."""

    outcome: ActionLifecycle
    kpi_before: float
    kpi_after: float
    duration_s: int


class ActionMonitor:
    """Watches a signal after action execution to confirm or revert."""

    async def monitor(
        self,
        proposal: ActionProposal,
        get_current_value: Callable[[], float],
        rollback_window_s: int = 60,
    ) -> MonitorResult:
        """Poll value source and decide CONFIRMED or REVERTED.

        Compares the distance between the current reading and the
        proposed value. If the final reading drifts further than the
        initial distance, the action is considered degraded.
        """
        kpi_before = get_current_value()
        initial_distance = abs(kpi_before - proposal.proposed_value)

        elapsed = 0
        latest = kpi_before
        while elapsed < rollback_window_s:
            await asyncio.sleep(2)
            elapsed += 2
            latest = get_current_value()

        final_distance = abs(latest - proposal.proposed_value)
        outcome = ActionLifecycle.REVERTED if final_distance > initial_distance else ActionLifecycle.CONFIRMED
        return MonitorResult(
            outcome=outcome,
            kpi_before=kpi_before,
            kpi_after=latest,
            duration_s=elapsed,
        )
