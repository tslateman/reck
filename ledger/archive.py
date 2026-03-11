"""Stub: decision archive that persists the full decision record.

Stores each decision as a JSON line in data/decisions.jsonl.
Supports querying recent records and checking for precedent
(whether a source+rule combination has been seen before).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from reck.events import DecisionRecord
from reck.lore import notify_cmux, write_decision, write_failure
from reck.serialize import default_serializer


class DecisionArchive:
    """Append-only decision log backed by a JSONL file."""

    def __init__(self, data_dir: Path = Path("data")) -> None:
        self._data_dir = data_dir
        self._path = self._data_dir / "decisions.jsonl"
        self._precedents: set[tuple[str, str]] = set()

    def record(self, decision: DecisionRecord) -> None:
        """Serialize a decision record and append it to the log."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(decision), default=default_serializer) + "\n")
        self._precedents.add((decision.proposal.source, decision.proposal.rule_name))

        if decision.outcome.name == "CONFIRMED":
            rule = decision.proposal.rule_name
            src = decision.proposal.source
            write_decision(
                f"Reck applied {rule} on {src}: delta {decision.proposal.delta:+.1f} -> CONFIRMED",
                tags=f"reck,decision,{rule}",
            )
            notify_cmux(
                f"Reck: {decision.outcome.name}",
                f"{rule} on {src}: delta {decision.proposal.delta:+.1f}",
            )
        elif decision.outcome.name == "REVERTED":
            rule = decision.proposal.rule_name
            src = decision.proposal.source
            delta = decision.kpi_after - decision.kpi_before
            write_failure(
                "ActionReverted",
                f"Reck reverted {rule} on {src}: KPI delta {delta:+.2f}",
                tags=f"reck,failure,{rule}",
            )
            notify_cmux(
                f"Reck: {decision.outcome.name}",
                f"{rule} on {src}: delta {delta:+.2f}",
            )

    def query(self, last_n: int = 10) -> list[dict]:
        """Return the last N decision records."""
        if not self._path.exists():
            return []
        with open(self._path) as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-last_n:]]

    def check_precedent(self, source: str, rule_name: str) -> bool:
        """True if a decision with matching source and rule_name exists."""
        if (source, rule_name) in self._precedents:
            return True
        if not self._path.exists():
            return False
        # Cold-start: scan file once and populate cache
        with open(self._path) as f:
            for line in f:
                record = json.loads(line)
                proposal = record.get("proposal", {})
                self._precedents.add((proposal.get("source", ""), proposal.get("rule_name", "")))
        return (source, rule_name) in self._precedents
