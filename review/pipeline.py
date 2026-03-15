"""Review pipeline: run checks in manifest order, short-circuit on first FAIL."""

from __future__ import annotations

from reck.events import AgentResult, CheckResult, Verdict
from review.checks import CheckFn


def run_checks(result: AgentResult, checks: list[tuple[CheckFn, dict]]) -> list[CheckResult]:
    """Execute checks in order. First FAIL short-circuits. ESCALATE propagates immediately."""
    results: list[CheckResult] = []

    for check_fn, criteria in checks:
        check_result = check_fn(result, criteria)
        results.append(check_result)

        if check_result.verdict is Verdict.ESCALATE:
            break
        if check_result.verdict is Verdict.FAIL:
            break

    return results
