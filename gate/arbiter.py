"""Stub: Gate arbiter that makes go/no-go decisions on proposed actions.

Combines constraint check results with precedent history to decide
whether an action proceeds, is blocked, or requires escalation.
"""

from __future__ import annotations

from reck.events import ActionProposal, ConstraintResult, GateDecision, Verdict


class GateKeeper:
    """Decides whether a validated proposal may execute."""

    def __init__(self, confidence_threshold: float = 0.3) -> None:
        self.confidence_threshold = confidence_threshold

    def decide(
        self,
        proposal: ActionProposal,
        constraint: ConstraintResult,
        has_precedent: bool,
        rule_confidence: float = 0.5,
        pattern_history: dict | None = None,
    ) -> tuple[GateDecision, str]:
        """Return a gate decision and reason string.

        Logic:
        - FAIL verdict -> NO_GO
        - ESCALATE verdict -> ESCALATE
        - Low confidence -> ESCALATE
        - Novel pattern -> ESCALATE (first-time fix)
        - Otherwise -> GO
        """
        if constraint.verdict is Verdict.FAIL:
            return GateDecision.NO_GO, constraint.reason

        if constraint.verdict is Verdict.ESCALATE:
            return GateDecision.ESCALATE, constraint.reason

        if rule_confidence < self.confidence_threshold:
            return GateDecision.ESCALATE, f"low confidence: {rule_confidence:.2f}"

        # First-time fix check using pattern history
        if pattern_history:
            count = pattern_history["count"]
            success_rate = pattern_history["success_rate"]
            # A pattern seen > 5 times with > 80% success is "known"
            if count > 5 and success_rate > 0.8:
                return GateDecision.GO, "high-confidence pattern match"
            if count < 2:
                return (
                    GateDecision.ESCALATE,
                    "novel anomaly signature requires approval",
                )

        if not has_precedent:
            return GateDecision.ESCALATE, "first-time fix requires approval"

        return GateDecision.GO, "precedent exists, constraints satisfied"
