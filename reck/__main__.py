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

from act.executor import ActClient, ActionExecutor
from breaker.circuit import CircuitBreaker
from counsel.dispatch import PraxisCounselDispatcher
from counsel.packager import ContextPackager
from escalate.handler import EscalationHandler
from gate.arbiter import GateKeeper
from guard.checker import ConstraintChecker, GuardClient
from ledger.archive import DecisionArchive
from memory.baselines import BaselineStore
from memory.patterns import PatternMemory
from monitor.watcher import ActionMonitor
from reck.infra.bridge import RedpandaBridge
from reason.graph import CausalGraph
from reason.inference import InferenceEngine
from reck.events import (
    ActionLifecycle,
    DecisionRecord,
    GateDecision,
    SignalEvent,
    Verdict,
)
from reck.lore import emit_escalation
from reck.metrics import tracer
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
    graph = CausalGraph(data_path=PROJECT_ROOT / "data" / "graph.json")
    if not (PROJECT_ROOT / "data" / "graph.json").exists():
        graph.load_topology(PROJECT_ROOT / "sim" / "topology.yaml")
        graph.save_state()
    else:
        graph.load_state()
    inference = InferenceEngine(graph)
    packager = ContextPackager(baselines, graph)
    dispatcher = PraxisCounselDispatcher()
    await dispatcher.listen()
    engine = RuleEngine(PROJECT_ROOT / "rules" / "example.yaml")
    checker = ConstraintChecker(PROJECT_ROOT / "guard" / "constraints.yaml")
    guard_client = GuardClient()
    gatekeeper = GateKeeper()
    act_client = ActClient()
    executor = ActionExecutor(act_client=act_client)
    watcher = ActionMonitor()
    confidence = RuleConfidence(db_path=PROJECT_ROOT / "data" / "confidence.db")
    breaker = CircuitBreaker()
    escalation = EscalationHandler(data_dir=PROJECT_ROOT / "data")
    archive = DecisionArchive(data_dir=PROJECT_ROOT / "data")
    watch_client = WatchClient()
    bridge = RedpandaBridge()
    bridge.start()

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
            with tracer.trace("watch"):
                anomaly_event = watch_client.forward(event)

            if anomaly_event is None:
                with tracer.trace("watch_fallback"):
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
                # Tier 2: Why are we cascading?
                hypotheses = []
                neighbors = graph.get_neighbors(anomaly_event.source)
                if neighbors:
                    df = baselines.get_history(neighbors + [anomaly_event.source], last_n=100)
                    hypotheses = inference.rank_interventions(anomaly_event.source, df)[:3]

                escalation.escalate(anomaly_event, None, None, "circuit breaker tripped", causal_hypotheses=hypotheses)
                emit_escalation(source=LINE_ID, reason="circuit breaker tripped")
                continue

            # Rules
            with tracer.trace("match"):
                proposal = engine.match(anomaly_event)

            if proposal is None:
                logger.info("No rule matched for %s. Analyzing causality...", anomaly_event.source)
                # Tier 2: Root cause analysis
                hypotheses = []
                neighbors = graph.get_neighbors(anomaly_event.source)
                if neighbors:
                    df = baselines.get_history(neighbors + [anomaly_event.source], last_n=100)
                    hypotheses = inference.rank_interventions(anomaly_event.source, df)[:3]

                escalation.escalate(anomaly_event, None, None, "no rule matched", causal_hypotheses=hypotheses)
                continue

            logger.info(
                "Rule matched: %s -> %s (delta %.1f)",
                proposal.rule_name,
                proposal.target,
                proposal.delta,
            )

            # Guard (Shadow Mode)
            with tracer.trace("guard"):
                rust_result = guard_client.validate(proposal)

            with tracer.trace("guard_shadow"):
                py_result = checker.validate(proposal)

            # Consensus & Restrictive Default
            if rust_result is None:
                constraint = py_result
            else:
                constraint = rust_result
                # Constitutional Check: Verify Rust matches Python baseline
                if rust_result.verdict != py_result.verdict:
                    logger.warning(
                        "constitution.violation",
                        extra={
                            "error_code": "GUARD_MISMATCH",
                            "rust_verdict": rust_result.verdict.name,
                            "py_verdict": py_result.verdict.name,
                            "action_id": proposal.action_id,
                        },
                    )
                    # If mismatch, default to Fail for safety
                    if py_result.verdict == Verdict.FAIL or rust_result.verdict == Verdict.FAIL:
                        constraint.verdict = Verdict.FAIL
                        constraint.reason = f"Mismatch (R:{rust_result.verdict.name} P:{py_result.verdict.name})"

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

                # Tier 2 context
                hypotheses = []
                neighbors = graph.get_neighbors(anomaly_event.source)
                if neighbors:
                    df = baselines.get_history(neighbors + [anomaly_event.source], last_n=100)
                    hypotheses = inference.rank_interventions(anomaly_event.source, df)[:3]

                # Tier 3: Asynchronous Counsel from Fleet
                narrative = ""
                diagnostic_intent = ""

                # Assemble and dispatch context
                request = packager.package(anomaly_event, proposal.action_id, hypotheses)
                if await dispatcher.dispatch(request):
                    logger.info("Awaiting fleet counsel for %s", proposal.action_id)
                    # Wait up to 30s for the return trip
                    response = await dispatcher.wait_for_response(proposal.action_id, timeout_s=30.0)
                    if response:
                        logger.info("Received fleet counsel for %s", proposal.action_id)
                        narrative = response.narrative
                        diagnostic_intent = response.diagnostic_intent

                escalation.escalate(
                    anomaly_event,
                    proposal,
                    constraint,
                    gate_reason,
                    causal_hypotheses=hypotheses,
                    counsel_narrative=narrative,
                    diagnostic_intent=diagnostic_intent,
                )
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
            with tracer.trace("act"):
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

    async def log_stats() -> None:
        """Periodically log and save hot-path latency statistics."""
        latency_path = PROJECT_ROOT / "data" / "latency.json"
        while True:
            await asyncio.sleep(60.0)
            stats = tracer.get_stats()
            if stats:
                tracer.save_stats(latency_path)
                logger.info("Hot-path Latency (ms):")
                for component, data in stats.items():
                    logger.info(
                        "  %s: p50=%.2f, p95=%.2f, p99=%.2f (n=%d)",
                        component,
                        data["p50"],
                        data["p95"],
                        data["p99"],
                        data["count"],
                    )

    # --- Start tasks ---
    tasks = [
        asyncio.create_task(plant.run(callback=signal_queue, interval=1.0)),
        asyncio.create_task(process_signals()),
        asyncio.create_task(log_stats()),
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
    tracer.save_stats(PROJECT_ROOT / "data" / "latency.json")
    bridge.stop()
    watch_client.close()
    guard_client.close()
    act_client.close()
    baselines.close()
    patterns.close()
    dispatcher.close()
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
