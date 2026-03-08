"""Stub: CLI entry point for the virtual plant simulator.

Usage:
    python -m sim            # Normal operation at 1Hz
    python -m sim --anomaly  # Inject temperature drift after 10s
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from reck.events import SignalEvent
from sim.plant import Plant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def print_events(queue: asyncio.Queue[SignalEvent]) -> None:
    """Drain the event queue and print each event."""
    while True:
        event = await queue.get()
        logger.info("%s = %.3f %s", event.source, event.value, event.unit)


async def inject_anomaly(plant: Plant, delay: float = 10.0) -> None:
    """After delay, drift temperature setpoint up at +0.5C/s."""
    await asyncio.sleep(delay)
    logger.warning("Injecting temperature drift: +0.5C/s")
    drift_rate = 0.5  # C per second
    while True:
        sig = plant.signals["temperature"]
        sig.setpoint += drift_rate
        await asyncio.sleep(1.0)


async def main(anomaly: bool = False) -> None:
    plant = Plant()
    queue: asyncio.Queue[SignalEvent] = asyncio.Queue()

    tasks = [
        asyncio.create_task(plant.run(callback=queue, interval=1.0)),
        asyncio.create_task(print_events(queue)),
    ]

    if anomaly:
        tasks.append(asyncio.create_task(inject_anomaly(plant)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reck virtual plant simulator")
    parser.add_argument(
        "--anomaly",
        action="store_true",
        help="Inject temperature drift after 10 seconds",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(anomaly=args.anomaly))
    except KeyboardInterrupt:
        logger.info("Simulator stopped")
