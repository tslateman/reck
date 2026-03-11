"""Tests for Plan 009 Phase 1: Redpanda bridge.

Verifies that RedpandaBridge correctly mirrors MQTT traffic to Kafka.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reck.infra.bridge import RedpandaBridge


def test_bridge_mirrors_mqtt_to_kafka() -> None:
    """Bridge should produce to Kafka when an MQTT message is received."""

    with patch("paho.mqtt.client.Client"), patch("reck.infra.bridge.Producer") as mock_producer_class:
        mock_producer = MagicMock()
        mock_producer_class.return_value = mock_producer

        bridge = RedpandaBridge()

        # Simulate MQTT message
        mock_msg = MagicMock()
        mock_msg.topic = "site1/area1/line1/temp"
        mock_msg.payload = b"22.5"

        # Manually trigger the callback
        bridge._on_message(None, None, mock_msg)

        # Verify Kafka production
        mock_producer.produce.assert_called_once()
        args, kwargs = mock_producer.produce.call_args
        assert kwargs["topic"] == "reck.signals"
        assert kwargs["key"] == "site1/area1/line1/temp"
        assert kwargs["value"] == b"22.5"
