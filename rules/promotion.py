"""Rule promotion pipeline for Plan 005 Phase 3.

Manages candidates for Tier 1 rules based on pattern performance.
Allows human review and promotion from patterns to YAML rules.
"""

from __future__ import annotations

import fcntl
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import yaml


@dataclass
class RuleCandidate:
    id: int
    source: str
    deviation_type: str
    magnitude_bucket: int
    recipe: str
    occurrence_count: int
    success_rate: float
    last_seen: str


class RulePromoter:
    """Manages rule candidates and the promotion lifecycle."""

    def __init__(self, db_path: Path = Path("data/patterns.db")) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)

    def get_candidates(self, min_occurrences: int = 10, min_success_rate: float = 0.8) -> list[RuleCandidate]:
        """Return patterns that meet the promotion criteria."""
        rows = self._conn.execute(
            """WITH rated AS (
                 SELECT id, source, deviation_type, magnitude_bucket, recipe,
                        occurrence_count,
                        CAST(fix_success_count AS REAL) / (fix_success_count + fix_failure_count) AS rate,
                        last_seen
                 FROM anomaly_patterns
                 WHERE occurrence_count >= ?
                   AND (fix_success_count + fix_failure_count) > 0
               )
               SELECT id, source, deviation_type, magnitude_bucket, recipe,
                      occurrence_count, rate, last_seen
               FROM rated
               WHERE rate >= ?
               ORDER BY occurrence_count DESC""",
            (min_occurrences, min_success_rate),
        ).fetchall()

        return [
            RuleCandidate(
                id=r[0],
                source=r[1],
                deviation_type=r[2],
                magnitude_bucket=r[3],
                recipe=r[4],
                occurrence_count=r[5],
                success_rate=r[6],
                last_seen=r[7],
            )
            for r in rows
        ]

    def _promote_locked(self, rule_name: str, rules_path: Path, build_rule: Callable[[], dict]) -> str:
        """Append a rule to rules_path under a file lock, writing atomically."""
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = rules_path.with_suffix(rules_path.suffix + ".lock")
        with open(lock_path, "w") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                if rules_path.exists():
                    with open(rules_path) as f:
                        data = yaml.safe_load(f) or {"rules": []}
                else:
                    data = {"rules": []}

                if any(r["name"] == rule_name for r in data["rules"]):
                    return rule_name

                data["rules"].append(build_rule())

                fd, tmp_path = tempfile.mkstemp(dir=rules_path.parent, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w") as f:
                        yaml.dump(data, f)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp_path, rules_path)
                except BaseException:
                    os.unlink(tmp_path)
                    raise
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

        return rule_name

    def promote(self, candidate_id: int, rules_path: Path) -> str:
        """Promote a candidate to a YAML rule. Returns the rule name."""
        row = self._conn.execute(
            """SELECT source, deviation_type, magnitude_bucket, recipe
               FROM anomaly_patterns WHERE id = ?""",
            (candidate_id,),
        ).fetchone()

        if not row:
            raise ValueError(f"Candidate {candidate_id} not found")

        source, dev_type, mag, recipe = row
        rule_name = f"auto_{source.replace('/', '_')}_{dev_type}_{mag}"

        # Note: This is a template rule. Real world would need more logic
        # for delta and target, but for the skeleton we use placeholders.
        def build_rule() -> dict:
            return {
                "name": rule_name,
                "source": source,
                "condition": f"deviation > {mag}.0",
                "action": {
                    "target": f"{source}_sp",
                    "delta": -5.0 if dev_type == "high" else 5.0,
                },
                "meta": {
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "pattern_id": candidate_id,
                },
            }

        return self._promote_locked(rule_name, rules_path, build_rule)

    def promote_hypothesis(self, treatment: str, outcome: str, effect: float, rules_path: Path) -> str:
        """Promote a causal hypothesis to a YAML rule."""
        rule_name = f"causal_{treatment.replace('/', '_')}_to_{outcome.replace('/', '_')}"

        # If effect is positive, we need to move treatment in opposite direction
        # to counter a positive deviation in outcome.
        # This is a heuristic for the skeleton.
        delta = -1.0 if effect > 0 else 1.0

        def build_rule() -> dict:
            return {
                "name": rule_name,
                "source": outcome,
                "condition": "deviation > 3.0",
                "action": {
                    "target": f"{treatment}_sp",
                    "delta": delta,
                },
                "meta": {
                    "promoted_at": datetime.now(timezone.utc).isoformat(),
                    "type": "causal_hypothesis",
                    "estimated_effect": effect,
                },
            }

        return self._promote_locked(rule_name, rules_path, build_rule)

    def close(self) -> None:
        self._conn.close()
