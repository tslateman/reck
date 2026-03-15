"""Unit tests for individual review checks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from reck.events import AgentResult, Verdict
from review.checks.historical import historical_check
from review.checks.reproducibility import reproducibility_check
from review.checks.schema import schema_check

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# --- Schema check ---


def test_schema_check_passes_valid_result(tmp_path: Path) -> None:
    schema = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "object"}}}
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(schema))

    result = AgentResult(agent_name="test-agent", structured_result={"summary": {}})
    cr = schema_check(result, {"schema_path": str(schema_file)})
    assert cr.verdict is Verdict.PASS


def test_schema_check_fails_invalid_result(tmp_path: Path) -> None:
    schema = {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "object"}}}
    schema_file = tmp_path / "schema.json"
    schema_file.write_text(json.dumps(schema))

    result = AgentResult(agent_name="test-agent", structured_result={"wrong": "shape"})
    cr = schema_check(result, {"schema_path": str(schema_file)})
    assert cr.verdict is Verdict.FAIL
    assert "summary" in cr.reason


def test_schema_check_fails_missing_schema_path() -> None:
    result = AgentResult(agent_name="test-agent", structured_result={})
    cr = schema_check(result, {})
    assert cr.verdict is Verdict.FAIL
    assert "schema_path" in cr.reason


def test_schema_check_fails_missing_schema_file() -> None:
    result = AgentResult(agent_name="test-agent", structured_result={})
    cr = schema_check(result, {"schema_path": "/nonexistent/schema.json"})
    assert cr.verdict is Verdict.FAIL
    assert "not found" in cr.reason


# --- Historical range check ---


def test_historical_passes_within_range() -> None:
    result = AgentResult(
        agent_name="test-agent",
        structured_result={"summary": {"failure_count": 5}},
        prior_results=[
            {"summary": {"failure_count": 4}},
            {"summary": {"failure_count": 5}},
            {"summary": {"failure_count": 6}},
            {"summary": {"failure_count": 5}},
        ],
    )
    cr = historical_check(result, {"metric_path": "summary.failure_count", "sigma_threshold": 3.0})
    assert cr.verdict is Verdict.PASS


def test_historical_fails_outside_range() -> None:
    result = AgentResult(
        agent_name="test-agent",
        structured_result={"summary": {"failure_count": 100}},
        prior_results=[
            {"summary": {"failure_count": 4}},
            {"summary": {"failure_count": 5}},
            {"summary": {"failure_count": 6}},
            {"summary": {"failure_count": 5}},
        ],
    )
    cr = historical_check(result, {"metric_path": "summary.failure_count", "sigma_threshold": 3.0})
    assert cr.verdict is Verdict.FAIL
    assert "z-score" in cr.reason


def test_historical_passes_insufficient_history() -> None:
    result = AgentResult(
        agent_name="test-agent",
        structured_result={"summary": {"failure_count": 5}},
        prior_results=[{"summary": {"failure_count": 4}}],
    )
    cr = historical_check(result, {"metric_path": "summary.failure_count"})
    assert cr.verdict is Verdict.PASS
    assert "Insufficient" in cr.reason


def test_historical_fails_missing_metric() -> None:
    result = AgentResult(agent_name="test-agent", structured_result={"summary": {}})
    cr = historical_check(result, {"metric_path": "summary.failure_count"})
    assert cr.verdict is Verdict.FAIL
    assert "not found" in cr.reason


def test_historical_fails_no_metric_path() -> None:
    result = AgentResult(agent_name="test-agent", structured_result={})
    cr = historical_check(result, {})
    assert cr.verdict is Verdict.FAIL
    assert "metric_path" in cr.reason


# --- Reproducibility check ---


def test_reproducibility_passes_no_template() -> None:
    result = AgentResult(agent_name="test-agent", structured_result={})
    cr = reproducibility_check(result, {})
    assert cr.verdict is Verdict.PASS
    assert "skipping" in cr.reason


def test_reproducibility_passes_no_failures_reported() -> None:
    result = AgentResult(
        agent_name="test-agent",
        structured_result={"checks": {"failed": [], "passed": ["a"]}},
    )
    cr = reproducibility_check(
        result,
        {"command_template": ["echo", "{check_name}"], "failure_key_path": "checks.failed"},
    )
    assert cr.verdict is Verdict.PASS


def test_reproducibility_detects_false_positive() -> None:
    """If a 'failed' check passes on re-run, that's a false positive -> FAIL."""

    def mock_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="ok", stderr="")

    result = AgentResult(
        agent_name="test-agent",
        structured_result={"checks": {"failed": ["prose-lint"], "passed": []}},
    )
    cr = reproducibility_check(
        result,
        {"command_template": ["test-bin", "check", "--only", "{check_name}"], "failure_key_path": "checks.failed"},
        run_command=mock_run,
    )
    assert cr.verdict is Verdict.FAIL
    assert "prose-lint" in cr.reason


def test_reproducibility_passes_confirmed_failure() -> None:
    """If a 'failed' check still fails on re-run, the report is accurate -> PASS."""

    def mock_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="fail")

    result = AgentResult(
        agent_name="test-agent",
        structured_result={"checks": {"failed": ["prose-lint"], "passed": []}},
    )
    cr = reproducibility_check(
        result,
        {"command_template": ["test-bin", "check", "--only", "{check_name}"], "failure_key_path": "checks.failed"},
        run_command=mock_run,
    )
    assert cr.verdict is Verdict.PASS


def test_reproducibility_escalates_unsafe_name() -> None:
    result = AgentResult(
        agent_name="test-agent",
        structured_result={"checks": {"failed": ["../../etc/passwd"], "passed": []}},
    )
    cr = reproducibility_check(
        result,
        {"command_template": ["test-bin", "{check_name}"], "failure_key_path": "checks.failed"},
    )
    assert cr.verdict is Verdict.ESCALATE
    assert "Unsafe" in cr.reason


def test_reproducibility_escalates_command_not_found() -> None:
    def mock_run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(f"{cmd[0]} not found")

    result = AgentResult(
        agent_name="test-agent",
        structured_result={"checks": {"failed": ["a-check"], "passed": []}},
    )
    cr = reproducibility_check(
        result,
        {"command_template": ["nonexistent-bin", "{check_name}"], "failure_key_path": "checks.failed"},
        run_command=mock_run,
    )
    assert cr.verdict is Verdict.ESCALATE


# --- AgentResult validation ---


def test_agent_result_rejects_unsafe_name() -> None:
    with pytest.raises(ValueError, match="agent_name must match"):
        AgentResult(agent_name="../evil")


def test_agent_result_accepts_valid_names() -> None:
    for name in ["drift-detector", "my_agent", "Agent1"]:
        AgentResult(agent_name=name)
