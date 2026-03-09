"""Tests for Plan 007 Phase 2: reactive dispatch.

Verifies that PraxisCounselDispatcher correctly spawns the praxis CLI
with the expected payload.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from counsel.dispatch import PraxisCounselDispatcher
from proto.reck_pb2 import AnomalyEvent, CounselRequest


@pytest.mark.asyncio
async def test_praxis_dispatch_spawns_subprocess() -> None:
    """Dispatcher calls Popen with the correct praxis emit command."""
    request = CounselRequest(action_id="act_123", anomaly=AnomalyEvent(source="test/signal"))

    dispatcher = PraxisCounselDispatcher()

    with patch("subprocess.Popen") as mock_popen:
        success = await dispatcher.dispatch(request)

        assert success is True
        assert mock_popen.called
        args, kwargs = mock_popen.call_args
        cmd = args[0]

        assert "praxis" in cmd[0]
        assert "emit" in cmd[1]
        assert "--from-triggers" in cmd[2]
        # The third arg is the JSON payload
        payload = cmd[3]
        assert '"actionId": "act_123"' in payload
        assert '"source": "test/signal"' in payload
