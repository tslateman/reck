"""Reactive dispatcher for Tier 3 reasoning.

Dispatches CounselRequests to the ecosystem via 'praxis emit'.
Fulfills the Trigger Router pattern by spawning Shipyard-managed agent fleets.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Callable

import paho.mqtt.client as mqtt
from google.protobuf import json_format
from paho.mqtt.enums import CallbackAPIVersion

from counsel.interface import CounselDispatcher
from proto.reck_pb2 import CounselRequest, CounselResponse

logger = logging.getLogger(__name__)

PRAXIS_BIN = Path.home() / "dev" / "praxis" / "bin" / "praxis"
MQTT_HOST = "localhost"
MQTT_PORT = 1883


class PraxisCounselDispatcher(CounselDispatcher):
    """Dispatches requests via Praxis and waits for results via MQTT."""

    def __init__(self, praxis_bin: Path = PRAXIS_BIN) -> None:
        self._praxis_bin = praxis_bin
        self._callback = None
        self._pending: dict[str, asyncio.Future[CounselResponse]] = {}
        self._mqtt = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self._mqtt.on_message = self._on_message
        self._connected = False

    async def dispatch(self, request: CounselRequest) -> bool:
        """Serialize CounselRequest to JSON and emit via Praxis."""
        if not self._connected:
            logger.warning(
                "counsel.dispatch.unavailable",
                extra={"error_code": "MQTT_NOT_CONNECTED", "action_id": request.action_id},
            )
            return False

        try:
            # 1. Register future for the return trip
            self._pending[request.action_id] = asyncio.get_running_loop().create_future()

            # 2. Convert to JSON for CLI transport
            payload = json_format.MessageToJson(request)

            # 3. Spawn praxis emit --from-triggers
            cmd = [str(self._praxis_bin), "emit", "--from-triggers", payload]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

            logger.info(
                "Dispatched CounselRequest to fleet",
                extra={"action_id": request.action_id, "source": request.anomaly.source},
            )
            return True

        except Exception as exc:
            logger.warning(
                "counsel.dispatch.failed",
                extra={"error": str(exc), "error_code": "PRAXIS_DISPATCH_FAILED", "action_id": request.action_id},
            )
            if request.action_id in self._pending:
                del self._pending[request.action_id]
            return False

    async def wait_for_response(self, action_id: str, timeout_s: float = 30.0) -> CounselResponse | None:
        """Wait for the async response from the fleet."""
        if action_id not in self._pending:
            return None

        future = self._pending[action_id]
        try:
            return await asyncio.wait_for(future, timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning("counsel.response.timeout", extra={"action_id": action_id, "error_code": "FLEET_TIMEOUT"})
            return None
        finally:
            if action_id in self._pending:
                del self._pending[action_id]

    async def listen(self, callback: Callable[[CounselResponse], None] | None = None) -> None:
        """Connect to MQTT and start the background loop."""
        self._callback = callback
        try:
            self._mqtt.connect(MQTT_HOST, MQTT_PORT)
            self._mqtt.subscribe("reck/counsel/results/#")
            # Run paho-mqtt loop in background thread
            self._mqtt.loop_start()
            self._connected = True
            logger.info("Counsel MQTT listener active")
        except Exception as exc:
            logger.warning(
                "counsel.mqtt.connection_failed",
                extra={"error": str(exc), "error_code": "MQTT_CONNECTION_FAILED"},
            )
            self._connected = False

    def _on_message(self, client, userdata, msg):
        """Handle incoming CounselResponse from MQTT."""
        try:
            # Topic: reck/counsel/results/<action_id>
            parts = msg.topic.split("/")
            if len(parts) < 4:
                return
            action_id = parts[3]

            if action_id in self._pending:
                response = CounselResponse()
                json_format.Parse(msg.payload.decode(), response)

                # Resolve the future on the main loop
                loop = self._pending[action_id].get_loop()
                loop.call_soon_threadsafe(self._pending[action_id].set_result, response)

                if self._callback:
                    loop.call_soon_threadsafe(self._callback, response)

        except Exception as exc:
            logger.warning("counsel.mqtt.parse_failed", extra={"error": str(exc), "error_code": "MQTT_PARSE_FAILED"})

    def close(self):
        self._mqtt.loop_stop()
        self._mqtt.disconnect()
