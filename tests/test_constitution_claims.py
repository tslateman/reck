"""Verify CONSTITUTION.md does not claim automated enforcement that does not exist."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONSTITUTION = PROJECT_ROOT / "CONSTITUTION.md"


def test_ci_pipeline_claim_matches_reality() -> None:
    text = CONSTITUTION.read_text()
    has_github_workflows = (PROJECT_ROOT / ".github" / "workflows").is_dir() and any(
        (PROJECT_ROOT / ".github" / "workflows").iterdir()
    )
    if "CI pipeline rejects" in text:
        assert has_github_workflows, (
            "CONSTITUTION.md claims an automated CI pipeline rejects noncompliant "
            "branches, but no .github/workflows directory exists."
        )
