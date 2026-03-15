"""3-strike escalation: aggregate context after repeated failures."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from reck.events import ReviewVerdict
from reck.lore import notify_cmux
from reck.serialize import default_serializer

_SECRET_PATTERNS = [
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"sk-\S+"),
    re.compile(r"AKIA\S+"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
]

_RAW_OUTPUT_MAX = 4096


@dataclass
class ReviewEscalationRecord:
    """Full context after 3 consecutive failures."""

    run_id: str
    agent_name: str
    total_attempts: int
    verdicts: list[ReviewVerdict]
    raw_outputs: list[str]
    suggested_action: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _scrub_secrets(text: str) -> str:
    """Strip known secret patterns from text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _truncate_and_scrub(text: str) -> str:
    """Truncate to 4KB and scrub secrets."""
    truncated = text[:_RAW_OUTPUT_MAX]
    return _scrub_secrets(truncated)


class ReviewEscalationHandler:
    """Writes escalation records to JSONL and notifies Cmux."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def escalate(
        self,
        agent_name: str,
        run_id: str,
        verdicts: list[ReviewVerdict],
        raw_outputs: list[str],
    ) -> ReviewEscalationRecord:
        """Build and persist an escalation record."""
        record = ReviewEscalationRecord(
            run_id=run_id,
            agent_name=agent_name,
            total_attempts=len(verdicts),
            verdicts=verdicts,
            raw_outputs=[_truncate_and_scrub(o) for o in raw_outputs],
            suggested_action=f"Manual review required for {agent_name} after {len(verdicts)} failed attempts",
        )

        review_dir = self._data_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        path = review_dir / "escalations.jsonl"

        with open(path, "a") as f:
            f.write(json.dumps(asdict(record), default=default_serializer, ensure_ascii=True) + "\n")

        # Notify via Cmux -- verdict summary and file pointer, not raw content
        all_issues = [issue for v in verdicts for issue in v.issues]
        summary = "; ".join(all_issues[:3]) if all_issues else "repeated failures"
        notify_cmux(
            f"Reck review: {agent_name} escalated",
            f"{summary} (see {path})",
        )

        return record
