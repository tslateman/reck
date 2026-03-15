"""Unit tests for the review pipeline: ordering, short-circuit, and escalation propagation."""

from __future__ import annotations

from reck.events import AgentResult, CheckResult, ReviewOutcome, Verdict
from review.pipeline import run_checks
from review.verdict import build_verdict


def _pass_check(result: AgentResult, criteria: dict) -> CheckResult:
    return CheckResult(check_name="pass_check", verdict=Verdict.PASS)


def _fail_check(result: AgentResult, criteria: dict) -> CheckResult:
    return CheckResult(check_name="fail_check", verdict=Verdict.FAIL, confidence=0.0, reason="something broke")


def _escalate_check(result: AgentResult, criteria: dict) -> CheckResult:
    return CheckResult(check_name="escalate_check", verdict=Verdict.ESCALATE, confidence=0.0, reason="critical issue")


def _make_result() -> AgentResult:
    return AgentResult(agent_name="test-agent", structured_result={"summary": {}})


# --- Pipeline tests ---


def test_all_pass() -> None:
    result = _make_result()
    checks = [(_pass_check, {}), (_pass_check, {})]
    results = run_checks(result, checks)
    assert len(results) == 2
    assert all(r.verdict is Verdict.PASS for r in results)


def test_first_fail_short_circuits() -> None:
    result = _make_result()
    checks = [(_pass_check, {}), (_fail_check, {}), (_pass_check, {})]
    results = run_checks(result, checks)
    assert len(results) == 2
    assert results[0].verdict is Verdict.PASS
    assert results[1].verdict is Verdict.FAIL


def test_escalate_propagates_immediately() -> None:
    result = _make_result()
    checks = [(_escalate_check, {}), (_pass_check, {})]
    results = run_checks(result, checks)
    assert len(results) == 1
    assert results[0].verdict is Verdict.ESCALATE


def test_empty_checks() -> None:
    result = _make_result()
    results = run_checks(result, [])
    assert results == []


# --- Verdict builder tests ---


def test_verdict_pass() -> None:
    result = _make_result()
    checks = [CheckResult(check_name="a", verdict=Verdict.PASS)]
    verdict = build_verdict(result, checks)
    assert verdict.verdict is ReviewOutcome.PASS
    assert verdict.issues == []
    assert verdict.confidence == 1.0


def test_verdict_fail() -> None:
    result = _make_result()
    checks = [
        CheckResult(check_name="a", verdict=Verdict.PASS),
        CheckResult(check_name="b", verdict=Verdict.FAIL, confidence=0.0, reason="bad"),
    ]
    verdict = build_verdict(result, checks)
    assert verdict.verdict is ReviewOutcome.FAIL
    assert "bad" in verdict.issues
    assert verdict.confidence == 0.5


def test_verdict_escalate() -> None:
    result = _make_result()
    checks = [CheckResult(check_name="a", verdict=Verdict.ESCALATE, confidence=0.0, reason="critical")]
    verdict = build_verdict(result, checks)
    assert verdict.verdict is ReviewOutcome.ESCALATE
