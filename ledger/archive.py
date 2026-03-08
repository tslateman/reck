"""Stub: decision archive that persists the full decision record.

Stores each decision as a JSON line in data/decisions.jsonl.
Supports querying recent records and checking for precedent
(whether a source+rule combination has been seen before).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from reck.events import DecisionRecord


def _serialize(obj: object) -> object:
    """JSON serializer for dataclasses containing enums and datetimes."""
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialize {type(obj)}")


class DecisionArchive:
    """Append-only decision log backed by a JSONL file."""

    def __init__(self, data_dir: Path = Path("data")) -> None:
        self._data_dir = data_dir
        self._path = self._data_dir / "decisions.jsonl"

    def record(self, decision: DecisionRecord) -> None:
        """Serialize a decision record and append it to the log."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a") as f:
            f.write(json.dumps(asdict(decision), default=_serialize) + "\n")

    def query(self, last_n: int = 10) -> list[dict]:
        """Return the last N decision records."""
        if not self._path.exists():
            return []
        with open(self._path) as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines[-last_n:]]

    def check_precedent(self, source: str, rule_name: str) -> bool:
        """True if a decision with matching source and rule_name exists."""
        if not self._path.exists():
            return False
        with open(self._path) as f:
            for line in f:
                record = json.loads(line)
                proposal = record.get("proposal", {})
                if (
                    proposal.get("source") == source
                    and proposal.get("rule_name") == rule_name
                ):
                    return True
        return False
