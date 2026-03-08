"""Stub: virtual plant simulator for development and testing.

Simulates a production line with temperature, pressure, and flow_rate
signals. First-order lag dynamics with configurable time constant and
Gaussian noise. Publishes SignalEvent JSON to MQTT; accepts setpoint
commands on {topic}/cmd.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from reck.events import SignalEvent

logger = logging.getLogger(__name__)

SIGNALS: dict[str, dict[str, float | str]] = {
    "temperature": {"setpoint": 200.0, "unit": "C"},
    "pressure": {"setpoint": 5.0, "unit": "bar"},
    "flow_rate": {"setpoint": 120.0, "unit": "L/min"},
}

TOPIC_PREFIX = "site1/area1/line1/cell1/extruder"


@dataclass
class PlantSignal:
    """Single signal with first-order lag dynamics."""

    name: str
    setpoint: float
    actual: float = 0.0
    unit: str = ""
    tau: float = 10.0
    sigma: float = 0.5
    initialized: bool = False

    def __post_init__(self) -> None:
        if not self.initialized:
            self.actual = self.setpoint
            self.initialized = True

    def step(self, dt: float) -> float:
        """Advance one time step. Returns noisy measurement."""
        alpha = 1.0 - pow(0.5, dt / self.tau) if self.tau > 0 else 1.0
        self.actual += alpha * (self.setpoint - self.actual)
        noise = random.gauss(0, self.sigma)
        return self.actual + noise


@dataclass
class Plant:
    """Virtual plant with multiple signals and MQTT publication."""

    tau: float = 10.0
    sigma: float = 0.5
    signals: dict[str, PlantSignal] = field(default_factory=dict)
    _last_time: float = 0.0

    def __post_init__(self) -> None:
        for name, cfg in SIGNALS.items():
            self.signals[name] = PlantSignal(
                name=name,
                setpoint=float(cfg["setpoint"]),
                unit=str(cfg["unit"]),
                tau=self.tau,
                sigma=self.sigma,
            )
        self._last_time = time.monotonic()

    def step(self) -> list[SignalEvent]:
        """Advance all signals one time step, return events."""
        now = time.monotonic()
        dt = now - self._last_time
        self._last_time = now

        events = []
        for name, sig in self.signals.items():
            value = sig.step(dt)
            source = f"{TOPIC_PREFIX}/{name}"
            events.append(
                SignalEvent(
                    source=source,
                    value=round(value, 3),
                    unit=sig.unit,
                    timestamp=datetime.now(timezone.utc),
                )
            )
        return events

    def set_setpoint(self, signal_name: str, value: float) -> None:
        """Accept a setpoint command."""
        if signal_name in self.signals:
            self.signals[signal_name].setpoint = value
            logger.info("Setpoint %s -> %.2f", signal_name, value)

    def event_to_json(self, event: SignalEvent) -> str:
        """Serialize a SignalEvent to JSON for MQTT publication."""
        return json.dumps(
            {
                "source": event.source,
                "value": event.value,
                "unit": event.unit,
                "timestamp": event.timestamp.isoformat(),
            }
        )

    async def run(
        self,
        callback: asyncio.Queue[SignalEvent] | None = None,
        interval: float = 1.0,
    ) -> None:
        """Run the plant loop, publishing events at the given interval."""
        logger.info("Plant started, publishing every %.1fs", interval)
        while True:
            events = self.step()
            for event in events:
                logger.debug("%s = %.3f %s", event.source, event.value, event.unit)
                if callback is not None:
                    await callback.put(event)
            await asyncio.sleep(interval)
