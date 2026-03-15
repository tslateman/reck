"""Build a ReviewVerdict from pipeline check results."""

from __future__ import annotations

from reck.events import (
    AgentResult,
    CheckResult,
    Recommendation,
    ReviewOutcome,
    ReviewVerdict,
    Verdict,
)


def build_verdict(result: AgentResult, check_results: list[CheckResult]) -> ReviewVerdict:
    """Aggregate check results into a final ReviewVerdict."""
    issues = [cr.reason for cr in check_results if cr.verdict is not Verdict.PASS and cr.reason]

    # Determine overall outcome
    has_escalate = any(cr.verdict is Verdict.ESCALATE for cr in check_results)
    has_fail = any(cr.verdict is Verdict.FAIL for cr in check_results)

    if has_escalate:
        outcome = ReviewOutcome.ESCALATE
    elif has_fail:
        outcome = ReviewOutcome.FAIL
    else:
        outcome = ReviewOutcome.PASS

    # Mean confidence across checks
    if check_results:
        confidence = sum(cr.confidence for cr in check_results) / len(check_results)
    else:
        confidence = 0.0

    # Recommendation
    if outcome is ReviewOutcome.ESCALATE:
        recommendation = Recommendation.ESCALATE
    elif outcome is ReviewOutcome.FAIL:
        recommendation = Recommendation.RETRY
    else:
        recommendation = Recommendation.SURFACE

    return ReviewVerdict(
        run_id=result.run_id,
        agent_name=result.agent_name,
        attempt=result.attempt,
        verdict=outcome,
        confidence=confidence,
        issues=issues,
        check_results=check_results,
        recommendation=recommendation,
    )
