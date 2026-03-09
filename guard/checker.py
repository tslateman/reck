"""Guard component for Plan 008 Phase 1.

Provides a gRPC client for the Rust Guard service and a local
ConstraintChecker for shadow validation.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, cast

import grpc
import jsonschema
import yaml

# Add proto directory to path for generated stubs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "proto"))

from reck.events import ActionProposal, ConstraintResult, Verdict

logger = logging.getLogger(__name__)

_TIMEOUT_S = 0.1  # gRPC budget
_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "reck" / "schemas"


class GuardClient:
    """Non-blocking gRPC client for the Rust Guard service."""

    def __init__(self, port: int = 50051) -> None:
        try:
            import reck_pb2_grpc

            self._channel = grpc.insecure_channel(f"localhost:{port}")
            self._stub = reck_pb2_grpc.GuardServiceStub(self._channel)
            self._available = True
        except ImportError:
            logger.debug("grpcio not available; GuardClient disabled")
            self._available = False

    def validate(self, proposal: ActionProposal) -> ConstraintResult | None:
        """Forward validation to Rust. Returns ConstraintResult if successful."""
        if not self._available:
            return None

        try:
            import reck_pb2

            # Convert internal dataclass to proto
            proto_proposal = reck_pb2.ActionProposal(
                action_id=proposal.action_id,
                source=proposal.source,
                target=proposal.target,
                delta=proposal.delta,
                previous_value=proposal.previous_value,
                proposed_value=proposal.proposed_value,
                rule_name=proposal.rule_name,
                confidence=proposal.confidence,
                lifecycle=cast(Any, int(proposal.lifecycle.value)),
                action_chain_id=proposal.action_chain_id,
                rollback_window_s=proposal.rollback_window_s,
            )

            res = self._stub.ValidateProposal(proto_proposal, timeout=_TIMEOUT_S)

            # Convert proto result back to internal dataclass
            return ConstraintResult(
                action_id=res.action_id,
                verdict=Verdict(res.verdict),
                violated_constraint=res.violated_constraint,
                reason=res.reason,
            )
        except Exception as exc:
            logger.warning(
                "guard.client.failed",
                extra={
                    "error": str(exc),
                    "error_code": "GRPC_GUARD_FAILED",
                    "action_id": proposal.action_id,
                },
            )
            return None

    def close(self) -> None:
        if self._available:
            self._channel.close()


@dataclass
class Constraint:
    parameter: str
    min: float
    max: float
    unit: str
    rate_of_change: float
    requires_approval: bool = False


def _validate_constraints(data: object) -> None:
    schema = json.loads((_SCHEMA_DIR / "constraints.schema.json").read_text())
    jsonschema.validate(data, schema)
    if isinstance(data, dict):
        for c in data.get("constraints", []):
            if c.get("min", 0) >= c.get("max", 0):
                raise ValueError(f"Constraint '{c.get('parameter', '?')}': min >= max")


class ConstraintChecker:
    """Validates proposals against loaded safety constraints (Python implementation)."""

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
                        f"proposed value {proposal.proposed_value} below minimum {constraint.min} {constraint.unit}"
                    ),
                )

            if proposal.proposed_value > constraint.max:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.FAIL,
                    violated_constraint=constraint.parameter,
                    reason=(
                        f"proposed value {proposal.proposed_value} exceeds maximum {constraint.max} {constraint.unit}"
                    ),
                )

            if abs(proposal.delta) > constraint.rate_of_change:
                return ConstraintResult(
                    action_id=proposal.action_id,
                    verdict=Verdict.FAIL,
                    violated_constraint=constraint.parameter,
                    reason=(f"delta {abs(proposal.delta)} exceeds rate-of-change limit {constraint.rate_of_change}"),
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
