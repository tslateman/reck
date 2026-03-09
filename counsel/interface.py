"""Mock boundary for Tier 3 Reactive Dispatch.

Defines the interface for sending requests to the fleet and receiving responses.
Allows 'just test' to run without real Praxis or MQTT dependencies.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Callable

from proto.reck_pb2 import CounselRequest, CounselResponse


class CounselDispatcher(ABC):
    """Interface for dispatching CounselRequests to the ecosystem."""

    @abstractmethod
    async def dispatch(self, request: CounselRequest) -> bool:
        """Send the request to the fleet. Returns True if successfully sent."""
        pass

    @abstractmethod
    async def listen(self, callback: Callable[[CounselResponse], None]) -> None:
        """Start listening for responses from the fleet."""
        pass


class MockCounselDispatcher(CounselDispatcher):
    """In-memory mock for 'just test'. Simulates async return trip."""

    def __init__(self, delay_s: float = 0.1) -> None:
        self.delay_s = delay_s
        self.callback: Callable[[CounselResponse], None] | None = None

    async def dispatch(self, request: CounselRequest) -> bool:
        """Wait briefly and then trigger the callback with a mock response."""
        if not self.callback:
            return False

        async def respond():
            await asyncio.sleep(self.delay_s)
            response = CounselResponse(
                action_id=request.action_id,
                narrative=f"Mock explanation for {request.anomaly.source}",
                diagnostic_intent="mock_vibration_sweep",
                agent_confidence=0.95,
            )
            if self.callback:
                self.callback(response)

        asyncio.create_task(respond())
        return True

    async def listen(self, callback: Callable[[CounselResponse], None]) -> None:
        """Store the callback for simulated responses."""
        self.callback = callback
