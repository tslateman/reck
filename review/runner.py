"""ReviewRunner: orchestrates the full review lifecycle."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from reck.events import (
    AgentResult,
    Recommendation,
    ReviewOutcome,
    ReviewVerdict,
)
from reck.serialize import default_serializer
from review.checks import CheckFn, CheckRegistry
from review.escalation import ReviewEscalationHandler
from review.pipeline import run_checks
from review.verdict import build_verdict

logger = logging.getLogger(__name__)


def _load_manifest(manifest_path: Path) -> dict:
    """Load and validate a review manifest YAML."""
    import jsonschema

    manifest = yaml.safe_load(manifest_path.read_text())
    schema_path = Path(__file__).resolve().parent.parent / "rules" / "review" / "review.schema.json"
    schema = json.loads(schema_path.read_text())
    jsonschema.validate(instance=manifest, schema=schema)
    return manifest


class ReviewRunner:
    """Orchestrates the full review lifecycle for a single agent result."""

    def __init__(
        self,
        agent_name: str,
        manifest_path: Path,
        registry: CheckRegistry,
        escalation_handler: ReviewEscalationHandler,
        data_dir: Path,
    ) -> None:
        self._agent_name = agent_name
        self._manifest_path = manifest_path
        self._registry = registry
        self._escalation = escalation_handler
        self._data_dir = data_dir
        self._review_dir = data_dir / "review"
        self._recorded_keys: set[tuple[str, int]] | None = None

    def _history_path(self) -> Path:
        return self._review_dir / f"{self._agent_name}.jsonl"

    def _load_prior_verdicts(self) -> list[dict]:
        """Load prior verdicts from JSONL history as raw dicts."""
        path = self._history_path()
        if not path.is_file():
            return []
        verdicts = []
        for line in path.read_text().splitlines():
            if line.strip():
                verdicts.append(json.loads(line))
        return verdicts

    def _ensure_recorded_keys(self) -> set[tuple[str, int]]:
        """Lazy-load and cache the set of recorded (run_id, attempt) pairs."""
        if self._recorded_keys is None:
            self._recorded_keys = set()
            path = self._history_path()
            if path.is_file():
                for line in path.read_text().splitlines():
                    if line.strip():
                        record = json.loads(line)
                        rid = record.get("run_id")
                        att = record.get("attempt")
                        if rid is not None and att is not None:
                            self._recorded_keys.add((rid, att))
        return self._recorded_keys

    def _already_recorded(self, run_id: str, attempt: int) -> bool:
        """Check if a verdict for (run_id, attempt) already exists."""
        return (run_id, attempt) in self._ensure_recorded_keys()

    def _persist(self, verdict: ReviewVerdict) -> None:
        """Append verdict to JSONL file. Idempotent on (run_id, attempt)."""
        if self._already_recorded(verdict.run_id, verdict.attempt):
            return
        self._review_dir.mkdir(parents=True, exist_ok=True)
        from dataclasses import asdict

        with open(self._history_path(), "a") as f:
            f.write(json.dumps(asdict(verdict), default=default_serializer, ensure_ascii=True) + "\n")
        self._ensure_recorded_keys().add((verdict.run_id, verdict.attempt))

    def review(self, result: AgentResult) -> ReviewVerdict:
        """Run the full review. Never raises into the caller."""
        try:
            return self._do_review(result)
        except Exception as exc:
            logger.exception("Unexpected error in review for %s", self._agent_name)
            error_verdict = ReviewVerdict(
                run_id=result.run_id,
                agent_name=result.agent_name,
                attempt=result.attempt,
                verdict=ReviewOutcome.ESCALATE,
                confidence=0.0,
                issues=[f"Internal error: {exc}"],
                recommendation=Recommendation.ESCALATE,
            )
            self._persist(error_verdict)
            return error_verdict

    def _do_review(self, result: AgentResult) -> ReviewVerdict:
        """Core review logic."""
        manifest = _load_manifest(self._manifest_path)

        # Hard invariant: first check must be type: schema
        checks_config = manifest["checks"]
        if checks_config[0]["type"] != "schema":
            raise ValueError("First check in manifest must be type: schema (constitutional constraint)")

        # Build check list from manifest
        check_list: list[tuple[CheckFn, dict]] = []
        for check_def in checks_config:
            check_fn = self._registry.get(check_def["type"])
            check_list.append((check_fn, check_def))

        # Run pipeline
        check_results = run_checks(result, check_list)

        # Build verdict
        verdict = build_verdict(result, check_results)

        # Persist
        self._persist(verdict)

        # 3-strike escalation
        if result.attempt >= 3 and verdict.verdict is not ReviewOutcome.PASS:
            self._escalation.escalate(
                agent_name=self._agent_name,
                run_id=result.run_id,
                verdicts=[verdict],
                raw_outputs=[result.raw_output],
            )

        return verdict
