"""Stub: Constraint checker that validates action proposals against safety bounds.

Loads constraints from YAML. Checks proposed values against min/max range
and rate-of-change limits. Returns PASS, FAIL, or ESCALATE verdicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import jsonschema
import yaml

from reck.events import ActionProposal, ConstraintResult, Verdict

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "reck" / "schemas"


def _validate_constraints(data: object) -> None:
    schema = json.loads((_SCHEMA_DIR / "constraints.schema.json").read_text())
    jsonschema.validate(data, schema)
    if isinstance(data, dict):
        for c in data.get("constraints", []):
            if c.get("min", 0) >= c.get("max", 0):
                raise ValueError(f"Constraint '{c.get('parameter', '?')}': min >= max")


@dataclass
class Constraint:
    parameter: str
    min: float
    max: float
    unit: str
    rate_of_change: float
    requires_approval: bool = False


class ConstraintChecker:
    """Validates proposals against loaded safety constraints."""

    def __init__(self, constraints_path: str | Path) -> None:
        self.constraints: list[Constraint] = []
        self._load(Path(constraints_path))

    def _load(self, path: Path) -> None:
        with path.open() as f:
            data = yaml.safe_load(f)
        _validate_constraints(data)
        for entry in data.get("constraints", []):
            self.constraints.append(
                Constraint(
                    parameter=entry["parameter"],
                    min=entry["min"],
                    max=entry["max"],
                    unit=entry["unit"],
                    rate_of_change=entry["rate_of_change"],
                    requires_approval=entry.get("requires_approval", False),
                )
            )

    def validate(self, proposal: ActionProposal) -> ConstraintResult:
        """Check proposal against all matching constraints."""
        for constraint in self.constraints:
            if not fnmatch(proposal.target, constraint.parameter):
                continue

            if proposal.proposed_value < constraint.min:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.FAIL,
                    violated_constraint=constraint.parameter,
                    reason=(
                        f"proposed value {proposal.proposed_value} "
                        f"below minimum {constraint.min} {constraint.unit}"
                    ),
                )

            if proposal.proposed_value > constraint.max:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.FAIL,
                    violated_constraint=constraint.parameter,
                    reason=(
                        f"proposed value {proposal.proposed_value} "
                        f"exceeds maximum {constraint.max} {constraint.unit}"
                    ),
                )

            if abs(proposal.delta) > constraint.rate_of_change:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.FAIL,
                    violated_constraint=constraint.parameter,
                    reason=(
                        f"delta {abs(proposal.delta)} exceeds "
                        f"rate-of-change limit {constraint.rate_of_change}"
                    ),
                )

            if constraint.requires_approval:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.ESCALATE,
                    violated_constraint=constraint.parameter,
                    reason="constraint requires human approval",
                )

        return ConstraintResult(
            action_id=proposal.action_id,
            verdict=Verdict.PASS,
        )
