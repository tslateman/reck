"""Shared event types for internal Python communication.

Stub: lightweight dataclasses mirroring proto/reck.proto.
Components pass these internally; protobuf serialization happens
at the MQTT and gRPC boundaries only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto


class Priority(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()


class ActionLifecycle(Enum):
    PROPOSED = auto()
    VALIDATED = auto()
    EXECUTING = auto()
    MONITORING = auto()
    CONFIRMED = auto()
    REVERTED = auto()
    FAILED = auto()


class Verdict(Enum):
    PASS = auto()
    FAIL = auto()
    ESCALATE = auto()


class GateDecision(Enum):
    GO = auto()
    NO_GO = auto()
    ESCALATE = auto()


@dataclass
class EventContext:
    recipe: str = ""
    batch: str = ""
    operator_shift: str = ""


@dataclass
class SignalEvent:
    source: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    state_transition: str = ""
    context: EventContext = field(default_factory=EventContext)


@dataclass
class AnomalyEvent:
    source: str
    value: float
    baseline_mean: float
    baseline_stddev: float
    deviation_sigma: float
    priority: Priority = Priority.LOW
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    context: EventContext = field(default_factory=EventContext)


@dataclass
class ActionProposal:
    source: str
    target: str
    delta: float
    previous_value: float
    proposed_value: float
    rule_name: str
    confidence: float
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    lifecycle: ActionLifecycle = ActionLifecycle.PROPOSED
    action_chain_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    rollback_window_s: int = 60


@dataclass
class ConstraintResult:
    action_id: str
    verdict: Verdict
    violated_constraint: str = ""
    reason: str = ""


class ReviewOutcome(Enum):
    PASS = auto()
    FAIL = auto()
    ESCALATE = auto()


class Recommendation(Enum):
    SURFACE = auto()
    RETRY = auto()
    ESCALATE = auto()


@dataclass
class AgentResult:
    """Input envelope wrapping background agent output."""

    agent_name: str
    structured_result: dict = field(default_factory=dict)
    raw_output: str = ""
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    attempt: int = 1
    prior_results: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    _AGENT_NAME_RE = __import__("re").compile(r"^[a-zA-Z0-9_-]+$")

    def __post_init__(self) -> None:
        if not self._AGENT_NAME_RE.match(self.agent_name):
            raise ValueError(f"agent_name must match ^[a-zA-Z0-9_-]+$, got {self.agent_name!r}")


@dataclass
class CheckResult:
    """Output of one check function."""

    check_name: str
    verdict: Verdict
    confidence: float = 1.0
    reason: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class ReviewVerdict:
    """Final pipeline output, serialized to JSON on stdout."""

    run_id: str
    agent_name: str
    attempt: int
    verdict: ReviewOutcome
    confidence: float
    issues: list[str] = field(default_factory=list)
    check_results: list[CheckResult] = field(default_factory=list)
    recommendation: Recommendation = Recommendation.SURFACE
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DecisionRecord:
    action_id: str
    anomaly: AnomalyEvent
    proposal: ActionProposal
    constraint_check: ConstraintResult
    gate_decision: GateDecision
    outcome: ActionLifecycle
    action_chain_id: str = ""
    escalation_reason: str = ""
    kpi_before: float = 0.0
    kpi_after: float = 0.0
    monitoring_duration_s: int = 0
    gear: int = 0
    confidence_at_decision: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
