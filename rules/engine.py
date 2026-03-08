"""Stub: Rule engine that matches anomalies against YAML-defined rules.

Loads rules at init, matches anomaly sources via fnmatch glob patterns,
and produces ActionProposals when thresholds are exceeded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import jsonschema
import yaml

from reck.events import ActionProposal, AnomalyEvent

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "reck" / "schemas"


def _validate_rules(data: object) -> None:
    schema = json.loads((_SCHEMA_DIR / "rules.schema.json").read_text())
    jsonschema.validate(data, schema)


@dataclass
class RuleCondition:
    signal_pattern: str
    threshold: float


@dataclass
class RuleAction:
    target_pattern: str
    delta: float


@dataclass
class Rule:
    name: str
    condition: RuleCondition
    action: RuleAction
    confidence: float


class RuleEngine:
    """Matches anomalies against loaded rules and proposes actions."""

    def __init__(self, rules_path: str | Path) -> None:
        self.rules: list[Rule] = []
        self._load(Path(rules_path))

    def _load(self, path: Path) -> None:
        with path.open() as f:
            data = yaml.safe_load(f)
        _validate_rules(data)
        for entry in data.get("rules", []):
            cond = entry["condition"]
            act = entry["action"]
            self.rules.append(
                Rule(
                    name=entry["name"],
                    condition=RuleCondition(
                        signal_pattern=cond["signal_pattern"],
                        threshold=cond["threshold"],
                    ),
                    action=RuleAction(
                        target_pattern=act["target_pattern"],
                        delta=act["delta"],
                    ),
                    confidence=entry["confidence"],
                )
            )

    def match(self, anomaly: AnomalyEvent) -> ActionProposal | None:
        """Return an ActionProposal for the first matching rule, or None."""
        for rule in self.rules:
            if not fnmatch(anomaly.source, rule.condition.signal_pattern):
                continue
            if anomaly.value <= rule.condition.threshold:
                continue
            previous_value = anomaly.baseline_mean
            return ActionProposal(
                source=anomaly.source,
                target=rule.action.target_pattern,
                delta=rule.action.delta,
                previous_value=previous_value,
                proposed_value=previous_value + rule.action.delta,
                rule_name=rule.name,
                confidence=rule.confidence,
            )
        return None
