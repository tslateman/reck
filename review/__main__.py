"""CLI entry point: python -m review."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from reck.events import AgentResult
from reck.serialize import default_serializer
from review.checks import CheckRegistry
from review.checks.historical import historical_check
from review.checks.reproducibility import reproducibility_check
from review.checks.schema import schema_check
from review.escalation import ReviewEscalationHandler
from review.runner import ReviewRunner

_MAX_INPUT_BYTES = 1_048_576  # 1MB
_MAX_PRIOR_RESULTS = 100


def _build_registry() -> CheckRegistry:
    registry = CheckRegistry()
    registry.register("schema", schema_check)
    registry.register("historical", historical_check)
    registry.register("reproducibility", reproducibility_check)
    return registry


def run_review(
    agent_name: str,
    result_path: Path,
    attempt: int = 1,
    prior_results_path: Path | None = None,
    data_dir: Path | None = None,
    allowed_dir: Path | None = None,
) -> int:
    """Run a review and return exit code (0=pass, 1=fail/escalate)."""
    project_root = Path(__file__).resolve().parent.parent

    if data_dir is None:
        data_dir = project_root / "data"

    if allowed_dir is None:
        allowed_dir = data_dir

    # Resolve and confine result path
    resolved = result_path.resolve(strict=True)
    allowed_resolved = allowed_dir.resolve()
    if not str(resolved).startswith(str(allowed_resolved)):
        print(
            json.dumps({"error": f"Path {resolved} is outside allowed directory {allowed_resolved}"}), file=sys.stderr
        )
        return 1

    # Size check before parsing
    size = resolved.stat().st_size
    if size > _MAX_INPUT_BYTES:
        print(json.dumps({"error": f"Input file too large: {size} bytes (max {_MAX_INPUT_BYTES})"}), file=sys.stderr)
        return 1

    raw_text = resolved.read_text()
    structured = json.loads(raw_text)

    # Load prior results
    prior_results: list[dict] = []
    if prior_results_path is not None:
        for line in prior_results_path.read_text().splitlines():
            if line.strip():
                prior_results.append(json.loads(line))
                if len(prior_results) >= _MAX_PRIOR_RESULTS:
                    break

    result = AgentResult(
        agent_name=agent_name,
        structured_result=structured,
        raw_output=raw_text,
        attempt=attempt,
        prior_results=prior_results,
    )

    # Find manifest
    manifest_path = project_root / "rules" / "review" / f"{agent_name}.yaml"
    if not manifest_path.is_file():
        print(json.dumps({"error": f"No manifest for agent {agent_name!r} at {manifest_path}"}), file=sys.stderr)
        return 1

    registry = _build_registry()
    escalation = ReviewEscalationHandler(data_dir=data_dir)
    runner = ReviewRunner(
        agent_name=agent_name,
        manifest_path=manifest_path,
        registry=registry,
        escalation_handler=escalation,
        data_dir=data_dir,
    )

    verdict = runner.review(result)

    print(json.dumps(asdict(verdict), default=default_serializer, ensure_ascii=True))

    return 0 if verdict.verdict.name == "PASS" else 1


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Reck review: evaluate background agent output")
    parser.add_argument("--agent", required=True, help="Agent name (matches manifest key)")
    parser.add_argument("--result", required=True, type=Path, help="Path to agent result JSON")
    parser.add_argument("--attempt", type=int, default=1, help="1-indexed retry count")
    parser.add_argument(
        "--prior-results", type=Path, default=None, help="Path to prior results JSONL (testing override)"
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="Data directory")
    parser.add_argument("--allowed-dir", type=Path, default=None, help="Allowed directory for input files")
    args = parser.parse_args()

    sys.exit(
        run_review(
            agent_name=args.agent,
            result_path=args.result,
            attempt=args.attempt,
            prior_results_path=args.prior_results,
            data_dir=args.data_dir,
            allowed_dir=args.allowed_dir,
        )
    )


if __name__ == "__main__":
    main()
