"""Stub: main orchestrator wiring the full detection-to-action loop.

Usage:
    python -m reck       # Start the full system (requires EMQX at localhost:1883)
    just dev             # Same, via justfile
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from act.executor import ActionExecutor
from breaker.circuit import CircuitBreaker
from escalate.handler import EscalationHandler
from gate.arbiter import GateKeeper
from guard.checker import ConstraintChecker
from ledger.archive import DecisionArchive
from memory.baselines import BaselineStore
from memory.patterns import PatternMemory
from monitor.watcher import ActionMonitor
from reck.events import (
    ActionLifecycle,
    DecisionRecord,
    GateDecision,
    SignalEvent,
)
from reck.lore import emit_escalation
from rules.confidence import RuleConfidence
from rules.engine import RuleEngine
from sim.plant import Plant
from triage.prioritizer import Prioritizer
from watch.client import WatchClient
from watch.detector import AnomalyDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("reck")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LINE_ID = "site1/area1/line1"


async def run_loop(*, anomaly: bool = False) -> None:
    """Wire and run the full detection-to-action loop."""

    # --- Initialize components ---
    plant = Plant()
    detector = AnomalyDetector()
    prioritizer = Prioritizer()
    baselines = BaselineStore(db_path=PROJECT_ROOT / "data" / "baselines.db")
    patterns = PatternMemory(db_path=PROJECT_ROOT / "data" / "patterns.db")
    engine = RuleEngine(PROJECT_ROOT / "rules" / "example.yaml")
    checker = ConstraintChecker(PROJECT_ROOT / "guard" / "constraints.yaml")
    gatekeeper = GateKeeper()
    executor = ActionExecutor()
    watcher = ActionMonitor()
    confidence = RuleConfidence(db_path=PROJECT_ROOT / "data" / "confidence.db")
    breaker = CircuitBreaker()
    escalation = EscalationHandler(data_dir=PROJECT_ROOT / "data")
    archive = DecisionArchive(data_dir=PROJECT_ROOT / "data")
    watch_client = WatchClient()

    signal_queue: asyncio.Queue[SignalEvent] = asyncio.Queue()

    def mqtt_publish(topic: str, value: float) -> None:
        """Stub MQTT publish: applies setpoint directly to the plant."""
        # Extract signal name from topic (last segment before /cmd)
        parts = topic.rstrip("/cmd").split("/")
        signal_name = parts[-1] if parts else topic
        # Remove _sp suffix if present (setpoint -> signal name)
        signal_name = signal_name.removesuffix("_sp")
        plant.set_setpoint(signal_name, value)

    async def process_signals() -> None:
        """Main processing loop: drain signal queue through the full chain."""
        while True:
            event = await signal_queue.get()
            confidence.apply_pending_decay()

            # Update baseline
            baselines.update_baseline(event.source, event.value)

            # Detect (primary: Rust hot-path, fallback: Python stub)
            anomaly_event = watch_client.forward(event)

            if anomaly_event is None:
                anomaly_event = detector.detect(event)

            if anomaly_event is None:
                continue

            # Triage & Pattern Memory
            patterns.record_occurrence(anomaly_event)
            history = patterns.lookup(anomaly_event)
            anomaly_event = prioritizer.prioritize(anomaly_event, pattern_history=history)
            baselines.record_anomaly(anomaly_event)
            logger.warning(
                "Anomaly: %s = %.2f (%.1f sigma, %s)",
                anomaly_event.source,
                anomaly_event.value,
                anomaly_event.deviation_sigma,
                anomaly_event.priority.name,
            )

            # Check breaker
            if breaker.tripped(LINE_ID):
                logger.error("Circuit breaker tripped for %s, skipping", LINE_ID)
                escalation.escalate(anomaly_event, None, None, "circuit breaker tripped")
                emit_escalation(source=LINE_ID, reason="circuit breaker tripped")
                continue

            # Rules
            proposal = engine.match(anomaly_event)
            if proposal is None:
                logger.info("No rule matched for %s", anomaly_event.source)
                continue

            logger.info(
                "Rule matched: %s -> %s (delta %.1f)",
                proposal.rule_name,
                proposal.target,
                proposal.delta,
            )

            # Guard
            constraint = checker.validate(proposal)
            proposal.lifecycle = ActionLifecycle.VALIDATED

            # Gate
            rule_confidence = confidence.get(proposal.rule_name)
            confidence.record_fired(proposal.rule_name)
            has_precedent = archive.check_precedent(proposal.source, proposal.rule_name)
            gate_decision, gate_reason = gatekeeper.decide(
                proposal,
                constraint,
                has_precedent,
                rule_confidence=rule_confidence,
                pattern_history=history,
            )

            if gate_decision == GateDecision.NO_GO:
                logger.warning("Gate: NO_GO - %s", gate_reason)
                record = DecisionRecord(
                    action_id=proposal.action_id,
                    anomaly=anomaly_event,
                    proposal=proposal,
                    constraint_check=constraint,
                    gate_decision=gate_decision,
                    outcome=ActionLifecycle.FAILED,
                    action_chain_id=proposal.action_chain_id,
                )
                archive.record(record)
                continue

            if gate_decision == GateDecision.ESCALATE:
                logger.warning("Gate: ESCALATE - %s", gate_reason)
                escalation.escalate(anomaly_event, proposal, constraint, gate_reason)
                record = DecisionRecord(
                    action_id=proposal.action_id,
                    anomaly=anomaly_event,
                    proposal=proposal,
                    constraint_check=constraint,
                    gate_decision=gate_decision,
                    outcome=ActionLifecycle.PROPOSED,
                    action_chain_id=proposal.action_chain_id,
                    escalation_reason=gate_reason,
                )
                archive.record(record)
                continue

            # Execute
            logger.info("Gate: GO - executing %s", proposal.action_id)
            executor.execute(proposal, mqtt_publish)

            # Monitor (short window for simulation)
            proposal.lifecycle = ActionLifecycle.MONITORING

            def get_value() -> float:
                sig = plant.signals.get("temperature")
                return sig.actual if sig else 0.0

            result = await watcher.monitor(proposal, get_value, rollback_window_s=proposal.rollback_window_s)

            if result.outcome == ActionLifecycle.REVERTED:
                logger.warning("Monitor: reverting %s", proposal.action_id)
                executor.revert(proposal.action_id, mqtt_publish)
                breaker.record_outcome(LINE_ID, proposal.action_chain_id, True)
            else:
                logger.info("Monitor: confirmed %s", proposal.action_id)
                proposal.lifecycle = ActionLifecycle.CONFIRMED
                breaker.record_outcome(LINE_ID, proposal.action_chain_id, False)

            success = result.outcome == ActionLifecycle.CONFIRMED
            confidence.update(proposal.rule_name, success)
            patterns.record_outcome(anomaly_event, success)

            record = DecisionRecord(
                action_id=proposal.action_id,
                anomaly=anomaly_event,
                proposal=proposal,
                constraint_check=constraint,
                gate_decision=gate_decision,
                outcome=result.outcome,
                action_chain_id=proposal.action_chain_id,
                kpi_before=result.kpi_before,
                kpi_after=result.kpi_after,
                monitoring_duration_s=result.duration_s,
            )
            archive.record(record)

    async def inject_drift(delay: float = 10.0) -> None:
        """After delay, drift temperature setpoint to trigger anomaly."""
        await asyncio.sleep(delay)
        logger.warning("Injecting temperature drift: +0.5C/s")
        drift_rate = 0.5
        while True:
            sig = plant.signals["temperature"]
            sig.setpoint += drift_rate
            await asyncio.sleep(1.0)

    # --- Start tasks ---
    tasks = [
        asyncio.create_task(plant.run(callback=signal_queue, interval=1.0)),
        asyncio.create_task(process_signals()),
    ]
    if anomaly:
        tasks.append(asyncio.create_task(inject_drift()))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    for t in tasks:
        t.cancel()
    watch_client.close()
    baselines.close()
    patterns.close()
    confidence.close()
    logger.info("Reck stopped")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reck autonomous manufacturing loop")
    parser.add_argument("--anomaly", action="store_true", help="Inject anomaly after 10s")
    args = parser.parse_args()
    asyncio.run(run_loop(anomaly=args.anomaly))


if __name__ == "__main__":
    main()
