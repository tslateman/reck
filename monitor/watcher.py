"""Post-action monitor that watches KPIs after setpoint changes.

Polls multiple value sources at configurable intervals for the rollback window.
Returns CONFIRMED if all tracked signals stabilize or improve, REVERTED
if any degrades beyond a configurable threshold from the proposed value.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from reck.events import ActionLifecycle, ActionProposal


@dataclass
class KpiSpec:
    """Specification for a single KPI to monitor."""

    name: str
    get_value: Callable[[], float]
    weight: float = 1.0
    max_degradation: float | None = None  # absolute; None = use default ratio


@dataclass
class MonitorResult:
    """Result of a post-action monitoring window."""

    outcome: ActionLifecycle
    kpi_before: dict[str, float] = field(default_factory=dict)
    kpi_after: dict[str, float] = field(default_factory=dict)
    duration_s: int = 0
    degraded_kpis: list[str] = field(default_factory=list)


class ActionMonitor:
    """Watches signals after action execution to confirm or revert."""

    def __init__(
        self,
        poll_interval_s: float = 2.0,
        default_degradation_ratio: float = 1.0,
    ) -> None:
        self._poll_interval_s = poll_interval_s
        self._default_ratio = default_degradation_ratio

    async def monitor(
        self,
        proposal: ActionProposal,
        get_current_value: Callable[[], float],
        rollback_window_s: int = 60,
        kpis: list[KpiSpec] | None = None,
    ) -> MonitorResult:
        """Poll value sources and decide CONFIRMED or REVERTED.

        When ``kpis`` is provided, monitors all listed signals.
        Falls back to single-signal monitoring via ``get_current_value``
        for backward compatibility.
        """
        if kpis is None:
            kpis = [KpiSpec(name=proposal.target, get_value=get_current_value)]

        # Capture baselines
        before: dict[str, float] = {}
        initial_distance: dict[str, float] = {}
        for kpi in kpis:
            val = kpi.get_value()
            before[kpi.name] = val
            initial_distance[kpi.name] = abs(val - proposal.proposed_value)

        # Poll loop
        elapsed = 0
        latest: dict[str, float] = dict(before)
        while elapsed < rollback_window_s:
            await asyncio.sleep(self._poll_interval_s)
            elapsed += int(self._poll_interval_s)
            for kpi in kpis:
                latest[kpi.name] = kpi.get_value()

        # Evaluate each KPI
        degraded: list[str] = []
        for kpi in kpis:
            final_distance = abs(latest[kpi.name] - proposal.proposed_value)
            threshold = kpi.max_degradation
            if threshold is None:
                threshold = initial_distance[kpi.name] * self._default_ratio
            if final_distance > threshold:
                degraded.append(kpi.name)

        outcome = ActionLifecycle.REVERTED if degraded else ActionLifecycle.CONFIRMED
        return MonitorResult(
            outcome=outcome,
            kpi_before=before,
            kpi_after=latest,
            duration_s=elapsed,
            degraded_kpis=degraded,
        )
