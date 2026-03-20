"""Redpanda Bridge for Phase 1 of Plan 009.

Mirrors MQTT signal traffic to a durable Redpanda topic.
Fulfills the 'Durable Log' requirement for high-fidelity auditing and replay.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import paho.mqtt.client as mqtt
from confluent_kafka import Producer

# Add proto directory to path for generated stubs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "proto"))

from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger(__name__)

MQTT_HOST = "localhost"
MQTT_PORT = 1883
KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "reck.signals"
DLQ_DIR = Path("data/dlq")

# Circuit breaker: trip after this many consecutive Kafka failures
_CB_THRESHOLD = 5
_CB_RESET_S = 30


class RedpandaBridge:
    """Mirrors MQTT signals to Redpanda (Kafka)."""

    def __init__(
        self,
        mqtt_host: str = MQTT_HOST,
        mqtt_port: int = MQTT_PORT,
        kafka_bootstrap: str = KAFKA_BOOTSTRAP,
        dlq_dir: Path = DLQ_DIR,
    ) -> None:
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._dlq_dir = dlq_dir

        # Kafka Producer configuration
        self._producer = Producer(
            {
                "bootstrap.servers": kafka_bootstrap,
                "client.id": "reck-bridge",
                "acks": "all",  # Ensure durability
            }
        )

        # MQTT Client configuration
        self._mqtt = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self._mqtt.on_message = self._on_message
        self._mqtt.on_connect = self._on_connect
        self._connected = False

        # Circuit breaker state
        self._kafka_failures = 0
        self._kafka_tripped = False
        self._kafka_trip_time: float = 0

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Bridge connected to EMQX")
            # Subscribe to all signals under the ecosystem root
            client.subscribe("site1/#")
            self._connected = True
        else:
            logger.error(f"Bridge failed to connect to EMQX: {rc}")

    def _kafka_circuit_open(self) -> bool:
        """Check if the Kafka circuit breaker is tripped."""
        if not self._kafka_tripped:
            return False
        import time

        if time.monotonic() - self._kafka_trip_time > _CB_RESET_S:
            logger.info("bridge.kafka.circuit_reset")
            self._kafka_tripped = False
            self._kafka_failures = 0
            return False
        return True

    def _write_dlq(self, topic: str, payload: bytes) -> None:
        """Append failed message to a dead-letter file for later replay."""
        import json
        import time

        self._dlq_dir.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"topic": topic, "payload": payload.decode("utf-8", errors="replace"), "ts": time.time()})
        with open(self._dlq_dir / "bridge.jsonl", "a") as f:
            f.write(entry + "\n")

    def _on_message(self, client, userdata, msg):
        """Forward MQTT message to Kafka with circuit breaker and DLQ."""
        if self._kafka_circuit_open():
            self._write_dlq(msg.topic, msg.payload)
            return

        try:
            self._producer.produce(
                topic=KAFKA_TOPIC, key=msg.topic, value=msg.payload, on_delivery=self._delivery_report
            )
            # Trigger delivery callbacks (async)
            self._producer.poll(0)

        except Exception as exc:
            logger.warning("bridge.forward.failed", extra={"topic": msg.topic, "error": str(exc)})
            self._kafka_failures += 1
            if self._kafka_failures >= _CB_THRESHOLD:
                import time

                self._kafka_tripped = True
                self._kafka_trip_time = time.monotonic()
                logger.warning("bridge.kafka.circuit_tripped", extra={"failures": self._kafka_failures})
            self._write_dlq(msg.topic, msg.payload)

    def _delivery_report(self, err, msg):
        """Callback for Kafka delivery reports."""
        if err is not None:
            logger.warning(f"Bridge failed to deliver to Redpanda: {err}")
            self._kafka_failures += 1
        else:
            self._kafka_failures = 0

    def start(self) -> None:
        """Connect to MQTT and start the bridge loop."""
        try:
            self._mqtt.connect(self._mqtt_host, self._mqtt_port)
            self._mqtt.loop_start()
        except Exception as exc:
            logger.warning(
                "bridge.mqtt.connection_failed", extra={"error": str(exc), "error_code": "BRIDGE_MQTT_FAILED"}
            )

    def stop(self) -> None:
        """Graceful shutdown."""
        self._mqtt.loop_stop()
        self._mqtt.disconnect()
        # Ensure all Kafka messages are flushed
        self._producer.flush()
        logger.info("Redpanda bridge stopped")
