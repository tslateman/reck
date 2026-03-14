"""Rule confidence tracker using Bayesian Beta distribution.

Tracks success/failure outcomes per rule and updates confidence scores.
Confidence decays toward the prior (0.5) for rules that have not fired
recently.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path

_UPSERT = "INSERT OR IGNORE INTO rule_confidence (rule_name, alpha, beta, updated_at) VALUES (?, 1.0, 1.0, ?)"


class RuleConfidence:
    def __init__(self, db_path: Path = Path("data/confidence.db")) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS rule_confidence (
                rule_name TEXT PRIMARY KEY,
                alpha REAL NOT NULL DEFAULT 1.0,
                beta REAL NOT NULL DEFAULT 1.0,
                last_fired TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
        self._conn.commit()

    def get(self, rule_name: str) -> float:
        """Return confidence = alpha / (alpha + beta). Default 0.5."""
        row = self._conn.execute(
            "SELECT alpha, beta FROM rule_confidence WHERE rule_name = ?",
            (rule_name,),
        ).fetchone()
        if row is None:
            return 0.5
        alpha, beta = row
        return alpha / (alpha + beta)

    def update(self, rule_name: str, success: bool) -> float:
        """Bayesian update. Returns new confidence.

        Success increments alpha; failure increments beta.
        """
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(_UPSERT, (rule_name, now))
        if success:
            self._conn.execute(
                "UPDATE rule_confidence SET alpha = alpha + 1, updated_at = ? WHERE rule_name = ?",
                (now, rule_name),
            )
        else:
            self._conn.execute(
                "UPDATE rule_confidence SET beta = beta + 1, updated_at = ? WHERE rule_name = ?",
                (now, rule_name),
            )
        self._conn.commit()
        return self.get(rule_name)

    def decay(
        self,
        rule_name: str,
        days_since_last_fire: float,
        half_life_days: float = 30.0,
    ) -> float:
        """Decay alpha and beta toward 1.0 using exponential decay.

        decay_factor = 0.5 ** (days / half_life_days)
        new_alpha = 1.0 + (alpha - 1.0) * decay_factor
        new_beta  = 1.0 + (beta  - 1.0) * decay_factor
        Returns new confidence.
        """
        row = self._conn.execute(
            "SELECT alpha, beta FROM rule_confidence WHERE rule_name = ?",
            (rule_name,),
        ).fetchone()
        if row is None:
            return 0.5
        alpha, beta = row
        factor = 0.5 ** (days_since_last_fire / half_life_days)
        new_alpha = 1.0 + (alpha - 1.0) * factor
        new_beta = 1.0 + (beta - 1.0) * factor
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE rule_confidence SET alpha = ?, beta = ?, updated_at = ? WHERE rule_name = ?",
            (new_alpha, new_beta, now, rule_name),
        )
        self._conn.commit()
        return new_alpha / (new_alpha + new_beta)

    def record_fired(self, rule_name: str) -> None:
        """Update last_fired timestamp. Creates row if missing."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(_UPSERT, (rule_name, now))
        self._conn.execute(
            "UPDATE rule_confidence SET last_fired = ?, updated_at = ? WHERE rule_name = ?",
            (now, now, rule_name),
        )
        self._conn.commit()

    def apply_pending_decay(self) -> None:
        """Apply decay to all rules not fired in over 1 day."""
        now = datetime.now(timezone.utc)
        rows = self._conn.execute(
            "SELECT rule_name, last_fired FROM rule_confidence WHERE last_fired IS NOT NULL"
        ).fetchall()
        for rule_name, last_fired_str in rows:
            last_fired = datetime.fromisoformat(last_fired_str)
            days = (now - last_fired).total_seconds() / 86400.0
            if days > 1.0:
                self.decay(rule_name, days)

    def get_distribution(self, rule_name: str) -> tuple[float, float]:
        """Return (alpha, beta) for *rule_name*. Default (1.0, 1.0)."""
        row = self._conn.execute(
            "SELECT alpha, beta FROM rule_confidence WHERE rule_name = ?",
            (rule_name,),
        ).fetchone()
        if row is None:
            return (1.0, 1.0)
        return (row[0], row[1])

    def credible_interval(self, rule_name: str, width: float = 0.9) -> tuple[float, float]:
        """Normal approximation credible interval for Beta(a, b).

        Uses the Wilson score style formula:
            mean = a / (a + b)
            std  = sqrt(a * b / ((a + b)**2 * (a + b + 1)))
            interval = mean +/- z * std

        Returns (lower, upper) clamped to [0, 1].
        """
        z_map = {0.9: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_map.get(width, 1.645)

        a, b = self.get_distribution(rule_name)
        n = a + b
        mean = a / n
        std = sqrt(a * b / (n**2 * (n + 1)))
        lower = max(0.0, mean - z * std)
        upper = min(1.0, mean + z * std)
        return (lower, upper)

    def close(self) -> None:
        self._conn.close()
