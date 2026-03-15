"""Schema validation check: validates structured_result against a JSON schema."""

from __future__ import annotations

from pathlib import Path

import jsonschema

from reck.events import AgentResult, CheckResult, Verdict


def schema_check(result: AgentResult, criteria: dict) -> CheckResult:
    """Validate result.structured_result against the JSON schema at criteria['schema_path']."""
    schema_path = criteria.get("schema_path")
    if not schema_path:
        return CheckResult(
            check_name="schema",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason="No schema_path in manifest criteria",
        )

    path = Path(schema_path)
    if not path.is_file():
        return CheckResult(
            check_name="schema",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason=f"Schema file not found: {schema_path}",
        )

    import json

    schema = json.loads(path.read_text())

    try:
        jsonschema.validate(instance=result.structured_result, schema=schema)
    except jsonschema.ValidationError as exc:
        return CheckResult(
            check_name="schema",
            verdict=Verdict.FAIL,
            confidence=0.0,
            reason=str(exc.message),
            detail={"path": list(exc.absolute_path), "validator": exc.validator},
        )

    return CheckResult(check_name="schema", verdict=Verdict.PASS)
