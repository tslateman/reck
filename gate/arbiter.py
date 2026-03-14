"""Gate arbiter that makes go/no-go decisions on proposed actions.

Combines constraint check results with the gear-based autonomy model
to decide whether an action proceeds, is blocked, or requires escalation.
"""

from __future__ import annotations

from reck.events import ActionProposal, ConstraintResult, GateDecision, Verdict
from reck.gear import DEFAULT_THRESHOLDS, Gear, select_gear


class GateKeeper:
    """Decides whether a validated proposal may execute."""

    def __init__(self, thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS) -> None:
        self.thresholds = thresholds

    def decide(
        self,
        proposal: ActionProposal,  # noqa: ARG002
        constraint: ConstraintResult,
        has_precedent: bool,
        rule_confidence: float = 0.5,
        pattern_history: dict | None = None,
        gear: Gear | None = None,
    ) -> tuple[GateDecision, str]:
        """Return a gate decision and reason string.

        Safety invariants checked first (override gear logic):
        1. FAIL verdict -> NO_GO
        2. ESCALATE verdict -> ESCALATE
        Then gear is computed (if not provided), followed by:
        3. Novel pattern (count < 2) -> ESCALATE
        4. No precedent -> ESCALATE
        5. Gear determines outcome (1st/2nd ESCALATE, 3rd+ GO)
        """
        # --- Safety invariants (trump gears) ---
        if constraint.verdict is Verdict.FAIL:
            return GateDecision.NO_GO, constraint.reason

        if constraint.verdict is Verdict.ESCALATE:
            return GateDecision.ESCALATE, constraint.reason

        # --- Compute gear ---
        if gear is None:
            gear = select_gear(rule_confidence, self.thresholds)

        # --- Novel pattern check ---
        if pattern_history and pattern_history["count"] < 2:
            return (
                GateDecision.ESCALATE,
                "novel anomaly signature requires approval",
            )

        # --- First-time fix check ---
        if not has_precedent:
            return GateDecision.ESCALATE, "first-time fix requires approval"

        # --- Gear-based decision ---
        if gear is Gear.FIRST:
            return GateDecision.ESCALATE, "1st gear: human approval required"
        if gear is Gear.SECOND:
            return GateDecision.ESCALATE, "2nd gear: suggest fix, awaiting gate"
        if gear is Gear.THIRD:
            return GateDecision.GO, "3rd gear: established pattern, close monitoring"
        if gear is Gear.FOURTH:
            return GateDecision.GO, "4th gear: proven pattern"
        # Gear.FIFTH
        return GateDecision.GO, "5th gear: crystallized, autonomous"
