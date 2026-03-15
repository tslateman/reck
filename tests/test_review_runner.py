"""Integration tests for ReviewRunner: valid results, failures, and 3-strike escalation."""

from __future__ import annotations

import json
from pathlib import Path

from reck.events import AgentResult, ReviewOutcome
from review.checks import CheckRegistry
from review.checks.historical import historical_check
from review.checks.reproducibility import reproducibility_check
from review.checks.schema import schema_check
from review.escalation import ReviewEscalationHandler
from review.runner import ReviewRunner


def _build_registry() -> CheckRegistry:
    registry = CheckRegistry()
    registry.register("schema", schema_check)
    registry.register("historical", historical_check)
    registry.register("reproducibility", reproducibility_check)
    return registry


def _write_manifest(tmp_path: Path, schema_path: str) -> Path:
    manifest = {
        "agent": "test-agent",
        "checks": [
            {"name": "schema", "type": "schema", "schema_path": schema_path},
            {"name": "historical_range", "type": "historical", "metric_path": "summary.count", "sigma_threshold": 3.0},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    import yaml

    manifest_path.write_text(yaml.dump(manifest))
    return manifest_path


def _write_schema(tmp_path: Path) -> Path:
    schema = {
        "type": "object",
        "required": ["summary"],
        "properties": {"summary": {"type": "object", "properties": {"count": {"type": "integer"}}}},
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema))
    return schema_path


def test_valid_result_passes(tmp_path: Path) -> None:
    schema_path = _write_schema(tmp_path)
    manifest_path = _write_manifest(tmp_path, str(schema_path))
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    result = AgentResult(agent_name="test-agent", structured_result={"summary": {"count": 5}})
    verdict = runner.review(result)
    assert verdict.verdict is ReviewOutcome.PASS

    # Verify persisted
    history = (data_dir / "review" / "test-agent.jsonl").read_text()
    assert verdict.run_id in history


def test_schema_mismatch_fails(tmp_path: Path) -> None:
    schema_path = _write_schema(tmp_path)
    manifest_path = _write_manifest(tmp_path, str(schema_path))
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    result = AgentResult(agent_name="test-agent", structured_result={"wrong": "shape"})
    verdict = runner.review(result)
    assert verdict.verdict is ReviewOutcome.FAIL


def test_three_strike_escalation(tmp_path: Path) -> None:
    schema_path = _write_schema(tmp_path)
    manifest_path = _write_manifest(tmp_path, str(schema_path))
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    # Simulate 3 failed attempts
    run_id = "deadbeef"
    for attempt in range(1, 4):
        result = AgentResult(
            agent_name="test-agent",
            structured_result={"wrong": "shape"},
            run_id=run_id,
            attempt=attempt,
        )
        verdict = runner.review(result)
        assert verdict.verdict is ReviewOutcome.FAIL

    # Verify escalation record written
    esc_path = data_dir / "review" / "escalations.jsonl"
    assert esc_path.is_file()
    records = [json.loads(line) for line in esc_path.read_text().splitlines() if line.strip()]
    assert len(records) == 1
    assert records[0]["agent_name"] == "test-agent"


def test_idempotent_writes(tmp_path: Path) -> None:
    """Running review twice with same (run_id, attempt) produces one record."""
    schema_path = _write_schema(tmp_path)
    manifest_path = _write_manifest(tmp_path, str(schema_path))
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    result = AgentResult(agent_name="test-agent", structured_result={"summary": {"count": 5}}, run_id="abc123")
    runner.review(result)
    runner.review(result)

    history = (data_dir / "review" / "test-agent.jsonl").read_text().splitlines()
    records = [line for line in history if line.strip()]
    assert len(records) == 1


def test_runner_catches_exceptions(tmp_path: Path) -> None:
    """Runner never raises -- internal errors become ESCALATE verdicts."""
    manifest_path = tmp_path / "bad-manifest.yaml"
    manifest_path.write_text("invalid: yaml: content: [")
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    result = AgentResult(agent_name="test-agent", structured_result={})
    verdict = runner.review(result)
    assert verdict.verdict is ReviewOutcome.ESCALATE
    assert len(verdict.issues) > 0


def test_first_check_must_be_schema(tmp_path: Path) -> None:
    """Pipeline refuses to run if first check is not type: schema."""
    import yaml

    manifest = {
        "agent": "test-agent",
        "checks": [
            {"name": "historical_range", "type": "historical", "metric_path": "summary.count"},
        ],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.dump(manifest))
    data_dir = tmp_path / "data"

    runner = ReviewRunner(
        agent_name="test-agent",
        manifest_path=manifest_path,
        registry=_build_registry(),
        escalation_handler=ReviewEscalationHandler(data_dir=data_dir),
        data_dir=data_dir,
    )

    result = AgentResult(agent_name="test-agent", structured_result={})
    verdict = runner.review(result)
    assert verdict.verdict is ReviewOutcome.ESCALATE
    assert any("schema" in issue.lower() for issue in verdict.issues)
