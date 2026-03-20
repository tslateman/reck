"""Stub: fire-and-forget subprocess bridge to Lore and Praxis CLIs.

Writes are non-blocking. Reck never waits for Lore or Praxis to acknowledge.
Failures are logged at DEBUG level and swallowed -- external CLI availability
must not affect the hot path.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

LORE_BIN = Path(os.environ.get("LORE_BIN", str(Path.home() / "dev" / "lore" / "lore.sh")))
PRAXIS_BIN = Path(os.environ.get("PRAXIS_BIN", str(Path.home() / "dev" / "praxis" / "bin" / "praxis")))
CMUX_BIN = Path(os.environ.get("CMUX_BIN", "/Applications/cmux.app/Contents/Resources/bin/cmux"))


def _spawn(args: list[str]) -> None:
    """Launch subprocess, fire-and-forget. Swallow all errors."""
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        logger.debug("Lore/Praxis subprocess failed: %s", exc)


def write_decision(text: str, tags: str = "reck,decision") -> None:
    """Record a confirmed decision to Lore."""
    _spawn([str(LORE_BIN), "remember", text, "--project", "reck", "--tags", tags])


def write_failure(error_type: str, text: str, tags: str = "reck,failure") -> None:
    """Record a failed/reverted action to Lore."""
    _spawn([str(LORE_BIN), "fail", error_type, text, "--project", "reck", "--tags", tags])


def emit_escalation(source: str, reason: str, rule_name: str = "") -> None:
    """Notify Praxis of an escalation or circuit-breaker trip."""
    payload = json.dumps({"source": source, "reason": reason, "rule_name": rule_name})
    _spawn([str(PRAXIS_BIN), "emit", "--from-triggers", payload])


def notify_cmux(title: str, body: str) -> None:
    """Push a cmux notification. Fire-and-forget, guarded on CMUX_WORKSPACE_ID."""
    if not os.environ.get("CMUX_WORKSPACE_ID") or not CMUX_BIN.is_file():
        return
    _spawn([str(CMUX_BIN), "notify", "--title", title, "--body", body])
